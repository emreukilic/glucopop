"""Application controller: tray icon, widget, one poller per person, alerts, dialogs."""

from __future__ import annotations

import sys
import webbrowser

from PySide6.QtCore import QLockFile, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QMenu, QMessageBox, QSystemTrayIcon,
                               QVBoxLayout)

from . import i18n, sources
from .config import MAX_PEOPLE, REPO, VERSION, Config
from .core import AlertEngine, Poller
from .i18n import age_text, tr
from .sources import Reading
from .ui.forms import PeopleBox, PersonDialog, SettingsForm
from .ui.widget import STATE_COLORS, GlucoseWidget
from .ui.wizard import SetupWizard
from .updater import Update, UpdateCheck, UpdateInstall


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
        self.people = PeopleBox(cfg, self)
        self.form = SettingsForm(cfg, show_language=True)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.people)
        lay.addWidget(self.form)
        lay.addWidget(bb)


class GlucoPopApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.cfg = Config()
        i18n.set_language(self.cfg["language"])
        self.widget: GlucoseWidget | None = None
        self.pollers: dict[str, Poller] = {}
        self.alerts: dict[str, AlertEngine] = {}
        self.readings: dict[str, Reading] = {}
        self.errors: dict[str, str] = {}
        self.update: Update | None = None
        self._upd_thread = None
        self.tray = QSystemTrayIcon(make_icon("--", STATE_COLORS["connecting"]))
        self.tray.setToolTip("GlucoPop")
        self.tray.activated.connect(self._tray_activated)
        self._build_menu()
        self.tray.show()
        self._age_timer = QTimer()
        self._age_timer.timeout.connect(self._reclassify)
        self._age_timer.start(30_000)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if not self.cfg["setup_done"] or not self.cfg.people:
            if not self.run_wizard(first_run=True):
                self.app.quit()
                return
        self._start_widget()
        self._start_pollers()
        QTimer.singleShot(20_000, self.check_updates)          # once shortly after start
        self._upd_timer = QTimer(); self._upd_timer.timeout.connect(self.check_updates)
        self._upd_timer.start(6 * 3600 * 1000)                 # then every 6 h

    def run_wizard(self, first_run: bool) -> bool:
        """The wizard still speaks the single-account language; what it produces becomes the
        active person (or the first one, on a fresh install)."""
        wz = SetupWizard(self.cfg, first_run=first_run)
        wz.setWindowIcon(make_icon("G", QColor("#3ec26b")))
        if wz.exec() == QDialog.DialogCode.Accepted:
            from .config import new_person
            person = self.cfg.active()
            if person is None:
                person = new_person()
                self.cfg.upsert(person)
                self.cfg.set_active(person["id"])
            person["source"] = self.cfg["source"]
            person["cfg"] = dict(self.cfg["source_cfg"])
            self.cfg.upsert(person)
            self.cfg.save()
            from .config import set_autostart
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
            self.widget.person_clicked.connect(self.set_active)
        else:
            self.widget.apply_config()
        self.widget.show()

    # ------------------------------------------------------------------ pollers
    def _start_pollers(self) -> None:
        self._stop_pollers()
        interval = int(self.cfg["refresh_seconds"])
        for person in self.cfg.people:
            if not person.get("source"):
                continue
            pid = person["id"]
            self.alerts[pid] = AlertEngine(self.cfg)
            poller = Poller(person["source"], dict(person["cfg"]), interval)
            # default arguments bind the id now; without them every callback would close over
            # the last person of the loop
            poller.reading.connect(lambda r, pid=pid: self._on_reading(pid, r))
            poller.error.connect(lambda m, pid=pid: self._on_error(pid, m))
            self.pollers[pid] = poller
            poller.start()

    def _stop_pollers(self) -> None:
        for poller in self.pollers.values():
            poller.stop()
        for poller in self.pollers.values():
            poller.wait(3000)
        self.pollers.clear()
        self.alerts.clear()

    def _forget_stale_people(self) -> None:
        """Drop cached readings for people who are no longer in the config."""
        live = {p["id"] for p in self.cfg.people}
        for d in (self.readings, self.errors):
            for pid in [k for k in d if k not in live]:
                d.pop(pid, None)

    def quit(self) -> None:
        self._stop_pollers()
        self.tray.hide()
        self.app.quit()

    # ------------------------------------------------------------------ people
    def set_active(self, pid: str) -> None:
        if pid == self.cfg.get("active_id"):
            return
        self.cfg.set_active(pid)
        self.cfg.save()
        self._build_menu()
        self._reclassify()

    def add_person(self) -> None:
        if len(self.cfg.people) >= MAX_PEOPLE:
            QMessageBox.information(None, "GlucoPop", tr("person_limit", n=MAX_PEOPLE))
            return
        dlg = PersonDialog(self.cfg)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.cfg.upsert(dlg.person())
        self.cfg.save()
        self._build_menu()
        self._start_pollers()

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        # NOTE: every QAction must be parented to the menu, otherwise Python garbage-collects it
        # and Qt silently drops it from the menu.
        self.menu = QMenu()
        m = self.menu

        def add(text, slot=None, enabled=True, menu=None):
            target = menu or m
            act = QAction(text, target)
            if slot:
                act.triggered.connect(slot)
            act.setEnabled(enabled)
            target.addAction(act)
            return act

        add("GlucoPop · " + tr("credit"), enabled=False)
        m.addSeparator()
        self.act_toggle = add(tr("m_hide"), self.toggle_widget)
        add(tr("m_refresh"), self.refresh_now)

        people = self.cfg.people
        if len(people) > 1:
            sub = m.addMenu(tr("people"))
            self._people_menu = sub                     # keep a reference; Qt does not own it
            active_id = self.cfg.get("active_id")
            for person in people:
                act = add(self.cfg.person_name(person), lambda _=False, pid=person["id"]: self.set_active(pid), menu=sub)
                act.setCheckable(True)
                act.setChecked(person["id"] == active_id)
        add(tr("person_add"), self.add_person, enabled=len(people) < MAX_PEOPLE)

        a = self.cfg.active()
        src_name = sources.SOURCES[a["source"]].name if a and a.get("source") in sources.SOURCES else "…"
        add(tr("m_open", site=src_name), self.open_site)
        m.addSeparator()
        add(tr("m_settings"), self.open_settings)
        add(tr("m_setup"), self.rerun_setup)
        add(tr("m_logout"), self.forget_all)
        m.addSeparator()
        if self.update:
            add("⬆ " + tr("m_update", ver="v" + self.update.version), self.install_update)
        else:
            add(tr("m_check_update"), lambda: self.check_updates(manual=True))
        add(tr("m_about"), self.about)
        add(tr("m_quit"), self.quit)
        self.tray.setContextMenu(m)

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
        for poller in self.pollers.values():
            poller.refresh_now()

    def open_site(self) -> None:
        a = self.cfg.active()
        if not a:
            return
        try:
            src = sources.create(a["source"], dict(a["cfg"]))
            if src.website:
                webbrowser.open(src.website)
        except Exception:
            pass

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            old_lang, old_refresh = self.cfg["language"], self.cfg["refresh_seconds"]
            old_people = [(p["id"], p["source"], tuple(sorted(p["cfg"].items()))) for p in self.cfg.people]
            dlg.people.apply()
            dlg.form.apply()
            self.cfg.save()
            from .config import set_autostart
            set_autostart(bool(self.cfg["autostart"]))
            if self.cfg["language"] != old_lang:
                i18n.set_language(self.cfg["language"])
            self._build_menu()
            if self.widget:
                self.widget.apply_config()
            new_people = [(p["id"], p["source"], tuple(sorted(p["cfg"].items()))) for p in self.cfg.people]
            self._forget_stale_people()
            if self.cfg["refresh_seconds"] != old_refresh or new_people != old_people:
                self._start_pollers()
            else:
                for pid in list(self.alerts):
                    self.alerts[pid] = AlertEngine(self.cfg)
            self._reclassify()

    def rerun_setup(self) -> None:
        """Re-runs the wizard for the active person — the others are untouched."""
        if self.run_wizard(first_run=False):
            a = self.cfg.active()
            if a:
                self.readings.pop(a["id"], None)
            if self.widget:
                self.widget.reading = None
                self.widget.apply_config()
            self._start_pollers()

    def forget_all(self) -> None:
        """Remove every person and every stored credential, then start over."""
        if QMessageBox.question(None, "GlucoPop", tr("forget_all_confirm")) != QMessageBox.StandardButton.Yes:
            return
        self._stop_pollers()
        for person in list(self.cfg.people):
            self.cfg.remove(person["id"])
        self.cfg.update(source="", source_cfg={}, setup_done=False)
        self.cfg.save()
        self.readings.clear(); self.errors.clear()
        if self.widget:
            self.widget.reading = None
            self.widget.set_rows([])
            self.widget.hide()
        if self.run_wizard(first_run=True):
            self._start_widget()
            self._start_pollers()
        else:
            self.quit()

    # ------------------------------------------------------------------ updates
    def check_updates(self, manual: bool = False) -> None:
        if self._upd_thread and self._upd_thread.isRunning():
            return
        self._upd_thread = UpdateCheck()
        self._upd_thread.found.connect(self._on_update_found)
        if manual:
            self._upd_thread.finished.connect(lambda: self._after_manual_check())
        self._upd_thread.start()

    def _after_manual_check(self) -> None:
        if not self.update:
            QMessageBox.information(None, "GlucoPop", tr("upd_none", ver=VERSION))

    def _on_update_found(self, upd: Update) -> None:
        first = self.update is None or self.update.version != upd.version
        self.update = upd
        self._build_menu()
        if first:
            self.tray.showMessage(tr("n_update_title", ver="v" + upd.version), tr("n_update_body", ver="v" + upd.version),
                                  QSystemTrayIcon.MessageIcon.Information, 10000)

    def install_update(self) -> None:
        upd = self.update
        if not upd:
            return
        if not upd.asset_url or sys.platform != "win32" or not getattr(sys, "frozen", False):
            webbrowser.open(upd.url)
            return
        if QMessageBox.question(None, "GlucoPop", tr("upd_confirm", ver="v" + upd.version)) != QMessageBox.StandardButton.Yes:
            return
        self._installer = UpdateInstall(upd)
        self._installer.progress.connect(lambda p: self.tray.setToolTip(tr("upd_downloading", p=p)))
        self._installer.failed.connect(lambda e: QMessageBox.warning(None, "GlucoPop", tr("upd_failed", err=e)))
        self._installer.started_install.connect(self.quit)
        self._installer.start()

    def about(self) -> None:
        QMessageBox.information(None, "GlucoPop", tr("about_text", ver=VERSION, repo=REPO))

    def _on_moved(self, x: int, y: int) -> None:
        self.cfg["pos"] = [x, y]
        self.cfg.save()

    # ------------------------------------------------------------------ data
    def _on_reading(self, pid: str, r: Reading) -> None:
        self.readings[pid] = r
        self.errors.pop(pid, None)
        self._reclassify(notify_for=pid)

    def _on_error(self, pid: str, msg: str) -> None:
        self.errors[pid] = msg
        active = self.cfg.active()
        if active and pid == active["id"]:
            if self.widget:
                self.widget.set_error(msg)
            self.tray.setToolTip(f"GlucoPop – {msg}")
            if pid not in self.readings:
                self.tray.setIcon(make_icon("!", STATE_COLORS["error"]))
        self._update_rows()

    def _state_of(self, pid: str) -> str:
        r = self.readings.get(pid)
        if not r:
            return "error" if pid in self.errors else "connecting"
        engine = self.alerts.get(pid)
        return engine.classify(r) if engine else "ok"

    def _update_rows(self) -> None:
        """Everyone except the active person, in config order."""
        if not self.widget:
            return
        active = self.cfg.active()
        unit = self.cfg["unit"]
        rows = []
        for person in self.cfg.people:
            pid = person["id"]
            if active and pid == active["id"]:
                continue
            r = self.readings.get(pid)
            rows.append({
                "id": pid,
                "name": self.cfg.person_name(person),
                "text": r.value_text(unit) if r else "--",
                "arrow": r.arrow if r else "",
                "state": self._state_of(pid),
            })
        self.widget.set_rows(rows)

    def _reclassify(self, notify_for: str | None = None) -> None:
        active = self.cfg.active()
        if not active:
            return
        unit = self.cfg["unit"]
        many = len(self.cfg.people) > 1

        # the big number
        ar = self.readings.get(active["id"])
        if ar:
            state = self._state_of(active["id"])
            txt = ar.value_text(unit)
            if self.widget:
                self.widget.set_reading(ar, state, self.cfg.person_name(active) if many else "")
            self.tray.setIcon(make_icon(txt if state != "stale" else "…", STATE_COLORS[state]))
            self.tray.setToolTip(f"{txt} {unit} {ar.arrow}  ({age_text(ar.age_seconds)})")
        self._update_rows()

        # alerts: every person is judged on their own, including the ones in the small rows
        for person in self.cfg.people:
            pid = person["id"]
            if notify_for is not None and pid != notify_for:
                continue
            r = self.readings.get(pid)
            engine = self.alerts.get(pid)
            if not r or not engine:
                continue
            state = engine.classify(r)
            should = engine.should_notify(state)
            if should and person.get("alerts", True):
                self._notify(state, r, self.cfg.person_name(person) if many else "")

    def _notify(self, state: str, r: Reading, who: str = "") -> None:
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
        if who:
            title = f"{who} · {title}"
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


def _use_os_trust_store() -> None:
    """Trust the Windows/macOS certificate store, so corporate TLS-inspection proxies work."""
    try:
        import truststore  # type: ignore
        truststore.inject_into_ssl()
    except Exception:
        pass


def main() -> int:
    _use_os_trust_store()
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
