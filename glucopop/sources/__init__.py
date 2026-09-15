"""Source registry."""

from __future__ import annotations

from typing import Any

from .base import AuthError, Field, Reading, Source, SourceError
from .dexcom import DexcomShare
from .libre import LibreLinkUp
from .medtrum import MedtrumEasyView
from .nightscout import Nightscout

SOURCES: dict[str, type[Source]] = {
    DexcomShare.id: DexcomShare,
    LibreLinkUp.id: LibreLinkUp,
    MedtrumEasyView.id: MedtrumEasyView,
    Nightscout.id: Nightscout,
}

# Which sensors each source covers (for the picker UI). i18n keys.
SOURCE_INFO = {
    "dexcom": {"title": "Dexcom", "sub": "src_sub_dexcom", "desc": "src_desc_dexcom"},
    "libre": {"title": "FreeStyle Libre", "sub": "src_sub_libre", "desc": "src_desc_libre"},
    "medtrum": {"title": "Medtrum", "sub": "src_sub_medtrum", "desc": "src_desc_medtrum"},
    "nightscout": {"title": "Nightscout / xDrip+", "sub": "src_sub_ns", "desc": "src_desc_ns"},
}


def create(source_id: str, cfg: dict[str, Any]) -> Source:
    cls = SOURCES.get(source_id)
    if cls is None:
        raise ValueError(f"unknown source: {source_id}")
    return cls(cfg)


__all__ = ["SOURCES", "SOURCE_INFO", "create", "Source", "Reading", "Field", "SourceError", "AuthError"]
