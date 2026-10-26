"""Interactive screen snipper tool for capturing template images.
Allows the user to drag a rectangle on their screen to snip any icon, button, or UI region.
Uses thread-safe 1:1 hardware pixel screen capture across all monitors and draws
precision crosshairs directly intersecting at the cursor tip.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QImage,
    QFont,
    QCursor,
)
from PyQt6.QtWidgets import QDialog

from app.core.vision import capture_screen_win32_bgra
from app.ui.assets import get_app_icon


class ScreenSnipper(QDialog):
    """Fullscreen semi-transparent overlay to select and crop a screen snippet."""

    snippet_captured = pyqtSignal(QImage, str)  # (cropped_qimage, saved_filepath)

    def __init__(self, parent=None, save_dir: Optional[str] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setWindowIcon(get_app_icon())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.save_dir = save_dir or os.path.join(os.getcwd(), "snippets")
        os.makedirs(self.save_dir, exist_ok=True)

        # Capture the entire virtual desktop across all connected monitors safely
        bgra, vx, vy, vw, vh = capture_screen_win32_bgra(region=None)
        if bgra is not None and vw > 0 and vh > 0:
            self.setGeometry(QRect(vx, vy, vw, vh))
            self.full_screenshot = QImage(bgra.data, vw, vh, vw * 4, QImage.Format.Format_ARGB32).copy()
        else:
            vx, vy, vw, vh = 0, 0, 1920, 1080
            self.setGeometry(QRect(vx, vy, vw, vh))
            self.full_screenshot = QImage(vw, vh, QImage.Format.Format_RGB32)
            self.full_screenshot.fill(QColor(15, 23, 42))

        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = self.mapFromGlobal(QCursor.pos())
        self.is_selecting = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.is_selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right click cancels snippet
            self.reject()

    def mouseMoveEvent(self, event):
        self.current_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.current_pos = event.pos()
            rect = self._get_selected_rect()

            if rect.width() >= 5 and rect.height() >= 5:
                # Crop image from full screenshot
                cropped = self.full_screenshot.copy(rect)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"snippet_{timestamp}.png"
                filepath = os.path.join(self.save_dir, filename)
                cropped.save(filepath, "PNG")

                self.snippet_captured.emit(cropped, filepath)
                self.accept()
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

        # 1. Draw the underlying 1:1 desktop screenshot
        painter.drawImage(self.rect(), self.full_screenshot)

        # 2. Dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

        # 3. Active selection region (if dragging)
        if self.is_selecting and self.start_pos and self.current_pos:
            sel_rect = self._get_selected_rect()
            if not sel_rect.isEmpty():
                # Reveal selected region without dark overlay
                painter.drawImage(sel_rect, self.full_screenshot, sel_rect)

                # Bright border around selected region
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
            # Help instruction banner
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

        # 4. Draw precision crosshairs directly intersecting at cursor tip
        cur = self.current_pos or self.mapFromGlobal(QCursor.pos())
        cx = cur.x()
        cy = cur.y()

        cross_pen = QPen(QColor(56, 189, 248, 190), 1, Qt.PenStyle.DashLine)
        painter.setPen(cross_pen)
        painter.drawLine(0, cy, self.width(), cy)
        painter.drawLine(cx, 0, cx, self.height())

        # Fine reticle at exact intersection
        reticle_pen = QPen(QColor(255, 255, 255, 240), 1.5)
        painter.setPen(reticle_pen)
        painter.drawLine(cx - 7, cy, cx - 2, cy)
        painter.drawLine(cx + 2, cy, cx + 7, cy)
        painter.drawLine(cx, cy - 7, cx, cy - 2)
        painter.drawLine(cx, cy + 2, cx, cy + 7)

        painter.end()
