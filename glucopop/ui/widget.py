"""The always-on-top glucose pop-up.

It shows the active person large, and everyone else as thin rows underneath — the same shape as
the medium widget on the phone. Rows are clickable: tapping one makes that person the big number,
which is faster than going through the tray menu and is the thing you actually want when a
child's value is the one that just went red.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import age_text, tr
from ..sources import Reading

PALETTES = {
    "dark": {"bg": QColor(21, 24, 29, 235), "fg": QColor("#f2f2f2"), "muted": QColor("#8a919c"),
             "border": QColor(255, 255, 255, 18), "rule": QColor(255, 255, 255, 22)},
    "light": {"bg": QColor(252, 252, 253, 240), "fg": QColor("#111318"), "muted": QColor("#6b7280"),
              "border": QColor(0, 0, 0, 25), "rule": QColor(0, 0, 0, 20)},
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
BASE_H = 96
ROW_H = 22


class GlucoseWidget(QWidget):
    moved = Signal(int, int)
    double_clicked = Signal()
    context_menu = Signal(QPoint)
    person_clicked = Signal(str)     # person id of a clicked row

    def __init__(self, cfg):
        super().__init__(None)
        self.cfg = cfg
        self.reading: Reading | None = None
        self.state = "connecting"
        self.message = tr("connecting")
        self.title = ""                 # the active person's name, shown only when there are others
        self.rows: list[dict] = []      # [{id, name, text, arrow, state}]
        self._row_rects: list[tuple[QRectF, str]] = []
        self._drag: QPoint | None = None
        self._moved_while_down = False
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
    def _visible_rows(self) -> list[dict]:
        from ..config import ROWS_SHOWN
        return self.rows[:ROWS_SHOWN] if self.cfg.get("show_others", True) else []

    def apply_config(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.cfg["always_on_top"]:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setWindowOpacity(float(self.cfg["opacity"]))
        s = SIZES.get(self.cfg["size"], 1.0)
        self.scale = s
        self._resize()
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

    def _resize(self) -> None:
        s = getattr(self, "scale", 1.0)
        h = BASE_H + ROW_H * len(self._visible_rows())
        self.setFixedSize(int(232 * s), int(h * s))

    # ------------------------------------------------------------------ data
    def set_reading(self, r: Reading, state: str, title: str = "") -> None:
        self.reading = r
        self.state = state
        self.title = title
        self.message = ""
        if state == "urgent_low":
            if not self._flash_timer.isActive():
                self._flash_timer.start(600)
        else:
            self._flash_timer.stop()
            self._flash = False
        self.update()

    def set_rows(self, rows: list[dict]) -> None:
        grew = len(self._visible_rows())
        self.rows = rows
        if len(self._visible_rows()) != grew:
            self._resize()
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
    def paintEvent(self, _ev) -> None:  # noqa: N802, C901
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        pal = PALETTES.get(self.cfg["theme"], PALETTES["dark"])
        s = self.scale
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 14 * s
        rows = self._visible_rows()
        head_h = BASE_H * s            # the big value lives in the top block; rows follow

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

        # accent bar, alongside the big value only
        bar = QRectF(rect.left() + 12 * s, rect.top() + 14 * s, 5 * s, head_h - 28 * s)
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
            self._row_rects = []
            self._paint_rows(p, rect, pal, rows, head_h)
            return

        r = self.reading
        value = r.value_text(unit)
        vcolor = color if not self._flash else QColor("#ffffff")

        # whose value this is — only worth the pixels when more than one person is followed
        top = rect.top() + (2 * s if self.title else 6 * s)
        if self.title:
            p.setPen(muted)
            p.setFont(QFont("Segoe UI", int(8.5 * s), QFont.Weight.DemiBold))
            p.drawText(QRectF(x0, rect.top() + 6 * s, rect.width() - 90 * s, 14 * s),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(self.title, Qt.TextElideMode.ElideRight, int(rect.width() - 100 * s)))
            top = rect.top() + 14 * s

        # value
        p.setPen(vcolor)
        p.setFont(QFont("Segoe UI", int(30 * s), QFont.Weight.Bold))
        fm = p.fontMetrics()
        vw = fm.horizontalAdvance(value)
        p.drawText(QRectF(x0, top, vw + 4, 46 * s),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
        # arrow
        p.setFont(QFont("Segoe UI Symbol", int(22 * s)))
        p.drawText(QRectF(x0 + vw + 8 * s, top, 40 * s, 46 * s),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, r.arrow)
        # unit + delta (right column)
        p.setPen(muted)
        p.setFont(QFont("Segoe UI", int(9 * s)))
        p.drawText(QRectF(rect.right() - 78 * s, rect.top() + 12 * s, 66 * s, 18 * s),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, unit)
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

        self._paint_rows(p, rect, pal, rows, head_h)

    def _paint_rows(self, p: QPainter, rect: QRectF, pal: dict, rows: list[dict], head_h: float) -> None:
        self._row_rects = []
        if not rows:
            return
        s = self.scale
        muted = pal["muted"] if not self._flash else QColor(255, 255, 255, 200)
        fgc = pal["fg"] if not self._flash else QColor("#ffffff")
        y = rect.top() + head_h - 8 * s
        p.setPen(QPen(pal["rule"], 1))
        p.drawLine(QPoint(int(rect.left() + 12 * s), int(y)), QPoint(int(rect.right() - 12 * s), int(y)))

        for row in rows:
            band = QRectF(rect.left() + 8 * s, y, rect.width() - 16 * s, ROW_H * s)
            self._row_rects.append((band, row["id"]))
            dot = QRectF(rect.left() + 14 * s, y + ROW_H * s / 2 - 3 * s, 6 * s, 6 * s)
            p.setBrush(STATE_COLORS.get(row["state"], STATE_COLORS["error"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(dot)
            p.setPen(muted)
            p.setFont(QFont("Segoe UI", int(9 * s)))
            fm = p.fontMetrics()
            p.drawText(QRectF(rect.left() + 28 * s, y, rect.width() - 110 * s, ROW_H * s),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(row["name"], Qt.TextElideMode.ElideRight, int(rect.width() - 118 * s)))
            p.setPen(fgc)
            p.setFont(QFont("Segoe UI", int(10 * s), QFont.Weight.DemiBold))
            p.drawText(QRectF(rect.right() - 80 * s, y, 68 * s, ROW_H * s),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{row['text']} {row['arrow']}".strip())
            y += ROW_H * s

    # ------------------------------------------------------------------ mouse
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved_while_down = False
        elif e.button() == Qt.MouseButton.RightButton:
            self.context_menu.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self._moved_while_down = True
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag is None:
            return
        self._drag = None
        if self._moved_while_down:
            self.moved.emit(self.x(), self.y())
            return
        # a click that did not drag: if it landed on a row, that person becomes the big number
        pos = e.position()
        for band, pid in self._row_rects:
            if band.contains(pos):
                self.person_clicked.emit(pid)
                return

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            for band, _pid in self._row_rects:
                if band.contains(e.position()):
                    return          # a double click on a row is two switches, not "open the site"
            self.double_clicked.emit()
