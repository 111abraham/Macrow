"""Visual group frame item enclosing multiple nodes."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QInputDialog,
    QColorDialog,
    QMenu,
    QApplication,
)

if TYPE_CHECKING:
    from app.ui.node_editor.node_items import BaseNodeItem


class NodeGroupItem(QGraphicsRectItem):
    """Encloses multiple nodes in an organized, draggable, resizable visual group frame."""

    def __init__(
        self,
        title: str = "Group",
        color: Optional[QColor] = None,
        parent: Optional[QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.title = title
        self.header_height = 32.0
        self.color = color or QColor(99, 102, 241)  # Indigo
        self.bg_color = QColor(30, 41, 59, 140)

        self.nodes: List["BaseNodeItem"] = []
        self._last_drag_pos: Optional[QPointF] = None
        self._is_resizing: bool = False
        self._resize_start_scene: Optional[QPointF] = None
        self._resize_start_rect: Optional[QRectF] = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Position behind Loop repeat bracket (z=0.1) and regular nodes (z=1.0)
        self.setZValue(0.05)
        self.setAcceptHoverEvents(True)

        self.setRect(0, 0, 300, 200)

    def add_node(self, node: "BaseNodeItem"):
        if getattr(node, "group", None) and node.group is not self:
            old_grp = node.group
            old_grp.remove_node(node)
            if not old_grp.nodes and old_grp.scene():
                if hasattr(old_grp.scene(), "remove_group"):
                    old_grp.scene().remove_group(old_grp)
        if node not in self.nodes:
            self.nodes.append(node)
            node.group = self

    def remove_node(self, node: "BaseNodeItem"):
        if node in self.nodes:
            self.nodes.remove(node)
            if getattr(node, "group", None) == self:
                node.group = None

    def fit_to_nodes(self, padding: float = 30.0):
        """Automatically expand bounding box to tightly enclose all member nodes."""
        if not self.nodes:
            return

        min_x = min(n.pos().x() for n in self.nodes)
        min_y = min(n.pos().y() for n in self.nodes)
        max_x = max(n.pos().x() + n.boundingRect().width() for n in self.nodes)
        max_y = max(n.pos().y() + n.boundingRect().height() for n in self.nodes)

        x = min_x - padding
        y = min_y - padding - self.header_height
        w = (max_x - min_x) + padding * 2
        h = (max_y - min_y) + padding * 2 + self.header_height

        self.prepareGeometryChange()
        self.setPos(x, y)
        self.setRect(0, 0, max(w, 200.0), max(h, 150.0))
        self.update()
        if self.scene() and hasattr(self.scene(), "scene_modified"):
            self.scene().scene_modified.emit()

    def get_resize_grip_rect(self) -> QRectF:
        """Returns corner bounding rect for mouse drag resizing."""
        r = self.rect()
        return QRectF(r.width() - 22, r.height() - 22, 22, 22)

    def hoverMoveEvent(self, event):
        if self.get_resize_grip_rect().contains(event.pos()):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.get_resize_grip_rect().contains(event.pos()):
                self._is_resizing = True
                self._resize_start_scene = event.scenePos()
                self._resize_start_rect = self.rect()
                self._resize_initial_node_rel_positions = {
                    n: (n.pos().x() - self.pos().x(), n.pos().y() - self.pos().y())
                    for n in self.nodes
                }
                event.accept()
                return

        self._last_drag_pos = event.scenePos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_resizing and self._resize_start_scene and self._resize_start_rect:
            delta = event.scenePos() - self._resize_start_scene
            new_w = max(80.0, self._resize_start_rect.width() + delta.x())
            new_h = max(60.0, self._resize_start_rect.height() + delta.y())
            self.prepareGeometryChange()
            self.setRect(0, 0, new_w, new_h)

            # Proportional compress / expand of space between nodes horizontally & vertically
            start_w = max(1.0, self._resize_start_rect.width())
            start_h = max(1.0, self._resize_start_rect.height())
            s_x = new_w / start_w
            s_y = new_h / start_h

            for node, (rx, ry) in getattr(self, "_resize_initial_node_rel_positions", {}).items():
                nx = self.pos().x() + max(8.0, rx * s_x)
                ny = self.pos().y() + self.header_height + max(8.0, (ry - self.header_height) * s_y)
                node.setPos(nx, ny)
                node.update_connected_wires()

            self.update()
            if self.scene() and hasattr(self.scene(), "update_loop_bounds"):
                self.scene().update_loop_bounds()
            event.accept()
            return

        if self._last_drag_pos and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.scenePos() - self._last_drag_pos
            self._last_drag_pos = event.scenePos()

            # Move all enclosed nodes in sync with the group frame!
            # If a member node is already selected in the scene, Qt's base item move
            # already moves it by delta. Only manually move nodes that are NOT selected.
            for node in self.nodes:
                if not node.isSelected():
                    node.setPos(node.pos() + delta)

        try:
            super().mouseMoveEvent(event)
        except (TypeError, AttributeError):
            pass

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            self._is_resizing = False
            self._resize_start_scene = None
            self._resize_start_rect = None
            if hasattr(self, "_resize_initial_node_rel_positions"):
                self._resize_initial_node_rel_positions.clear()
            if self.scene() and hasattr(self.scene(), "scene_modified"):
                self.scene().scene_modified.emit()
            if self.scene() and hasattr(self.scene(), "update_loop_bounds"):
                self.scene().update_loop_bounds()
            event.accept()
            return

        self._last_drag_pos = None
        super().mouseReleaseEvent(event)
        if self.scene() and hasattr(self.scene(), "scene_modified"):
            self.scene().scene_modified.emit()
            self.scene().scene_modified.emit()

    def prompt_rename(self):
        new_title, ok = QInputDialog.getText(
            None, "Rename Group", "Enter group title:", text=self.title
        )
        if ok and new_title.strip():
            self.set_title(new_title.strip())

    def set_title(self, new_title: str):
        self.title = new_title
        self.update()
        if self.scene() and hasattr(self.scene(), "scene_modified"):
            self.scene().scene_modified.emit()

    def prompt_color(self):
        col = QColorDialog.getColor(self.color, None, "Select Group Color")
        if col.isValid():
            self.set_color(col)

    def set_color(self, color: QColor):
        self.color = color
        self.update()
        if self.scene() and hasattr(self.scene(), "scene_modified"):
            self.scene().scene_modified.emit()

    def mouseDoubleClickEvent(self, event):
        """Double click group title bar to rename."""
        if event.pos().y() <= self.header_height:
            self.prompt_rename()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #1e293b; color: #f8fafc; border: 1px solid #334155; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #3b82f6; }
        """)
        act_rename = menu.addAction("✏ Rename Group...")
        act_color = menu.addAction("🎨 Change Color...")
        act_fit = menu.addAction("📐 Fit to Enclosed Nodes")
        menu.addSeparator()
        act_delete = menu.addAction("🗑 Delete Group Frame")

        action = menu.exec(event.screenPos())
        if action == act_rename:
            self.prompt_rename()
        elif action == act_color:
            self.prompt_color()
        elif action == act_fit:
            self.fit_to_nodes()
        elif action == act_delete:
            if self.scene() and hasattr(self.scene(), "remove_group"):
                self.scene().remove_group(self)
        event.accept()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        # Body background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self.bg_color))
        painter.drawRoundedRect(r, 8, 8)

        # Header background
        header_rect = QRectF(r.x(), r.y(), r.width(), self.header_height)
        header_brush = QColor(self.color.red(), self.color.green(), self.color.blue(), 180)
        painter.setBrush(QBrush(header_brush))
        painter.drawRoundedRect(header_rect, 8, 8)
        # Flatten bottom corners of header
        painter.fillRect(QRectF(r.x(), r.y() + 16, r.width(), self.header_height - 16), header_brush)

        # Border
        is_sel = self.isSelected()
        border_col = QColor(251, 146, 60) if is_sel else self.color
        painter.setPen(QPen(border_col, 2.0 if is_sel else 1.2, Qt.PenStyle.DashLine if not is_sel else Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(r, 8, 8)

        # Title text
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        text_rect = QRectF(r.x() + 12, r.y(), r.width() - 24, self.header_height)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"🗂  {self.title}",
        )

        # Resize grip notches in bottom-right corner
        grip_r = self.get_resize_grip_rect()
        painter.setPen(QPen(QColor(148, 163, 184, 180), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for off in (5, 9, 13):
            painter.drawLine(
                int(grip_r.right() - off), int(grip_r.bottom() - 3),
                int(grip_r.right() - 3), int(grip_r.bottom() - off)
            )
