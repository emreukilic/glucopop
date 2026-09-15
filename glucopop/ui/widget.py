"""The always-on-top glucose pop-up."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import age_text, tr
from ..sources import Reading

PALETTES = {
    "dark": {"bg": QColor(21, 24, 29, 235), "fg": QColor("#f2f2f2"), "muted": QColor("#8a919c"),
             "border": QColor(255, 255, 255, 18)},
    "light": {"bg": QColor(252, 252, 253, 240), "fg": QColor("#111318"), "muted": QColor("#6b7280"),
              "border": QColor(0, 0, 0, 25)},
}
STATE_COLORS = {
    "ok": QColor("#3ec26b"),
    "high": QColor("#f0a92a"),
    "low": QColor("#e5484d"),
    "urgent_low": QColor("#c1121f"),
    "stale": QColor("#6b7280"),
    "error": QColor("#9ca3af"),
    "connecting": QColor("#6b7280"),
}
SIZES = {"small": 0.8, "medium": 1.0, "large": 1.35}


class GlucoseWidget(QWidget):
    moved = Signal(int, int)
    double_clicked = Signal()
    context_menu = Signal(QPoint)

    def __init__(self, cfg):
        super().__init__(None)
        self.cfg = cfg
        self.reading: Reading | None = None
        self.state = "connecting"
        self.message = tr("connecting")
        self._drag: QPoint | None = None
        self._flash = False
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._toggle_flash)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self.update)
        self._tick.start(10_000)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.apply_config()

    # ------------------------------------------------------------------ config
    def apply_config(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.cfg["always_on_top"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setWindowOpacity(float(self.cfg["opacity"]))
        s = SIZES.get(self.cfg["size"], 1.0)
        self.scale = s
        self.setFixedSize(int(232 * s), int(96 * s))
        pos = self.cfg.get("pos")
        screen = self.screen().availableGeometry() if self.screen() else None
        if pos and screen:
            x = min(max(screen.left(), pos[0]), screen.right() - self.width())
            y = min(max(screen.top(), pos[1]), screen.bottom() - self.height())
            self.move(x, y)
        elif screen:
            self.move(screen.right() - self.width() - 24, screen.top() + 24)
        if visible:
            self.show()
        self.update()

    # ------------------------------------------------------------------ data
    def set_reading(self, r: Reading, state: str) -> None:
        self.reading = r
        self.state = state
        self.message = ""
        if state == "urgent_low":
            if not self._flash_timer.isActive():
                self._flash_timer.start(600)
        else:
            self._flash_timer.stop()
            self._flash = False
        self.update()

    def set_error(self, msg: str) -> None:
        self.message = msg
        if self.reading is None:
            self.state = "error"
        self.update()

    def _toggle_flash(self) -> None:
        self._flash = not self._flash
        self.update()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        pal = PALETTES.get(self.cfg["theme"], PALETTES["dark"])
        s = self.scale
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 14 * s

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        bg = QColor(pal["bg"])
        color = STATE_COLORS.get(self.state, STATE_COLORS["error"])
        if self._flash:
            bg = QColor(color)
            bg.setAlpha(230)
        p.fillPath(path, bg)
        p.setPen(QPen(pal["border"], 1))
        p.drawPath(path)

        # accent bar
        bar = QRectF(rect.left() + 12 * s, rect.top() + 14 * s, 5 * s, rect.height() - 28 * s)
        bp = QPainterPath()
        bp.addRoundedRect(bar, 2.5 * s, 2.5 * s)
        p.fillPath(bp, color)

        x0 = rect.left() + 28 * s
        fg = pal["fg"] if not self._flash else QColor("#ffffff")
        muted = pal["muted"] if not self._flash else QColor(255, 255, 255, 200)
        unit = self.cfg["unit"]

        if self.reading is None:
            p.setPen(fg)
            p.setFont(QFont("Segoe UI", int(26 * s), QFont.Weight.Bold))
            p.drawText(QRectF(x0, rect.top() + 8 * s, rect.width(), 46 * s),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "--")
            p.setPen(muted)
            p.setFont(QFont("Segoe UI", int(9 * s)))
            p.drawText(QRectF(x0, rect.top() + 58 * s, rect.width() - 40 * s, 24 * s),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(self.message or tr("connecting"), Qt.TextElideMode.ElideRight,
                                                  int(rect.width() - 50 * s)))
            return

        r = self.reading
        value = r.value_text(unit)
        vcolor = color if not self._flash else QColor("#ffffff")

        # value
        p.setPen(vcolor)
        f_val = QFont("Segoe UI", int(30 * s), QFont.Weight.Bold)
        p.setFont(f_val)
        fm = p.fontMetrics()
        vw = fm.horizontalAdvance(value)
        p.drawText(QRectF(x0, rect.top() + 6 * s, vw + 4, 50 * s),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
        # arrow
        p.setFont(QFont("Segoe UI Symbol", int(22 * s)))
        ax = x0 + vw + 8 * s
        p.drawText(QRectF(ax, rect.top() + 6 * s, 40 * s, 50 * s),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, r.arrow)
        # unit + delta (right column)
        p.setPen(muted)
        p.setFont(QFont("Segoe UI", int(9 * s)))
        right = QRectF(rect.right() - 78 * s, rect.top() + 12 * s, 66 * s, 18 * s)
        p.drawText(right, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, unit)
        delta = r.extra.get("delta")
        if self.cfg["show_delta"] and delta is not None:
            d = delta if unit == "mg/dL" else delta / 18.0
            txt = (f"{d:+.0f}" if unit == "mg/dL" else f"{d:+.1f}")
            p.setFont(QFont("Segoe UI", int(10 * s), QFont.Weight.DemiBold))
            p.drawText(QRectF(rect.right() - 78 * s, rect.top() + 32 * s, 66 * s, 20 * s),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, txt)

        # footer: age + status/message
        foot = age_text(r.age_seconds)
        if self.state == "stale":
            foot += "  ·  " + tr("stale")
        if self.message:
            foot += "  ·  " + self.message
        p.setPen(muted)
        p.setFont(QFont("Segoe UI", int(9 * s)))
        fm = p.fontMetrics()
        p.drawText(QRectF(x0, rect.top() + 60 * s, rect.width() - 40 * s, 22 * s),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(foot, Qt.TextElideMode.ElideRight, int(rect.width() - 44 * s)))

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_menu.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self.moved.emit(self.x(), self.y())

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
