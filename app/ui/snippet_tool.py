"""Interactive screen snipper tool for capturing template images.
Allows the user to drag a rectangle on their screen to snip any icon, button, or UI region.
Uses independent per-screen overlay windows to guarantee 1:1 hardware pixel capture
across mixed-DPI multi-monitor setups without shrinking, offset distortion, or black borders.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, List

from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
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


class SnipperCanvasOverlay(QWidget):
    """Fullscreen overlay for a single screen showing its 1:1 unscaled hardware screenshot."""

    def __init__(self, screen, controller: ScreenSnipper):
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
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # 1:1 native hardware screen capture
        self.pixmap = screen.grabWindow(0)
        self.image = self.pixmap.toImage()
        self.dpr = screen.devicePixelRatio()
        self.screen_geo = screen.geometry()

        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_selecting = False

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
            self.is_selecting = False
            self.current_pos = event.pos()
            sel_rect = self._get_selected_rect()

            if sel_rect.width() >= 5 and sel_rect.height() >= 5:
                # 1. Native 1:1 hardware pixel crop
                nx = int(round(sel_rect.x() * self.dpr))
                ny = int(round(sel_rect.y() * self.dpr))
                nw = max(1, int(round(sel_rect.width() * self.dpr)))
                nh = max(1, int(round(sel_rect.height() * self.dpr)))
                cropped = self.image.copy(nx, ny, nw, nh)

                # 2. Sample target color at center of bounding box
                c_px = int(round((sel_rect.x() + sel_rect.width() // 2) * self.dpr))
                c_py = int(round((sel_rect.y() + sel_rect.height() // 2) * self.dpr))
                c_px = max(0, min(c_px, self.image.width() - 1))
                c_py = max(0, min(c_py, self.image.height() - 1))
                c_col = self.image.pixelColor(c_px, c_py)
                self.controller.last_sampled_color = c_col.name().upper()

                # 3. Global desktop coordinates (aligned with Qt virtual desktop)
                gx = self.screen_geo.x() + sel_rect.x()
                gy = self.screen_geo.y() + sel_rect.y()
                gw = sel_rect.width()
                gh = sel_rect.height()

                # 4. Save snippet image
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"snippet_{timestamp}.png"
                filepath = os.path.join(self.controller.save_dir, filename)
                cropped.save(filepath, "PNG")

                self.controller.snippet_captured.emit(cropped, filepath)
                self.controller.region_captured.emit(gx, gy, gw, gh)
                self.controller.accept()
            else:
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. 1:1 hardware screenshot
        painter.drawPixmap(self.rect(), self.pixmap)

        # 2. Dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        # 3. Selection box
        if self.is_selecting and self.start_pos and self.current_pos:
            sel_rect = self._get_selected_rect()
            if not sel_rect.isEmpty():
                # Reveal selection without dark overlay
                src_rect = QRect(
                    int(round(sel_rect.x() * self.dpr)),
                    int(round(sel_rect.y() * self.dpr)),
                    int(round(sel_rect.width() * self.dpr)),
                    int(round(sel_rect.height() * self.dpr)),
                )
                painter.drawPixmap(sel_rect, self.pixmap, src_rect)

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
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setGeometry(0, 0, 1, 1)
        self.setWindowIcon(get_app_icon())

        self.save_dir = save_dir or os.path.join(os.getcwd(), "snippets")
        os.makedirs(self.save_dir, exist_ok=True)

        self.last_sampled_color: Optional[str] = None
        self.active_overlay: Optional[SnipperCanvasOverlay] = None

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
        return super().exec()

    def accept(self):
        for ov in self.overlays:
            ov.close()
        super().accept()

    def reject(self):
        for ov in self.overlays:
            ov.close()
        super().reject()
