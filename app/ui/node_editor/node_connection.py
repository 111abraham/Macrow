"""Cubic bezier curve connection wires between node sockets."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsItem

if TYPE_CHECKING:
    from app.ui.node_editor.node_socket import NodeSocketItem


class NodeConnection(QGraphicsPathItem):
    """Smooth bezier curve connecting an output socket to an input socket."""

    def __init__(
        self,
        start_socket: Optional["NodeSocketItem"] = None,
        end_socket: Optional["NodeSocketItem"] = None,
        parent: Optional[QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.start_socket = start_socket
        self.end_socket = end_socket
        self.target_pos: Optional[QPointF] = None  # Used while dragging new wire
        self.is_drop_target: bool = False  # Set to True when hovering node over wire to auto-insert

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(-1)  # Behind nodes

        self.color = QColor(56, 189, 248)  # Cyan
        self.selected_color = QColor(251, 146, 60)  # Orange

        if start_socket:
            start_socket.add_connection(self)
        if end_socket:
            end_socket.add_connection(self)

        self.update_path()

    def set_target_pos(self, pos: QPointF):
        """Set floating target position while dragging wire from a socket."""
        self.target_pos = pos
        self.update_path()

    def set_end_socket(self, socket: "NodeSocketItem"):
        if self.end_socket:
            self.end_socket.remove_connection(self)
        self.end_socket = socket
        self.target_pos = None
        if socket:
            socket.add_connection(self)
        self.update_path()

    def update_path(self):
        if not self.start_socket:
            return

        p1 = self.start_socket.scene_pos()
        if self.end_socket:
            p2 = self.end_socket.scene_pos()
        elif self.target_pos:
            p2 = self.target_pos
        else:
            return

        # Calculate smooth cubic bezier path flowing left-to-right
        dx = max(40.0, abs(p2.x() - p1.x()) * 0.5)

        ctrl1 = QPointF(p1.x() + dx, p1.y())
        ctrl2 = QPointF(p2.x() - dx, p2.y())

        path = QPainterPath()
        path.moveTo(p1)
        path.cubicTo(ctrl1, ctrl2, p2)

        self.setPath(path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_sel = self.isSelected()
        is_highlighted = getattr(self, "is_drop_target", False)
        is_executing = bool(self.end_socket and self.end_socket.node and getattr(self.end_socket.node, "is_executing", False))

        if is_highlighted:
            glow_pen = QPen(QColor(245, 158, 11, 150), 8.0)
            painter.setPen(glow_pen)
            painter.drawPath(self.path())
            col = QColor(251, 191, 36)  # Amber gold
            pen_width = 3.2
            pen_style = Qt.PenStyle.DashLine
        elif is_executing:
            glow_pen = QPen(QColor(16, 185, 129, 130), 8.0)
            painter.setPen(glow_pen)
            painter.drawPath(self.path())
            col = QColor(52, 211, 153)  # Emerald green
            pen_width = 3.2
            pen_style = Qt.PenStyle.SolidLine
        else:
            col = self.selected_color if is_sel else (self.start_socket.color if self.start_socket else self.color)
            pen_width = 3.0 if is_sel else 2.2
            pen_style = Qt.PenStyle.SolidLine
            if is_sel:
                glow_pen = QPen(QColor(col.red(), col.green(), col.blue(), 90), pen_width + 4.0)
                painter.setPen(glow_pen)
                painter.drawPath(self.path())

        painter.setPen(QPen(col, pen_width, pen_style, Qt.PenCapStyle.RoundCap))
        painter.drawPath(self.path())

    def clean_up(self):
        """Disconnect and remove from both connected sockets."""
        if self.start_socket:
            self.start_socket.remove_connection(self)
            self.start_socket = None
        if self.end_socket:
            self.end_socket.remove_connection(self)
            self.end_socket = None
