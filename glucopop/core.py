"""Background poller + alert state machine (Qt-agnostic logic, Qt thread wrapper)."""

from __future__ import annotations

import time
import traceback
from typing import Optional

import requests
from PySide6.QtCore import QObject, QThread, Signal

from . import sources
from .i18n import tr
from .sources import AuthError, Reading, SourceError


def error_text(err: BaseException) -> str:
    """Map an exception to a user-facing message."""
    if isinstance(err, AuthError):
        msg = str(err)
        if msg == "llu_terms":
            return tr("e_llu_terms")
        return tr("e_auth") + (f" ({msg})" if msg and msg not in ("invalid_credentials", "Unauthorized") else "")
    if isinstance(err, SourceError):
        msg = str(err)
        key = {"no_data": "e_no_data", "libre_no_connection": "e_libre_no_connection",
               "medtrum_no_follow": "e_medtrum_no_follow", "rate_limited": "e_rate_limited"}.get(msg)
        return tr(key) if key else msg
    if isinstance(err, requests.exceptions.SSLError):
        return tr("e_ssl")
    if isinstance(err, requests.RequestException):
        return tr("e_net", err=type(err).__name__)
    return f"{type(err).__name__}: {err}"


class Poller(QThread):
    """Polls the configured source; emits readings / errors to the GUI thread."""

    reading = Signal(object)      # Reading
    error = Signal(str)           # user-facing message
    state = Signal(str)           # 'connecting' | 'ok' | 'error'

    def __init__(self, source_id: str, source_cfg: dict, interval: int = 60, parent: QObject | None = None):
        super().__init__(parent)
        self.source_id = source_id
        self.source_cfg = source_cfg
        self.interval = max(20, int(interval))
        self._stop = False
        self._wake = False
        self.last: Optional[Reading] = None

    def stop(self) -> None:
        self._stop = True
        self._wake = True

    def refresh_now(self) -> None:
        self._wake = True

    def run(self) -> None:  # noqa: C901
        self.state.emit("connecting")
        try:
            src = sources.create(self.source_id, self.source_cfg)
        except Exception as e:  # pragma: no cover
            self.error.emit(str(e))
            return
        backoff = 0
        while not self._stop:
            try:
                r = src.latest()
                self.last = r
                self.reading.emit(r)
                self.state.emit("ok")
                backoff = 0
            except Exception as e:  # noqa: BLE001
                self.error.emit(error_text(e))
                self.state.emit("error")
                backoff = min(300, (backoff or 15) * 2)
                if isinstance(e, AuthError):
                    backoff = 300
                traceback.print_exc()

            # Align next poll with the expected next reading (~5 min cadence) when we have data
            wait = self.interval
            if backoff:
                wait = backoff
            elif self.last and self.last.timestamp:
                age = self.last.age_seconds
                if age < 300:
                    nxt = 300 - age + 15  # a little after the next expected sample
                    wait = min(self.interval, max(20, nxt)) if self.interval < nxt else nxt
            self._wake = False
            t_end = time.time() + wait
            while time.time() < t_end and not self._wake and not self._stop:
                self.msleep(250)


class AlertEngine:
    """Decides when to notify. Pure logic, no Qt."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._last_state = "ok"
        self._last_notify = 0.0
        self._last_stale_notify = 0.0

    def classify(self, r: Reading) -> str:
        mg = r.mgdl
        if r.age_seconds > int(self.cfg["stale_minutes"]) * 60:
            return "stale"
        if mg < float(self.cfg["urgent_low"]):
            return "urgent_low"
        if mg < float(self.cfg["low"]):
            return "low"
        if mg > float(self.cfg["high"]):
            return "high"
        return "ok"

    def should_notify(self, state: str) -> bool:
        if not self.cfg["notify"]:
            self._last_state = state
            return False
        now = time.time()
        repeat = float(self.cfg["repeat_minutes"]) * 60
        if state == "ok":
            self._last_state = state
            return False
        if state == "stale":
            fire = now - self._last_stale_notify > max(repeat, 600)
            if fire:
                self._last_stale_notify = now
            self._last_state = state
            return fire
        changed = state != self._last_state
        # urgent low: repeat faster
        rep = min(repeat, 300) if state == "urgent_low" else repeat
        fire = changed or (now - self._last_notify > rep)
        if fire:
            self._last_notify = now
        self._last_state = state
        return fire
