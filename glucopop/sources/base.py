"""Common data model and base class for all glucose data sources."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

MMOL_TO_MGDL = 18.0

# Normalised trend names (Nightscout vocabulary)
TRENDS = (
    "DoubleUp", "SingleUp", "FortyFiveUp", "Flat",
    "FortyFiveDown", "SingleDown", "DoubleDown", "NONE",
)

TREND_ARROW = {
    "DoubleUp": "⇈",
    "SingleUp": "↑",
    "FortyFiveUp": "↗",
    "Flat": "→",
    "FortyFiveDown": "↘",
    "SingleDown": "↓",
    "DoubleDown": "⇊",
    "NONE": "",
    "NotComputable": "?",
    "RateOutOfRange": "⇕",
}


class SourceError(Exception):
    """Generic source error (network, unexpected payload, no data)."""


class AuthError(SourceError):
    """Credentials rejected."""


@dataclass
class Reading:
    mgdl: float
    trend: str = "NONE"           # one of TRENDS
    timestamp: float = 0.0        # unix seconds (UTC)
    source: str = ""
    person: str = ""              # whose data (follower setups)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def mmol(self) -> float:
        return round(self.mgdl / MMOL_TO_MGDL, 1)

    @property
    def arrow(self) -> str:
        return TREND_ARROW.get(self.trend, "?")

    @property
    def age_seconds(self) -> int:
        return max(0, int(time.time() - self.timestamp))

    @property
    def local_time(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).astimezone()

    def value(self, unit: str) -> float:
        return round(self.mgdl) if unit == "mg/dL" else self.mmol

    def value_text(self, unit: str) -> str:
        return f"{int(round(self.mgdl))}" if unit == "mg/dL" else f"{self.mmol:.1f}"


@dataclass
class Field:
    """Describes a credential/config field the UI must ask for."""
    key: str
    label_key: str                # i18n key
    kind: str = "text"            # text | password | choice | url
    choices: list[tuple[str, str]] = field(default_factory=list)  # (value, i18n label key)
    default: str = ""
    required: bool = True
    help_key: str = ""


class Source:
    """Base class. Subclasses set `id`, `name`, `fields`, implement `connect` and `latest`."""

    id: str = ""
    name: str = ""
    website: str = ""
    fields: list[Field] = []
    poll_seconds: int = 60        # sensible default poll interval

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def connect(self) -> None:
        """Authenticate. Raise AuthError/SourceError on failure."""

    def latest(self) -> Reading:
        """Return the most recent reading. Reconnect transparently if needed."""
        raise NotImplementedError

    # helpers -----------------------------------------------------------
    def describe(self) -> str:
        return self.name

    @staticmethod
    def _mgdl_from_any(value: float, unit_hint: str = "") -> float:
        """Accept mmol or mg/dL by magnitude if unit is unknown."""
        if unit_hint == "mmol/L":
            return float(value) * MMOL_TO_MGDL
        if unit_hint == "mg/dL":
            return float(value)
        return float(value) * MMOL_TO_MGDL if float(value) < 35 else float(value)
