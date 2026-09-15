"""Medtrum TouchCare (A6 / A7 / Nano) via EasyView.

Two account types:
  * patient : the wearer's own EasyView account (easyview.medtrum.eu/v3)
  * follow  : an EasyFollow follower account
EasyView reports glucose in mmol/L.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

import requests

from .base import MMOL_TO_MGDL, AuthError, Field, Reading, Source, SourceError

# glucoseRate -> normalised trend
RATE_MAP = {0: "Flat", 8: "Flat", 1: "FortyFiveUp", 2: "SingleUp", 3: "DoubleUp",
            4: "FortyFiveDown", 5: "SingleDown", 6: "DoubleDown"}
SERVERS = [("https://easyview.medtrum.eu", "r_medtrum_eu"),
           ("https://easyview.medtrum.fr", "r_medtrum_fr"),
           ("https://easyview.medtrum.com", "r_medtrum_global")]


class MedtrumEasyView(Source):
    id = "medtrum"
    name = "Medtrum EasyView"
    website = "https://easyview.medtrum.eu/v3/#/monitor"
    poll_seconds = 60
    fields = [
        Field("account_type", "f_medtrum_type", "choice",
              choices=[("patient", "medtrum_patient"), ("follow", "medtrum_follow")], default="patient",
              help_key="h_medtrum_type"),
        Field("username", "f_email", "text"),
        Field("password", "f_password", "password"),
        Field("server", "f_server", "choice", choices=SERVERS, default="https://easyview.medtrum.eu"),
        Field("follow_user", "f_medtrum_follow_user", "text", required=False, help_key="h_medtrum_follow_user"),
    ]

    def __init__(self, cfg: dict[str, Any]):
        super().__init__(cfg)
        self.base = str(cfg.get("server") or SERVERS[0][0]).rstrip("/")
        self.mode = cfg.get("account_type", "patient")
        self.session = requests.Session()
        if self.mode == "follow":
            self.session.headers.update({
                "DevInfo": "Android 12;Xiaomi vayu;Android 12",
                "AppTag": "v=1.2.70(112);n=eyfo;p=android",
                "User-Agent": "okhttp/3.5.0",
            })
        else:
            # Look like the EasyView v3 web app – the server stalls non-browser requests.
            self.session.headers.update({
                "AppTag": "v=3.0.2(15);n=eyvw",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/json",
                "Origin": self.base,
                "Referer": self.base + "/v3/",
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"),
                "X-Requested-With": "XMLHttpRequest",
            })
        self.uid: str | None = None
        self.realname = ""
        self._ok = False

    # ------------------------------------------------------------------ patient
    def _p_login(self) -> None:
        r = self.session.post(self.base + "/v3/api/v2.0/login",
                              json={"user_name": self.cfg["username"], "password": self.cfg["password"],
                                    "user_type": "P"}, timeout=40)
        if r.status_code in (401, 403):
            raise AuthError("invalid_credentials")
        r.raise_for_status()
        d = r.json()
        if d.get("error", 1) != 0:
            raise AuthError(str(d.get("msg") or "invalid_credentials"))
        self.uid = str(int(d["uid"]))
        self.realname = d.get("realname", "")

    def _p_status(self) -> dict:
        now = datetime.now(timezone.utc)
        s = now.replace(hour=0, minute=0, second=0, microsecond=0)
        e = s.replace(hour=23, minute=59, second=59)
        param = base64.b64encode(json.dumps({"ts": [int(s.timestamp()), int(e.timestamp())], "tz": 0}).encode()).decode()
        r = self.session.get(f"{self.base}/api/v2.1/monitor/{self.uid}/status", params={"param": param}, timeout=40)
        if r.status_code in (401, 403):
            raise _SessionExpired()
        r.raise_for_status()
        return r.json()

    def _p_latest(self) -> Reading:
        if not self.uid:
            self._p_login()
        try:
            body = self._p_status()
        except _SessionExpired:
            self._p_login()
            body = self._p_status()
        if body.get("error") not in (0, None):
            raise SourceError(str(body.get("msg") or body))
        ss = (body.get("data") or {}).get("sensor_status") or {}
        if ss.get("glucose") is None:
            raise SourceError("no_data")
        return self._reading(ss, self.realname)

    # ------------------------------------------------------------------ follow
    def _f_login(self) -> None:
        r = self.session.post(self.base + "/mobile/ajax/login",
                              data={"apptype": "Follow", "user_name": self.cfg["username"],
                                    "password": self.cfg["password"], "platform": "google", "user_type": "M"},
                              timeout=20)
        r.raise_for_status()
        try:
            d = r.json()
        except ValueError:
            d = {}
        if d.get("res") == "ERR" or d.get("error") not in (None, 0):
            raise AuthError(str(d.get("msg") or "invalid_credentials"))
        self._ok = True

    def _f_data(self) -> dict:
        r = self.session.get(self.base + "/mobile/ajax/logindata", timeout=20)
        r.raise_for_status()
        return r.json()

    def _f_latest(self) -> Reading:
        if not self._ok:
            self._f_login()
        body = self._f_data()
        if body.get("res") == "ERR" or "monitorlist" not in body:
            self._f_login()
            body = self._f_data()
        if body.get("res") == "ERR":
            raise SourceError(str(body.get("msg")))
        monitors = body.get("monitorlist") or []
        if not monitors:
            raise SourceError("medtrum_no_follow")
        want = (self.cfg.get("follow_user") or "").strip().lower()
        chosen = None
        if want:
            chosen = next((m for m in monitors if str(m.get("username", "")).lower() == want), None)
            if chosen is None:
                raise SourceError("follow user not found: " + ", ".join(str(m.get("username")) for m in monitors))
        else:
            chosen = monitors[0]
        ss = chosen.get("sensor_status") or {}
        if ss.get("glucose") is None:
            raise SourceError("no_data")
        return self._reading(ss, str(chosen.get("username", "")))

    # ------------------------------------------------------------------ common
    def _reading(self, ss: dict, person: str) -> Reading:
        return Reading(
            mgdl=float(ss["glucose"]) * MMOL_TO_MGDL,
            trend=RATE_MAP.get(int(ss.get("glucoseRate", 0) or 0), "NONE"),
            timestamp=float(ss["updateTime"]),
            source=self.name,
            person=person,
            extra={"status": ss.get("status"), "battery": ss.get("batteryPercent")},
        )

    def connect(self) -> None:
        if not self.cfg.get("username") or not self.cfg.get("password"):
            raise AuthError("Missing credentials")
        self._f_login() if self.mode == "follow" else self._p_login()

    def latest(self) -> Reading:
        return self._f_latest() if self.mode == "follow" else self._p_latest()


class _SessionExpired(SourceError):
    pass
