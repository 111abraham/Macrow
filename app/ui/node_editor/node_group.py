"""Visual group frame item enclosing multiple nodes."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QInputDialog,
    QApplication,
)

if TYPE_CHECKING:
    from app.ui.node_editor.node_items import BaseNodeItem


class NodeGroupItem(QGraphicsRectItem):
    """Encloses multiple nodes in an organized, draggable visual group frame."""

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

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(-2)  # Behind connections and nodes

        self.setRect(0, 0, 300, 200)

    def add_node(self, node: "BaseNodeItem"):
        if node not in self.nodes:
            self.nodes.append(node)
            node.group = self

    def remove_node(self, node: "BaseNodeItem"):
        if node in self.nodes:
            self.nodes.remove(node)
            if node.group == self:
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

        self.setPos(x, y)
        self.setRect(0, 0, max(w, 200.0), max(h, 150.0))

    def mousePressEvent(self, event):
        self._last_drag_pos = event.scenePos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._last_drag_pos and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.scenePos() - self._last_drag_pos
            self._last_drag_pos = event.scenePos()

            # Move all enclosed nodes in sync with the group frame!
            for node in self.nodes:
                node.setPos(node.pos() + delta)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._last_drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double click group title bar to rename."""
        if event.pos().y() <= self.header_height:
            new_title, ok = QInputDialog.getText(
                None, "Rename Group", "Enter group title:", text=self.title
            )
            if ok and new_title.strip():
                self.title = new_title.strip()
                self.update()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

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
