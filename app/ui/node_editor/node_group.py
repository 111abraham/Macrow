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
        max_x = max(n.pos().x() + (n.clamp_width if hasattr(n, "clamp_width") else n.boundingRect().width()) for n in self.nodes)
        max_y = max(n.pos().y() + (n.clamp_height if hasattr(n, "clamp_height") else n.boundingRect().height()) for n in self.nodes)

        x = min_x - padding
        y = min_y - padding - self.header_height
        w = (max_x - min_x) + padding * 2
        h = (max_y - min_y) + padding * 2 + self.header_height

        self._in_node_sync = True
        try:
            self.prepareGeometryChange()
            self.setPos(x, y)
            self.setRect(0, 0, max(w, 200.0), max(h, 150.0))
            self.update()
        finally:
            self._in_node_sync = False
        if self.scene() and hasattr(self.scene(), "scene_modified"):
            self.scene().scene_modified.emit()

    def expand_to_contain_node(self, node: "BaseNodeItem", padding: float = 24.0):
        """Expands the group's bounding rectangle if a node is dragged near or beyond its right/bottom bounds."""
        if not self.scene():
            return
        gx = self.pos().x()
        gy = self.pos().y()
        gw = self.rect().width()
        gh = self.rect().height()

        item_w = node.clamp_width if hasattr(node, "clamp_width") else getattr(node, "width", 150.0)
        item_h = node.clamp_height if hasattr(node, "clamp_height") else getattr(node, "height", 80.0)

        needed_w = (node.pos().x() - gx) + item_w + padding
        needed_h = (node.pos().y() - gy) + item_h + padding

        new_w = max(gw, needed_w)
        new_h = max(gh, needed_h)

        if new_w > gw + 1.0 or new_h > gh + 1.0:
            self._in_node_sync = True
            try:
                self.prepareGeometryChange()
                self.setRect(0, 0, new_w, new_h)
                self.update()
            finally:
                self._in_node_sync = False
            if hasattr(self.scene(), "update_loop_bounds"):
                self.scene().update_loop_bounds()

    def sync_chain_nodes(self):
        """Discovers and adopts any nodes that were inserted into the chain of grouped nodes."""
        if not self.scene():
            return
        from app.ui.node_editor.node_items import BaseNodeItem, LoopNodeItem
        grp_nodes = set(self.nodes)
        adopted = []
        for n in getattr(self.scene(), "nodes", []):
            if n in grp_nodes or not isinstance(n, BaseNodeItem) or isinstance(n, LoopNodeItem):
                continue
            # Check 1: Spliced or connected between two nodes of this group
            # (has an upstream link from a group node AND a downstream link to a group node)
            has_in_from_grp = any(
                c.start_socket and c.start_socket.node in grp_nodes
                for sock in n.input_sockets for c in sock.connections
            )
            has_out_to_grp = any(
                c.end_socket and c.end_socket.node in grp_nodes
                for sock in n.output_sockets for c in sock.connections
            )
            if has_in_from_grp and has_out_to_grp:
                adopted.append(n)
                continue

            # Check 2: Located inside this group's bounding rect AND connected to any node in the group
            if (has_in_from_grp or has_out_to_grp) and self.sceneBoundingRect().contains(n.sceneBoundingRect().center()):
                adopted.append(n)

        for n in adopted:
            self.add_node(n)
            self.expand_to_contain_node(n)

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

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            if not getattr(self, "_in_node_sync", False) and not self._is_resizing:
                self.sync_chain_nodes()
            from app.ui.node_editor.node_items import LoopNodeItem
            # If group is inside an enclosing LoopNodeItem (and loop is not selected and not in sync), clamp inside loop cavity
            if not getattr(self, "_in_node_sync", False) and not self._is_resizing:
                enclosing_loop = None
                for it in self.scene().items():
                    if isinstance(it, LoopNodeItem) and it not in self.nodes and not it.isSelected():
                        body_nodes = set(it.get_body_nodes())
                        if any(n in body_nodes for n in self.nodes) or it.sceneBoundingRect().contains(self.sceneBoundingRect().center()):
                            enclosing_loop = it
                            break
                if enclosing_loop:
                    lx = enclosing_loop.pos().x()
                    ly = enclosing_loop.pos().y()
                    min_x = lx + enclosing_loop.spine_width + 8.0
                    min_y = ly + enclosing_loop.header_height + 8.0
                    max_x = max(min_x, lx + enclosing_loop.clamp_width - self.rect().width() - 8.0)
                    max_y = max(min_y, ly + enclosing_loop.clamp_height - enclosing_loop.shelf_height - self.rect().height() - 8.0)
                    new_pos = QPointF(
                        min(max(new_pos.x(), min_x), max_x),
                        min(max(new_pos.y(), min_y), max_y)
                    )

            old_pos = self.pos()
            delta = new_pos - old_pos
            if not getattr(self, "_in_node_sync", False) and not self._is_resizing and (delta.x() != 0 or delta.y() != 0):
                self._in_node_sync = True
                try:
                    # Identify body nodes of any LoopNodeItem in this group so LoopNodeItem moves them
                    nested_body_nodes = set()
                    for n in self.nodes:
                        if isinstance(n, LoopNodeItem):
                            nested_body_nodes.update(n.get_body_nodes())

                    for node in list(self.nodes):
                        if not node.isSelected() and node not in nested_body_nodes:
                            node.setPos(node.pos() + delta)
                            if hasattr(node, "update_connected_wires"):
                                node.update_connected_wires()
                finally:
                    self._in_node_sync = False
            return super().itemChange(change, new_pos)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.sync_chain_nodes()
            if self.get_resize_grip_rect().contains(event.pos()):
                self._is_resizing = True
                self._resize_start_scene = event.scenePos()
                self._resize_start_rect = self.rect()
                nested_body_nodes = set()
                for n in self.nodes:
                    from app.ui.node_editor.node_items import LoopNodeItem
                    if isinstance(n, LoopNodeItem):
                        nested_body_nodes.update(n.get_body_nodes())
                self._resize_initial_node_rel_positions = {
                    n: (n.pos().x() - self.pos().x(), n.pos().y() - self.pos().y())
                    for n in self.nodes if n not in nested_body_nodes
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
            self._last_drag_pos = event.scenePos()

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
