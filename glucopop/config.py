"""Configuration storage: %APPDATA%/GlucoPop/config.json (+ Windows Credential Manager for passwords).

The app follows one or more people: yourself, a child, a partner, a friend. Each one is an entry
in `people` with its own service and account; everything else (unit, thresholds, appearance) is
shared, because the widget has room for one set of rules and four people's numbers.

Credentials are keyed by the person's id, not by the service, so two people on the same service
do not overwrite each other's password — which is exactly what the single-account version did.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

APP_NAME = "GlucoPop"
VERSION = "0.2.0"
REPO = "emreukilic/glucopop"
AUTHOR = "Emre Kılıç"
BRAND = "TypeHealthy"

SECRET_KEYS = ("password", "secret")
MAX_PEOPLE = 6          # the widget stops being readable beyond this
ROWS_SHOWN = 3          # how many of the others fit under the active one

DEFAULTS: dict[str, Any] = {
    "language": "tr",
    "people": [],           # [{id, name, source, cfg, alerts}]
    "active_id": "",
    "source": "",           # legacy single-account fields, kept for migration and for the wizard
    "source_cfg": {},
    "unit": "mg/dL",
    "low": 90,
    "high": 180,
    "urgent_low": 55,
    "refresh_seconds": 60,
    "stale_minutes": 15,
    "notify": True,
    "sound": True,
    "repeat_minutes": 15,
    "opacity": 0.92,
    "size": "medium",
    "theme": "dark",
    "show_delta": True,
    "show_others": True,
    "always_on_top": True,
    "autostart": False,
    "pos": None,
    "setup_done": False,
}


def config_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = config_dir() / "config.json"


# --------------------------------------------------------------------------- secrets
def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def _secret_name(owner: str, key: str) -> str:
    """`owner` is a person id now; it used to be a source id, and old entries are read once
    during migration under their old name."""
    return f"{owner}:{key}"


def save_secret(owner: str, key: str, value: str) -> bool:
    kr = _keyring()
    if not kr:
        return False
    try:
        kr.set_password(APP_NAME, _secret_name(owner, key), value)
        return True
    except Exception:
        return False


def load_secret(owner: str, key: str) -> str | None:
    kr = _keyring()
    if not kr:
        return None
    try:
        return kr.get_password(APP_NAME, _secret_name(owner, key))
    except Exception:
        return None


def delete_secret(owner: str, key: str) -> None:
    kr = _keyring()
    if not kr:
        return
    try:
        kr.delete_password(APP_NAME, _secret_name(owner, key))
    except Exception:
        pass


# --------------------------------------------------------------------------- people
def new_person(source: str = "", cfg: dict | None = None, name: str = "") -> dict[str, Any]:
    return {"id": uuid.uuid4().hex[:12], "name": name, "source": source,
            "cfg": dict(cfg or {}), "alerts": True}


class Config:
    def __init__(self) -> None:
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # ----------------------------------------------------------------- people access
    @property
    def people(self) -> list[dict[str, Any]]:
        return self.data.setdefault("people", [])

    def person(self, pid: str) -> dict[str, Any] | None:
        return next((p for p in self.people if p["id"] == pid), None)

    def active(self) -> dict[str, Any] | None:
        return self.person(self.data.get("active_id", "")) or (self.people[0] if self.people else None)

    def set_active(self, pid: str) -> None:
        if self.person(pid):
            self.data["active_id"] = pid

    def upsert(self, person: dict[str, Any]) -> None:
        for i, p in enumerate(self.people):
            if p["id"] == person["id"]:
                self.people[i] = person
                break
        else:
            self.people.append(person)
        if not self.data.get("active_id"):
            self.data["active_id"] = person["id"]

    def remove(self, pid: str) -> None:
        for k in SECRET_KEYS:
            delete_secret(pid, k)
        self.data["people"] = [p for p in self.people if p["id"] != pid]
        if self.data.get("active_id") == pid:
            self.data["active_id"] = self.people[0]["id"] if self.people else ""

    def person_name(self, p: dict[str, Any]) -> str:
        """What to call someone in the widget: their own name, else whatever the service knows."""
        from . import sources  # local import: config must stay importable without the sources package
        return p.get("name") or (sources.SOURCES[p["source"]].name if p.get("source") in sources.SOURCES else "…")

    # ----------------------------------------------------------------- load / save
    def load(self) -> None:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    stored = json.load(f)
                self.data.update(stored)
            except Exception:
                pass

        legacy_src = self.data.get("source")
        if not self.data.get("people") and legacy_src:
            # Upgrading from the single-account version: the one account becomes the first
            # person, and its password moves from the source-keyed slot to a person-keyed one.
            p = new_person(legacy_src, self.data.get("source_cfg") or {})
            for k in SECRET_KEYS:
                if p["cfg"].get(k) == "__keyring__":
                    old = load_secret(legacy_src, k)
                    if old:
                        save_secret(p["id"], k, old)
            self.data["people"] = [p]
            self.data["active_id"] = p["id"]

        for p in self.people:
            p.setdefault("alerts", True)
            p.setdefault("name", "")
            cfg = dict(p.get("cfg") or {})
            for k in SECRET_KEYS:
                if cfg.get(k) == "__keyring__":
                    cfg[k] = load_secret(p["id"], k) or ""
            p["cfg"] = cfg
        if self.people and not self.person(self.data.get("active_id", "")):
            self.data["active_id"] = self.people[0]["id"]
        self._mirror_active()

    def _mirror_active(self) -> None:
        """Keep the legacy `source`/`source_cfg` pointing at the active person. The wizard and
        the credential form still speak that language; everything else reads `people`."""
        a = self.active()
        self.data["source"] = a["source"] if a else ""
        self.data["source_cfg"] = dict(a["cfg"]) if a else {}

    def save(self) -> None:
        out = dict(self.data)
        people_out = []
        for p in self.people:
            q = dict(p)
            cfg = dict(q.get("cfg") or {})
            for k in SECRET_KEYS:
                if cfg.get(k):
                    if save_secret(q["id"], k, cfg[k]):
                        cfg[k] = "__keyring__"
                    # else: stays in the json (fallback, file is user-only in %APPDATA%)
            q["cfg"] = cfg
            people_out.append(q)
        out["people"] = people_out
        a = self.active()
        out["source"] = a["source"] if a else ""
        out["source_cfg"] = {}      # never write the active copy: people[] is the only truth
        tmp = CONFIG_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)

    # ----------------------------------------------------------------- dict-ish access
    def __getitem__(self, k: str) -> Any:
        return self.data[k]

    def get(self, k: str, default: Any = None) -> Any:
        return self.data.get(k, default)

    def __setitem__(self, k: str, v: Any) -> None:
        self.data[k] = v

    def update(self, **kw: Any) -> None:
        self.data.update(kw)


# --------------------------------------------------------------------------- autostart (Windows)
def set_autostart(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import winreg  # type: ignore
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                pyw = Path(sys.executable).with_name("pythonw.exe")
                exe = pyw if pyw.exists() else Path(sys.executable)
                cmd = f'"{exe}" -m glucopop'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass
