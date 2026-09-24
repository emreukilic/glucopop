"""Medtronic CareLink: discovery, sign-in pieces, tokens, times, and the readings — offline."""

from __future__ import annotations

import base64
import json
import threading
import time
from datetime import datetime, timezone

import pytest

from glucopop.sources import AuthError, SourceError, carelink
from glucopop.sources.carelink import (CareLink, authorize_url, clock_offset, identify, jwt_claims, parse_discovery,
                                        parse_message, parse_sso, read_time, to_tokens, token_for, vault_key)

HOUR = 3600.0
TOKEN_URL = "https://carelink-login.minimed.eu/oauth/token"
DATA = "clcloud.minimed.eu/connect/carepartner/v13/display/message"


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else ("" if body is None else json.dumps(body))

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class FakeSession:
    """Routes by method and URL fragment, in order; records every call."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []
        self.lock = threading.Lock()

    def _go(self, method, url, **kw):
        with self.lock:
            self.calls.append((method, url, kw))
        for m, frag, fn in self.routes:
            if m == method and frag in url:
                return fn(kw)
        raise AssertionError(f"unexpected {method} {url}")

    def get(self, url, **kw):
        return self._go("GET", url, **kw)

    def post(self, url, **kw):
        return self._go("POST", url, **kw)


class MemoryVault:
    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.saves = []

    def load(self, key):
        return self.store.get(key)

    def save(self, key, t):
        self.store[key] = t
        self.saves.append(t)

    def forget(self, key):
        self.store.pop(key, None)


def jwt(payload: dict) -> str:
    return "h." + base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=") + ".s"


def wall(ts: float, offset: float) -> str:
    """The patient's wall clock, written the way CareLink writes it."""
    return datetime.fromtimestamp(ts + offset, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def tokens(**over):
    t = {"access": "acc-1", "refresh": "ref-1", "expires_at": time.time() + HOUR, "token_url": TOKEN_URL,
         "client_id": "client", "cumulus": "https://clcloud.minimed.eu/connect/carepartner/v13"}
    t.update(over)
    return t


def message(values, age_min=2.0, trend="UP", offset=3 * HOUR, now=None, **extra):
    now = time.time() if now is None else now
    newest = now - age_min * 60
    sgs = [{"sg": v, "sensorState": "NO_ERROR_MESSAGE", "timestamp": wall(newest - (len(values) - 1 - i) * 300, offset)}
           for i, v in enumerate(values)]
    pd = {"sgs": sgs, "lastSGTrend": trend, "firstName": "Ayşe", "lastName": "Yılmaz",
          "lastConduitDateTime": wall(newest + 20, offset), "lastConduitUpdateServerDateTime": (newest + 30) * 1000,
          "systemStatusMessage": "NO_ERROR_MESSAGE", "medicalDeviceFamily": "NGP"}
    pd.update(extra)
    return {"metadata": {}, "patientData": pd}


@pytest.fixture(autouse=True)
def _fresh_tokens():
    carelink.reset_tokens()
    yield
    carelink.reset_tokens()


CFG = {"region": "eu", "username": "ayse.y", "role": "carepartner", "patient": "kid.y"}
KEY = vault_key("eu", "ayse.y")


# --------------------------------------------------------------------------- discovery & login config

DISCOVERY = {"CP": [
    {"region": "US", "UseSSOConfiguration": "Auth0SSOConfiguration",
     "Auth0SSOConfiguration": "https://carelink.minimed.com/configs/v1/carepartner_auth0_us_sso_config_v1.json",
     "baseUrlCareLink": "https://carelink.minimed.com/api/carepartner/v2", "baseUrlCumulus": "https://clcloud.minimed.com/connect/carepartner/v13"},
    {"region": "EU", "UseSSOConfiguration": "Auth0SSOConfiguration",
     "Auth0SSOConfiguration": "https://carelink.minimed.eu/configs/v1/carepartner_auth0_ous_sso_config_v1.json",
     "baseUrlCareLink": "https://carelink.minimed.eu/api/carepartner/v2", "baseUrlCumulus": "https://clcloud.minimed.eu/connect/carepartner/v13/"},
]}
SSO = {"server": {"hostname": "carelink-login.minimed.eu", "port": 443, "prefix": ""},
       "client": {"client_id": "PeAh", "scope": "profile openid offline_access", "audience": "carepartner.patient.ous",
                  "redirect_uri": "com.medtronic.carepartner:/sso"},
       "system_endpoints": {"authorization_endpoint_path": "/authorize", "token_endpoint_path": "/oauth/token"}}


def test_discovery_picks_the_region():
    eu = parse_discovery(DISCOVERY, "eu")
    assert eu["sso_url"].endswith("carepartner_auth0_ous_sso_config_v1.json")
    assert eu["cumulus"] == "https://clcloud.minimed.eu/connect/carepartner/v13"
    assert "minimed.com" in parse_discovery(DISCOVERY, "us")["sso_url"]
    with pytest.raises(SourceError):
        parse_discovery({"CP": []}, "eu")


def test_login_configuration_and_authorize_address():
    c = parse_sso(SSO)
    assert c["base"] == "https://carelink-login.minimed.eu"
    url = authorize_url(c, "CH", "ST")
    assert url.startswith("https://carelink-login.minimed.eu/authorize?")
    for part in ("client_id=PeAh", "response_type=code", "redirect_uri=com.medtronic.carepartner%3A%2Fsso",
                 "audience=carepartner.patient.ous", "code_challenge=CH", "code_challenge_method=S256", "state=ST",
                 "scope=profile%20openid%20offline_access"):
        assert part in url
    assert parse_sso({**SSO, "server": {"hostname": "h", "port": 8443, "prefix": "/mmcl/"}})["base"] == "https://h:8443/mmcl"
    with pytest.raises(SourceError):
        parse_sso({"server": {"hostname": "h"}, "client": {}})


# --------------------------------------------------------------------------- tokens

def test_expiry_is_the_sooner_of_claim_and_expires_in():
    now = 1_800_000_000.0
    t = to_tokens({"access_token": jwt({"exp": now + 600}), "refresh_token": "r", "expires_in": 3600},
                  {"token_url": TOKEN_URL, "client_id": "c"}, None, now)
    assert t["expires_at"] == now + 600


def test_refresh_without_new_refresh_token_keeps_the_old_one():
    prev = tokens(refresh="old")
    assert to_tokens({"access_token": "a", "expires_in": 60}, prev, prev)["refresh"] == "old"
    with pytest.raises(SourceError):
        to_tokens({"access_token": "a"}, {"token_url": TOKEN_URL, "client_id": "c"}, None)


def test_claims_decode_with_names():
    assert jwt_claims(jwt({"name": "Ayşe"}))["name"] == "Ayşe"
    assert jwt_claims("nope") is None
    assert vault_key("EU", " Ayse.Y ") == "eu_ayse.y"


def test_a_token_about_to_expire_is_renewed_and_the_rotated_one_kept_at_once():
    vault = MemoryVault({KEY: tokens(expires_at=time.time() + 120)})
    sent = {}

    def renew(kw):
        sent["body"] = kw["data"]
        return Resp(body={"access_token": "acc-2", "refresh_token": "ref-2", "expires_in": 3600})

    t = token_for(FakeSession([("POST", TOKEN_URL, renew)]), vault, KEY)
    assert t["access"] == "acc-2"
    assert "grant_type=refresh_token" in sent["body"] and "refresh_token=ref-1" in sent["body"]
    assert [s["refresh"] for s in vault.saves] == ["ref-2"]


def test_two_threads_share_one_renewal():
    vault = MemoryVault({KEY: tokens(expires_at=0)})
    renewals = []

    def renew(kw):
        renewals.append(kw["data"])
        time.sleep(0.05)
        if "refresh_token=ref-1" not in kw["data"]:
            return Resp(403, {"error": "invalid_grant"})
        return Resp(body={"access_token": "acc-2", "refresh_token": "ref-2", "expires_in": 3600})

    s = FakeSession([("POST", TOKEN_URL, renew)])
    out = []
    threads = [threading.Thread(target=lambda: out.append(token_for(s, vault, KEY)["access"])) for _ in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert out == ["acc-2"] * 4
    assert len(renewals) == 1


def test_a_dead_refresh_token_means_signing_in_again():
    vault = MemoryVault({KEY: tokens(expires_at=0)})
    s = FakeSession([("POST", TOKEN_URL, lambda kw: Resp(403, {"error": "invalid_grant"}))])
    with pytest.raises(AuthError) as e:
        token_for(s, vault, KEY)
    assert str(e.value) == "carelink_login"


# --------------------------------------------------------------------------- times

def test_what_a_time_means():
    assert read_time("2026-09-23T21:05:00.000Z") == (datetime(2026, 9, 23, 21, 5, tzinfo=timezone.utc).timestamp(), True)
    assert read_time("2026-09-23T21:05:00")[1] is True
    assert read_time("2026-09-23T21:05:00+03:00") == (datetime(2026, 9, 23, 18, 5, tzinfo=timezone.utc).timestamp(), False)
    assert read_time(1_790_000_000_000) == (1_790_000_000.0, False)
    assert read_time("1970-01-01T00:00:00.000Z") is None
    assert read_time(0) is None and read_time(None) is None


@pytest.mark.parametrize("offset", [3 * HOUR, -4 * HOUR, 5.5 * HOUR, 5.75 * HOUR, 0.0])
def test_the_patients_offset_is_recovered(offset):
    server = datetime(2026, 9, 23, 18, 5, 30, tzinfo=timezone.utc).timestamp()
    got, source = clock_offset({"lastConduitUpdateServerDateTime": server * 1000,
                                "lastConduitDateTime": wall(server - 20, offset)}, 99.0)
    assert (got, source) == (offset, "conduit")
    assert clock_offset({}, 7 * HOUR) == (7 * HOUR, "device")


# --------------------------------------------------------------------------- readings

def test_newest_valid_reading_true_instant_delta_and_arrow():
    now = datetime(2026, 9, 23, 18, 30, tzinfo=timezone.utc).timestamp()
    p = parse_message(message([120, 125, 131], now=now), now, 0.0)
    assert p["latest"] == (now - 120, 131)          # not three hours in the future
    assert len(p["points"]) == 3 and p["delta"] == 6 and p["trend"] == "FortyFiveUp"
    assert p["name"] == "Ayşe Yılmaz" and p["offset"] == 3 * HOUR and p["offset_from"] == "conduit"


@pytest.mark.parametrize("raw,trend", [("UP_DOUBLE", "SingleUp"), ("UP_TRIPLE", "DoubleUp"), ("DOWN", "FortyFiveDown"),
                                       ("DOWN_DOUBLE", "SingleDown"), ("DOWN_TRIPLE", "DoubleDown")])
def test_arrows(raw, trend):
    now = time.time()
    assert parse_message(message([100, 110], trend=raw, now=now), now, 0.0)["trend"] == trend


def test_no_arrow_is_steady_only_when_the_last_five_minutes_were():
    now = time.time()
    assert parse_message(message([100, 103], trend="NONE", now=now), now, 0.0)["trend"] == "Flat"
    assert parse_message(message([100, 112], trend="NONE", now=now), now, 0.0)["trend"] == "NONE"
    assert parse_message(message([100], trend="NONE", now=now), now, 0.0)["trend"] == "NONE"


def test_zeros_errors_and_future_rows_are_no_readings():
    now = datetime(2026, 9, 23, 18, 30, tzinfo=timezone.utc).timestamp()
    m = message([120, 125, 131], now=now)
    m["patientData"]["sgs"] += [
        {"sg": 0, "sensorState": "SG_BELOW_40_MGDL", "timestamp": wall(now - 60, 3 * HOUR)},
        {"sg": 140, "sensorState": "NO_ERROR_MESSAGE", "timestamp": wall(now + HOUR, 3 * HOUR)},
        {"sg": 150, "sensorState": "NO_ERROR_MESSAGE", "timestamp": "1970-01-01T00:00:00.000Z"},
    ]
    p = parse_message(m, now, 0.0)
    assert p["latest"][1] == 131 and len(p["points"]) == 3 and p["trend"] == "NONE"


def test_flat_pre_2025_shape_and_status():
    now = time.time()
    assert parse_message(message([99, 101], now=now)["patientData"], now, 0.0)["latest"][1] == 101
    p = parse_message({"patientData": {"sgs": [], "systemStatusMessage": "WARM_UP"}}, now, 0.0)
    assert p["latest"] is None and p["status"] == "WARM_UP"


# --------------------------------------------------------------------------- the source

def test_reads_the_display_message_as_the_care_partner_for_the_patient():
    vault = MemoryVault({KEY: tokens()})
    s = FakeSession([("POST", DATA, lambda kw: Resp(body=message([120, 126])))])
    r = CareLink(dict(CFG), vault=vault, session=s).latest()
    assert r.mgdl == 126 and r.trend == "FortyFiveUp" and r.person == "Ayşe Yılmaz"
    assert 60 < time.time() - r.timestamp < 240
    method, url, kw = s.calls[0]
    assert kw["headers"]["Authorization"] == "Bearer acc-1"
    assert kw["json"] == {"username": "ayse.y", "role": "carepartner", "patientId": "kid.y", "appVersion": "3.8.0"}


def test_a_refused_token_is_renewed_once_and_the_read_retried():
    vault = MemoryVault({KEY: tokens()})
    n = {"i": 0}

    def data(kw):
        n["i"] += 1
        return Resp(401) if n["i"] == 1 else Resp(body=message([90, 92]))

    s = FakeSession([("POST", TOKEN_URL, lambda kw: Resp(body={"access_token": "acc-2", "refresh_token": "ref-2", "expires_in": 3600})),
                     ("POST", DATA, data)])
    assert CareLink(dict(CFG), vault=vault, session=s).latest().mgdl == 92


def test_refused_even_with_a_fresh_token_is_a_permission_and_not_renewed_on_every_poll():
    vault = MemoryVault({KEY: tokens()})
    renewals = []

    def renew(kw):
        renewals.append(1)
        return Resp(body={"access_token": f"acc-{len(renewals) + 1}", "refresh_token": f"ref-{len(renewals) + 1}", "expires_in": 3600})

    s = FakeSession([("POST", TOKEN_URL, renew), ("POST", DATA, lambda kw: Resp(403))])
    src = CareLink(dict(CFG), vault=vault, session=s)
    for _ in range(2):
        with pytest.raises(SourceError) as e:
            src.latest()
        assert str(e.value) == "carelink_forbidden"
    assert len(renewals) == 1


def test_not_signed_in_yet():
    s = FakeSession([])
    with pytest.raises(AuthError):
        CareLink({"region": "eu"}, vault=MemoryVault(), session=s).latest()
    with pytest.raises(AuthError):
        CareLink(dict(CFG), vault=MemoryVault(), session=s).latest()


def test_no_readings_carries_medtronics_status():
    vault = MemoryVault({KEY: tokens()})
    s = FakeSession([("POST", DATA, lambda kw: Resp(body={"patientData": {"sgs": [], "systemStatusMessage": "WARM_UP"}}))])
    with pytest.raises(SourceError) as e:
        CareLink(dict(CFG), vault=vault, session=s).latest()
    assert str(e.value) == "carelink_status:WARM_UP"


# --------------------------------------------------------------------------- who signed in

REG = {"region": "eu", "sso_url": "https://x", "carelink": "https://carelink.minimed.eu/api/carepartner/v2", "cumulus": "https://c"}


def test_a_care_partner_with_the_active_links_only():
    s = FakeSession([
        ("GET", "/api/carepartner/v2/users/me", lambda kw: Resp(body={"role": "CARE_PARTNER_OUS", "firstName": "Emre"})),
        ("GET", "/api/carepartner/v2/links/patients", lambda kw: Resp(body=[
            {"username": "kid1", "firstName": "Deniz", "lastName": "K", "status": "ACTIVE"},
            {"username": "kid2", "firstName": "Ece", "status": "ACTIVE"},
            {"username": "old", "firstName": "Old", "status": "INACTIVE"}])),
    ])
    who = identify(s, tokens(access=jwt({"token_details": {"preferred_username": "emre.k"}})), "eu", REG)
    assert who["username"] == "emre.k" and who["role"] == "carepartner"
    assert who["patients"] == [{"username": "kid1", "name": "Deniz K"}, {"username": "kid2", "name": "Ece"}]


def test_falls_back_to_the_website_api_and_the_profile():
    s = FakeSession([
        ("GET", "/api/carepartner/v2/users/me", lambda kw: Resp(404)),
        ("GET", "carelink.minimed.eu/patient/users/me/profile", lambda kw: Resp(body={"username": "self.user"})),
        ("GET", "carelink.minimed.eu/patient/users/me", lambda kw: Resp(body={"role": "PATIENT_OUS", "firstName": "Can", "lastName": "Ö"})),
    ])
    who = identify(s, tokens(access=jwt({"sub": "auth0|x"})), "eu", REG)
    assert who["username"] == "self.user" and who["role"] == "patient"
    assert who["patients"] == [{"username": "self.user", "name": "Can Ö"}]


def test_a_care_partner_nobody_has_invited():
    s = FakeSession([("GET", "/users/me", lambda kw: Resp(body={"role": "CARE_PARTNER"})),
                     ("GET", "/links/patients", lambda kw: Resp(body=[]))])
    with pytest.raises(SourceError) as e:
        identify(s, tokens(access=jwt({"preferred_username": "p"})), "eu", REG)
    assert str(e.value) == "carelink_no_patient"


# --------------------------------------------------------------------------- where a sign-in is kept

def renewing(access, refresh):
    return FakeSession([("POST", TOKEN_URL, lambda kw: Resp(body={"access_token": access, "refresh_token": refresh,
                                                                  "expires_in": 3600}))])


def test_a_new_sign_in_stays_in_memory_until_someone_is_saved_with_it():
    vault = MemoryVault()
    carelink.remember_tokens(KEY, tokens(expires_at=0), pending=True)
    assert token_for(renewing("acc-2", "ref-2"), vault, KEY)["access"] == "acc-2"   # renewed and used …
    assert vault.saves == []                                                        # … and written nowhere
    carelink.persist_pending({vault_key("eu", "somebody.else")}, vault)
    assert vault.saves == []
    carelink.persist_pending({KEY}, vault)
    assert [t["refresh"] for t in vault.saves] == ["ref-2"]                         # the newest one
    # from now on every renewal is written at once, as for any saved sign-in
    carelink.remember_tokens(KEY, tokens(access="acc-2", refresh="ref-2", expires_at=0))
    token_for(renewing("acc-3", "ref-3"), vault, KEY)
    assert [t["refresh"] for t in vault.saves] == ["ref-2", "ref-3"]


def test_a_cancelled_sign_in_leaves_nothing_behind():
    vault = MemoryVault()
    carelink.remember_tokens(KEY, tokens(), pending=True)
    carelink.forget_tokens(KEY)
    carelink.persist_pending({KEY}, vault)
    assert vault.saves == []


def test_a_renewal_running_while_a_sign_in_is_retired_cannot_write_it_back():
    vault = MemoryVault({KEY: tokens(expires_at=0)})
    inside, go = threading.Event(), threading.Event()

    def renew(kw):
        inside.set()
        go.wait(2)
        return Resp(body={"access_token": "acc-2", "refresh_token": "ref-2", "expires_in": 3600})

    th = threading.Thread(target=lambda: token_for(FakeSession([("POST", TOKEN_URL, renew)]), vault, KEY))
    th.start()
    assert inside.wait(2)
    retirer = threading.Thread(target=lambda: carelink.retire(KEY, vault))
    retirer.start()
    go.set()
    th.join(2)
    retirer.join(2)
    assert KEY not in vault.store                       # the renewal wrote first, the retirement last
    with pytest.raises(AuthError):
        token_for(FakeSession([]), vault, KEY)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A Config on a temporary file, with a dictionary for the Credential Manager."""
    from glucopop import config
    store: dict[str, str] = {}
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config, "save_secret", lambda owner, key, value: store.__setitem__(f"{owner}:{key}", value) or True)
    monkeypatch.setattr(config, "load_secret", lambda owner, key: store.get(f"{owner}:{key}"))
    monkeypatch.setattr(config, "delete_secret", lambda owner, key: store.pop(f"{owner}:{key}", None))
    c = config.Config()
    c.store = store
    return c


def row(username, **cfg):
    from glucopop.config import new_person
    return new_person("carelink", {"region": "eu", "username": username, "role": "carepartner", "patient": "kid", **cfg})


STORED = f"carelink_{KEY}:rt"


def test_a_sign_in_reaches_the_credential_store_only_with_a_saved_row(cfg):
    carelink.remember_tokens(KEY, tokens(), pending=True)
    cfg.save()
    assert STORED not in cfg.store                      # signed in, but nobody saved with it yet
    cfg.upsert(row("ayse.y"))
    cfg.save()
    kept = json.loads(cfg.store[STORED])
    assert kept["refresh"] == "ref-1" and "access" not in kept   # the access token stays in memory
    from glucopop import config
    assert "ref-1" not in config.CONFIG_PATH.read_text(encoding="utf-8")   # and nothing of it in the settings file


def test_a_shared_sign_in_goes_with_the_last_row_that_uses_it(cfg):
    a, b = row("ayse.y", patient="kid1"), row("ayse.y", patient="kid2")
    carelink.remember_tokens(KEY, tokens(), pending=True)
    cfg.upsert(a)
    cfg.upsert(b)
    cfg.save()
    cfg.remove(a["id"])
    assert STORED in cfg.store
    cfg.remove(b["id"])
    assert STORED not in cfg.store
    with pytest.raises(AuthError):                      # and out of memory too
        token_for(FakeSession([]), carelink.KeyringVault(), KEY)


def test_signing_in_to_another_account_forgets_the_old_one(cfg):
    a = row("ayse.y")
    carelink.remember_tokens(KEY, tokens(), pending=True)
    cfg.upsert(a)
    cfg.save()
    other = vault_key("eu", "mehmet.y")
    carelink.remember_tokens(other, tokens(refresh="ref-m"), pending=True)
    cfg.upsert({**a, "cfg": {**a["cfg"], "username": "mehmet.y"}})
    cfg.save()
    assert STORED not in cfg.store
    assert json.loads(cfg.store[f"carelink_{other}:rt"])["refresh"] == "ref-m"


def test_moving_a_row_to_another_service_forgets_its_sign_in(cfg):
    a = row("ayse.y")
    carelink.remember_tokens(KEY, tokens(), pending=True)
    cfg.upsert(a)
    cfg.save()
    cfg.upsert({**a, "source": "nightscout", "cfg": {"url": "https://ns.example"}})
    assert STORED not in cfg.store


def test_a_row_replaced_by_one_with_the_same_account_keeps_the_sign_in(cfg):
    # the settings dialog adds and edits before it removes, so a row deleted and re-added with
    # the same Medtronic account in one go does not take the new row's sign-in with it
    a = row("ayse.y")
    carelink.remember_tokens(KEY, tokens(), pending=True)
    cfg.upsert(a)
    cfg.save()
    carelink.remember_tokens(KEY, tokens(refresh="ref-new"), pending=True)   # signed in again, for the new row
    cfg.upsert(row("ayse.y"))
    cfg.remove(a["id"])
    cfg.save()
    assert json.loads(cfg.store[STORED])["refresh"] == "ref-new"


def test_every_text_the_medtronic_parts_use_exists_in_both_languages():
    import pathlib
    import re as _re

    from glucopop.i18n import STRINGS
    from glucopop.sources import SOURCE_INFO

    root = pathlib.Path(carelink.__file__).parents[1]
    code = (root / "ui" / "carelink_login.py").read_text(encoding="utf-8")
    keys = set(_re.findall(r'tr\("([a-z0-9_]+)"', code))
    keys |= set(_re.findall(r'"(cl_[a-z_]+|e_cl_[a-z_]+|e_carelink_[a-z_]+)"', (root / "ui" / "forms.py").read_text(encoding="utf-8")))
    keys |= set(_re.findall(r'"(e_cl_[a-z_]+|e_carelink_[a-z_]+)"', (root / "core.py").read_text(encoding="utf-8")))
    keys |= {SOURCE_INFO["carelink"]["sub"], SOURCE_INFO["carelink"]["desc"]}
    for f in CareLink.fields:
        keys |= {f.label_key, f.help_key} | {label for _, label in f.choices}
    assert {"cl_login", "e_cl_window", "e_carelink_login", "e_cl_warmup"} <= keys
    for lang in ("en", "tr"):
        missing = sorted(k for k in keys if k and k not in STRINGS[lang])
        assert not missing, (lang, missing)


def test_the_picker_offers_medtronic():
    from glucopop.sources import SOURCE_INFO, SOURCES, create
    assert "carelink" in SOURCE_INFO and SOURCES["carelink"] is CareLink
    src = create("carelink", dict(CFG))
    assert isinstance(src, CareLink)
