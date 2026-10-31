"""Interactive screen snipper tool for capturing template images.
Allows the user to drag a rectangle on their screen to snip any icon, button, or UI region.
Uses independent per-screen overlay windows to guarantee 1:1 hardware pixel capture
across mixed-DPI multi-monitor setups without shrinking, offset distortion, or black borders.
"""

from __future__ import annotations

import os
import time
import ctypes
from ctypes import wintypes
from datetime import datetime
from typing import Optional, List

from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QImage,
    QPixmap,
    QFont,
    QCursor,
    QGuiApplication,
)
from PyQt6.QtWidgets import QDialog, QWidget

from app.ui.assets import get_app_icon
from app.core.win32_api import user32, get_screen_physical_rect, get_cursor_pos, init_dpi_awareness


class SnipperCanvasOverlay(QWidget):
    """Fullscreen overlay for a single screen showing its 1:1 unscaled hardware screenshot."""

    def __init__(self, screen, controller: ScreenSnipper):
        super().__init__()
        init_dpi_awareness()
        self.screen_obj = screen
        self.controller = controller
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setScreen(screen)

        # 1:1 physical screen rectangle across multi-monitor desktop
        self.phys_rect = get_screen_physical_rect(screen)
        px, py, pw, ph = self.phys_rect
        self.setGeometry(px, py, pw, ph)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 1:1 native hardware screen capture
        self.pixmap = screen.grabWindow(0)
        self.image = self.pixmap.toImage()
        self.dpr = screen.devicePixelRatio()
        self.screen_geo = screen.geometry()

        self.start_pos: Optional[QPoint] = None
        self.is_selecting = False

        # Pre-seed current_pos from actual physical cursor position
        cur_px, cur_py = get_cursor_pos()
        if px <= cur_px < px + pw and py <= cur_py < py + ph:
            self.current_pos: Optional[QPoint] = QPoint(cur_px - px, cur_py - py)
        else:
            self.current_pos = None

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
        try:
            hwnd = int(self.winId())
            px, py, pw, ph = self.phys_rect
            # SWP_NOZORDER = 0x0004, SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(hwnd, 0, px, py, pw, ph, 0x0004 | 0x0040)
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def update_cursor_at(self, phys_gx, phys_gy=None):
        """Update crosshair and selection rect from physical cursor position (called by timer)."""
        if phys_gy is None:
            if hasattr(phys_gx, "x") and hasattr(phys_gx, "y"):
                phys_gy = int(phys_gx.y())
                phys_gx = int(phys_gx.x())
            elif isinstance(phys_gx, (tuple, list)):
                phys_gx, phys_gy = int(phys_gx[0]), int(phys_gx[1])
            else:
                return

        px, py, pw, ph = self.phys_rect
        in_screen = (px <= phys_gx < px + pw and py <= phys_gy < py + ph)
        if in_screen or self.is_selecting:
            local_pt = QPoint(phys_gx - px, phys_gy - py)
            if self.current_pos != local_pt:
                self.current_pos = local_pt
                self.update()
        elif self.current_pos is not None:
            self.current_pos = None
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.controller.reject()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.controller.set_active_overlay(self)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.controller.reject()

    def mouseMoveEvent(self, event):
        self.current_pos = event.pos()
        self.controller.on_mouse_move_on_overlay(self)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.finish_selection(event.pos())

    def finish_selection(self, end_pos: Optional[QPoint] = None):
        if not self.is_selecting:
            return
        self.is_selecting = False
        if end_pos is not None:
            self.current_pos = end_pos
        sel_rect = self._get_selected_rect()

        if sel_rect.width() >= 5 and sel_rect.height() >= 5:
            # 1. Native 1:1 hardware pixel crop
            nx = max(0, min(sel_rect.x(), self.image.width() - 1))
            ny = max(0, min(sel_rect.y(), self.image.height() - 1))
            nw = min(sel_rect.width(), self.image.width() - nx)
            nh = min(sel_rect.height(), self.image.height() - ny)
            cropped = self.image.copy(nx, ny, nw, nh)

            # 2. Sample target color at center of bounding box
            c_px = nx + nw // 2
            c_py = ny + nh // 2
            c_px = max(0, min(c_px, self.image.width() - 1))
            c_py = max(0, min(c_py, self.image.height() - 1))
            c_col = self.image.pixelColor(c_px, c_py)
            self.controller.last_sampled_color = c_col.name().upper()

            # 3. Global desktop physical coordinates (aligned with Win32 virtual desktop)
            px, py, _, _ = self.phys_rect
            gx = px + nx
            gy = py + ny
            gw = nw
            gh = nh

            # 4. Save snippet image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"snippet_{timestamp}.png"
            filepath = os.path.join(self.controller.save_dir, filename)
            cropped.save(filepath, "PNG")

            self.controller.snippet_captured.emit(cropped, filepath)
            self.controller.region_captured.emit(gx, gy, gw, gh)
            self.controller.accept()
        else:
            self.start_pos = None
            self.update()

    def _get_selected_rect(self) -> QRect:
        if not self.start_pos or not self.current_pos:
            return QRect()
        x1 = min(self.start_pos.x(), self.current_pos.x())
        y1 = min(self.start_pos.y(), self.current_pos.y())
        x2 = max(self.start_pos.x(), self.current_pos.x())
        y2 = max(self.start_pos.y(), self.current_pos.y())
        return QRect(x1, y1, x2 - x1, y2 - y1)

    def paintEvent(self, event):
        painter = QPainter(self)

        # 1. 1:1 hardware screenshot
        painter.drawPixmap(self.rect(), self.pixmap)

        # 2. Dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        # 3. Selection box
        if self.is_selecting and self.start_pos and self.current_pos:
            sel_rect = self._get_selected_rect()
            if not sel_rect.isEmpty():
                # Reveal selection without dark overlay (1:1 physical source rect)
                painter.drawPixmap(sel_rect, self.pixmap, sel_rect)

                # Bright border
                pen = QPen(QColor(56, 189, 248), 2, Qt.PenStyle.SolidLine)
                painter.setPen(pen)
                painter.drawRect(sel_rect)

                # Dimension badge
                w, h = sel_rect.width(), sel_rect.height()
                badge_text = f" {w} × {h} px "
                painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                fm = painter.fontMetrics()
                bw = fm.horizontalAdvance(badge_text) + 8
                bh = fm.height() + 4
                bx = sel_rect.left()
                by = sel_rect.top() - bh - 6
                if by < 10:
                    by = sel_rect.bottom() + 6
                badge_rect = QRect(bx, by, bw, bh)
                painter.fillRect(badge_rect, QColor(15, 23, 42, 220))
                painter.setPen(QPen(QColor(56, 189, 248), 1))
                painter.drawRect(badge_rect)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        else:
            # Help banner
            help_text = "Drag to snip a screen element  •  Esc or Right-click to cancel"
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(help_text) + 24
            th = fm.height() + 12
            hx = (self.width() - tw) // 2
            hy = 40
            banner_rect = QRect(hx, hy, tw, th)
            painter.fillRect(banner_rect, QColor(15, 23, 42, 220))
            painter.setPen(QPen(QColor(56, 189, 248), 1))
            painter.drawRect(banner_rect)
            painter.setPen(QColor(241, 245, 249))
            painter.drawText(banner_rect, Qt.AlignmentFlag.AlignCenter, help_text)

        # 4. Precision crosshairs
        if self.current_pos:
            cx = self.current_pos.x()
            cy = self.current_pos.y()
            cross_pen = QPen(QColor(56, 189, 248, 190), 1, Qt.PenStyle.DashLine)
            painter.setPen(cross_pen)
            painter.drawLine(0, cy, self.width(), cy)
            painter.drawLine(cx, 0, cx, self.height())

            reticle_pen = QPen(QColor(255, 255, 255, 240), 1.5)
            painter.setPen(reticle_pen)
            painter.drawLine(cx - 7, cy, cx - 2, cy)
            painter.drawLine(cx + 2, cy, cx + 7, cy)
            painter.drawLine(cx, cy - 7, cx, cy - 2)
            painter.drawLine(cx, cy + 2, cx, cy + 7)


class ScreenSnipper(QDialog):
    """Multi-monitor screen snipper controller managing per-screen overlays."""

    snippet_captured = pyqtSignal(QImage, str)  # (cropped_qimage, saved_filepath)
    region_captured = pyqtSignal(int, int, int, int)  # (global_x, global_y, width, height)

    def __init__(self, parent=None, save_dir: Optional[str] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(0, 0, 1, 1)
        self.setWindowIcon(get_app_icon())

        self.save_dir = save_dir or os.path.join(os.getcwd(), "snippets")
        os.makedirs(self.save_dir, exist_ok=True)

        self.last_sampled_color: Optional[str] = None
        self.active_overlay: Optional[SnipperCanvasOverlay] = None
        self._start_time = time.time()
        self._drag_active_via_os = False

        # Create one independent native canvas per connected screen
        screens = QGuiApplication.screens()
        self.overlays: List[SnipperCanvasOverlay] = []
        for s in screens:
            try:
                overlay = SnipperCanvasOverlay(s, self)
                self.overlays.append(overlay)
            except Exception:
                pass

        # Compatibility attributes for inspector callers
        if self.overlays:
            self.full_screenshot = self.overlays[0].image
            self.vx = self.overlays[0].screen_geo.x()
            self.vy = self.overlays[0].screen_geo.y()
        else:
            self.full_screenshot = QImage()
            self.vx = 0
            self.vy = 0

        # Background watchdog timer (~40 FPS) for OS-level hotkeys and cursor tracking
        self.track_timer = QTimer(self)
        self.track_timer.setInterval(25)
        self.track_timer.timeout.connect(self._track_cursor)
        self.track_timer.start()

    def _track_cursor(self):
        VK_ESCAPE = 0x1B
        VK_RBUTTON = 0x02
        VK_LBUTTON = 0x01

        try:
            # 1. Universal Escape check: cancels immediately under all conditions
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                self.reject()
                return

            # 2. Universal Right-click check: cancels immediately
            if user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000:
                self.reject()
                return

            # 3. Global cursor tracking: ensures crosshair tracks everywhere across monitors
            cur_px, cur_py = get_cursor_pos()
            for ov in self.overlays:
                ov.update_cursor_at(cur_px, cur_py)

            # 4. OS-level physical drag tracking (guards against swallowed/blocked Qt mouse events)
            if (time.time() - self._start_time) > 0.120:
                l_down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
                any_qt_selecting = any(ov.is_selecting for ov in self.overlays)

                if l_down and not any_qt_selecting and not self._drag_active_via_os:
                    for ov in self.overlays:
                        px, py, pw, ph = ov.phys_rect
                        if px <= cur_px < px + pw and py <= cur_py < py + ph:
                            self._drag_active_via_os = True
                            self.active_overlay = ov
                            ov.start_pos = QPoint(cur_px - px, cur_py - py)
                            ov.current_pos = ov.start_pos
                            ov.is_selecting = True
                            ov.update()
                            break
                elif not l_down and (any_qt_selecting or self._drag_active_via_os):
                    self._drag_active_via_os = False
                    for ov in self.overlays:
                        if ov.is_selecting:
                            px, py, _, _ = ov.phys_rect
                            ov.finish_selection(QPoint(cur_px - px, cur_py - py))
                            break
        except Exception:
            pass

    def set_active_overlay(self, active_overlay: SnipperCanvasOverlay):
        self.active_overlay = active_overlay
        for ov in self.overlays:
            if ov is not active_overlay and ov.is_selecting:
                ov.is_selecting = False
                ov.update()

    def on_mouse_move_on_overlay(self, active_overlay: SnipperCanvasOverlay):
        for ov in self.overlays:
            if ov is not active_overlay and ov.current_pos is not None:
                ov.current_pos = None
                ov.update()

    def exec(self):
        for ov in self.overlays:
            ov.show()
        # Find overlay under cursor and raise/activate it
        cur_px, cur_py = get_cursor_pos()
        target = None
        for ov in self.overlays:
            px, py, pw, ph = ov.phys_rect
            if px <= cur_px < px + pw and py <= cur_py < py + ph:
                target = ov
                break
        if not target and self.overlays:
            target = self.overlays[0]
        if target:
            target.raise_()
            target.activateWindow()
            try:
                user32.SetForegroundWindow(int(target.winId()))
            except Exception:
                pass
        return super().exec()

    def closeEvent(self, event):
        if hasattr(self, "track_timer"):
            self.track_timer.stop()
        for ov in self.overlays:
            ov.close()
        super().closeEvent(event)

    def accept(self):
        if hasattr(self, "track_timer"):
            self.track_timer.stop()
        for ov in self.overlays:
            ov.close()
        super().accept()

    def reject(self):
        if hasattr(self, "track_timer"):
            self.track_timer.stop()
        for ov in self.overlays:
            ov.close()
        super().reject()
