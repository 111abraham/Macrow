"""
Visual indicator overlay for Point Clicker Desktop.
Renders a crisp, pulsing red dot at coordinates where playback clicks or acts.
Click-through and non-activating so it never steals focus or blocks real input.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen
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
        hwnd = int(self.winId())
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
        )

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
