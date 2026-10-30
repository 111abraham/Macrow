"""
Visual indicator overlay for Point Clicker Desktop.
Renders a crisp, pulsing red dot at coordinates where playback clicks or acts.
Click-through and non-activating so it never steals focus or blocks real input.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QFont
import ctypes
from app.core.win32_api import user32, GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_NOACTIVATE


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
    """Transparent click-through bounding box overlay highlighting search regions on screen.
    Features vibrant dashed borders, corner reticles, translucent tint, and dimension pill badge.
    """

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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.region_rect = QRect(0, 0, 100, 100)
        self.accent_color = QColor(217, 70, 239)  # Fuchsia/Magenta (#D946EF)
        self.label_text = "Pixel Search Region"

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
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
            iw = max(8, int(w))
            ih = max(8, int(h))
        except (ValueError, TypeError):
            self.hide()
            return

        self.region_rect = QRect(ix, iy, iw, ih)
        self.label_text = label
        try:
            self.accent_color = QColor(color_hex)
            if not self.accent_color.isValid():
                self.accent_color = QColor(217, 70, 239)
        except Exception:
            self.accent_color = QColor(217, 70, 239)

        self.setGeometry(self.region_rect)
        self.show()
        self.update()

    def hide_overlay(self):
        """Hides the highlight overlay."""
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        r = QRect(1, 1, w - 2, h - 2)

        # 1. Soft interior tint
        tint_col = QColor(
            self.accent_color.red(),
            self.accent_color.green(),
            self.accent_color.blue(),
            30,
        )
        painter.fillRect(r, tint_col)

        # 2. Dashed perimeter border
        dash_pen = QPen(self.accent_color, 2, Qt.PenStyle.DashLine)
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

        # 4. Info badge / pill label
        rx = self.region_rect.x()
        ry = self.region_rect.y()
        badge_text = f"🎨 {self.label_text}: {w}×{h} (X:{rx}, Y:{ry})"
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        txt_w = fm.horizontalAdvance(badge_text) + 16
        txt_h = fm.height() + 6

        pill_text = None
        if w >= txt_w and h >= (txt_h + 8):
            pill_text = badge_text
        elif w >= 50 and h >= 22:
            pill_text = f"{w}×{h}"
            txt_w = fm.horizontalAdvance(pill_text) + 10
            txt_h = fm.height() + 4

        if pill_text:
            pill_rect = QRect(4, 4, min(txt_w, w - 8), min(txt_h, h - 8))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(15, 23, 42, 220)))  # Slate 900 dark translucent
            painter.drawRoundedRect(pill_rect, 4, 4)

            painter.setPen(QPen(self.accent_color, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(pill_rect, 4, 4)

            painter.setPen(QColor(241, 245, 249))
            painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, pill_text)
