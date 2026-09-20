"""Deciding what a glucose reading means, and whether to say anything about it.

Split out of `core` so it can be tested without a GUI toolkit. `core` has always described itself
as "Qt-agnostic logic, Qt thread wrapper", but the logic sat behind a `PySide6` import, so the
one part of this app where a mistake is dangerous was the part no test could reach. Nothing here
imports Qt, and nothing here should.
"""

from __future__ import annotations

import math
import time

from .sources import Reading


class AlertEngine:
    """Decides when to notify. Pure logic, no Qt."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self._last_state = "ok"
        self._last_notify = 0.0
        self._last_stale_notify = 0.0

    def classify(self, r: Reading) -> str:
        mg = r.mgdl
        # A number we cannot compare is not a number we may call normal: every comparison below
        # is false for NaN, so it would fall through to "ok" and be drawn as in range. Sources
        # are guarded at the seam now, so this should be unreachable — it stays because the cost
        # of being wrong here is the whole point of the app.
        if not math.isfinite(mg):
            return "error"

        stale_after = int(self.cfg["stale_minutes"]) * 60
        age = r.age_seconds

        # An urgent low outranks staleness, and that ordering is deliberate.
        #
        # Staleness used to be decided first, so a reading of 38 that was a minute past the
        # threshold stopped being an urgent low at all: it lost the word urgent and dropped from
        # the fast five-minute repeat to the slow one. A feed running a few minutes behind is
        # ordinary; being hypo while the app decides the news is too old to mention is not.
        #
        # It does not hold forever. Past twice the user's own threshold the value has stopped
        # being evidence about now, and the staleness alert — which fits a sensor that has
        # actually stopped — takes over.
        if mg < float(self.cfg["urgent_low"]) and age <= stale_after * 2:
            return "urgent_low"
        if age > stale_after:
            return "stale"
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
