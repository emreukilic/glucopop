"""Checks GitHub Releases for a newer version, and installs it where that can be done safely.

On Windows the installer is silent: it closes the app, writes over it and starts the new one.
On macOS it is not. Replacing a running .app from inside itself breaks the code signature
Gatekeeper checked on launch, and an app that quietly rewrites a signed bundle is the shape
of thing macOS is right to distrust. So the Mac build downloads the disk image, opens it, and
lets the person drag the new version over the old one — two seconds of their attention in
exchange for a signature that still means something."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import requests
from PySide6.QtCore import QThread, Signal

from .config import REPO, VERSION

API = f"https://api.github.com/repos/{REPO}/releases/latest"


@dataclass
class Update:
    version: str
    url: str          # release page
    asset_url: str    # setup exe download (may be empty)
    notes: str


def _ver_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def check() -> Update | None:
    r = requests.get(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "GlucoPop"}, timeout=15)
    r.raise_for_status()
    d = r.json()
    tag = str(d.get("tag_name", "")).lstrip("v")
    if not tag or _ver_tuple(tag) <= _ver_tuple(VERSION):
        return None
    want = ".dmg" if sys.platform == "darwin" else ".exe"
    asset = ""
    for a in d.get("assets", []):
        name = a.get("name", "").lower()
        if name.startswith("glucopop") and name.endswith(want):
            # the fixed-name copy is the one the website links to; either will do here
            asset = a.get("browser_download_url", "")
            break
    return Update(tag, d.get("html_url", f"https://github.com/{REPO}/releases/latest"), asset, d.get("body", "") or "")


class UpdateCheck(QThread):
    found = Signal(object)   # Update

    def run(self) -> None:
        try:
            u = check()
            if u:
                self.found.emit(u)
        except Exception:
            pass


class UpdateInstall(QThread):
    progress = Signal(int)   # percent
    failed = Signal(str)
    started_install = Signal()
    opened_image = Signal()   # macOS: the disk image is on screen, we are not quitting

    def __init__(self, upd: Update):
        super().__init__()
        self.upd = upd

    def run(self) -> None:
        try:
            ext = ".dmg" if sys.platform == "darwin" else ".exe"
            path = os.path.join(tempfile.gettempdir(), f"GlucoPop-{self.upd.version}{ext}")
            with requests.get(self.upd.asset_url, stream=True, timeout=60, headers={"User-Agent": "GlucoPop"}) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                done = 0
                with open(path, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            self.progress.emit(int(done * 100 / total))
            if sys.platform == "darwin":
                # opens the disk image in Finder; the person drags GlucoPop across, as they did
                # the first time. Nothing is replaced behind their back.
                subprocess.Popen(["/usr/bin/open", path], close_fds=True)
                self.opened_image.emit()
                return
            # Installer kills us, installs over the old files and relaunches the new version.
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RESTARTAPP=1"],
                             creationflags=flags, close_fds=True)
            self.started_install.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))
