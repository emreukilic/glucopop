"""Source registry."""

from __future__ import annotations

import math
import time
from typing import Any

from .base import AuthError, Field, Reading, Source, SourceError
from .carelink import CareLink
from .dexcom import DexcomShare
from .libre import LibreLinkUp
from .medtrum import MedtrumEasyView
from .nightscout import Nightscout

SOURCES: dict[str, type[Source]] = {
    DexcomShare.id: DexcomShare,
    LibreLinkUp.id: LibreLinkUp,
    MedtrumEasyView.id: MedtrumEasyView,
    CareLink.id: CareLink,
    Nightscout.id: Nightscout,
}

# Which sensors each source covers (for the picker UI). i18n keys. The order is the picker's.
SOURCE_INFO = {
    "dexcom": {"title": "Dexcom", "sub": "src_sub_dexcom", "desc": "src_desc_dexcom"},
    "libre": {"title": "FreeStyle Libre", "sub": "src_sub_libre", "desc": "src_desc_libre"},
    "medtrum": {"title": "Medtrum", "sub": "src_sub_medtrum", "desc": "src_desc_medtrum"},
    "carelink": {"title": "Medtronic", "sub": "src_sub_carelink", "desc": "src_desc_carelink"},
    "nightscout": {"title": "Nightscout / xDrip+", "sub": "src_sub_ns", "desc": "src_desc_ns"},
}


def _checked(r: Reading) -> Reading:
    """The one gate every live reading passes through.

    Each adapter parses somebody else's JSON and trusts the number it finds. Medtrum reports a
    sensor that is still warming up as ``glucose: 0`` — not null, which is what the adapter checks
    for — so a brand new sensor produced a reading of exactly 0 mg/dL. That is below every low
    threshold there is, which means ``classify`` calls it ``urgent_low`` and the alert repeats on
    the fast five-minute schedule: a hypo alarm, over and over, for someone whose sensor has not
    started yet. Zero is also simply wrong on screen.

    The same hole takes a missing or unparseable value to NaN, which compares false against every
    threshold and therefore reads as "in range" — green, and silent.

    So a value outside the range a sensor can physically report is treated as no reading at all,
    which the app already knows how to show and to say something honest about.
    """
    mgdl = float(r.mgdl)
    if not math.isfinite(mgdl) or mgdl <= 10 or mgdl >= 1000:
        raise SourceError("no_data", f"implausible value: {r.mgdl}")
    # A time we cannot trust makes every "x minutes ago" a fiction, and a reading stamped in the
    # future never goes stale, so the staleness guard stops working altogether.
    ts = float(r.timestamp)
    if not math.isfinite(ts) or ts <= 0 or ts > time.time() + 300:
        raise SourceError("no_data", f"implausible time: {r.timestamp}")
    return r


def create(source_id: str, cfg: dict[str, Any]) -> Source:
    cls = SOURCES.get(source_id)
    if cls is None:
        raise ValueError(f"unknown source: {source_id}")
    src = cls(cfg)
    inner = src.latest
    src.latest = lambda: _checked(inner())   # type: ignore[method-assign]
    return src


__all__ = ["SOURCES", "SOURCE_INFO", "create", "Source", "Reading", "Field", "SourceError", "AuthError"]
