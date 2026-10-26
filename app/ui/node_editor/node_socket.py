"""Sockets (ports) for connecting nodes in the node editor."""

from __future__ import annotations

from typing import List, Optional, TYPE_CHECKING
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import QGraphicsItem

if TYPE_CHECKING:
    from app.ui.node_editor.node_connection import NodeConnection
    from app.ui.node_editor.node_items import BaseNodeItem


class NodeSocketItem(QGraphicsItem):
    """Circle socket on the side of a node for wiring connections."""

    TYPE_INPUT = "input"
    TYPE_OUTPUT = "output"

    def __init__(
        self,
        node: "BaseNodeItem",
        socket_type: str = TYPE_OUTPUT,
        name: str = "Out",
        color: Optional[QColor] = None,
        radius: float = 6.0,
    ):
        super().__init__(node)
        self.node = node
        self.socket_type = socket_type
        self.name = name
        self.radius = radius

        if color:
            self.color = color
        elif socket_type == self.TYPE_INPUT:
            self.color = QColor(56, 189, 248)  # Cyan
        else:
            self.color = QColor(16, 185, 129)  # Emerald green

        self.connections: List["NodeConnection"] = []
        self.setAcceptHoverEvents(True)
        self.is_hovered = False
        self.is_snap_target = False  # Set to True when wire is close and ready to snap!

    def set_snap_target(self, active: bool):
        """Highlights the socket when a dragged wire gets close for easy snapping."""
        if self.is_snap_target != active:
            self.is_snap_target = active
            self.update()

    def has_connections(self) -> bool:
        return len(self.connections) > 0

    def boundingRect(self) -> QRectF:
        r = self.radius + 8
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        r = self.radius

        # Snapping Highlight when wire is being dragged nearby!
        if self.is_snap_target:
            r += 2.0
            # Outer bright pulsing amber snap halo
            painter.setPen(Qt.PenStyle.NoPen)
            halo_color = QColor(250, 204, 21, 140)  # Bright amber glow
            painter.setBrush(QBrush(halo_color))
            painter.drawEllipse(QPointF(0, 0), r + 6.0, r + 6.0)

            # Vibrant border
            painter.setPen(QPen(QColor(255, 255, 255), 2.2))
            painter.setBrush(QBrush(QColor(250, 204, 21)))
            painter.drawEllipse(QPointF(0, 0), r, r)
            return

        if self.is_hovered:
            r += 1.5
            # Outer subtle glow
            painter.setPen(Qt.PenStyle.NoPen)
            glow_color = QColor(self.color)
            glow_color.setAlpha(90)
            painter.setBrush(QBrush(glow_color))
            painter.drawEllipse(QPointF(0, 0), r + 4, r + 4)

        painter.setPen(QPen(QColor(241, 245, 249), 1.5))
        painter.setBrush(QBrush(self.color if self.connections else QColor(30, 41, 59)))
        painter.drawEllipse(QPointF(0, 0), r, r)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def scene_pos(self) -> QPointF:
        """Returns the absolute position in the scene coordinate system."""
        return self.mapToScene(QPointF(0, 0))

    def add_connection(self, connection: "NodeConnection"):
        if connection not in self.connections:
            self.connections.append(connection)
            self.update()

    def remove_connection(self, connection: "NodeConnection"):
        if connection in self.connections:
            self.connections.remove(connection)
            self.update()

    def disconnect_all(self):
        """Unplugs and removes all wires connected to this socket."""
        for conn in list(self.connections):
            if self.scene():
                if hasattr(self.scene(), "remove_connection"):
                    self.scene().remove_connection(conn)
                else:
                    conn.clean_up()
                    self.scene().removeItem(conn)
            else:
                conn.clean_up()
        self.connections.clear()
        self.update()

    def update_connections(self):
        for conn in self.connections:
            conn.update_path()
