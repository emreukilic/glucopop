"""Configuration storage: %APPDATA%/GlucoPop/config.json (+ Windows Credential Manager for passwords)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_NAME = "GlucoPop"
VERSION = "0.1.1"
REPO = "emreukilic/glucopop"
AUTHOR = "Emre Kılıç"
BRAND = "TypeHealthy"

SECRET_KEYS = ("password", "secret")

DEFAULTS: dict[str, Any] = {
    "language": "tr",
    "source": "",
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


def _secret_name(source: str, key: str) -> str:
    return f"{source}:{key}"


def save_secret(source: str, key: str, value: str) -> bool:
    kr = _keyring()
    if not kr:
        return False
    try:
        kr.set_password(APP_NAME, _secret_name(source, key), value)
        return True
    except Exception:
        return False


def load_secret(source: str, key: str) -> str | None:
    kr = _keyring()
    if not kr:
        return None
    try:
        return kr.get_password(APP_NAME, _secret_name(source, key))
    except Exception:
        return None


def delete_secret(source: str, key: str) -> None:
    kr = _keyring()
    if not kr:
        return
    try:
        kr.delete_password(APP_NAME, _secret_name(source, key))
    except Exception:
        pass


# --------------------------------------------------------------------------- config
class Config:
    def __init__(self) -> None:
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    stored = json.load(f)
                self.data.update(stored)
            except Exception:
                pass
        # pull secrets back from credential manager
        src = self.data.get("source")
        scfg = dict(self.data.get("source_cfg") or {})
        if src:
            for k in SECRET_KEYS:
                if scfg.get(k) == "__keyring__":
                    scfg[k] = load_secret(src, k) or ""
        self.data["source_cfg"] = scfg

    def save(self) -> None:
        out = dict(self.data)
        src = out.get("source")
        scfg = dict(out.get("source_cfg") or {})
        if src:
            for k in SECRET_KEYS:
                if scfg.get(k):
                    if save_secret(src, k, scfg[k]):
                        scfg[k] = "__keyring__"
                    # else: stays in the json (fallback, file is user-only in %APPDATA%)
        out["source_cfg"] = scfg
        tmp = CONFIG_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        os.replace(tmp, CONFIG_PATH)

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
