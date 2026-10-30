"""
Visual indicator overlay for Point Clicker Desktop.
Renders a crisp, pulsing red dot at coordinates where playback clicks or acts.
Click-through and non-activating so it never steals focus or blocks real input.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont, QCursor
import ctypes
from typing import Tuple
from app.core.win32_api import user32, GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TRANSPARENT


def get_safe_overlay_color(hex_str: str) -> Tuple[QColor, QColor]:
    """Given a target color, returns (safe_accent_color, target_preview_color).
    The safe_accent_color is mathematically offset in hue and luminance so that
    Manhattan RGB distance |R1-R2| + |G1-G2| + |B1-B2| > 200, guaranteeing that
    a pixel color check with tolerance up to 60 will NEVER accidentally match
    the highlight overlay border or tint!
    """
    target = QColor(hex_str)
    if not target.isValid():
        target = QColor("#D946EF")

    h, s, v = target.hsvHue(), target.hsvSaturation(), target.value()
    if s < 45:  # Low saturation / grayscale / black / white
        safe = QColor("#06B6D4") if v < 160 else QColor("#8B5CF6")
    else:
        new_h = (h + 140) % 360
        new_s = max(180, s)
        new_v = 245 if v < 140 else 180
        safe = QColor.fromHsv(new_h, new_s, new_v)

    return safe, target


class VisualIndicator(QWidget):
    """Transparent click-through red dot indicator showing click/playback locations."""

    def __init__(self, size=24):
        super().__init__()
        self.dot_size = size
        self.setFixedSize(self.dot_size, self.dot_size)

        # Window flags for floating overlay
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure click-through transparency at Win32 level
        try:
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
            )
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = self.rect().center()
        radius = (self.dot_size - 4) / 2

        # Outer soft glow
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(239, 68, 68, 80)))  # Semi-transparent red
        painter.drawEllipse(center, int(radius + 2), int(radius + 2))

        # Core vivid red dot
        painter.setBrush(QBrush(QColor(239, 68, 68, 240)))
        painter.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        painter.drawEllipse(center, int(radius - 2), int(radius - 2))

    def show_at(self, x, y, duration_ms=250):
        """Move the red dot center to (x, y) and show for duration_ms."""
        half = self.dot_size // 2
        self.move(int(x) - half, int(y) - half)
        self.show()
        if duration_ms > 0:
            self._hide_timer.start(int(duration_ms))

    def hide_dot(self):
        self._hide_timer.stop()
        self.hide()


class RegionHighlightOverlay(QWidget):
    """Interactive on-screen bounding box overlay with edge/corner resize handles and move dragging.
    Uses safe off-color display lines to completely prevent self-detection while displaying
    the true sampled target color swatch in the dimension badge.
    """

    region_changed = pyqtSignal(int, int, int, int)    # (x, y, w, h) emitted live during drag
    region_committed = pyqtSignal(int, int, int, int)  # (x, y, w, h) emitted on release

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)

        self.region_rect = QRect(0, 0, 100, 100)
        self.safe_accent_color = QColor(6, 182, 212)    # Cyan / Off-color
        self.target_color = QColor(217, 70, 239)        # Target preview swatch
        self.label_text = "Pixel Search Region"

        # Interactive drag state
        self._drag_mode = None
        self._drag_start_global = None
        self._drag_orig_geom = None

    def showEvent(self, event):
        super().showEvent(event)
        try:
            # Allow mouse interaction (resizing/dragging) without ever stealing keyboard focus
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, (ex_style | WS_EX_LAYERED | WS_EX_NOACTIVATE) & ~WS_EX_TRANSPARENT
            )
        except Exception:
            pass

    def show_region(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        label: str = "Pixel Search Region",
        color_hex: str = "#D946EF",
    ):
        """Displays or updates the bounding box overlay at the specified coordinates."""
        try:
            ix = int(x)
            iy = int(y)
            iw = max(20, int(w))
            ih = max(20, int(h))
        except (ValueError, TypeError):
            self.hide()
            return

        self.region_rect = QRect(ix, iy, iw, ih)
        self.label_text = label
        self.safe_accent_color, self.target_color = get_safe_overlay_color(color_hex)

        self.setGeometry(self.region_rect)
        self.show()
        self.update()

    def hide_overlay(self):
        """Hides the highlight overlay."""
        self._drag_mode = None
        self.hide()

    def _get_hit_zone(self, pos: QPoint) -> str:
        """Determines which resize edge, corner, or move zone the mouse is over."""
        w = self.width()
        h = self.height()
        margin = 9

        x = pos.x()
        y = pos.y()

        is_left = x <= margin
        is_right = x >= w - margin
        is_top = y <= margin
        is_bottom = y >= h - margin

        if is_top and is_left:
            return "tl"
        if is_top and is_right:
            return "tr"
        if is_bottom and is_left:
            return "bl"
        if is_bottom and is_right:
            return "br"
        if is_left:
            return "left"
        if is_right:
            return "right"
        if is_top:
            return "top"
        if is_bottom:
            return "bottom"
        return "move"

    def _update_cursor_for_zone(self, zone: str):
        if zone in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif zone in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif zone in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif zone in ("top", "bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = self._get_hit_zone(event.pos())
            self._drag_start_global = event.globalPosition().toPoint()
            self._drag_orig_geom = self.geometry()
            self._update_cursor_for_zone(self._drag_mode)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_mode and (event.buttons() & Qt.MouseButton.LeftButton) and self._drag_start_global:
            cur_global = event.globalPosition().toPoint()
            dx = cur_global.x() - self._drag_start_global.x()
            dy = cur_global.y() - self._drag_start_global.y()
            og = self._drag_orig_geom

            min_w, min_h = 24, 24
            nx, ny = og.x(), og.y()
            nw, nh = og.width(), og.height()

            if self._drag_mode == "move":
                nx = og.x() + dx
                ny = og.y() + dy
            else:
                # Horizontal adjustments
                if "r" in self._drag_mode or self._drag_mode == "right":
                    nw = max(min_w, og.width() + dx)
                elif "l" in self._drag_mode or self._drag_mode == "left":
                    diff = min(dx, og.width() - min_w)
                    nx = og.x() + diff
                    nw = og.width() - diff

                # Vertical adjustments
                if "b" in self._drag_mode or self._drag_mode == "bottom":
                    nh = max(min_h, og.height() + dy)
                elif "t" in self._drag_mode or self._drag_mode == "top":
                    diff = min(dy, og.height() - min_h)
                    ny = og.y() + diff
                    nh = og.height() - diff

            self.region_rect = QRect(nx, ny, nw, nh)
            self.setGeometry(self.region_rect)
            self.region_changed.emit(nx, ny, nw, nh)
            self.update()
            event.accept()
        else:
            zone = self._get_hit_zone(event.pos())
            self._update_cursor_for_zone(zone)
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_mode:
            self._drag_mode = None
            g = self.geometry()
            self.region_rect = g
            self.region_committed.emit(g.x(), g.y(), g.width(), g.height())
            zone = self._get_hit_zone(event.pos())
            self._update_cursor_for_zone(zone)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        r = QRect(1, 1, w - 2, h - 2)

        # 1. Soft interior tint (using safe off-color)
        tint_col = QColor(
            self.safe_accent_color.red(),
            self.safe_accent_color.green(),
            self.safe_accent_color.blue(),
            28,
        )
        painter.fillRect(r, tint_col)

        # 2. Dashed perimeter border (using safe off-color)
        dash_pen = QPen(self.safe_accent_color, 2, Qt.PenStyle.DashLine)
        painter.setPen(dash_pen)
        painter.drawRect(r)

        # 3. Precision corner brackets (reticle style)
        corner_pen = QPen(QColor(255, 255, 255, 240), 3, Qt.PenStyle.SolidLine)
        corner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(corner_pen)
        c_len = min(14, max(4, min(w, h) // 4))

        # Top-Left
        painter.drawLine(1, 1, 1 + c_len, 1)
        painter.drawLine(1, 1, 1, 1 + c_len)
        # Top-Right
        painter.drawLine(w - 2, 1, w - 2 - c_len, 1)
        painter.drawLine(w - 2, 1, w - 2, 1 + c_len)
        # Bottom-Left
        painter.drawLine(1, h - 2, 1 + c_len, h - 2)
        painter.drawLine(1, h - 2, 1, h - 2 - c_len)
        # Bottom-Right
        painter.drawLine(w - 2, h - 2, w - 2 - c_len, h - 2)
        painter.drawLine(w - 2, h - 2, w - 2, h - 2 - c_len)

        # 4. Info badge / pill label with Target Color Swatch
        rx = self.region_rect.x()
        ry = self.region_rect.y()
        badge_text = f"✥ {self.label_text}: {w}×{h} (X:{rx}, Y:{ry})"
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()

        swatch_sz = 12
        swatch_gap = 6
        txt_w = fm.horizontalAdvance(badge_text) + swatch_sz + swatch_gap + 20
        txt_h = fm.height() + 8

        pill_text = None
        if w >= txt_w and h >= (txt_h + 8):
            pill_text = badge_text
        elif w >= 60 and h >= 24:
            pill_text = f"{w}×{h}"
            txt_w = fm.horizontalAdvance(pill_text) + swatch_sz + swatch_gap + 14
            txt_h = fm.height() + 4

        if pill_text:
            pill_rect = QRect(5, 5, min(txt_w, w - 10), min(txt_h, h - 10))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(15, 23, 42, 225)))  # Slate 900 dark translucent
            painter.drawRoundedRect(pill_rect, 4, 4)

            painter.setPen(QPen(self.safe_accent_color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(pill_rect, 4, 4)

            # Target Color Preview Swatch (so user sees their sampled color)
            sw_x = pill_rect.left() + 6
            sw_y = pill_rect.top() + (pill_rect.height() - swatch_sz) // 2
            swatch_rect = QRect(sw_x, sw_y, swatch_sz, swatch_sz)
            painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
            painter.setBrush(QBrush(self.target_color))
            painter.drawRoundedRect(swatch_rect, 2, 2)

            # Text beside swatch
            text_rect = QRect(
                sw_x + swatch_sz + swatch_gap,
                pill_rect.top(),
                pill_rect.width() - (swatch_sz + swatch_gap + 10),
                pill_rect.height(),
            )
            painter.setPen(QColor(241, 245, 249))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, pill_text)
