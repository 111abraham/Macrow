"""Interactive viewport for the node graph canvas."""

from __future__ import annotations

import math
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QWheelEvent,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPainterPathStroker,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
    QRubberBand,
    QApplication,
)

from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.node_items import BaseNodeItem, StartNodeItem
from app.ui.node_editor.node_connection import NodeConnection


class NodeView(QGraphicsView):
    """Zoomable, pannable canvas with grid background and box selection."""

    def __init__(self, scene: NodeScene, parent=None):
        super().__init__(scene, parent)
        self.node_scene = scene

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Canvas grid colors
        self.bg_color = QColor(15, 23, 42)        # Slate 900
        self.grid_minor = QColor(30, 41, 59, 100)  # Slate 800
        self.grid_major = QColor(51, 65, 85, 120)  # Slate 700

        self._is_panning = False
        self._pan_start_pos = QPointF()
        self.current_zoom = 1.0

        # Knife Tool (Y + Left Click Drag Cuts Wires)
        self._y_key_held = False
        self._is_cutting = False
        self._cut_path_points: list[QPointF] = []
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        # Fill deep dark background
        painter.fillRect(rect, self.bg_color)

        grid_size = 25.0
        major_interval = 4

        left = math.floor(rect.left() / grid_size) * grid_size
        top = math.floor(rect.top() / grid_size) * grid_size

        # Subtle dotted/lined grid
        minor_pen = QPen(self.grid_minor, 1.0)
        major_pen = QPen(self.grid_major, 1.2)

        x = left
        while x < rect.right():
            idx = int(round(x / grid_size))
            painter.setPen(major_pen if idx % major_interval == 0 else minor_pen)
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid_size

        y = top
        while y < rect.bottom():
            idx = int(round(y / grid_size))
            painter.setPen(major_pen if idx % major_interval == 0 else minor_pen)
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid_size

    def wheelEvent(self, event: QWheelEvent):
        """Zoom in/out centered under cursor."""
        zoom_in_factor = 1.15
        zoom_out_factor = 1.0 / zoom_in_factor

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        current_scale = self.transform().m11()
        if current_scale <= 0.001:
            current_scale = 1.0

        new_scale = current_scale * zoom_factor
        if 0.05 <= new_scale <= 5.0:
            self.scale(zoom_factor, zoom_factor)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        # 1. Knife Tool: Y held + Left Click starts cutting wire trail
        if event.button() == Qt.MouseButton.LeftButton and self._y_key_held:
            self._is_cutting = True
            scene_pt = self.mapToScene(event.pos())
            self._cut_path_points = [scene_pt]
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return

        # 2. Alt + Left click:
        # If clicked on a node: Duplicate selected node(s) in-place and drag duplicates!
        # If clicked on empty canvas: Canvas panning
        if event.button() == Qt.MouseButton.LeftButton and (event.modifiers() & Qt.KeyboardModifier.AltModifier):
            item = self.itemAt(event.pos())
            target_node = None
            curr = item
            while curr:
                if isinstance(curr, BaseNodeItem):
                    target_node = curr
                    break
                curr = curr.parentItem()

            if target_node and not isinstance(target_node, StartNodeItem):
                if not target_node.isSelected():
                    self.node_scene.clearSelection()
                    target_node.setSelected(True)

                self.node_scene.duplicate_selected_in_place()
                super().mousePressEvent(event)
                return
            else:
                self._is_panning = True
                self._pan_start_pos = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return

        # 3. Middle click panning
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Knife tool drag: slice intersecting connections
        if self._is_cutting:
            cur_scene_pt = self.mapToScene(event.pos())
            if not self._cut_path_points or (self._cut_path_points[-1] - cur_scene_pt).manhattanLength() > 2.0:
                prev_pt = self._cut_path_points[-1]
                self._cut_path_points.append(cur_scene_pt)

                seg_path = QPainterPath()
                seg_path.moveTo(prev_pt)
                seg_path.lineTo(cur_scene_pt)

                stroker = QPainterPathStroker()
                stroker.setWidth(8.0)
                laser_segment = stroker.createStroke(seg_path)

                cut_conns = []
                for conn in list(self.node_scene.connections):
                    if conn.path().intersects(laser_segment) or conn.shape().intersects(laser_segment):
                        cut_conns.append(conn)

                for conn in cut_conns:
                    self.node_scene.remove_connection(conn)

                self.viewport().update()
                event.accept()
                return

        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._is_cutting and event.button() == Qt.MouseButton.LeftButton:
            self._is_cutting = False
            self._cut_path_points.clear()
            if not self._y_key_held:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport().update()
            event.accept()
            return

        if self._is_panning and (event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton)):
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.node_scene.scene_modified.emit()

    def keyPressEvent(self, event: QKeyEvent):
        # Y key alone activates knife wire-cutting tool
        if event.key() == Qt.Key.Key_Y and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._y_key_held = True
            self.setCursor(Qt.CursorShape.CrossCursor)
            event.accept()
            return

        # Ctrl+C: Copy selected nodes
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            self.node_scene.copy_selected()
            event.accept()
            return

        # Ctrl+V: Paste nodes
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V:
            self.node_scene.paste_clipboard()
            event.accept()
            return

        # Ctrl+D: Duplicate
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_D:
            self.node_scene.duplicate_selected()
            event.accept()
            return

        # Ctrl+G: Group
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_G:
            self.node_scene.group_selected()
            event.accept()
            return

        # Delete or Backspace
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.node_scene.delete_selected()
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Y:
            self._y_key_held = False
            if not self._is_cutting:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().keyReleaseEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        if self._is_cutting and len(self._cut_path_points) >= 2:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            laser_path = QPainterPath()
            laser_path.moveTo(self._cut_path_points[0])
            for pt in self._cut_path_points[1:]:
                laser_path.lineTo(pt)

            # Outer glow: bright crimson laser
            glow_pen = QPen(
                QColor(239, 68, 68, 160),
                6.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(glow_pen)
            painter.drawPath(laser_path)

            # Inner core: glowing light-red laser beam
            core_pen = QPen(
                QColor(254, 226, 226, 250),
                2.2,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
            painter.setPen(core_pen)
            painter.drawPath(laser_path)

    def fit_all(self):
        """Fit all nodes and connections comfortably within the viewport."""
        if not self.node_scene.nodes:
            self.resetTransform()
            self.current_zoom = 1.0
            return

        rect = self.node_scene.itemsBoundingRect()
        if rect.isEmpty():
            return

        # Add generous padding around the graph
        margin = 80.0
        target_rect = rect.adjusted(-margin, -margin, margin, margin)

        self.fitInView(target_rect, Qt.AspectRatioMode.KeepAspectRatio)

        # Sync zoom factor from current view transform
        transform = self.transform()
        self.current_zoom = max(0.15, min(3.0, transform.m11()))

    def reset_view(self):
        """Frame the entire graph in view."""
        self.fit_all()
