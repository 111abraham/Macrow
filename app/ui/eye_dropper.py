"""Interactive Eye Dropper tool for sampling screen coordinates and pixel colors.
Uses per-screen native overlays with 1:1 hardware pixel capture to guarantee
100% pixel-accurate sampling across mixed-DPI multi-monitor setups without offset distortion,
color shifting, or mouse clipping.
"""

from __future__ import annotations

import time
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple, List

from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QCursor,
    QGuiApplication,
    QPixmap,
    QImage,
)
from PyQt6.QtWidgets import QDialog, QWidget

from app.core.win32_api import get_cursor_pos
from app.ui.assets import get_app_icon

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


def get_real_cursor_pos() -> Tuple[int, int]:
    """Get exact cursor coordinate from Qt virtual desktop when available, with Win32 fallback."""
    try:
        if QGuiApplication.instance():
            pos = QCursor.pos()
            return int(pos.x()), int(pos.y())
    except Exception:
        pass
    return get_cursor_pos()


def get_pixel_color_at(x: int, y: int) -> Tuple[QColor, str, Tuple[int, int, int]]:
    """Sample exact pixel color from desktop at global (x, y) across all monitors safely."""
    try:
        app = QGuiApplication.instance()
        if app:
            pt = QPoint(int(x), int(y))
            screen = QGuiApplication.screenAt(pt)
            if not screen:
                screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                dpr = screen.devicePixelRatio()
                lx = int(pt.x() - geo.x())
                ly = int(pt.y() - geo.y())
                px = max(0, int(round(lx * dpr)))
                py = max(0, int(round(ly * dpr)))
                pix = screen.grabWindow(0, px, py, 1, 1)
                img = pix.toImage()
                if not img.isNull() and img.width() > 0 and img.height() > 0:
                    c = img.pixelColor(0, 0)
                    hex_code = f"#{c.red():02X}{c.green():02X}{c.blue():02X}"
                    return c, hex_code, (c.red(), c.green(), c.blue())
    except Exception:
        pass

    try:
        hdc = user32.GetDC(None)
        if hdc:
            col = gdi32.GetPixel(hdc, int(x), int(y))
            user32.ReleaseDC(None, hdc)
            if col != 0xFFFFFFFF and col != -1:
                r = col & 0xFF
                g = (col >> 8) & 0xFF
                b = (col >> 16) & 0xFF
                hex_code = f"#{r:02X}{g:02X}{b:02X}"
                return QColor(r, g, b), hex_code, (r, g, b)
    except Exception:
        pass

    return QColor(255, 255, 255), "#FFFFFF", (255, 255, 255)


class EyeDropperScreenOverlay(QWidget):
    """Independent native overlay per screen providing 1:1 hardware pixel sampling and HUD."""

    def __init__(self, screen, controller: CoordinateEyeDropper):
        super().__init__()
        self.screen_obj = screen
        self.controller = controller
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 1:1 unscaled hardware screenshot of this display
        self.pixmap: QPixmap = screen.grabWindow(0)
        self.image: QImage = self.pixmap.toImage()
        self.dpr: float = screen.devicePixelRatio()
        self.screen_geo: QRect = screen.geometry()

        self.has_cursor = False
        self.local_x = 0
        self.local_y = 0
        self.grid_colors: List[List[QColor]] = []
        self.cur_color = QColor(255, 255, 255)
        self.cur_hex = "#FFFFFF"
        self.cur_rgb = (255, 255, 255)
        self.global_x = 0
        self.global_y = 0

    def update_cursor_at(self, global_pt: QPoint):
        """Updates sampling and crosshairs for the given global cursor coordinate."""
        if not self.screen_geo.contains(global_pt):
            if self.has_cursor:
                self.has_cursor = False
                self.update()
            return

        self.has_cursor = True
        self.local_x = global_pt.x() - self.screen_geo.x()
        self.local_y = global_pt.y() - self.screen_geo.y()
        self.global_x = global_pt.x()
        self.global_y = global_pt.y()

        # Map to 1:1 hardware image pixel
        px = int(round(self.local_x * self.dpr))
        py = int(round(self.local_y * self.dpr))
        img_w = self.image.width()
        img_h = self.image.height()

        px = max(0, min(px, img_w - 1))
        py = max(0, min(py, img_h - 1))

        if img_w > 0 and img_h > 0:
            self.cur_color = self.image.pixelColor(px, py)
            self.cur_hex = f"#{self.cur_color.red():02X}{self.cur_color.green():02X}{self.cur_color.blue():02X}"
            self.cur_rgb = (self.cur_color.red(), self.cur_color.green(), self.cur_color.blue())

            # 7x7 grid around cursor
            grid = []
            for gy in range(py - 3, py + 4):
                row = []
                for gx in range(px - 3, px + 4):
                    if 0 <= gx < img_w and 0 <= gy < img_h:
                        row.append(self.image.pixelColor(gx, gy))
                    else:
                        row.append(QColor(0, 0, 0))
                grid.append(row)
            self.grid_colors = grid
        else:
            self.cur_color = QColor(255, 255, 255)
            self.cur_hex = "#FFFFFF"
            self.cur_rgb = (255, 255, 255)
            self.grid_colors = []

        # Sync controller state
        self.controller.cur_x = self.global_x
        self.controller.cur_y = self.global_y
        self.controller.cur_hex = self.cur_hex
        self.controller.cur_rgb = self.cur_rgb
        self.controller.cur_color = self.cur_color

        self.update()

    def mouseMoveEvent(self, event):
        pos = event.globalPosition().toPoint()
        self.controller.on_mouse_moved_global(pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.commit(self.global_x, self.global_y, self.cur_hex, self.cur_rgb)
        elif event.button() == Qt.MouseButton.RightButton:
            self.controller.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.controller.reject()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.controller.commit(self.global_x, self.global_y, self.cur_hex, self.cur_rgb)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)

        # 1. 1:1 unscaled hardware desktop screenshot
        # Renders the exact desktop surface as an opaque canvas so mouse clicks never punch through
        painter.drawPixmap(self.rect(), self.pixmap)

        if not self.has_cursor:
            painter.end()
            return

        lx = self.local_x
        ly = self.local_y

        # Crosshair lines point toward cursor tip with open center (pixel aligned)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        cross_pen = QPen(QColor(56, 189, 248, 200), 1, Qt.PenStyle.DashLine)
        painter.setPen(cross_pen)
        gap = 6
        painter.drawLine(0, ly, max(0, lx - gap), ly)
        painter.drawLine(min(self.width(), lx + gap), ly, self.width(), ly)
        painter.drawLine(lx, 0, lx, max(0, ly - gap))
        painter.drawLine(lx, min(self.height(), ly + gap), lx, self.height())

        # Precision reticle with open center at intersection
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        reticle_pen = QPen(QColor(255, 255, 255, 240), 1.5)
        painter.setPen(reticle_pen)
        painter.drawLine(lx - 8, ly, lx - 2, ly)
        painter.drawLine(lx + 2, ly, lx + 8, ly)
        painter.drawLine(lx, ly - 8, lx, ly - 2)
        painter.drawLine(lx, ly + 2, lx, ly + 8)

        # Magnifier HUD position
        hud_w = 160
        hud_h = 105
        hud_x = lx + 25
        hud_y = ly + 25

        if hud_x + hud_w > self.width():
            hud_x = lx - hud_w - 25
        if hud_y + hud_h > self.height():
            hud_y = ly - hud_h - 25

        hud_rect = QRect(hud_x, hud_y, hud_w, hud_h)

        # HUD box
        painter.setPen(QPen(QColor(56, 189, 248), 1.5))
        painter.setBrush(QBrush(QColor(15, 23, 42, 245)))
        painter.drawRoundedRect(hud_rect, 6, 6)

        # Draw magnified 7x7 pixel grid
        cell_size = 7
        grid_origin_x = hud_x + 8
        grid_origin_y = hud_y + 8

        if self.grid_colors and len(self.grid_colors) == 7:
            for gy in range(7):
                for gx in range(7):
                    c = self.grid_colors[gy][gx]
                    painter.fillRect(
                        grid_origin_x + gx * cell_size,
                        grid_origin_y + gy * cell_size,
                        cell_size,
                        cell_size,
                        c,
                    )
            painter.setPen(QPen(QColor(239, 68, 68), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(
                grid_origin_x + 3 * cell_size,
                grid_origin_y + 3 * cell_size,
                cell_size,
                cell_size,
            )
        else:
            painter.fillRect(grid_origin_x, grid_origin_y, 49, 49, self.cur_color)

        painter.setPen(QPen(QColor(71, 85, 105), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(grid_origin_x, grid_origin_y, 49, 49)

        # Swatch + Hex
        swatch_rect = QRect(hud_x + 66, hud_y + 8, 22, 22)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(QBrush(self.cur_color))
        painter.drawRoundedRect(swatch_rect, 3, 3)

        painter.setPen(QColor(241, 245, 249))
        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.drawText(
            QRect(hud_x + 94, hud_y + 10, 60, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.cur_hex,
        )

        # Coordinates Readout
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(56, 189, 248))
        painter.drawText(
            QRect(hud_x + 66, hud_y + 34, 88, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"X:{self.global_x}  Y:{self.global_y}",
        )

        # RGB readout
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Normal))
        painter.setPen(QColor(148, 163, 184))
        painter.drawText(
            QRect(hud_x + 8, hud_y + 64, hud_w - 16, 16),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"RGB: {self.cur_rgb[0]}, {self.cur_rgb[1]}, {self.cur_rgb[2]}",
        )

        # Instruction
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.DemiBold))
        painter.setPen(QColor(203, 213, 225))
        painter.drawText(
            QRect(hud_x + 8, hud_y + 82, hud_w - 16, 16),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Click or Enter to commit  •  Esc to cancel",
        )

        painter.end()


class CoordinateEyeDropper(QDialog):
    """Multi-monitor interactive Eye Dropper controller managing independent per-screen overlays."""

    coord_picked = pyqtSignal(int, int, str, tuple)  # (x, y, hex_color, (r, g, b))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setGeometry(0, 0, 1, 1)
        self.setWindowIcon(get_app_icon())

        self._is_committed = False
        self._start_time = time.time()
        self.cur_x, self.cur_y = get_real_cursor_pos()
        self.cur_hex = "#FFFFFF"
        self.cur_rgb = (255, 255, 255)
        self.cur_color = QColor(255, 255, 255)

        # Create one independent native canvas overlay per connected screen
        screens = QGuiApplication.screens()
        self.overlays: List[EyeDropperScreenOverlay] = []
        for s in screens:
            try:
                overlay = EyeDropperScreenOverlay(s, self)
                self.overlays.append(overlay)
            except Exception:
                pass

        # Smooth position tracking timer (~40 FPS)
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(25)
        self.track_timer.timeout.connect(self._track_cursor)
        self.track_timer.start()

        # Initial positioning
        self._track_cursor()

    def _track_cursor(self):
        # Universal Escape key check: cancels immediately even if focus shifted
        VK_ESCAPE = 0x1B
        VK_LBUTTON = 0x01
        VK_RBUTTON = 0x02

        try:
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self.reject()
                return

            # OS-level physical click detection (after 150ms startup threshold to prevent false triggers)
            if (time.time() - self._start_time) > 0.150:
                if user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
                    self.commit(self.cur_x, self.cur_y, self.cur_hex, self.cur_rgb)
                    return
                if user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000:
                    self.reject()
                    return
        except Exception:
            pass

        pos = QCursor.pos()
        self.on_mouse_moved_global(pos)

    def on_mouse_moved_global(self, global_pt: QPoint):
        for ov in self.overlays:
            ov.update_cursor_at(global_pt)

    def commit(self, x: int, y: int, hex_col: str, rgb: Tuple[int, int, int]):
        """Commits the sampled coordinate and color, then closes."""
        if self._is_committed:
            return
        self._is_committed = True
        self.track_timer.stop()
        self.cur_x = x
        self.cur_y = y
        self.cur_hex = hex_col
        self.cur_rgb = rgb
        for ov in self.overlays:
            ov.close()
        self.coord_picked.emit(x, y, hex_col, rgb)
        self.accept()

    def exec(self):
        for ov in self.overlays:
            ov.show()
            ov.raise_()
            ov.activateWindow()
            ov.setFocus()
        return super().exec()

    def accept(self):
        self.track_timer.stop()
        for ov in self.overlays:
            ov.close()
        super().accept()

    def reject(self):
        self.track_timer.stop()
        for ov in self.overlays:
            ov.close()
        super().reject()
