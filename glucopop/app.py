"""Application controller: tray icon, widget, poller, alerts, dialogs."""

from __future__ import annotations

import sys
import webbrowser

from PySide6.QtCore import QLockFile, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QMenu, QMessageBox, QSystemTrayIcon,
                               QVBoxLayout)

from . import i18n, sources
from .config import REPO, VERSION, Config, set_autostart
from .core import AlertEngine, Poller
from .i18n import age_text, tr
from .sources import Reading
from .ui.forms import SettingsForm
from .ui.widget import STATE_COLORS, GlucoseWidget
from .ui.wizard import SetupWizard


def make_icon(text: str, color: QColor) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 16, 16)
    p.setPen(QColor("white"))
    size = 30 if len(text) <= 2 else 24 if len(text) == 3 else 18
    p.setFont(QFont("Segoe UI", size, QFont.Weight.Bold))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return QIcon(pm)


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("m_settings").rstrip("…"))
        self.form = SettingsForm(cfg, show_language=True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self); lay.addWidget(self.form); lay.addWidget(bb)


class GlucoPopApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.cfg = Config()
        i18n.set_language(self.cfg["language"])
        self.widget: GlucoseWidget | None = None
        self.poller: Poller | None = None
        self.alerts = AlertEngine(self.cfg)
        self.tray = QSystemTrayIcon(make_icon("--", STATE_COLORS["connecting"]))
        self.tray.setToolTip("GlucoPop")
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()
        self.last_reading: Reading | None = None
        self._age_timer = QTimer()
        self._age_timer.timeout.connect(self._reclassify)
        self._age_timer.start(30_000)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not self.cfg["setup_done"] or not self.cfg["source"]:
            if not self.run_wizard(first_run=True):
                self.app.quit()
                return
        self._start_widget()
        self._start_poller()

    def run_wizard(self, first_run: bool) -> bool:
        wz = SetupWizard(self.cfg, first_run=first_run)
        wz.setWindowIcon(make_icon("G", QColor("#3ec26b")))
        if wz.exec() == QDialog.DialogCode.Accepted:
            self.cfg.save()
            set_autostart(bool(self.cfg["autostart"]))
            i18n.set_language(self.cfg["language"])
            self._build_menu()
            return True
        i18n.set_language(self.cfg["language"])
        return False

    def _start_widget(self) -> None:
        if self.widget is None:
            self.widget = GlucoseWidget(self.cfg)
            self.widget.moved.connect(self._on_moved)
            self.widget.double_clicked.connect(self.open_site)
            self.widget.context_menu.connect(lambda pos: self.menu.exec(pos))
        else:
            self.widget.apply_config()
        self.widget.show()

    def _start_poller(self) -> None:
        self._stop_poller()
        self.alerts = AlertEngine(self.cfg)
        self.poller = Poller(self.cfg["source"], dict(self.cfg["source_cfg"]), int(self.cfg["refresh_seconds"]))
        self.poller.reading.connect(self._on_reading)
        self.poller.error.connect(self._on_error)
        self.poller.start()

    def _stop_poller(self) -> None:
        if self.poller:
            self.poller.stop()
            self.poller.wait(3000)
            self.poller = None

    def quit(self) -> None:
        self._stop_poller()
        self.tray.hide()
        self.app.quit()

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        self.menu = QMenu()
        hdr = QAction("GlucoPop · " + tr("credit")); hdr.setEnabled(False); self.menu.addAction(hdr); self.menu.addSeparator()
        self.act_toggle = QAction(tr("m_hide")); self.act_toggle.triggered.connect(self.toggle_widget)
        self.menu.addAction(self.act_toggle)
        a = QAction(tr("m_refresh")); a.triggered.connect(self.refresh_now); self.menu.addAction(a)
        src_name = sources.SOURCES[self.cfg["source"]].name if self.cfg.get("source") in sources.SOURCES else "…"
        a = QAction(tr("m_open", site=src_name)); a.triggered.connect(self.open_site); self.menu.addAction(a)
        self.menu.addSeparator()
        a = QAction(tr("m_settings")); a.triggered.connect(self.open_settings); self.menu.addAction(a)
        a = QAction(tr("m_setup")); a.triggered.connect(self.rerun_setup); self.menu.addAction(a)
        self.menu.addSeparator()
        a = QAction(tr("m_about")); a.triggered.connect(self.about); self.menu.addAction(a)
        a = QAction(tr("m_quit")); a.triggered.connect(self.quit); self.menu.addAction(a)
        self.tray.setContextMenu(self.menu)
        self._keep = [self.menu]  # prevent GC of actions

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_widget(force_show=True)

    def toggle_widget(self, force_show: bool = False) -> None:
        if not self.widget:
            return
        if self.widget.isVisible() and not force_show:
            self.widget.hide()
            self.act_toggle.setText(tr("m_show"))
        else:
            self.widget.show(); self.widget.raise_()
            self.act_toggle.setText(tr("m_hide"))

    def refresh_now(self) -> None:
        if self.poller:
            self.poller.refresh_now()

    def open_site(self) -> None:
        try:
            src = sources.create(self.cfg["source"], dict(self.cfg["source_cfg"]))
            if src.website:
                webbrowser.open(src.website)
        except Exception:
            pass

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            old_lang, old_refresh = self.cfg["language"], self.cfg["refresh_seconds"]
            dlg.form.apply()
            self.cfg.save()
            set_autostart(bool(self.cfg["autostart"]))
            if self.cfg["language"] != old_lang:
                i18n.set_language(self.cfg["language"])
                self._build_menu()
            if self.widget:
                self.widget.apply_config()
            if self.cfg["refresh_seconds"] != old_refresh:
                self._start_poller()
            else:
                self.alerts = AlertEngine(self.cfg)
            self._reclassify()

    def rerun_setup(self) -> None:
        if self.run_wizard(first_run=False):
            if self.widget:
                self.widget.reading = None
                self.widget.apply_config()
            self.last_reading = None
            self._start_poller()

    def about(self) -> None:
        QMessageBox.information(None, "GlucoPop", tr("about_text", ver=VERSION, repo=REPO))

    def _on_moved(self, x: int, y: int) -> None:
        self.cfg["pos"] = [x, y]
        self.cfg.save()

    # ------------------------------------------------------------------ data
    def _on_reading(self, r: Reading) -> None:
        self.last_reading = r
        self._reclassify(notify=True)

    def _on_error(self, msg: str) -> None:
        if self.widget:
            self.widget.set_error(msg)
        self.tray.setToolTip(f"GlucoPop – {msg}")
        if self.last_reading is None:
            self.tray.setIcon(make_icon("!", STATE_COLORS["error"]))

    def _reclassify(self, notify: bool = False) -> None:
        r = self.last_reading
        if not r:
            return
        state = self.alerts.classify(r)
        unit = self.cfg["unit"]
        txt = r.value_text(unit)
        if self.widget:
            self.widget.set_reading(r, state)
        self.tray.setIcon(make_icon(txt if state != "stale" else "…", STATE_COLORS[state]))
        self.tray.setToolTip(f"{txt} {unit} {r.arrow}  ({age_text(r.age_seconds)})")
        if self.alerts.should_notify(state):
            self._notify(state, r)

    def _notify(self, state: str, r: Reading) -> None:
        unit = self.cfg["unit"]
        body = f"{r.value_text(unit)} {unit} {r.arrow}  ({age_text(r.age_seconds)})"
        if state == "stale":
            title, body = tr("n_stale_title"), tr("n_stale_body", age=age_text(r.age_seconds))
            icon = QSystemTrayIcon.MessageIcon.Information
        elif state == "urgent_low":
            title, icon = tr("n_urgent_title"), QSystemTrayIcon.MessageIcon.Critical
        elif state == "low":
            title, icon = tr("n_low_title"), QSystemTrayIcon.MessageIcon.Warning
        else:
            title, icon = tr("n_high_title"), QSystemTrayIcon.MessageIcon.Warning
        self.tray.showMessage(title, body, icon, 8000)
        if self.cfg["sound"]:
            _beep(state)
        if self.widget and not self.widget.isVisible() and state != "stale":
            self.toggle_widget(force_show=True)


def _beep(state: str) -> None:
    if sys.platform == "win32":
        try:
            import winsound
            if state == "urgent_low":
                for _ in range(3):
                    winsound.Beep(880, 180)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
        except Exception:
            pass
    QApplication.beep()


def main() -> int:
    QApplication.setApplicationName("GlucoPop")
    QApplication.setOrganizationName("GlucoPop")
    QApplication.setQuitOnLastWindowClosed(False)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setWindowIcon(make_icon("G", QColor("#3ec26b")))

    # single instance
    lock_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation) + "/glucopop.lock"
    lock = QLockFile(lock_path)
    if not lock.tryLock(100):
        QMessageBox.information(None, "GlucoPop", "GlucoPop is already running (see the system tray).")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "GlucoPop", "System tray not available.")
        return 1

    ctl = GlucoPopApp(app)
    QTimer.singleShot(0, ctl.start)
    return app.exec()
