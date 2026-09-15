"""Reusable form widgets: dynamic credential form + widget settings form."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from .. import sources
from ..core import error_text
from ..i18n import LANGUAGES, age_text, tr
from ..sources import Field


class TestThread(QThread):
    done = Signal(bool, str, object)

    def __init__(self, source_id: str, cfg: dict):
        super().__init__()
        self.source_id, self.cfg = source_id, cfg

    def run(self) -> None:
        try:
            src = sources.create(self.source_id, self.cfg)
            src.connect()
            r = src.latest()
            self.done.emit(True, "", r)
        except Exception as e:  # noqa: BLE001
            self.done.emit(False, error_text(e), None)


class CredentialForm(QWidget):
    """Builds inputs from a Source's Field list; offers a 'test connection' button."""

    tested = Signal(bool)

    def __init__(self, unit_getter=lambda: "mg/dL", parent=None):
        super().__init__(parent)
        self.unit_getter = unit_getter
        self.source_id = ""
        self.inputs: dict[str, QWidget] = {}
        self.fields: list[Field] = []
        self.ok = False
        self._thread: TestThread | None = None

        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.test_btn = QPushButton(tr("wz_test"))
        self.test_btn.clicked.connect(self.run_test)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row = QHBoxLayout()
        row.addWidget(self.test_btn)
        row.addWidget(self.status, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self.form)
        lay.addSpacing(8)
        lay.addLayout(row)
        lay.addStretch(1)

    # ------------------------------------------------------------------ build
    def set_source(self, source_id: str, values: dict[str, Any] | None = None) -> None:
        self.source_id = source_id
        self.ok = False
        self.status.setText("")
        while self.form.rowCount():
            self.form.removeRow(0)
        self.inputs.clear()
        cls = sources.SOURCES[source_id]
        self.fields = cls.fields
        values = values or {}
        for f in self.fields:
            w: QWidget
            if f.kind == "choice":
                cb = QComboBox()
                for val, key in f.choices:
                    cb.addItem(tr(key), val)
                idx = cb.findData(values.get(f.key, f.default))
                cb.setCurrentIndex(max(0, idx))
                cb.currentIndexChanged.connect(self._invalidate)
                w = cb
            else:
                le = QLineEdit(str(values.get(f.key, f.default) or ""))
                if f.kind == "password":
                    le.setEchoMode(QLineEdit.EchoMode.Password)
                if f.kind == "url":
                    le.setPlaceholderText("https://…")
                le.textChanged.connect(self._invalidate)
                w = le
            if f.help_key:
                w.setToolTip(tr(f.help_key))
            label = tr(f.label_key)
            self.form.addRow(label + ("" if f.required else " ⁽ᵒᵖᵗ⁾"), w)
            if f.help_key:
                h = QLabel(tr(f.help_key))
                h.setWordWrap(True)
                h.setStyleSheet("color: palette(mid); font-size: 11px;")
                self.form.addRow("", h)
            self.inputs[f.key] = w
        # medtrum: show/hide follow_user depending on type
        if source_id == "medtrum":
            self._medtrum_toggle()
            self.inputs["account_type"].currentIndexChanged.connect(self._medtrum_toggle)

    def _medtrum_toggle(self) -> None:
        is_follow = self.inputs["account_type"].currentData() == "follow"
        w = self.inputs["follow_user"]
        w.setVisible(is_follow)
        lbl = self.form.labelForField(w)
        if lbl:
            lbl.setVisible(is_follow)

    def _invalidate(self, *_a) -> None:
        if self.ok:
            self.ok = False
            self.status.setText("")
            self.tested.emit(False)

    # ------------------------------------------------------------------ values
    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in self.fields:
            w = self.inputs[f.key]
            out[f.key] = w.currentData() if isinstance(w, QComboBox) else w.text().strip() if f.kind != "password" else w.text()
        return out

    def missing_required(self) -> list[str]:
        vals = self.values()
        return [tr(f.label_key) for f in self.fields if f.required and not vals.get(f.key)]

    # ------------------------------------------------------------------ test
    def run_test(self) -> None:
        miss = self.missing_required()
        if miss:
            self.status.setText("⚠ " + ", ".join(miss))
            return
        self.test_btn.setEnabled(False)
        self.status.setText(tr("wz_testing"))
        self._thread = TestThread(self.source_id, self.values())
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_done(self, ok: bool, err: str, r) -> None:
        self.test_btn.setEnabled(True)
        self.ok = ok
        if ok:
            unit = self.unit_getter()
            self.status.setText("✅ " + tr("wz_test_ok", value=r.value_text(unit), unit=unit, arrow=r.arrow,
                                          age=age_text(r.age_seconds)))
        else:
            self.status.setText("❌ " + tr("wz_test_fail", err=err))
        self.tested.emit(ok)


class SettingsForm(QWidget):
    """Widget appearance + alert settings."""

    def __init__(self, cfg, show_language=True, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.lang = QComboBox()
        for code, name in LANGUAGES:
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg["language"])))
        if show_language:
            form.addRow(tr("s_language"), self.lang)

        self.unit = QComboBox()
        self.unit.addItems(["mg/dL", "mmol/L"])
        self.unit.setCurrentText(cfg["unit"])
        self.unit.currentTextChanged.connect(self._unit_changed)
        form.addRow(tr("s_unit"), self.unit)

        self.low = QDoubleSpinBox(); self.high = QDoubleSpinBox(); self.urgent = QDoubleSpinBox()
        for sb in (self.low, self.high, self.urgent):
            sb.setRange(1, 600)
        self._set_thresholds(cfg["unit"], cfg["low"], cfg["high"], cfg["urgent_low"])
        form.addRow(tr("s_urgent_low"), self.urgent)
        form.addRow(tr("s_low"), self.low)
        form.addRow(tr("s_high"), self.high)

        self.refresh = QSpinBox(); self.refresh.setRange(20, 600); self.refresh.setSuffix(" " + tr("s_sec"))
        self.refresh.setValue(int(cfg["refresh_seconds"]))
        form.addRow(tr("s_refresh"), self.refresh)

        self.stale = QSpinBox(); self.stale.setRange(6, 120); self.stale.setSuffix(" " + tr("s_min"))
        self.stale.setValue(int(cfg["stale_minutes"]))
        form.addRow(tr("s_stale"), self.stale)

        self.notify = QCheckBox(tr("s_notify")); self.notify.setChecked(bool(cfg["notify"]))
        self.sound = QCheckBox(tr("s_sound")); self.sound.setChecked(bool(cfg["sound"]))
        self.repeat = QSpinBox(); self.repeat.setRange(1, 120); self.repeat.setSuffix(" " + tr("s_min"))
        self.repeat.setValue(int(cfg["repeat_minutes"]))
        form.addRow("", self.notify)
        form.addRow("", self.sound)
        form.addRow(tr("s_repeat"), self.repeat)

        self.size = QComboBox()
        for k, key in (("small", "s_small"), ("medium", "s_medium"), ("large", "s_large")):
            self.size.addItem(tr(key), k)
        self.size.setCurrentIndex(max(0, self.size.findData(cfg["size"])))
        form.addRow(tr("s_size"), self.size)

        self.theme = QComboBox()
        self.theme.addItem(tr("t_dark"), "dark"); self.theme.addItem(tr("t_light"), "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg["theme"])))
        form.addRow(tr("s_theme"), self.theme)

        self.opacity = QSlider(Qt.Orientation.Horizontal); self.opacity.setRange(30, 100)
        self.opacity.setValue(int(float(cfg["opacity"]) * 100))
        form.addRow(tr("s_opacity"), self.opacity)

        self.delta = QCheckBox(tr("s_show_delta")); self.delta.setChecked(bool(cfg["show_delta"]))
        self.ontop = QCheckBox(tr("s_click_through")); self.ontop.setChecked(bool(cfg["always_on_top"]))
        self.autostart = QCheckBox(tr("s_autostart")); self.autostart.setChecked(bool(cfg["autostart"]))
        form.addRow("", self.delta)
        form.addRow("", self.ontop)
        form.addRow("", self.autostart)

    def _set_thresholds(self, unit: str, low, high, urgent) -> None:
        mmol = unit == "mmol/L"
        for sb, v in ((self.low, low), (self.high, high), (self.urgent, urgent)):
            sb.setDecimals(1 if mmol else 0)
            sb.setSingleStep(0.1 if mmol else 1)
            sb.setSuffix(" " + unit)
            sb.setValue(float(v) / 18.0 if mmol else float(v))

    def _unit_changed(self, unit: str) -> None:
        # convert displayed thresholds between units (values are stored in mg/dL)
        prev_mmol = self.low.decimals() == 1
        conv = (lambda v: v * 18.0) if prev_mmol else (lambda v: v)
        self._set_thresholds(unit, conv(self.low.value()), conv(self.high.value()), conv(self.urgent.value()))

    def apply(self) -> None:
        unit = self.unit.currentText()
        k = 18.0 if unit == "mmol/L" else 1.0
        self.cfg.update(
            language=self.lang.currentData(),
            unit=unit,
            low=round(self.low.value() * k, 1),
            high=round(self.high.value() * k, 1),
            urgent_low=round(self.urgent.value() * k, 1),
            refresh_seconds=self.refresh.value(),
            stale_minutes=self.stale.value(),
            notify=self.notify.isChecked(),
            sound=self.sound.isChecked(),
            repeat_minutes=self.repeat.value(),
            size=self.size.currentData(),
            theme=self.theme.currentData(),
            opacity=self.opacity.value() / 100.0,
            show_delta=self.delta.isChecked(),
            always_on_top=self.ontop.isChecked(),
            autostart=self.autostart.isChecked(),
        )
