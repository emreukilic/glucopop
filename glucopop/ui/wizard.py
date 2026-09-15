"""First-run wizard: language → sensor → sign-in → widget settings → done."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .. import i18n
from ..config import Config
from ..i18n import LANGUAGES, tr
from ..sources import SOURCE_INFO
from .forms import CredentialForm, SettingsForm


class SourceCard(QPushButton):
    def __init__(self, source_id: str, parent=None):
        super().__init__(parent)
        self.source_id = source_id
        info = SOURCE_INFO[source_id]
        self.setCheckable(True)
        self.setMinimumHeight(84)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr(info["desc"]))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        t = QLabel(info["title"]); t.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        s = QLabel(tr(info["sub"])); s.setStyleSheet("color: palette(mid);")
        for w in (t, s):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(t); lay.addWidget(s)
        self.setStyleSheet("""
            QPushButton { text-align:left; border:1px solid palette(mid); border-radius:10px; }
            QPushButton:hover { border-color: palette(highlight); }
            QPushButton:checked { border:2px solid palette(highlight); background: palette(alternate-base); }
        """)


class SetupWizard(QDialog):
    """Returns accepted() when the user finished; config is updated in place (not saved)."""

    finished_ok = Signal()

    def __init__(self, cfg: Config, first_run: bool = True, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.first_run = first_run
        self.setWindowTitle(tr("wz_title"))
        self.setMinimumSize(620, 560)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        self.stack = QStackedWidget()
        self.title = QLabel(); self.title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.subtitle = QLabel(); self.subtitle.setWordWrap(True); self.subtitle.setStyleSheet("color: palette(mid);")

        self.back_btn = QPushButton(); self.next_btn = QPushButton(); self.cancel_btn = QPushButton()
        self.back_btn.clicked.connect(self.go_back)
        self.next_btn.clicked.connect(self.go_next)
        self.cancel_btn.clicked.connect(self.reject)
        self.next_btn.setDefault(True)
        nav = QHBoxLayout()
        nav.addWidget(self.cancel_btn); nav.addStretch(1); nav.addWidget(self.back_btn); nav.addWidget(self.next_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.addWidget(self.title); root.addWidget(self.subtitle); root.addSpacing(10)
        root.addWidget(self.stack, 1); root.addLayout(nav)

        self._build_pages()
        self.stack.setCurrentIndex(0)
        self._refresh_texts()

    # ------------------------------------------------------------------ pages
    def _build_pages(self) -> None:
        # 0 welcome / language
        p0 = QWidget(); l0 = QVBoxLayout(p0)
        self.welcome_text = QLabel(); self.welcome_text.setWordWrap(True)
        self.lang_combo = QComboBox()
        for code, name in LANGUAGES:
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(self.cfg["language"])))
        self.lang_combo.currentIndexChanged.connect(self._lang_changed)
        self.lang_label = QLabel()
        row = QHBoxLayout(); row.addWidget(self.lang_label); row.addWidget(self.lang_combo); row.addStretch(1)
        l0.addWidget(self.welcome_text); l0.addSpacing(16); l0.addLayout(row); l0.addStretch(1)
        self.stack.addWidget(p0)

        # 1 source picker
        p1 = QWidget(); g = QGridLayout(p1); g.setSpacing(12)
        self.cards = QButtonGroup(self); self.cards.setExclusive(True)
        for i, sid in enumerate(SOURCE_INFO):
            c = SourceCard(sid)
            self.cards.addButton(c)
            g.addWidget(c, i // 2, i % 2)
            if sid == self.cfg.get("source"):
                c.setChecked(True)
        g.setRowStretch(3, 1)
        self.cards.buttonClicked.connect(lambda *_: self._refresh_nav())
        self.stack.addWidget(p1)

        # 2 credentials
        self.cred = CredentialForm(unit_getter=lambda: self.cfg["unit"])
        self.cred.tested.connect(lambda *_: self._refresh_nav())
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QScrollArea.Shape.NoFrame); sc.setWidget(self.cred)
        self.stack.addWidget(sc)

        # 3 settings
        self.settings = SettingsForm(self.cfg, show_language=False)
        sc2 = QScrollArea(); sc2.setWidgetResizable(True); sc2.setFrameShape(QScrollArea.Shape.NoFrame); sc2.setWidget(self.settings)
        self.stack.addWidget(sc2)

        # 4 done
        p4 = QWidget(); l4 = QVBoxLayout(p4)
        self.done_text = QLabel(); self.done_text.setWordWrap(True)
        l4.addWidget(self.done_text); l4.addStretch(1)
        self.stack.addWidget(p4)

    def _lang_changed(self) -> None:
        code = self.lang_combo.currentData()
        self.cfg["language"] = code
        i18n.set_language(code)
        self._refresh_texts()
        # rebuild translated pages
        cur_src = self.selected_source()
        if cur_src:
            self.cred.set_source(cur_src, self.cred.values() if self.cred.source_id == cur_src else self.cfg.get("source_cfg"))
        for b in self.cards.buttons():
            info = SOURCE_INFO[b.source_id]
            b.setToolTip(tr(info["desc"]))
            b.findChildren(QLabel)[1].setText(tr(info["sub"]))
        # settings form: rebuild
        self.settings = SettingsForm(self.cfg, show_language=False)
        self.stack.widget(3).setWidget(self.settings)  # QScrollArea deletes the previous form

    def _refresh_texts(self) -> None:
        self.setWindowTitle(tr("wz_title"))
        self.welcome_text.setText(tr("wz_welcome_text"))
        self.lang_label.setText(tr("wz_language") + ":")
        self.done_text.setText(tr("wz_done_text"))
        self.back_btn.setText(tr("back")); self.cancel_btn.setText(tr("cancel"))
        self.cred.test_btn.setText(tr("wz_test"))
        self._refresh_nav()

    def selected_source(self) -> str:
        b = self.cards.checkedButton()
        return b.source_id if b else ""

    # ------------------------------------------------------------------ nav
    def _refresh_nav(self) -> None:
        i = self.stack.currentIndex()
        titles = [("wz_welcome", "tagline"), ("wz_source", "wz_source_sub"), ("wz_login", "wz_login_sub"),
                  ("wz_settings", "wz_settings_sub"), ("wz_done", "")]
        t, s = titles[i]
        self.title.setText(tr(t)); self.subtitle.setText(tr(s) if s else "")
        self.back_btn.setVisible(i > 0)
        self.next_btn.setText(tr("finish") if i == 4 else tr("next"))
        ok = True
        if i == 1:
            ok = bool(self.selected_source())
        elif i == 2:
            ok = self.cred.ok
            if not ok:
                self.subtitle.setText(tr("wz_login_sub") + "  —  " + tr("wz_need_test"))
        self.next_btn.setEnabled(ok)

    def go_back(self) -> None:
        i = self.stack.currentIndex()
        if i > 0:
            self.stack.setCurrentIndex(i - 1)
            self._refresh_nav()

    def go_next(self) -> None:
        i = self.stack.currentIndex()
        if i == 1:
            sid = self.selected_source()
            prev = self.cfg.get("source_cfg") if self.cfg.get("source") == sid else {}
            if self.cred.source_id != sid:
                self.cred.set_source(sid, prev)
        elif i == 2:
            self.cfg["source"] = self.cred.source_id
            self.cfg["source_cfg"] = self.cred.values()
        elif i == 3:
            self.settings.apply()
        if i == 4:
            self.cfg["setup_done"] = True
            self.accept()
            return
        self.stack.setCurrentIndex(i + 1)
        self._refresh_nav()
