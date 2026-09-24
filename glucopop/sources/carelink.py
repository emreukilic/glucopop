"""Medtronic CareLink — MiniMed 780G / 770G and Simplera, through the cloud behind MiniMed Mobile.

Unlike the other services there is no username and password to send. Medtronic signs people in
on its own web page (Auth0, with a reCAPTCHA) and hands back a pair of tokens. The page is shown
in GlucoPop's own sign-in window (``ui/carelink_login.py``); the password is typed into
Medtronic's page and GlucoPop neither reads nor keeps it. What is kept is the refresh token, in
the Windows Credential Manager (the Keychain on a Mac) like every other secret here, once a person
who uses it has been saved. Where to sign in — the login host,
the client id, the redirect — is read from Medtronic's discovery document at sign-in time rather
than written down in this file, so a move on their side needs no new release as long as the shape
holds.

The protocol is unofficial: the one xDrip+, the Nightscout bridges and the Home Assistant
integration use, written here from the protocol itself, not from their code.

  discovery  GET …/connect/carepartner/v13/discover/android/3.8 → one entry per region with the
             Auth0 configuration, ``baseUrlCareLink`` (who am I, whom do I follow) and
             ``baseUrlCumulus`` (the readings).
  sign-in    OAuth2 authorization code with PKCE, public client, redirected to the official app's
             URL scheme and caught by the sign-in window before anything opens it.
  tokens     refresh tokens rotate: the newest one must always be kept, and two refreshes of the
             same token must never run side by side (see ``token_for``).
  readings   POST {baseUrlCumulus}/display/message → {"patientData": {"sgs": […], …}}. Its times
             are the patient's wall clock written as if they were UTC (see ``clock_offset``).
"""

from __future__ import annotations

import base64
import json
import re
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional
from urllib.parse import quote

import requests

from .base import AuthError, Field, Reading, Source, SourceError

DISCOVERY = "https://clcloud.minimed.eu/connect/carepartner/v13/discover/android/3.8"
APP_VERSION = "3.8.0"          # what the official app reports; some accounts are refused without it
REFRESH_MARGIN = 600           # seconds before expiry a token is renewed
FORBIDDEN_QUIET = 600          # a refusal even with a fresh token is not retried sooner than this
TIMEOUT = 25

# Medtronic counts arrows one step later than Dexcom: one arrow is 1–2 mg/dL a minute (Dexcom's
# 45°), two are 2–3 (Dexcom's single), three are over 3 (Dexcom's double). "No arrow" is under 1 —
# or no trend at all; see parse_message for which.
TRENDS = {"UP": "FortyFiveUp", "UP_DOUBLE": "SingleUp", "UP_TRIPLE": "DoubleUp",
          "DOWN": "FortyFiveDown", "DOWN_DOUBLE": "SingleDown", "DOWN_TRIPLE": "DoubleDown"}


def vault_key(region: str | None, username: str | None) -> str:
    """One sign-in per account and region, shared by every row that follows someone through it."""
    return f"{(region or 'eu').strip().lower()}_{(username or '').strip().lower()}"


def _tld(region: str) -> str:
    return "com" if region == "us" else "eu"


def _https(v: Any) -> Optional[str]:
    return v.rstrip("/") if isinstance(v, str) and v.lower().startswith("https://") else None


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _form(q: dict[str, Any]) -> str:
    return "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in q.items() if v not in (None, ""))


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""


def _full_name(x: Any) -> str:
    x = x if isinstance(x, dict) else {}
    return " ".join(p for p in (_text(x.get("firstName")), _text(x.get("lastName"))) if p)


# --------------------------------------------------------------------------- discovery, sign-in

def parse_discovery(j: Any, region: str) -> dict[str, Any]:
    want = "US" if region == "us" else "EU"
    entries = j.get("CP") if isinstance(j, dict) and isinstance(j.get("CP"), list) else []
    cp = next((x for x in entries if isinstance(x, dict) and str(x.get("region", "")).upper() == want), None)
    if cp is None:
        raise SourceError("carelink_unsupported")
    key = cp.get("UseSSOConfiguration") if isinstance(cp.get("UseSSOConfiguration"), str) and cp.get("UseSSOConfiguration") \
        else "Auth0SSOConfiguration"
    sso_url = _https(cp.get(key))
    if not sso_url:
        raise SourceError("carelink_unsupported")
    return {"region": region, "sso_url": sso_url, "carelink": _https(cp.get("baseUrlCareLink")),
            "cumulus": _https(cp.get("baseUrlCumulus"))}


def parse_sso(j: Any) -> dict[str, Any]:
    """The login configuration — its shape checked, so an unknown one says "needs an update"."""
    j = j if isinstance(j, dict) else {}
    server, client, ep = j.get("server") or {}, j.get("client") or {}, j.get("system_endpoints") or {}
    host = server.get("hostname")
    ok = all(isinstance(v, str) and v for v in (host, client.get("client_id"), client.get("redirect_uri"),
                                               ep.get("authorization_endpoint_path"), ep.get("token_endpoint_path")))
    if not ok:
        raise SourceError("carelink_unsupported")
    port = int(server.get("port") or 443)
    prefix = str(server.get("prefix") or "").strip("/")
    base = f"https://{host}{'' if port == 443 else f':{port}'}{'/' + prefix if prefix else ''}"
    return {"base": base, "client_id": client["client_id"],
            "scope": client.get("scope") or "profile openid offline_access",
            "audience": client.get("audience") or None, "redirect_uri": client["redirect_uri"],
            "authorize_path": ep["authorization_endpoint_path"], "token_path": ep["token_endpoint_path"]}


def discover(session: requests.Session, region: str) -> dict[str, Any]:
    r = session.get(DISCOVERY, timeout=TIMEOUT, headers={"Accept": "application/json"})
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code}")
    return parse_discovery(r.json(), region)


def load_sso(session: requests.Session, url: str) -> dict[str, Any]:
    r = session.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"})
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code}")
    return parse_sso(r.json())


def authorize_url(sso: dict[str, Any], challenge: str, state: str) -> str:
    return _join(sso["base"], sso["authorize_path"]) + "?" + _form({
        "client_id": sso["client_id"], "response_type": "code", "scope": sso["scope"],
        "redirect_uri": sso["redirect_uri"], "audience": sso.get("audience"),
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
    })


def jwt_claims(token: str) -> Optional[dict[str, Any]]:
    """The payload of a JWT, unverified: only ever used to read an expiry or a username."""
    parts = token.split(".") if isinstance(token, str) else []
    if len(parts) < 2:
        return None
    try:
        raw = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        v = json.loads(raw.decode("utf-8"))
        return v if isinstance(v, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


def _token_call(session: requests.Session, url: str, form: dict[str, Any]) -> dict[str, Any]:
    r = session.post(url, data=_form(form), timeout=TIMEOUT,
                     headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    # Auth0 answers a dead or reused refresh token with 400/401/403 — "invalid_grant" in all of them.
    if r.status_code in (400, 401, 403):
        raise AuthError("carelink_login")
    if r.status_code == 429:
        raise SourceError("rate_limited")
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code}")
    return r.json()


def to_tokens(j: dict[str, Any], where: dict[str, Any], previous: Optional[dict[str, Any]],
              now: Optional[float] = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    access = j.get("access_token") if isinstance(j, dict) else None
    if not isinstance(access, str) or not access:
        raise SourceError("bad_response")
    # a refresh answered without a new refresh token keeps the old one: only rotation replaces it
    refresh = j.get("refresh_token") or (previous or {}).get("refresh")
    if not refresh:
        raise SourceError("bad_response")
    candidates = []
    exp = (jwt_claims(access) or {}).get("exp")
    if isinstance(exp, (int, float)) and exp > 0:
        candidates.append(float(exp))
    try:
        if float(j.get("expires_in") or 0) > 0:
            candidates.append(now + float(j["expires_in"]))
    except (TypeError, ValueError):
        pass
    return {"access": access, "refresh": refresh, "expires_at": min(candidates) if candidates else now + 3600,
            "token_url": where["token_url"], "client_id": where["client_id"],
            "cumulus": where.get("cumulus") or (previous or {}).get("cumulus")}


def exchange_code(session: requests.Session, sso: dict[str, Any], code: str, verifier: str,
                  cumulus: Optional[str] = None) -> dict[str, Any]:
    token_url = _join(sso["base"], sso["token_path"])
    j = _token_call(session, token_url, {"grant_type": "authorization_code", "client_id": sso["client_id"],
                                         "code": code, "redirect_uri": sso["redirect_uri"], "code_verifier": verifier})
    return to_tokens(j, {"token_url": token_url, "client_id": sso["client_id"], "cumulus": cumulus}, None)


# --------------------------------------------------------------------------- where tokens live

class KeyringVault:
    """The refresh token and where to renew it, in the Credential Manager; the access token stays in
    memory (it is long, and a running desktop app renews it when it needs to)."""

    def load(self, key: str) -> Optional[dict[str, Any]]:
        from ..config import load_secret
        raw = load_secret("carelink_" + key, "rt")
        if not raw:
            return None
        try:
            v = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(v, dict) or not v.get("refresh") or not v.get("token_url") or not v.get("client_id"):
            return None
        return {**v, "access": "", "expires_at": 0}

    def save(self, key: str, t: dict[str, Any]) -> None:
        from ..config import save_secret
        save_secret("carelink_" + key, "rt", json.dumps({k: t.get(k) for k in ("refresh", "token_url", "client_id", "cumulus")}))

    def forget(self, key: str) -> None:
        from ..config import delete_secret
        delete_secret("carelink_" + key, "rt")


# The tokens every CareLink row shares, and one lock around renewing them. The poller and the
# "test connection" button run on threads of their own, and with rotating refresh tokens two
# renewals of the same token are fatal: Auth0 takes a retired token coming back as theft and
# revokes the lot. Under the lock the second thread finds the token already renewed and uses it.
_live: dict[str, dict[str, Any]] = {}
# Sign-ins nobody has been saved with yet. They live in memory only, so a window closed with
# Cancel leaves no way into someone's data behind in the Credential Manager; they reach the vault
# when a person who uses them is saved (persist_pending, called from Config.save).
_pending: set[str] = set()
_lock = threading.Lock()


def remember_tokens(key: str, t: dict[str, Any], pending: bool = False) -> None:
    with _lock:
        _live[key] = t
        if pending:
            _pending.add(key)
        else:
            _pending.discard(key)


def forget_tokens(key: str) -> None:
    with _lock:
        _live.pop(key, None)
        _pending.discard(key)


def persist_pending(in_use: set[str], vault: Any = None) -> None:
    """The sign-ins a saved person now reads through go to the vault; the rest stay in memory and
    end with the app. Under the lock, so a renewal cannot slip in between and be overwritten by
    the token it replaced."""
    vault = vault if vault is not None else KeyringVault()
    with _lock:
        for key in sorted(_pending):
            if key in in_use and key in _live:
                _pending.discard(key)
                try:
                    vault.save(key, _live[key])
                except Exception:  # noqa: BLE001 — held in memory; a restart may need a new sign-in
                    pass


def reset_tokens() -> None:
    """tests only"""
    with _lock:
        _live.clear()
        _pending.clear()


def token_for(session: requests.Session, vault: Any, key: str, failed: Optional[str] = None,
              now: Callable[[], float] = time.time) -> dict[str, Any]:
    """A usable token for this account, renewed if it is about to run out — or, with ``failed``, if
    the service has just refused that very token (one already replaced is simply handed over)."""
    with _lock:
        t = _live.get(key)
        if t is None:
            t = vault.load(key)
            if t:
                _live[key] = t
        if not t:
            raise AuthError("carelink_login")
        stale = (t["access"] == failed) if failed is not None else (t["expires_at"] - now() <= REFRESH_MARGIN)
        if not stale:
            return t
        j = _token_call(session, t["token_url"], {"grant_type": "refresh_token", "client_id": t["client_id"],
                                                   "refresh_token": t["refresh"]})
        nxt = to_tokens(j, t, t, now())
        _live[key] = nxt
        if key not in _pending:
            try:
                # at once: the old refresh token is dead from this moment
                vault.save(key, nxt)
            except Exception:  # noqa: BLE001 — held in memory; a restart may need a new sign-in
                pass
        return nxt


# --------------------------------------------------------------------------- who signed in

def _get_json(session: requests.Session, url: str, access: str) -> Any:
    r = session.get(url, timeout=TIMEOUT, headers={"Authorization": f"Bearer {access}", "Accept": "application/json"})
    if r.status_code in (401, 403):
        raise AuthError("carelink_login")
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code}")
    return r.json()


def _first_of(tries: list[Callable[[], Any]]) -> Any:
    err: Exception = SourceError("bad_response")
    for run in tries:
        try:
            return run()
        except Exception as e:  # noqa: BLE001
            err = e
    raise err


def identify(session: requests.Session, t: dict[str, Any], region: str, reg: dict[str, Any],
             sso: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Who has just signed in, and whom they can follow. The mobile API first, the website's second."""
    web = f"https://carelink.minimed.{_tld(region)}/patient"
    access = t["access"]
    me = _first_of(([lambda: _get_json(session, f"{reg['carelink']}/users/me", access)] if reg.get("carelink") else [])
                   + [lambda: _get_json(session, f"{web}/users/me", access)])
    me = me if isinstance(me, dict) else {}
    role = "carepartner" if re.search(r"CARE_?PARTNER", str(me.get("role", "")), re.I) else "patient"

    claims = jwt_claims(access) or {}
    details = claims.get("token_details") if isinstance(claims.get("token_details"), dict) else {}
    username = (_text(details.get("preferred_username")) or _text(claims.get("preferred_username"))
                or _text(me.get("username")) or _text(me.get("loginId")))
    if not username:
        try:
            username = _text((_get_json(session, f"{web}/users/me/profile", access) or {}).get("username"))
        except Exception:  # noqa: BLE001
            pass
    if not username and sso:
        try:
            username = _text((_get_json(session, _join(sso["base"], "/userinfo"), access) or {}).get("preferred_username"))
        except Exception:  # noqa: BLE001
            pass
    if not username:
        raise SourceError("carelink_unsupported")

    out = {"username": username, "role": role, "first_name": _text(me.get("firstName")), "last_name": _text(me.get("lastName"))}
    if role == "patient":
        return {**out, "patients": [{"username": username, "name": _full_name(me) or username}]}
    links = _first_of(([lambda: _get_json(session, f"{reg['carelink']}/links/patients", access)] if reg.get("carelink") else [])
                      + [lambda: _get_json(session, f"{web}/m2m/links/patients", access)])
    rows = links if isinstance(links, list) else (links.get("patients") if isinstance(links, dict) else None) or []
    patients = [{"username": _text(x.get("username")), "name": _full_name(x) or _text(x.get("username"))}
                for x in rows if isinstance(x, dict) and _text(x.get("username"))
                and (not x.get("status") or str(x.get("status")).upper() == "ACTIVE")]
    if not patients:
        raise SourceError("carelink_no_patient")
    return {**out, "patients": patients}


# --------------------------------------------------------------------------- the readings

_TIME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?$", re.I)


def read_time(v: Any) -> Optional[tuple[float, bool]]:
    """(unix seconds, is-wall-clock). CareLink nearly always writes the patient's wall clock marked
    "Z" or unmarked; a real offset or epoch milliseconds are true instants; warm-up rows carry the
    epoch or nothing, and are no time at all."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (v / 1000.0, False) if v > 946_684_800_000 else None
    if not isinstance(v, str):
        return None
    m = _TIME.match(v.strip())
    if not m or int(m.group(1)) < 2000:
        return None
    frac = (m.group(7) or "0")[:3].ljust(3, "0")
    naive = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)),
                     int(m.group(6) or 0))
    secs = (naive - datetime(1970, 1, 1)).total_seconds() + int(frac) / 1000.0
    zone = m.group(8)
    if zone and zone.upper() != "Z":
        sign = -1 if zone.startswith("-") else 1
        d = zone[1:].replace(":", "")
        return secs - sign * (int(d[:2]) * 3600 + int(d[2:4]) * 60), False
    return secs, True


def device_offset(at: Optional[float] = None) -> float:
    at = time.time() if at is None else at
    off = datetime.fromtimestamp(at).astimezone().utcoffset()
    return off.total_seconds() if off else 0.0


def clock_offset(pd: dict[str, Any], fallback: float) -> tuple[float, str]:
    """The patient's offset from UTC, in seconds, recovered from the one pair of fields that states
    the same moment twice: ``lastConduitDateTime`` (their phone's wall clock, marked as UTC) and
    ``lastConduitUpdateServerDateTime`` (Medtronic's server clock, epoch ms). Read naively every time
    in the message is off by it — in Türkiye, three hours in the future. Rounded to a quarter of an
    hour (India, Nepal) and bounded to the offsets that exist; zero if Medtronic ever writes true
    UTC. Without the pair, this computer's own offset stands in."""
    try:
        server = float(pd.get("lastConduitUpdateServerDateTime") or 0) / 1000.0
    except (TypeError, ValueError):
        server = 0.0
    wall = read_time(pd.get("lastConduitDateTime"))
    if server > 0 and wall and wall[1]:
        q = 900.0
        off = round((wall[0] - server) / q) * q + 0.0
        if abs(off) <= 14 * 3600:
            return off, "conduit"
    return fallback, "device"


def parse_message(j: Any, now: float, fallback_offset: float) -> dict[str, Any]:
    wrapped = isinstance(j, dict) and isinstance(j.get("patientData"), dict)
    pd = j["patientData"] if wrapped else (j if isinstance(j, dict) else {})
    off, source = clock_offset(pd, fallback_offset)
    rows = pd.get("sgs") if isinstance(pd.get("sgs"), list) else []

    def when(v: Any) -> Optional[float]:
        x = read_time(v)
        return None if x is None else (x[0] - off if x[1] else x[0])

    all_rows = []
    for p in rows:
        p = p if isinstance(p, dict) else {}
        try:
            sg = float(p.get("sg"))
        except (TypeError, ValueError):
            sg = float("nan")
        all_rows.append((when(p.get("timestamp", p.get("datetime"))), sg, str(p.get("sensorState") or "NO_ERROR_MESSAGE")))
    # a 0, a sensor error or a time from the future is no reading; nothing is invented to fill it
    valid = sorted(((t, sg) for t, sg, st in all_rows
                    if t is not None and t <= now + 300 and sg == sg and sg > 0 and st == "NO_ERROR_MESSAGE"))
    latest = valid[-1] if valid else None
    newest = max((t for t, _, _ in all_rows if t is not None), default=None)
    prev = next((p for p in reversed(valid[:-1]) if latest and p[0] < latest[0]), None)
    gap = (latest[0] - prev[0]) if latest and prev else None
    delta = (latest[1] - prev[1]) if gap is not None and 180 <= gap <= 420 else None

    trend = "NONE"
    # the trend belongs to the newest reading; if that one is an error row it belongs to nobody
    if latest and newest is not None and latest[0] == newest:
        raw = str(pd.get("lastSGTrend") or "NONE").upper()
        # "no arrow" is Medtronic's steady — but also what it sends with no trend at all, so it is
        # only drawn steady when the last five minutes really were (under 1 mg/dL a minute)
        trend = TRENDS.get(raw) or ("Flat" if delta is not None and abs(delta) < 5 else "NONE")
    return {"points": valid, "latest": latest, "trend": trend, "delta": delta, "name": _full_name(pd),
            "status": _text(pd.get("systemStatusMessage")), "offset": off, "offset_from": source}


class CareLink(Source):
    id = "carelink"
    name = "Medtronic CareLink"
    website = "https://carelink.minimed.eu/"
    poll_seconds = 60
    # The only field the form shows: the account, its role and whom it follows are filled in by
    # signing in (see ui/forms.py), never typed.
    fields = [
        Field("region", "f_region", "choice", choices=[("eu", "r_ous"), ("us", "r_us")], default="eu",
              help_key="h_carelink"),
    ]

    def __init__(self, cfg: dict[str, Any], vault: Any = None, session: Optional[requests.Session] = None,
                 now: Callable[[], float] = time.time):
        super().__init__(cfg)
        self.region = "us" if cfg.get("region") == "us" else "eu"
        self.key = vault_key(self.region, cfg.get("username"))
        self.vault = vault if vault is not None else KeyringVault()
        self.session = session or requests.Session()
        self.now = now
        self._forbidden_at = 0.0
        if self.region == "us":
            self.website = "https://carelink.minimed.com/"

    def _ready(self) -> None:
        if not _text(self.cfg.get("username")):
            raise AuthError("carelink_login")

    def connect(self) -> None:
        self._ready()
        token_for(self.session, self.vault, self.key, now=self.now)

    def _post(self, url: str, access: str) -> requests.Response:
        role = "carepartner" if self.cfg.get("role") == "carepartner" else "patient"
        body = {"username": _text(self.cfg.get("username")), "role": role,
                "patientId": _text(self.cfg.get("patient")) or _text(self.cfg.get("username")), "appVersion": APP_VERSION}
        return self.session.post(url, json=body, timeout=TIMEOUT,
                                 headers={"Authorization": f"Bearer {access}", "Accept": "application/json"})

    def _message(self) -> Any:
        self._ready()
        t = token_for(self.session, self.vault, self.key, now=self.now)
        url = (t.get("cumulus") or f"https://clcloud.minimed.{_tld(self.region)}/connect/carepartner/v13") + "/display/message"
        r = self._post(url, t["access"])
        if r.status_code in (401, 403) and self.now() - self._forbidden_at > FORBIDDEN_QUIET:
            t = token_for(self.session, self.vault, self.key, failed=t["access"], now=self.now)
            r = self._post(url, t["access"])
            # refused again with a token minted a moment ago: a permission, not a sign-in — and not
            # something another renewal on every poll would change
            if r.status_code == 403:
                self._forbidden_at = self.now()
        if r.status_code == 401:
            raise AuthError("carelink_login")
        if r.status_code == 403:
            raise SourceError("carelink_forbidden")
        if r.status_code == 204:
            raise SourceError("no_data")
        if r.status_code == 429:
            raise SourceError("rate_limited")
        if r.status_code != 200:
            raise SourceError(f"HTTP {r.status_code}")
        if not (r.text or "").strip():
            raise SourceError("no_data")
        try:
            return r.json()
        except ValueError:
            raise SourceError("bad_response") from None

    def latest(self) -> Reading:
        p = parse_message(self._message(), self.now(), device_offset(self.now()))
        if not p["latest"]:
            # Medtronic says why there is nothing to show; its words beat a generic guess
            raise SourceError(f"carelink_status:{p['status']}" if p["status"] else "no_data")
        t, mgdl = p["latest"]
        return Reading(mgdl=mgdl, trend=p["trend"], timestamp=t, source=self.name, person=p["name"],
                       extra={"delta": p["delta"]} if p["delta"] is not None else {})
