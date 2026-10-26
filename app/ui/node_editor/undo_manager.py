"""Undo and Redo Manager for the Macro Node Graph Editor."""

from __future__ import annotations

import copy
from typing import List, Dict, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QPointF

from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.node_items import (
    BaseNodeItem,
    StartNodeItem,
    ActionNodeItem,
    VisionNodeItem,
    IfConditionNodeItem,
    MathNodeItem,
    PixelColorNodeItem,
    HotkeyNodeItem,
    LoopNodeItem,
    StopNodeItem,
)


NODE_CLASS_MAP = {
    "StartNodeItem": StartNodeItem,
    "ActionNodeItem": ActionNodeItem,
    "VisionNodeItem": VisionNodeItem,
    "IfConditionNodeItem": IfConditionNodeItem,
    "MathNodeItem": MathNodeItem,
    "PixelColorNodeItem": PixelColorNodeItem,
    "HotkeyNodeItem": HotkeyNodeItem,
    "LoopNodeItem": LoopNodeItem,
    "StopNodeItem": StopNodeItem,
}


def serialize_scene(scene: NodeScene) -> Dict[str, Any]:
    """Captures full state of the node scene into a serializable snapshot."""
    nodes_data = []
    for node in scene.nodes:
        nodes_data.append({
            "id": getattr(node, "id", None) or hex(id(node)),
            "class_name": node.__class__.__name__,
            "node_type": node.node_type,
            "title": getattr(node, "title", "Node"),
            "pos": (node.pos().x(), node.pos().y()),
            "properties": copy.deepcopy(node.properties),
        })

    connections_data = []
    for conn in scene.connections:
        s_sock = conn.start_socket
        e_sock = conn.end_socket
        if s_sock and e_sock and s_sock.node and e_sock.node:
            s_idx = s_sock.node.output_sockets.index(s_sock) if s_sock in s_sock.node.output_sockets else 0
            e_idx = e_sock.node.input_sockets.index(e_sock) if e_sock in e_sock.node.input_sockets else 0
            connections_data.append({
                "from_node": getattr(s_sock.node, "id", None) or hex(id(s_sock.node)),
                "from_socket_idx": s_idx,
                "to_node": getattr(e_sock.node, "id", None) or hex(id(e_sock.node)),
                "to_socket_idx": e_idx,
            })

    groups_data = []
    for grp in scene.groups:
        groups_data.append({
            "title": grp.title,
            "node_ids": [getattr(n, "id", None) or hex(id(n)) for n in grp.nodes],
        })

    return {
        "nodes": nodes_data,
        "connections": connections_data,
        "groups": groups_data,
    }


def deserialize_scene(scene: NodeScene, data: Dict[str, Any]):
    """Rebuilds the scene from a snapshot dictionary."""
    scene.clear()
    scene.nodes.clear()
    scene.connections.clear()
    scene.groups.clear()

    id_to_node = {}

    # 1. Recreate Nodes
    for nd in data.get("nodes", []):
        cls_name = nd.get("class_name", "ActionNodeItem")
        cls = NODE_CLASS_MAP.get(cls_name, ActionNodeItem)
        props = copy.deepcopy(nd.get("properties", {}))
        node_type = nd.get("node_type", "click")

        if cls is StartNodeItem:
            node = StartNodeItem()
        elif cls is ActionNodeItem:
            node = ActionNodeItem(action_type=node_type, properties=props)
        elif cls is VisionNodeItem:
            node = VisionNodeItem(vision_type=node_type, properties=props)
        else:
            node = cls(properties=props)

        node.id = nd.get("id")
        pos = nd.get("pos", (0, 0))
        scene.add_node(node, QPointF(pos[0], pos[1]))
        id_to_node[node.id] = node

    # 2. Reconnect Wires
    for cd in data.get("connections", []):
        src = id_to_node.get(cd.get("from_node"))
        dst = id_to_node.get(cd.get("to_node"))
        if src and dst:
            s_idx = cd.get("from_socket_idx", 0)
            e_idx = cd.get("to_socket_idx", 0)
            if s_idx < len(src.output_sockets) and e_idx < len(dst.input_sockets):
                scene.add_connection(src.output_sockets[s_idx], dst.input_sockets[e_idx])

    # 3. Recreate Groups
    for gd in data.get("groups", []):
        grp_nodes = [id_to_node[nid] for nid in gd.get("node_ids", []) if nid in id_to_node]
        scene.add_group(title=gd.get("title", "Group"), nodes=grp_nodes)


class UndoManager(QObject):
    """Manages undo and redo stacks for the node graph editor."""

    state_changed = pyqtSignal()

    def __init__(self, scene: NodeScene, max_depth: int = 50, parent=None):
        super().__init__(parent)
        self.scene = scene
        self.max_depth = max_depth
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        self.is_operating = False

    def push_state(self):
        """Pushes current scene snapshot onto the undo stack."""
        if self.is_operating:
            return

        snapshot = serialize_scene(self.scene)
        # Avoid duplicate consecutive snapshots
        if self.undo_stack and self._snapshots_equal(self.undo_stack[-1], snapshot):
            return

        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.max_depth:
            self.undo_stack.pop(0)

        self.redo_stack.clear()
        self.state_changed.emit()

    def undo(self) -> bool:
        """Restores previous state from undo stack."""
        if len(self.undo_stack) <= 1:
            return False

        self.is_operating = True
        try:
            curr_state = self.undo_stack.pop()
            self.redo_stack.append(curr_state)
            prev_state = self.undo_stack[-1]
            deserialize_scene(self.scene, prev_state)
            self.state_changed.emit()
            return True
        finally:
            self.is_operating = False

    def redo(self) -> bool:
        """Restores next state from redo stack."""
        if not self.redo_stack:
            return False

        self.is_operating = True
        try:
            next_state = self.redo_stack.pop()
            self.undo_stack.append(next_state)
            deserialize_scene(self.scene, next_state)
            self.state_changed.emit()
            return True
        finally:
            self.is_operating = False

    def can_undo(self) -> bool:
        return len(self.undo_stack) > 1

    def can_redo(self) -> bool:
        return len(self.redo_stack) > 0

    def _snapshots_equal(self, a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """Quick equality comparison between two snapshots."""
        try:
            if len(a.get("nodes", [])) != len(b.get("nodes", [])):
                return False
            if len(a.get("connections", [])) != len(b.get("connections", [])):
                return False
            if len(a.get("groups", [])) != len(b.get("groups", [])):
                return False
            for na, nb in zip(a.get("nodes", []), b.get("nodes", [])):
                if na.get("id") != nb.get("id"):
                    return False
                if na.get("pos") != nb.get("pos"):
                    return False
                if na.get("properties") != nb.get("properties"):
                    return False
            return True
        except Exception:
            return False
