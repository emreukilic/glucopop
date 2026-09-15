"""Nightscout – the universal bridge.

Anyone uploading to a Nightscout site (xDrip+, Juggluco, AAPS, Loop, xDrip4iOS, CareLink
follower, LinX/AiDEX or Sibionics via companion apps...) can use this source.
Also works with the xDrip+ built-in web service ("http://<phone-ip>:17580") and
Juggluco's web server ("http://<phone-ip>:17580") on the local network.
"""

from __future__ import annotations

import hashlib
from typing import Any

import requests

from .base import AuthError, Field, Reading, Source, SourceError

DIRECTIONS = {"DoubleUp", "SingleUp", "FortyFiveUp", "Flat", "FortyFiveDown",
              "SingleDown", "DoubleDown", "NONE", "NOT COMPUTABLE", "RATE OUT OF RANGE"}


class Nightscout(Source):
    id = "nightscout"
    name = "Nightscout"
    website = ""
    poll_seconds = 60
    fields = [
        Field("url", "f_ns_url", "url", help_key="h_ns_url"),
        Field("secret", "f_ns_secret", "password", required=False, help_key="h_ns_secret"),
    ]

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        url = str(cfg.get("url", "")).strip().rstrip("/")
        if url and not url.startswith("http"):
            url = "https://" + url
        self.url = url
        self.website = url
        self.secret = str(cfg.get("secret", "") or "").strip()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "GlucoPop"})
        if self.secret and not self.secret.lower().startswith("token=") and "-" not in self.secret[:20]:
            # classic API_SECRET -> sha1 header
            self.session.headers["api-secret"] = hashlib.sha1(self.secret.encode()).hexdigest()

    def _params(self) -> dict:
        p = {"count": 2}
        s = self.secret
        if s and ("-" in s[:20] or s.lower().startswith("token=")):
            # access token (subject-xxxx style) -> query param
            p["token"] = s.split("=", 1)[1] if s.lower().startswith("token=") else s
        return p

    def connect(self) -> None:
        if not self.url:
            raise AuthError("Missing URL")
        r = self.session.get(self.url + "/api/v1/status.json", params=self._params(), timeout=15)
        if r.status_code in (401, 403):
            raise AuthError("unauthorized")
        r.raise_for_status()

    def latest(self) -> Reading:
        r = self.session.get(self.url + "/api/v1/entries/sgv.json", params=self._params(), timeout=15)
        if r.status_code in (401, 403):
            raise AuthError("unauthorized")
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise SourceError("no_data")
        row = rows[0]
        direction = str(row.get("direction") or "NONE")
        direction = {"NOT COMPUTABLE": "NotComputable", "RATE OUT OF RANGE": "RateOutOfRange"}.get(direction, direction)
        ts_ms = row.get("date") or row.get("mills") or 0
        delta = None
        if len(rows) > 1 and rows[1].get("sgv") is not None:
            delta = float(row["sgv"]) - float(rows[1]["sgv"])
        return Reading(
            mgdl=float(row["sgv"]),
            trend=direction,
            timestamp=float(ts_ms) / 1000.0,
            source=self.name,
            extra={"device": row.get("device"), "delta": delta},
        )
