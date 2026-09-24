"""Signing in to Medtronic CareLink, in a window of GlucoPop's own.

CareLink has no endpoint that takes a username and password: its login is a web page with a
reCAPTCHA. So the page is shown here in an embedded browser, the person signs in on it, and when
Medtronic redirects to the official app's URL scheme with a one-time code, the window catches the
redirect before anything tries to open it, and exchanges the code for tokens. The password is typed
into Medtronic's page; GlucoPop neither reads nor keeps it. The browser profile is off the record:
no cookies or history outlive the window.

Qt WebEngine is imported only here, only when the window opens — it is a large library, and
everyone who does not use Medtronic should not pay for it at start-up.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any, Optional
from urllib.parse import parse_qs, urlsplit

import requests
from PySide6.QtCore import QEventLoop, Qt, QThread, QUrl, Signal
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from ..i18n import tr
from ..sources import carelink

# Threads outlive the window if it is closed mid-request; they are held here until they finish,
# so Qt never destroys one that is still running.
_running: set[QThread] = set()

# The official app's URL scheme, where Medtronic sends the one-time code (the login configuration
# names it; this is what it has always said). Registered with Qt WebEngine before the first
# browser object exists — later registrations are ignored — so that a redirect to it is an
# ordinary navigation this window is asked about. Unregistered, Chromium takes it for an outside
# app to launch, and asks nobody unless the person clicked a moment before.
KNOWN_SCHEME = "com.medtronic.carepartner"
_scheme_registered = False


def _start(t: QThread) -> None:
    _running.add(t)
    t.finished.connect(lambda: _running.discard(t))
    t.start()


def _register_scheme() -> None:
    global _scheme_registered
    if _scheme_registered:
        return
    _scheme_registered = True
    from PySide6.QtCore import QByteArray
    from PySide6.QtWebEngineCore import QWebEngineUrlScheme
    s = QWebEngineUrlScheme(QByteArray(KNOWN_SCHEME.encode()))
    s.setSyntax(QWebEngineUrlScheme.Syntax.Path)
    QWebEngineUrlScheme.registerScheme(s)


class _Prepare(QThread):
    """Discovery and the login configuration, off the GUI thread."""
    done = Signal(object, object, str)   # reg, sso, error

    def __init__(self, region: str):
        super().__init__()
        self.region = region

    def run(self) -> None:
        try:
            s = requests.Session()
            reg = carelink.discover(s, self.region)
            self.done.emit(reg, carelink.load_sso(s, reg["sso_url"]), "")
        except Exception as e:  # noqa: BLE001
            from ..core import error_text
            self.done.emit(None, None, error_text(e))


class _Finish(QThread):
    """The code for tokens, then who signed in — off the GUI thread."""
    done = Signal(object, str)           # account dict, error

    def __init__(self, region: str, reg: dict, sso: dict, code: str, verifier: str):
        super().__init__()
        self.region, self.reg, self.sso, self.code, self.verifier = region, reg, sso, code, verifier

    def run(self) -> None:
        try:
            s = requests.Session()
            tokens = carelink.exchange_code(s, self.sso, self.code, self.verifier, self.reg.get("cumulus"))
            who = carelink.identify(s, tokens, self.region, self.reg, self.sso)
            key = carelink.vault_key(self.region, who["username"])
            # memory only, until a person who uses this sign-in is saved (see Config.save)
            carelink.remember_tokens(key, tokens, pending=True)
            self.done.emit({**who, "region": self.region}, "")
        except Exception as e:  # noqa: BLE001
            from ..core import error_text
            self.done.emit(None, error_text(e))


class CareLinkLogin(QDialog):
    """Medtronic's sign-in page. ``result_account`` holds who signed in, once someone has."""

    def __init__(self, region: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("cl_login"))
        self.resize(480, 720)
        self.region = "us" if region == "us" else "eu"
        self.result_account: Optional[dict[str, Any]] = None
        self.error = ""
        self._verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
        self._state = base64.urlsafe_b64encode(secrets.token_bytes(16)).rstrip(b"=").decode()
        self._reg: Optional[dict] = None
        self._sso: Optional[dict] = None
        self._got_code = False

        self.status = QLabel(tr("cl_signing_in"))
        self.status.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.status)
        self._scheme = ""           # the official app's URL scheme, once the login configuration says
        self._view = None
        self._page = None
        self._profile = None

        try:
            from PySide6.QtCore import QByteArray
            from PySide6.QtWebEngineCore import (QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestJob,
                                                 QWebEngineUrlSchemeHandler)
            _register_scheme()
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as e:  # noqa: BLE001 — a build without the browser, or one it cannot load
            self._fail(tr("e_cl_window") + f" ({type(e).__name__})")
            return

        dialog = self

        class Page(QWebEnginePage):
            # The redirect to the official app's scheme is caught here and never followed.
            def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802 (Qt's name)
                if dialog._scheme and url.scheme().lower() == dialog._scheme:
                    dialog._caught(url.toString())
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main_frame)

        class Catcher(QWebEngineUrlSchemeHandler):
            # The same redirect, should it ever get past the page: answered with nothing, and caught.
            def requestStarted(self, job):  # noqa: N802 (Qt's name)
                url = job.requestUrl().toString()
                job.fail(QWebEngineUrlRequestJob.Error.RequestAborted)
                if dialog._scheme == KNOWN_SCHEME:
                    dialog._caught(url)

        # Made here, before the window is shown, and in this order. A browser view added to a window
        # already on screen makes Qt rebuild that window. And a profile destroyed before its page
        # makes Qt warn and can crash; children are destroyed in the order they were made, so the
        # view, with the page inside it, has to come first.
        self._view = QWebEngineView(self)
        self._profile = QWebEngineProfile(self)    # no storage name: off the record
        self._catcher = Catcher(self._profile)
        self._profile.installUrlSchemeHandler(QByteArray(KNOWN_SCHEME.encode()), self._catcher)
        self._page = Page(self._profile, self._view)
        self._page.renderProcessTerminated.connect(self._crashed)
        self._view.setPage(self._page)
        self._view.loadFinished.connect(self._loaded)
        lay.addWidget(self._view, 1)

        prep = _Prepare(self.region)
        prep.done.connect(self._prepared)
        _start(prep)

    # ------------------------------------------------------------------ steps
    def _prepared(self, reg, sso, err: str) -> None:
        if self.error or self._view is None:
            return
        if err or not reg or not sso:
            self._fail(err or tr("e_carelink_unsupported"))
            return
        self._reg, self._sso = reg, sso
        scheme = sso["redirect_uri"].split(":", 1)[0].lower()
        if not scheme or scheme in ("http", "https"):
            self._fail(tr("e_carelink_unsupported"))
            return
        self._scheme = scheme
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self._verifier.encode()).digest()).rstrip(b"=").decode()
        self._view.load(QUrl(carelink.authorize_url(sso, challenge, self._state)))
        self.status.setText(tr("h_carelink_window"))

    def _loaded(self, ok: bool) -> None:
        # a page that failed to load (no network, a proxy) says so above it; the caught redirect
        # also ends as a load that did not finish, which is not a failure
        if self._got_code or self.error:
            return
        self.status.setText(tr("h_carelink_window") if ok else "⚠ " + tr("e_cl_page"))

    def _crashed(self, *_a) -> None:
        if not self._got_code:
            self._fail(tr("e_cl_window"))

    def _caught(self, url: str) -> None:
        if self._got_code:
            return
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items() if v}
        if q.get("error"):
            self._fail(tr("e_carelink_denied") + (f" ({q.get('error_description') or q['error']})"))
            return
        if not q.get("code") or q.get("state") != self._state:
            self._fail(tr("e_carelink_denied"))
            return
        self._got_code = True
        if self._view is not None:
            self._view.hide()
        self.status.setText(tr("wz_testing"))
        fin = _Finish(self.region, self._reg or {}, self._sso or {}, q["code"], self._verifier)
        fin.done.connect(self._finished)
        _start(fin)

    def _finished(self, who, err: str) -> None:
        if err or not who:
            self._fail(err or tr("e_carelink_denied"))
            return
        self.result_account = who
        self.accept()

    def _fail(self, message: str) -> None:
        self.error = message
        self.status.setText("❌ " + message)
        if self._view is not None:
            self._view.hide()

    def done(self, r: int) -> None:  # noqa: D401 (Qt's name)
        # The view, and the page inside it, go before their profile: Qt warns, and can crash, when a
        # profile is destroyed while a page still uses it — the order the dialog's children go in.
        if self._view is not None:
            self._view.hide()
            self._view.deleteLater()
            self._view = self._page = None
        super().done(r)


def sign_in(region: str, parent=None) -> tuple[Optional[dict[str, Any]], str]:
    """Shows the window; returns (account, error). Both empty means the window was closed."""
    dlg = CareLinkLogin(region, parent)
    # Not exec(): with a browser view inside, QDialog.exec() returns at once, before anyone has
    # had a chance to sign in (seen on Qt 6.8). A loop of our own that ends only when the dialog
    # is closed — signed in, failed, or cancelled — does what exec() should.
    loop = QEventLoop()
    dlg.finished.connect(loop.quit)
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.show()
    loop.exec()
    account, error = dlg.result_account, (dlg.error if dlg.result_account is None else "")
    dlg.deleteLater()           # its browser profile with it; nothing of the session is kept
    return account, error
