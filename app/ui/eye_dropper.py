"""Interactive Eye Dropper tool for sampling screen coordinates and pixel colors.
Uses direct Win32 GetCursorPos and hardware blit for 100% pixel-accurate
physical sampling across multi-monitor virtual screen setups without lag or crashing.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional, Tuple, List
import numpy as np

from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QCursor,
)
from PyQt6.QtWidgets import QDialog

from app.core.win32_api import get_cursor_pos
from app.ui.assets import get_app_icon

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# Configure 64-bit safe ctypes types to prevent pointer truncation crashes
user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

gdi32.GetPixel.restype = wintypes.COLORREF
gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]

gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.UINT,
]


def get_real_cursor_pos() -> Tuple[int, int]:
    """Get exact hardware cursor coordinate from Windows API."""
    return get_cursor_pos()


def get_pixel_color_at(x: int, y: int) -> Tuple[QColor, str, Tuple[int, int, int]]:
    """Sample exact pixel color from desktop device context at (x, y) safely."""
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


def sample_grid_fast(center_x: int, center_y: int, size: int = 7) -> List[List[QColor]]:
    """Fast sampling of size x size grid around cursor via a single BitBlt rather than 49 GetPixel calls."""
    half = size // 2
    try:
        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            return []

        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, size, size)
        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

        gdi32.BitBlt(
            hdc_mem, 0, 0, size, size,
            hdc_screen, center_x - half, center_y - half,
            0x00CC0020  # SRCCOPY
        )

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = size
        bmi.biHeight = -size  # Top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = (ctypes.c_uint8 * (size * size * 4))()
        gdi32.GetDIBits(hdc_mem, hbmp, 0, size, ctypes.byref(buf), ctypes.byref(bmi), 0)

        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

        arr = np.frombuffer(buf, dtype=np.uint8).reshape((size, size, 4))
        grid = []
        for gy in range(size):
            row = []
            for gx in range(size):
                b = int(arr[gy, gx, 0])
                g = int(arr[gy, gx, 1])
                r = int(arr[gy, gx, 2])
                row.append(QColor(r, g, b))
            grid.append(row)
        return grid
    except Exception:
        return []


class CoordinateEyeDropper(QDialog):
    """Translucent fullscreen overlay providing real-time hardware-accurate pixel sampling."""

    coord_picked = pyqtSignal(int, int, str, tuple)  # (x, y, hex_color, (r, g, b))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowIcon(get_app_icon())
        # Use BlankCursor so our precision crosshair reticle acts as the exact cursor tip
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._is_committed = False

        # Spans the entire virtual desktop across all monitors including secondary and multi-monitor offsets
        vx = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
        vy = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
        vw = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
        vh = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
        if vw <= 0 or vh <= 0:
            vx, vy, vw, vh = 0, 0, 1920, 1080
        self.setGeometry(QRect(vx, vy, vw, vh))

        # Initial sample: cur_x, cur_y is Win32 physical coordinates;
        # local_x, local_y is Qt widget coordinates for crosshair painting.
        self.cur_x, self.cur_y = get_real_cursor_pos()
        loc = self.mapFromGlobal(QCursor.pos())
        self.local_x = loc.x()
        self.local_y = loc.y()

        self.cur_color, self.cur_hex, self.cur_rgb = get_pixel_color_at(self.cur_x, self.cur_y)
        self.grid_colors = sample_grid_fast(self.cur_x, self.cur_y, 7)

        # Update timer for smooth tracking (~33 FPS) without stalling mouse event loop
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(30)
        self.track_timer.timeout.connect(self._update_tracking)
        self.track_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def mouseMoveEvent(self, event):
        # Ultra fast: do NOT query slow GDI functions in mouseMoveEvent!
        # Update local coordinates and repaint instantly for butter-smooth 144Hz movement.
        pos = event.position().toPoint()
        self.local_x = pos.x()
        self.local_y = pos.y()
        self.cur_x, self.cur_y = get_real_cursor_pos()
        self.update()

    def _commit_and_accept(self):
        """Commits the sampled coordinate and color, then closes the dialog."""
        if self._is_committed:
            return
        self._is_committed = True
        self.track_timer.stop()
        x, y = get_real_cursor_pos()
        color, hex_col, rgb = get_pixel_color_at(x, y)
        self.coord_picked.emit(x, y, hex_col, rgb)
        self.accept()

    def _update_tracking(self):
        try:
            # Universal Escape key check: cancels immediately even if focus shifted
            VK_ESCAPE = 0x1B
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self.track_timer.stop()
                self.reject()
                return

            new_x, new_y = get_real_cursor_pos()
            self.cur_x = new_x
            self.cur_y = new_y
            loc = self.mapFromGlobal(QCursor.pos())
            self.local_x = loc.x()
            self.local_y = loc.y()

            self.cur_color, self.cur_hex, self.cur_rgb = get_pixel_color_at(new_x, new_y)
            self.grid_colors = sample_grid_fast(new_x, new_y, 7)
            self.update()
        except Exception:
            pass

    def closeEvent(self, event):
        self.track_timer.stop()
        super().closeEvent(event)

    def reject(self):
        self.track_timer.stop()
        super().reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.track_timer.stop()
            self.reject()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            # Commit on Enter or Space
            self._commit_and_accept()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Commit on Click or Ctrl+Click
            self._commit_and_accept()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right click cancels sampling
            self.track_timer.stop()
            self.reject()

    def paintEvent(self, event):
        painter = QPainter(self)

        # 1. Fill entire window with almost-invisible alpha=1 tint.
        # This prevents Windows layered click-through so clicking commits EVERYWHERE!
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        lx = self.local_x
        ly = self.local_y

        # Crosshair lines point directly through cursor tip (pixel aligned)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        cross_pen = QPen(QColor(56, 189, 248, 200), 1, Qt.PenStyle.DashLine)
        painter.setPen(cross_pen)
        painter.drawLine(0, ly, self.width(), ly)
        painter.drawLine(lx, 0, lx, self.height())

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
            f"X:{self.cur_x}  Y:{self.cur_y}",
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
