"""Graphics scene managing nodes, connections, and groups."""

from __future__ import annotations

import copy
import uuid
from typing import List, Optional, Dict, Any
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsItem

from app.ui.node_editor.node_socket import NodeSocketItem
from app.ui.node_editor.node_connection import NodeConnection
from app.ui.node_editor.node_group import NodeGroupItem
from app.ui.node_editor.node_items import (
    BaseNodeItem,
    StartNodeItem,
    ActionNodeItem,
    VisionNodeItem,
)


class NodeScene(QGraphicsScene):
    """Interactive node graph canvas scene."""

    node_selected = pyqtSignal(object)  # Emits BaseNodeItem or None
    scene_modified = pyqtSignal()

    # Shared clipboard across scene instances for copy/paste
    _clipboard: Optional[Dict[str, Any]] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-100000, -100000, 200000, 200000)

        self.nodes: List[BaseNodeItem] = []
        self.connections: List[NodeConnection] = []
        self.groups: List[NodeGroupItem] = []

        # Interactive wiring & snapping state
        self._dragging_connection: Optional[NodeConnection] = None
        self._drag_start_socket: Optional[NodeSocketItem] = None
        self._unplugged_from_socket: Optional[NodeSocketItem] = None
        self._current_snap_socket: Optional[NodeSocketItem] = None

        self.selectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        sel = self.selectedItems()
        node = None
        for item in sel:
            if isinstance(item, BaseNodeItem):
                node = item
                break
        self.node_selected.emit(node)

    def add_node(self, node: BaseNodeItem, pos: Optional[QPointF] = None) -> BaseNodeItem:
        if pos:
            node.setPos(pos)
        self.addItem(node)
        self.nodes.append(node)
        self.scene_modified.emit()
        return node

    def remove_node(self, node: BaseNodeItem):
        if isinstance(node, StartNodeItem):
            # Do not allow deleting Start node
            return

        if node in self.nodes:
            self.nodes.remove(node)

        # Remove all connected wires
        for sock in node.input_sockets + node.output_sockets:
            for conn in list(sock.connections):
                self.remove_connection(conn)

        # Remove from any group
        if node.group:
            node.group.remove_node(node)

        self.removeItem(node)
        self.update_loop_bounds()
        self.scene_modified.emit()

    def update_loop_bounds(self):
        """Update enclosing bracket bounds for all C-clamp repeat zones."""
        for n in list(self.nodes):
            if hasattr(n, "update_clamp_bounds"):
                n.update_clamp_bounds()

    def add_connection(
        self, start_socket: NodeSocketItem, end_socket: NodeSocketItem
    ) -> Optional[NodeConnection]:
        # Validate connection
        if not start_socket or not end_socket:
            return None
        if start_socket.node == end_socket.node:
            return None  # Cannot connect node to itself

        # Ensure start is output and end is input
        if start_socket.socket_type == NodeSocketItem.TYPE_INPUT:
            start_socket, end_socket = end_socket, start_socket
        if (
            start_socket.socket_type != NodeSocketItem.TYPE_OUTPUT
            or end_socket.socket_type != NodeSocketItem.TYPE_INPUT
        ):
            return None

        # Check if identical connection already exists
        for conn in self.connections:
            if conn.start_socket == start_socket and conn.end_socket == end_socket:
                return conn

        conn = NodeConnection(start_socket, end_socket)
        self.addItem(conn)
        self.connections.append(conn)
        self.update_loop_bounds()
        self.scene_modified.emit()
        return conn

    def remove_connection(self, conn: NodeConnection):
        if conn in self.connections:
            self.connections.remove(conn)
        conn.clean_up()
        self.removeItem(conn)
        self.update_loop_bounds()
        self.scene_modified.emit()

    def add_group(self, title: str = "Group", nodes: Optional[List[BaseNodeItem]] = None) -> NodeGroupItem:
        group = NodeGroupItem(title=title)
        self.addItem(group)
        self.groups.append(group)
        if nodes:
            for n in nodes:
                group.add_node(n)
            group.fit_to_nodes()
        self.scene_modified.emit()
        return group

    def remove_group(self, group: NodeGroupItem):
        if group in self.groups:
            self.groups.remove(group)
        for n in list(group.nodes):
            group.remove_node(n)
        self.removeItem(group)
        self.scene_modified.emit()

    # --- Mouse interaction for interactive wiring, snapping & unplugging ---

    def _find_snap_socket(
        self, pos: QPointF, start_socket: Optional[NodeSocketItem], max_dist: float = 26.0
    ) -> Optional[NodeSocketItem]:
        """Finds the nearest compatible socket for snapping within max_dist scene units."""
        if not start_socket:
            return None

        target_type = (
            NodeSocketItem.TYPE_INPUT
            if start_socket.socket_type == NodeSocketItem.TYPE_OUTPUT
            else NodeSocketItem.TYPE_OUTPUT
        )
        closest: Optional[NodeSocketItem] = None
        min_d = max_dist

        for node in self.nodes:
            if node == start_socket.node:
                continue
            sockets = node.input_sockets if target_type == NodeSocketItem.TYPE_INPUT else node.output_sockets
            for sock in sockets:
                sp = sock.scene_pos()
                dx = sp.x() - pos.x()
                dy = sp.y() - pos.y()
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < min_d:
                    min_d = dist
                    closest = sock

        return closest

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)

        # Right click on a socket with wires disconnects all wires
        if isinstance(item, NodeSocketItem) and event.button() == Qt.MouseButton.RightButton:
            if item.connections:
                item.disconnect_all()
                self.scene_modified.emit()
                event.accept()
                return

        # Left click on a socket: start dragging a wire or UNPLUG existing wire
        if isinstance(item, NodeSocketItem) and event.button() == Qt.MouseButton.LeftButton:
            # UNPLUG FEATURE:
            # If clicking an INPUT socket that already has incoming wire(s), unplug the wire!
            if item.socket_type == NodeSocketItem.TYPE_INPUT and item.connections:
                conn_to_unplug = item.connections[-1]
                orig_start = conn_to_unplug.start_socket

                # Detach from this input socket
                item.remove_connection(conn_to_unplug)
                conn_to_unplug.end_socket = None
                conn_to_unplug.set_target_pos(event.scenePos())

                self._dragging_connection = conn_to_unplug
                self._drag_start_socket = orig_start
                self._unplugged_from_socket = item
                event.accept()
                return

            # Standard wire dragging from socket
            self._drag_start_socket = item
            self._dragging_connection = NodeConnection(start_socket=item)
            self._dragging_connection.set_target_pos(event.scenePos())
            self._unplugged_from_socket = None
            self.addItem(self._dragging_connection)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging_connection:
            cur_pos = event.scenePos()

            # Dynamic snapping: highlight candidate socket when wire approaches it
            snap_target = self._find_snap_socket(cur_pos, self._drag_start_socket)
            if snap_target != self._current_snap_socket:
                if self._current_snap_socket:
                    self._current_snap_socket.set_snap_target(False)
                self._current_snap_socket = snap_target
                if self._current_snap_socket:
                    self._current_snap_socket.set_snap_target(True)

            if self._current_snap_socket:
                # Snap wire end directly to candidate socket center
                self._dragging_connection.set_target_pos(self._current_snap_socket.scene_pos())
            else:
                self._dragging_connection.set_target_pos(cur_pos)

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging_connection and event.button() == Qt.MouseButton.LeftButton:
            conn = self._dragging_connection
            start_sock = self._drag_start_socket
            unplugged_from = self._unplugged_from_socket

            target_sock = self._current_snap_socket
            if not target_sock:
                item = self.itemAt(event.scenePos(), self.views()[0].transform() if self.views() else None)
                if isinstance(item, NodeSocketItem) and item != start_sock:
                    target_sock = item

            # Reset snap target highlight
            if self._current_snap_socket:
                self._current_snap_socket.set_snap_target(False)
                self._current_snap_socket = None

            self._dragging_connection = None
            self._drag_start_socket = None
            self._unplugged_from_socket = None

            if target_sock and start_sock and target_sock != start_sock:
                if unplugged_from:
                    # Reconnect unplugged wire to new target
                    conn.set_end_socket(target_sock)
                    self.scene_modified.emit()
                else:
                    # Clean up temporary wire and establish official connection
                    self.removeItem(conn)
                    conn.clean_up()
                    self.add_connection(start_sock, target_sock)
            else:
                # Released in empty space:
                if unplugged_from:
                    # Connection was unplugged and dropped in empty space -> DELETE connection!
                    if conn in self.connections:
                        self.connections.remove(conn)
                    conn.clean_up()
                    self.removeItem(conn)
                    self.scene_modified.emit()
                else:
                    # Discard temporary dragging line
                    self.removeItem(conn)
                    conn.clean_up()

            event.accept()
            return

        super().mouseReleaseEvent(event)

    # --- Clipboard: Copy & Paste (Ctrl+C / Ctrl+V) ---

    def copy_selected(self) -> int:
        """Copies selected nodes and internal connections into internal clipboard."""
        selected_nodes = [
            item for item in self.selectedItems()
            if isinstance(item, BaseNodeItem) and not isinstance(item, StartNodeItem)
        ]
        if not selected_nodes:
            return 0

        nodes_data = []
        for n in selected_nodes:
            nodes_data.append({
                "id": getattr(n, "id", None) or hex(id(n)),
                "class_name": n.__class__.__name__,
                "node_type": n.node_type,
                "title": getattr(n, "title", "Node"),
                "pos": (n.pos().x(), n.pos().y()),
                "properties": copy.deepcopy(n.properties),
            })

        conns_data = []
        for conn in self.connections:
            s = conn.start_socket
            e = conn.end_socket
            if s and e and s.node in selected_nodes and e.node in selected_nodes:
                s_idx = s.node.output_sockets.index(s) if s in s.node.output_sockets else 0
                e_idx = e.node.input_sockets.index(e) if e in e.node.input_sockets else 0
                conns_data.append({
                    "from_node": getattr(s.node, "id", None) or hex(id(s.node)),
                    "from_socket_idx": s_idx,
                    "to_node": getattr(e.node, "id", None) or hex(id(e.node)),
                    "to_socket_idx": e_idx,
                })

        NodeScene._clipboard = {
            "nodes": nodes_data,
            "connections": conns_data,
            "offset_count": 1,
        }
        return len(nodes_data)

    def paste_clipboard(self, offset_step: Optional[QPointF] = None) -> List[BaseNodeItem]:
        """Pastes clipboard contents with offset into the scene."""
        if not NodeScene._clipboard or not NodeScene._clipboard.get("nodes"):
            return []

        from app.ui.node_editor.undo_manager import NODE_CLASS_MAP

        clip = NodeScene._clipboard
        nodes_data = clip.get("nodes", [])
        conns_data = clip.get("connections", [])
        offset_multiplier = clip.get("offset_count", 1)

        offset = offset_step if offset_step is not None else QPointF(40.0 * offset_multiplier, 40.0 * offset_multiplier)
        clip["offset_count"] = offset_multiplier + 1

        self.clearSelection()
        id_map: Dict[str, BaseNodeItem] = {}
        new_nodes: List[BaseNodeItem] = []

        for nd in nodes_data:
            cls_name = nd.get("class_name", "ActionNodeItem")
            cls = NODE_CLASS_MAP.get(cls_name, ActionNodeItem)
            props = copy.deepcopy(nd.get("properties", {}))
            ntype = nd.get("node_type", "click")

            if cls is ActionNodeItem:
                node = ActionNodeItem(action_type=ntype, properties=props)
            elif cls is VisionNodeItem:
                node = VisionNodeItem(vision_type="wait_image", properties=props)
            elif cls is StartNodeItem:
                continue
            else:
                node = cls(properties=props)

            node.id = uuid.uuid4().hex[:8]
            old_id = nd.get("id")
            if old_id:
                id_map[old_id] = node

            orig_pos = nd.get("pos", (0, 0))
            new_pos = QPointF(orig_pos[0], orig_pos[1]) + offset
            self.add_node(node, new_pos)
            node.setSelected(True)
            new_nodes.append(node)

        # Recreate internal connections between the newly pasted nodes
        for cd in conns_data:
            src = id_map.get(cd.get("from_node"))
            dst = id_map.get(cd.get("to_node"))
            if src and dst:
                s_idx = cd.get("from_socket_idx", 0)
                e_idx = cd.get("to_socket_idx", 0)
                if s_idx < len(src.output_sockets) and e_idx < len(dst.input_sockets):
                    self.add_connection(src.output_sockets[s_idx], dst.input_sockets[e_idx])

        self.scene_modified.emit()
        return new_nodes

    # --- Grouping & Duplication Features ---

    def group_selected(self) -> Optional[NodeGroupItem]:
        selected_nodes = [item for item in self.selectedItems() if isinstance(item, BaseNodeItem)]
        if not selected_nodes:
            return None

        group = self.add_group(title=f"Group {len(self.groups) + 1}", nodes=selected_nodes)
        self.clearSelection()
        group.setSelected(True)
        return group

    def duplicate_selected(self) -> List[BaseNodeItem]:
        """Duplicates all selected nodes and internal connections with an offset."""
        count = self.copy_selected()
        if count == 0:
            return []
        return self.paste_clipboard(offset_step=QPointF(40, 40))

    def duplicate_selected_in_place(self) -> List[BaseNodeItem]:
        """Duplicates all selected nodes and internal connections in-place (0 offset) for drag-duplication."""
        count = self.copy_selected()
        if count == 0:
            return []
        return self.paste_clipboard(offset_step=QPointF(0.0, 0.0))

    def toggle_bypass_selected(self) -> int:
        """Toggles bypass state on all selected nodes (excluding StartNodeItem)."""
        from app.ui.node_editor.node_items import StartNodeItem
        selected_nodes = [
            item for item in self.selectedItems()
            if isinstance(item, BaseNodeItem) and not isinstance(item, StartNodeItem)
        ]
        if not selected_nodes:
            return 0

        # If any node is NOT bypassed, bypass all. If all are already bypassed, unbypass all.
        any_active = any(not getattr(n, "bypassed", False) for n in selected_nodes)
        new_state = any_active

        for n in selected_nodes:
            n.set_bypassed(new_state)

        self.scene_modified.emit()
        return len(selected_nodes)

    def delete_selected(self):
        """Deletes selected nodes, groups, and connections. Auto-heals wires across deleted inline nodes."""
        items = list(self.selectedItems())
        selected_nodes = {item for item in items if isinstance(item, BaseNodeItem)}

        # Auto-heal wires across deleted inline nodes (connect predecessors to successors)
        connections_to_heal = []
        for node in selected_nodes:
            incoming = [
                c.start_socket for sock in node.input_sockets for c in sock.connections
                if c.start_socket and c.start_socket.node not in selected_nodes
            ]
            outgoing = [
                c.end_socket for sock in node.output_sockets for c in sock.connections
                if c.end_socket and c.end_socket.node not in selected_nodes
            ]
            for in_sock, out_sock in zip(incoming, outgoing):
                if in_sock and out_sock:
                    connections_to_heal.append((in_sock, out_sock))

        for item in items:
            if isinstance(item, NodeConnection):
                self.remove_connection(item)
            elif isinstance(item, BaseNodeItem):
                self.remove_node(item)
            elif isinstance(item, NodeGroupItem):
                self.remove_group(item)

        # Re-establish healed connections
        for in_sock, out_sock in connections_to_heal:
            self.add_connection(in_sock, out_sock)
