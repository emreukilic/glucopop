"""FreeStyle Libre 2 / 2 Plus / 3 via LibreLinkUp.

User-side requirements:
  * A LibreLinkUp account that follows the sensor wearer (you may follow yourself:
    in the FreeStyle Libre app -> Share -> Connected apps -> LibreLinkUp -> invite your own e-mail).
  * Log in here with the LibreLinkUp account.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

import requests

from .base import AuthError, Field, Reading, Source, SourceError

DEFAULT_BASE = "https://api.libreview.io"
LLU_VERSION = "4.16.0"
# TrendArrow 1..5 (LibreLinkUp) -> normalised trend
TREND_MAP = {1: "SingleDown", 2: "FortyFiveDown", 3: "Flat", 4: "FortyFiveUp", 5: "SingleUp"}


class LibreLinkUp(Source):
    id = "libre"
    name = "LibreLinkUp"
    website = "https://www.libreview.com/"
    poll_seconds = 60
    fields = [
        Field("username", "f_email", "text", help_key="h_libre_user"),
        Field("password", "f_password", "password"),
        Field("patient", "f_libre_patient", "text", required=False, help_key="h_libre_patient"),
    ]

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.base = cfg.get("_region_base") or DEFAULT_BASE
        self.session = requests.Session()
        self.session.headers.update({
            "accept-encoding": "gzip",
            "cache-control": "no-cache",
            "connection": "Keep-Alive",
            "content-type": "application/json",
            "product": "llu.android",
            "version": LLU_VERSION,
        })
        self.token: str | None = None
        self.account_id_hash: str | None = None
        self.patient_id: str | None = cfg.get("patient") or None
        self.person = ""

    # ------------------------------------------------------------------ http
    def _headers(self) -> dict:
        h = {}
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        if self.account_id_hash:
            h["account-id"] = self.account_id_hash
        return h

    def _request(self, method: str, path: str, **kw):
        r = self.session.request(method, self.base + path, headers=self._headers(), timeout=20, **kw)
        if r.status_code == 401:
            raise _SessionExpired()
        if r.status_code == 403:
            raise AuthError("Forbidden (HTTP 403) – LibreLinkUp version may need updating")
        if r.status_code == 429:
            raise SourceError("rate_limited")
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ api
    def connect(self) -> None:
        user = str(self.cfg["username"]).strip()
        pwd = self.cfg["password"]
        if not user or not pwd:
            raise AuthError("Missing credentials")
        self.token = None
        self.account_id_hash = None
        body = self._request("POST", "/llu/auth/login", json={"email": user, "password": pwd})
        data = body.get("data") or {}
        # regional redirect
        if data.get("redirect") and data.get("region"):
            self.base = f"https://api-{data['region']}.libreview.io"
            body = self._request("POST", "/llu/auth/login", json={"email": user, "password": pwd})
            data = body.get("data") or {}
        status = body.get("status", 0)
        if status == 2:
            raise AuthError("invalid_credentials")
        if status == 4 or data.get("step"):
            raise AuthError("llu_terms")   # user must accept new terms in the LibreLinkUp app
        if status not in (0, None):
            raise AuthError(f"LibreLinkUp error status {status}: {body.get('error', {}).get('message', '')}")
        ticket = data.get("authTicket") or {}
        self.token = ticket.get("token")
        user_id = (data.get("user") or {}).get("id", "")
        if not self.token or not user_id:
            raise AuthError("Login response incomplete")
        self.account_id_hash = hashlib.sha256(user_id.encode()).hexdigest()

    def _connections(self) -> list[dict]:
        body = self._request("GET", "/llu/connections")
        return body.get("data") or []

    def latest(self) -> Reading:
        if not self.token:
            self.connect()
        try:
            conns = self._connections()
        except _SessionExpired:
            self.connect()
            conns = self._connections()
        if not conns:
            raise SourceError("libre_no_connection")
        conn = None
        if self.patient_id:
            for c in conns:
                full = f"{c.get('firstName','')} {c.get('lastName','')}".strip().lower()
                if c.get("patientId") == self.patient_id or full == self.patient_id.lower():
                    conn = c
                    break
            if conn is None:
                names = ", ".join(f"{c.get('firstName','')} {c.get('lastName','')}".strip() for c in conns)
                raise SourceError(f"patient not found; available: {names}")
        else:
            conn = conns[0]
        gm = conn.get("glucoseMeasurement") or {}
        if not gm or gm.get("ValueInMgPerDl") is None:
            raise SourceError("no_data")
        self.person = f"{conn.get('firstName','')} {conn.get('lastName','')}".strip()
        ts = _parse_ts(gm.get("FactoryTimestamp"), utc=True) or _parse_ts(gm.get("Timestamp"), utc=False)
        return Reading(
            mgdl=float(gm["ValueInMgPerDl"]),
            trend=TREND_MAP.get(gm.get("TrendArrow"), "NONE"),
            timestamp=ts,
            source=self.name,
            person=self.person,
            extra={"is_high": gm.get("isHigh"), "is_low": gm.get("isLow"),
                   "sensor": (conn.get("sensor") or {}).get("sn")},
        )


class _SessionExpired(SourceError):
    pass


def _parse_ts(s: str | None, utc: bool) -> float:
    """LibreLinkUp timestamps look like '9/15/2026 1:05:00 PM'."""
    if not s:
        return 0.0
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if utc:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone()  # naive local
            return dt.timestamp()
        except ValueError:
            continue
    return 0.0
