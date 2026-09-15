"""Dexcom Share data source (G6 / G7 / ONE / ONE+).

Requirements on the user's side:
  * Dexcom app -> Share enabled with at least one follower invited.
  * Credentials are the *sharer's* Dexcom account (username / e-mail / phone).
Endpoints and application id follow the well-known pydexcom implementation.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from .base import AuthError, Field, Reading, Source, SourceError

APPLICATION_ID = "d89443d2-327c-4a6f-89e5-496bbb0317db"
BASES = {
    "ous": "https://shareous1.dexcom.com/ShareWebServices/Services/",
    "us": "https://share2.dexcom.com/ShareWebServices/Services/",
    "jp": "https://share.dexcom.jp/ShareWebServices/Services/",
}
TREND_MAP = {
    "None": "NONE", "DoubleUp": "DoubleUp", "SingleUp": "SingleUp", "FortyFiveUp": "FortyFiveUp",
    "Flat": "Flat", "FortyFiveDown": "FortyFiveDown", "SingleDown": "SingleDown",
    "DoubleDown": "DoubleDown", "NotComputable": "NotComputable", "RateOutOfRange": "RateOutOfRange",
    # numeric legacy values
    0: "NONE", 1: "DoubleUp", 2: "SingleUp", 3: "FortyFiveUp", 4: "Flat", 5: "FortyFiveDown",
    6: "SingleDown", 7: "DoubleDown", 8: "NotComputable", 9: "RateOutOfRange",
}


class DexcomShare(Source):
    id = "dexcom"
    name = "Dexcom Share"
    website = "https://clarity.dexcom.eu/"
    poll_seconds = 60
    fields = [
        Field("username", "f_dexcom_user", "text", help_key="h_dexcom_user"),
        Field("password", "f_password", "password"),
        Field("region", "f_region", "choice",
              choices=[("ous", "r_ous"), ("us", "r_us"), ("jp", "r_jp")], default="ous"),
    ]

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.base = BASES.get(cfg.get("region", "ous"), BASES["ous"])
        self.session = requests.Session()
        self.session.headers.update({
            "Accept-Encoding": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Dexcom Share/3.0.2.11 CFNetwork/711.2.23 Darwin/14.0.0",
        })
        self.account_id: str | None = None
        self.session_id: str | None = None

    # ------------------------------------------------------------------ http
    def _post(self, endpoint: str, json: dict | None = None, params: dict | None = None):
        r = self.session.post(self.base + endpoint, json=json or {}, params=params, timeout=20)
        if r.status_code == 500:
            # Dexcom returns structured errors with 500
            try:
                err = r.json()
            except ValueError:
                err = {}
            code = err.get("Code", "")
            msg = err.get("Message", r.text[:200])
            if code in ("SessionIdNotFound", "SessionNotValid"):
                raise _SessionExpired(msg)
            if code in ("AccountPasswordInvalid", "SSO_AuthenticateAccountNotFound",
                        "SSO_AuthenticatePasswordInvalid", "AccountNotFound", "InvalidArgument"):
                raise AuthError(msg or code)
            if code == "SSO_AuthenticateMaxAttemptsExceeed":
                raise AuthError("Too many failed attempts – wait 10 minutes")
            raise SourceError(f"{code}: {msg}")
        if r.status_code in (401, 403):
            raise AuthError("Unauthorized")
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------ api
    def connect(self) -> None:
        user = str(self.cfg["username"]).strip()
        pwd = self.cfg["password"]
        if not user or not pwd:
            raise AuthError("Missing credentials")
        payload = {"accountName": user, "password": pwd, "applicationId": APPLICATION_ID}
        self.account_id = self._post("General/AuthenticatePublisherAccount", payload)
        if not self.account_id or self.account_id == "00000000-0000-0000-0000-000000000000":
            raise AuthError("Account not found")
        self.session_id = self._post(
            "General/LoginPublisherAccountById",
            {"accountId": self.account_id, "password": pwd, "applicationId": APPLICATION_ID},
        )
        if not self.session_id or self.session_id == "00000000-0000-0000-0000-000000000000":
            raise AuthError("Login failed")

    def _read(self) -> list[dict]:
        return self._post(
            "Publisher/ReadPublisherLatestGlucoseValues",
            params={"sessionId": self.session_id, "minutes": 1440, "maxCount": 2},
        )

    def latest(self) -> Reading:
        if not self.session_id:
            self.connect()
        try:
            rows = self._read()
        except _SessionExpired:
            self.connect()
            rows = self._read()
        if not rows:
            raise SourceError("no_data")
        row = rows[0]
        ts = _parse_wt(row.get("WT") or row.get("ST") or row.get("DT"))
        prev = rows[1] if len(rows) > 1 else None
        delta = (float(row["Value"]) - float(prev["Value"])) if prev else None
        return Reading(
            mgdl=float(row["Value"]),
            trend=TREND_MAP.get(row.get("Trend"), "NONE"),
            timestamp=ts,
            source=self.name,
            extra={"delta": delta},
        )


class _SessionExpired(SourceError):
    pass


def _parse_wt(s: str | None) -> float:
    """'Date(1690000000000)' or 'Date(1690000000000-0400)' -> unix seconds (UTC)."""
    if not s:
        return 0.0
    m = re.search(r"Date\((\d+)", s)
    return int(m.group(1)) / 1000.0 if m else 0.0
