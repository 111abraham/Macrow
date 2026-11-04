"""Interactive viewport for the node graph canvas."""

from __future__ import annotations

import math
import time
from typing import Optional, List, Set, Dict
from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint, QTimer
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
    QCursor,
)
from PyQt6.QtWidgets import (
    QGraphicsView,
    QRubberBand,
    QApplication,
    QMenu,
)

from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.node_items import (
    BaseNodeItem,
    StartNodeItem,
    ActionNodeItem,
    VisionNodeItem,
    IfConditionNodeItem,
    CompareNodeItem,
    TimerNodeItem,
    MathNodeItem,
    PixelColorNodeItem,
    HotkeyNodeItem,
    LoopNodeItem,
    StopNodeItem,
    AIVisionNodeItem,
    StickyNoteNodeItem,
)
from app.ui.node_editor.node_group import NodeGroupItem
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

        # Houdini-style workflow states:
        # 1. A + Drag align anchor
        self._a_key_held = False
        self._a_align_node: Optional[BaseNodeItem] = None
        self._a_align_start_scene_pos: Optional[QPointF] = None

        # 2. Ctrl / Shift branch dragging & toggle selection
        self._branch_drag_nodes: List[QGraphicsItem] = []
        self._branch_drag_prev_scene_pos: Optional[QPointF] = None
        self._ctrl_candidate_item: Optional[QGraphicsItem] = None
        self._ctrl_press_pos: Optional[QPoint] = None
        self._ctrl_initial_selected: bool = False
        self._is_ctrl_branch_drag: bool = False
        self._shift_candidate_item: Optional[QGraphicsItem] = None
        self._shift_press_pos: Optional[QPoint] = None
        self._shift_initial_selected: bool = False
        self._is_shift_branch_drag: bool = False
        self._shift_rubberband_initial_selection: Optional[Set[QGraphicsItem]] = None

        # 3. Shake to disconnect tracker
        self._dragged_node: Optional[BaseNodeItem] = None
        self._shake_samples: List[tuple[float, float, float]] = []
        self._shake_triggered: bool = False

        # 4. Wire drop candidate
        self._hovered_wire: Optional[NodeConnection] = None

        # 5. Multi-selection drag tracking
        self._pending_single_selection: Optional[QGraphicsItem] = None
        self._press_view_pos: Optional[QPoint] = None

        # Space Navigation
        self._space_held = False
        self._last_selected_node: Optional[BaseNodeItem] = None

        # Edge Auto-Panning
        self._edge_scroll_timer = QTimer(self)
        self._edge_scroll_timer.setInterval(20)
        self._edge_scroll_timer.timeout.connect(self._on_edge_scroll_tick)
        self._edge_scroll_delta = QPointF(0, 0)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _get_node_at(self, pos: QPoint) -> Optional[BaseNodeItem]:
        item = self.itemAt(pos)
        curr = item
        while curr:
            if isinstance(curr, BaseNodeItem):
                return curr
            curr = curr.parentItem()
        return None

    def _get_selectable_item_at(self, pos: QPoint) -> Optional[QGraphicsItem]:
        """Returns node item or group item under cursor."""
        item = self.itemAt(pos)
        curr = item
        while curr:
            if isinstance(curr, (BaseNodeItem, NodeGroupItem)):
                return curr
            curr = curr.parentItem()
        return None

    @staticmethod
    def _is_loop_socket(sock) -> bool:
        """Check if socket belongs to a LoopNodeItem (repeat zone)."""
        if not sock or not getattr(sock, "node", None):
            return False
        return isinstance(sock.node, LoopNodeItem)

    def _get_downstream_nodes(self, start_item: QGraphicsItem) -> List[QGraphicsItem]:
        visited = set()
        if isinstance(start_item, NodeGroupItem):
            queue = list(start_item.nodes)
        elif isinstance(start_item, BaseNodeItem):
            queue = [start_item]
        else:
            return []

        result = []

        # Identify any enclosing repeat zones to exclude when dragging enclosed nodes
        enclosing_loops = set()
        if self.node_scene:
            for n in self.node_scene.nodes:
                if isinstance(n, LoopNodeItem):
                    body = n.get_body_nodes()
                    if isinstance(start_item, BaseNodeItem) and (start_item in body or n.sceneBoundingRect().contains(start_item.sceneBoundingRect().center())) and n is not start_item:
                        enclosing_loops.add(n)
                    elif isinstance(start_item, NodeGroupItem) and (any(m in body for m in start_item.nodes) or n.sceneBoundingRect().contains(start_item.sceneBoundingRect().center())):
                        enclosing_loops.add(n)

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            if curr not in enclosing_loops:
                result.append(curr)

            for sock in curr.output_sockets:
                for conn in sock.connections:
                    end_sock = conn.end_socket
                    if end_sock and end_sock.node:
                        target = end_sock.node
                        if target in enclosing_loops:
                            continue
                        if target not in visited:
                            queue.append(target)

        # Include start group itself and any other groups that contain downstream nodes
        items = [n for n in result if n not in enclosing_loops]
        if self.node_scene:
            for grp in getattr(self.node_scene, "groups", []):
                if grp is start_item or any(n in result for n in grp.nodes):
                    if grp not in items:
                        items.append(grp)
                    for n in grp.nodes:
                        if n not in items and n not in enclosing_loops:
                            items.append(n)
        return items

    def _get_upstream_nodes(self, start_item: QGraphicsItem) -> List[QGraphicsItem]:
        visited = set()
        if isinstance(start_item, NodeGroupItem):
            queue = list(start_item.nodes)
        elif isinstance(start_item, BaseNodeItem):
            queue = [start_item]
        else:
            return []

        result = []

        # Identify any enclosing repeat zones to exclude when dragging enclosed nodes
        enclosing_loops = set()
        if self.node_scene:
            for n in self.node_scene.nodes:
                if isinstance(n, LoopNodeItem):
                    body = n.get_body_nodes()
                    if isinstance(start_item, BaseNodeItem) and (start_item in body or n.sceneBoundingRect().contains(start_item.sceneBoundingRect().center())) and n is not start_item:
                        enclosing_loops.add(n)
                    elif isinstance(start_item, NodeGroupItem) and (any(m in body for m in start_item.nodes) or n.sceneBoundingRect().contains(start_item.sceneBoundingRect().center())):
                        enclosing_loops.add(n)

        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            if curr not in enclosing_loops:
                result.append(curr)

            for sock in curr.input_sockets:
                for conn in sock.connections:
                    start_sock = conn.start_socket
                    if start_sock and start_sock.node:
                        target = start_sock.node
                        if target in enclosing_loops:
                            continue
                        if target not in visited:
                            queue.append(target)

        # Include start group itself and any other groups that contain upstream nodes
        items = [n for n in result if n not in enclosing_loops]
        if self.node_scene:
            for grp in getattr(self.node_scene, "groups", []):
                if grp is start_item or any(n in result for n in grp.nodes):
                    if grp not in items:
                        items.append(grp)
                    for n in grp.nodes:
                        if n not in items and n not in enclosing_loops:
                            items.append(n)
        return items

    def _find_nodes_between(self, node_a: BaseNodeItem, node_b: BaseNodeItem) -> Set[BaseNodeItem]:
        """Finds all nodes on the graph path between node_a and node_b for Shift+Click range selection."""
        # 1. Check directed path A -> B
        down_a = {x for x in self._get_downstream_nodes(node_a) if isinstance(x, BaseNodeItem)}
        up_b = {x for x in self._get_upstream_nodes(node_b) if isinstance(x, BaseNodeItem)}
        between_ab = down_a.intersection(up_b)
        if between_ab:
            return between_ab

        # 2. Check directed path B -> A
        down_b = {x for x in self._get_downstream_nodes(node_b) if isinstance(x, BaseNodeItem)}
        up_a = {x for x in self._get_upstream_nodes(node_a) if isinstance(x, BaseNodeItem)}
        between_ba = down_b.intersection(up_a)
        if between_ba:
            return between_ba

        # 3. Check undirected shortest path via BFS across all connections
        adj: Dict[BaseNodeItem, List[BaseNodeItem]] = {}
        for conn in self.node_scene.connections:
            if conn.start_socket and conn.end_socket:
                na, nb = conn.start_socket.node, conn.end_socket.node
                if na and nb:
                    adj.setdefault(na, []).append(nb)
                    adj.setdefault(nb, []).append(na)

        visited = {node_a: None}
        queue = [node_a]
        found = False
        while queue:
            curr = queue.pop(0)
            if curr == node_b:
                found = True
                break
            for neighbor in adj.get(curr, []):
                if neighbor not in visited:
                    visited[neighbor] = curr
                    queue.append(neighbor)

        if found:
            path = set()
            curr = node_b
            while curr is not None:
                path.add(curr)
                curr = visited[curr]
            return path

        return {node_a, node_b}

    def _on_edge_scroll_tick(self):
        if self._edge_scroll_delta.isNull():
            self._edge_scroll_timer.stop()
            return

        # Stop if no left mouse button held and no wire drag active
        if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton) and not getattr(self.node_scene, "_dragging_connection", None):
            self._edge_scroll_timer.stop()
            return

        h_bar = self.horizontalScrollBar()
        v_bar = self.verticalScrollBar()
        h_bar.setValue(int(h_bar.value() + self._edge_scroll_delta.x()))
        v_bar.setValue(int(v_bar.value() + self._edge_scroll_delta.y()))

        global_pos = QCursor.pos()
        view_pos = self.mapFromGlobal(global_pos)
        scene_pos = self.mapToScene(view_pos)

        # 1. Update dragged wire end position if active
        if self.node_scene._dragging_connection:
            snap_target = self.node_scene._find_snap_socket(scene_pos, self.node_scene._drag_start_socket)
            if snap_target != self.node_scene._current_snap_socket:
                if self.node_scene._current_snap_socket:
                    self.node_scene._current_snap_socket.set_snap_target(False)
                self.node_scene._current_snap_socket = snap_target
                if self.node_scene._current_snap_socket:
                    self.node_scene._current_snap_socket.set_snap_target(True)

            if self.node_scene._current_snap_socket:
                self.node_scene._dragging_connection.set_target_pos(self.node_scene._current_snap_socket.scene_pos())
            else:
                self.node_scene._dragging_connection.set_target_pos(scene_pos)

        # 2. Update branch drag if active
        if self._branch_drag_nodes and self._branch_drag_prev_scene_pos:
            delta = scene_pos - self._branch_drag_prev_scene_pos
            self._branch_drag_prev_scene_pos = scene_pos
            for n in self._branch_drag_nodes:
                n.setPos(n.pos() + delta)
                n.update_connected_wires()

        # 3. Update normal dragged node
        if self._dragged_node and not self._branch_drag_nodes:
            move_ev = QMouseEvent(
                QMouseEvent.Type.MouseMove,
                QPointF(view_pos),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.LeftButton,
                QApplication.keyboardModifiers(),
            )
            self.mouseMoveEvent(move_ev)

    def _find_wire_under_node(self, node: QGraphicsItem) -> Optional[NodeConnection]:
        node_rect = node.sceneBoundingRect()
        for conn in self.node_scene.connections:
            if conn.start_socket and conn.end_socket:
                if conn.start_socket.node != node and conn.end_socket.node != node:
                    if isinstance(node, LoopNodeItem):
                        body = node.get_body_nodes()
                        if conn.start_socket.node in body or conn.end_socket.node in body:
                            continue
                    if isinstance(node, NodeGroupItem):
                        grp_nodes = set(node.nodes)
                        if conn.start_socket.node in grp_nodes or conn.end_socket.node in grp_nodes:
                            continue
                    if conn.path().intersects(node_rect) or conn.shape().intersects(node_rect):
                        return conn
        return None

    def _show_quick_add_menu(self, global_pos: QPoint, scene_pos: QPointF):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px;
                color: #e4e4e7;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 11px;
            }
            QMenu::item {
                padding: 5px 22px 5px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #27272a;
                color: #38bdf8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #27272a;
                margin: 4px 6px;
            }
            QMenu::section {
                padding: 4px 10px;
                font-weight: 700;
                font-size: 10px;
                color: #38bdf8;
                letter-spacing: 0.5px;
            }
        """)

        def add_node_item(node_instance):
            self.node_scene.clearSelection()
            self.node_scene.add_node(node_instance, scene_pos)
            node_instance.setSelected(True)
            self.node_scene.scene_modified.emit()

        menu.addSection("MOUSE ACTIONS")
        menu.addAction("🖱 Mouse Click", lambda: add_node_item(ActionNodeItem("click")))
        menu.addAction("🖱 Double Click", lambda: add_node_item(ActionNodeItem("dblclick")))
        menu.addAction("🖱 Mouse Down (Hold)", lambda: add_node_item(ActionNodeItem("down")))
        menu.addAction("🖱 Mouse Up (Release)", lambda: add_node_item(ActionNodeItem("up")))
        menu.addAction("🏹 Mouse Move", lambda: add_node_item(ActionNodeItem("move")))
        menu.addAction("📜 Mouse Wheel Scroll", lambda: add_node_item(ActionNodeItem("wheel")))
        menu.addAction("⏳ Delay / Wait", lambda: add_node_item(ActionNodeItem("delay")))

        menu.addSeparator()
        menu.addSection("KEYBOARD ACTIONS")
        menu.addAction("⌨ Key Press (Tap)", lambda: add_node_item(ActionNodeItem("key_press", {"key": "Enter", "vk": 13})))
        menu.addAction("⌨ Key Down (Hold)", lambda: add_node_item(ActionNodeItem("key_down", {"key": "Shift", "vk": 16})))
        menu.addAction("⌨ Key Up (Release)", lambda: add_node_item(ActionNodeItem("key_up", {"key": "Shift", "vk": 16})))
        menu.addAction("⌨ Key Combo (Hotkey)", lambda: add_node_item(HotkeyNodeItem()))
        menu.addAction("🔤 Type Text", lambda: add_node_item(ActionNodeItem("type")))

        menu.addSeparator()
        menu.addSection("LOGIC & CONDITIONS")
        menu.addAction("🔁 C-Clamp Repeat Zone (Loop)", lambda: add_node_item(LoopNodeItem()))
        menu.addAction("🔀 If Condition (Single)", lambda: add_node_item(IfConditionNodeItem()))
        menu.addAction("⚖ Compare / Logic Gate (AND/OR)", lambda: add_node_item(CompareNodeItem()))
        menu.addAction("⏱️ Timer / Cooldown", lambda: add_node_item(TimerNodeItem()))
        menu.addAction("🎨 Pixel Color Check", lambda: add_node_item(PixelColorNodeItem()))
        menu.addAction("🔢 Math / Variable", lambda: add_node_item(MathNodeItem()))

        menu.addSeparator()
        menu.addSection("VISION AI & MULTIMODAL")
        menu.addAction("🤖 AI Vision Action (VLA Agent)", lambda: add_node_item(AIVisionNodeItem()))
        menu.addAction("⏱ Wait For Image (AI Screen)", lambda: add_node_item(VisionNodeItem()))
        menu.addAction("⏹ Stop Playback", lambda: add_node_item(StopNodeItem()))

        menu.addSeparator()
        menu.addSection("DOCUMENTATION & ANNOTATION")
        menu.addAction("📝 Sticky Note (Canvas Note)", lambda: add_node_item(StickyNoteNodeItem()))

        menu.exec(global_pos)

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

    def focusNextPrevChild(self, next: bool) -> bool:
        """Prevent Tab key from switching widget focus away from the canvas."""
        return False

    def _trigger_shake_disconnect(self, nodes):
        """Disconnects all wires connected to node(s) or group(s). If inline, heals connections between upstream and downstream."""
        if not nodes:
            return
        if not isinstance(nodes, list):
            nodes = [nodes]

        # 1. Handle NodeGroupItem(s) in shaken items:
        # Separate group from external chain, heal external wire, but keep all internal nodes and connections intact!
        groups = [n for n in nodes if isinstance(n, NodeGroupItem)]
        for grp in groups:
            grp_nodes = set(grp.nodes)
            incoming = []
            outgoing = []
            to_remove = []

            for n in grp.nodes:
                in_socks = [n.socket_in] if isinstance(n, LoopNodeItem) else n.input_sockets
                for sock in in_socks:
                    for c in list(sock.connections):
                        if c.start_socket and c.start_socket.node and c.start_socket.node not in grp_nodes:
                            if c.start_socket not in incoming:
                                incoming.append(c.start_socket)
                            if c not in to_remove:
                                to_remove.append(c)

                out_socks = [n.socket_done] if isinstance(n, LoopNodeItem) else n.output_sockets
                for sock in out_socks:
                    for c in list(sock.connections):
                        if c.end_socket and c.end_socket.node and c.end_socket.node not in grp_nodes:
                            if c.end_socket not in outgoing:
                                outgoing.append(c.end_socket)
                            if c not in to_remove:
                                to_remove.append(c)

            for c in to_remove:
                self.node_scene.remove_connection(c)

            # Heal inline connection between predecessor and successor outside the group
            for in_sock, out_sock in zip(incoming, outgoing):
                if in_sock and out_sock:
                    self.node_scene.add_connection(in_sock, out_sock)

            # If this group was inside another group, separate from parent group
            for other_grp in getattr(self.node_scene, "groups", []):
                if other_grp is not grp and grp in getattr(other_grp, "nodes", []):
                    other_grp.remove_node(grp)

        # 2. Handle BaseNodeItem(s) in shaken items
        base_nodes = [n for n in nodes if isinstance(n, BaseNodeItem)]
        if base_nodes:
            node_set = set(base_nodes)

            # External incoming sockets: start sockets from outside nodes leading into this group
            incoming = []
            for n in base_nodes:
                in_socks = [n.socket_in] if isinstance(n, LoopNodeItem) else n.input_sockets
                for sock in in_socks:
                    for c in sock.connections:
                        if c.start_socket and c.start_socket.node and c.start_socket.node not in node_set:
                            if c.start_socket not in incoming:
                                incoming.append(c.start_socket)

            # External outgoing sockets: end sockets on outside nodes receiving from this group
            outgoing = []
            for n in base_nodes:
                out_socks = [n.socket_done] if isinstance(n, LoopNodeItem) else n.output_sockets
                for sock in out_socks:
                    for c in sock.connections:
                        if c.end_socket and c.end_socket.node and c.end_socket.node not in node_set:
                            if c.end_socket not in outgoing:
                                outgoing.append(c.end_socket)

            # Disconnect connections on shaken nodes:
            # For LoopNodeItem, only disconnect external sockets (socket_in and socket_done)
            # keeping socket_body and socket_repeat intact with enclosed body nodes
            to_remove = []
            for n in base_nodes:
                if isinstance(n, LoopNodeItem):
                    target_socks = [n.socket_in, n.socket_done]
                else:
                    target_socks = n.input_sockets + n.output_sockets

                for sock in target_socks:
                    for conn in list(sock.connections):
                        if conn not in to_remove:
                            to_remove.append(conn)
            for conn in to_remove:
                self.node_scene.remove_connection(conn)

            # Heal inline connection between predecessor and successor
            for in_sock, out_sock in zip(incoming, outgoing):
                if in_sock and out_sock:
                    self.node_scene.add_connection(in_sock, out_sock)

            # Shaking individual nodes frees them from any enclosing group container
            for n in base_nodes:
                grp = getattr(n, "group", None)
                if grp:
                    grp.remove_node(n)
                    if not grp.nodes and grp.scene() and hasattr(grp.scene(), "remove_group"):
                        grp.scene().remove_group(grp)
                    else:
                        grp.fit_to_nodes()

        self.node_scene.scene_modified.emit()
        self.node_scene.update_loop_bounds()

    def mousePressEvent(self, event: QMouseEvent):
        # 0. Space + Left click pan navigation with hand cursor
        if event.button() == Qt.MouseButton.LeftButton and self._space_held:
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

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
            target_node = self._get_node_at(event.pos())
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

        # 3. Middle click or Right click panning
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # 4. Check interaction with sockets first (wires, unplugging)
        from app.ui.node_editor.node_socket import NodeSocketItem
        raw_item = self.itemAt(event.pos())
        if isinstance(raw_item, NodeSocketItem):
            super().mousePressEvent(event)
            return

        # 5. Houdini Gestures & Node / Group Selection:
        if event.button() == Qt.MouseButton.LeftButton:
            target_item = self._get_selectable_item_at(event.pos())
            target_node = target_item if isinstance(target_item, BaseNodeItem) else None

            if target_item:
                if target_node and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self._last_selected_node = target_node
                # A + Drag: Align branch horizontally
                if self._a_key_held and target_node:
                    self._a_align_node = target_node
                    self._a_align_start_scene_pos = self.mapToScene(event.pos())
                    event.accept()
                    return

                sel = self.node_scene.selectedItems()
                is_multi_sel = (target_item.isSelected() and len(sel) > 1)

                if is_multi_sel:
                    # Target is part of an existing multi-selection:
                    # Defer potential single click deselect/isolate to mouseRelease, and allow dragging the entire selection!
                    self._pending_single_selection = target_item
                    self._press_view_pos = event.pos()
                    self._dragged_node = target_item
                    scene_pos = self.mapToScene(event.pos())
                    self._shake_samples = [(time.time(), scene_pos.x(), scene_pos.y())]
                    self._shake_triggered = False
                    self.node_scene._current_selected_node = target_item
                    self.node_scene.node_selected.emit(target_item)
                    super().mousePressEvent(event)
                    return

                # Ctrl + Click (toggle selection) or Ctrl + Drag (downstream branch)
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._ctrl_candidate_item = target_item
                    self._ctrl_press_pos = event.pos()
                    self._ctrl_initial_selected = target_item.isSelected()
                    self._is_ctrl_branch_drag = False
                    event.accept()
                    return

                # Shift + Click (add selection) or Shift + Drag (upstream branch)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._shift_candidate_item = target_item
                    self._shift_press_pos = event.pos()
                    self._shift_initial_selected = target_item.isSelected()
                    self._is_shift_branch_drag = False
                    event.accept()
                    return

                # Normal node or group drag: track for shake disconnect and wire auto-insert
                self._dragged_node = target_item
                self._press_view_pos = event.pos()
                now = time.time()
                scene_pos = self.mapToScene(event.pos())
                self._shake_samples = [(now, scene_pos.x(), scene_pos.y())]
                self._shake_triggered = False

                if not target_item.isSelected():
                    self.node_scene.clearSelection()
                    target_item.setSelected(True)
                self._pending_single_selection = None

                self.node_scene._current_selected_node = target_item
                self.node_scene.node_selected.emit(target_item)
            else:
                # Clicked empty canvas: clear selection and empty inspector
                from app.ui.node_editor.node_socket import NodeSocketItem
                if not isinstance(raw_item, NodeSocketItem):
                    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        # Shift + Drag on canvas: retain initial selection to additively combine with rubberband!
                        self._shift_rubberband_initial_selection = set(self.node_scene.selectedItems())
                    elif not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                        self.node_scene._current_selected_node = None
                        self.node_scene.clearSelection()
                        self.node_scene.node_selected.emit(None)

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

        # Houdini A + Drag alignment in progress
        if self._a_align_node:
            event.accept()
            return

        # Check if Ctrl candidate gesture transitioned to a Ctrl + Drag!
        if self._ctrl_candidate_item and not self._is_ctrl_branch_drag and self._ctrl_press_pos:
            if (event.pos() - self._ctrl_press_pos).manhattanLength() > 5:
                self._is_ctrl_branch_drag = True
                self._branch_drag_nodes = self._get_downstream_nodes(self._ctrl_candidate_item)
                self._branch_drag_prev_scene_pos = self.mapToScene(event.pos())
                self.node_scene.clearSelection()
                for n in self._branch_drag_nodes:
                    n.setSelected(True)

        # Check if Shift candidate gesture transitioned to a Shift + Drag!
        if self._shift_candidate_item and not self._is_shift_branch_drag and self._shift_press_pos:
            if (event.pos() - self._shift_press_pos).manhattanLength() > 5:
                self._is_shift_branch_drag = True
                self._branch_drag_nodes = self._get_upstream_nodes(self._shift_candidate_item)
                self._branch_drag_prev_scene_pos = self.mapToScene(event.pos())
                self.node_scene.clearSelection()
                for n in self._branch_drag_nodes:
                    n.setSelected(True)

        # Houdini Ctrl / Shift branch dragging
        if self._branch_drag_nodes and self._branch_drag_prev_scene_pos:
            cur_scene_pos = self.mapToScene(event.pos())
            delta = cur_scene_pos - self._branch_drag_prev_scene_pos
            self._branch_drag_prev_scene_pos = cur_scene_pos
            for n in self._branch_drag_nodes:
                n.setPos(n.pos() + delta)
                if hasattr(n, "update_connected_wires"):
                    n.update_connected_wires()
            event.accept()
            return

        # If dragging confirmed, cancel pending single selection so multi-selection stays active
        if self._pending_single_selection and self._press_view_pos:
            if (event.pos() - self._press_view_pos).manhattanLength() > 4:
                self._pending_single_selection = None

        # Edge auto-panning check when dragging connection or dragging nodes
        is_dragging_item = (
            getattr(self.node_scene, "_dragging_connection", None) is not None
            or self._dragged_node is not None
            or bool(self._branch_drag_nodes)
            or (bool(event.buttons() & Qt.MouseButton.LeftButton) and len(self.node_scene.selectedItems()) > 0)
        )
        if is_dragging_item and not self._is_panning and not self._is_cutting:
            vr = self.viewport().rect()
            p = event.pos()
            margin = 50.0
            dx = 0.0
            dy = 0.0

            if p.x() < margin:
                dx = -max(4.0, (margin - p.x()) * 0.4)
            elif p.x() > vr.width() - margin:
                dx = max(4.0, (p.x() - (vr.width() - margin)) * 0.4)

            if p.y() < margin:
                dy = -max(4.0, (margin - p.y()) * 0.4)
            elif p.y() > vr.height() - margin:
                dy = max(4.0, (p.y() - (vr.height() - margin)) * 0.4)

            if dx != 0.0 or dy != 0.0:
                self._edge_scroll_delta = QPointF(dx, dy)
                if not self._edge_scroll_timer.isActive():
                    self._edge_scroll_timer.start()
            else:
                self._edge_scroll_delta = QPointF(0.0, 0.0)
                self._edge_scroll_timer.stop()
        else:
            if self._edge_scroll_timer.isActive():
                self._edge_scroll_delta = QPointF(0.0, 0.0)
                self._edge_scroll_timer.stop()

        super().mouseMoveEvent(event)

        # Shake detection and wire drop target detection during node or group drag
        if self._dragged_node and not self._is_cutting and not self._is_panning:
            now = time.time()
            scene_pos = self.mapToScene(event.pos())
            self._shake_samples = [s for s in self._shake_samples if now - s[0] <= 0.45]
            self._shake_samples.append((now, scene_pos.x(), scene_pos.y()))

            # Shake detection: check for rapid horizontal oscillations (>= 3 reversals, >= 70px travel)
            if not self._shake_triggered and len(self._shake_samples) >= 5:
                reversals = 0
                prev_dir = 0
                total_travel = 0.0
                for i in range(1, len(self._shake_samples)):
                    dx = self._shake_samples[i][1] - self._shake_samples[i - 1][1]
                    total_travel += abs(dx)
                    if abs(dx) > 8.0:
                        cur_dir = 1 if dx > 0 else -1
                        if prev_dir != 0 and cur_dir != prev_dir:
                            reversals += 1
                        prev_dir = cur_dir

                if reversals >= 3 and total_travel >= 70.0:
                    sel_nodes = [item for item in self.node_scene.selectedItems() if isinstance(item, (BaseNodeItem, NodeGroupItem))]
                    if not sel_nodes or self._dragged_node not in sel_nodes:
                        sel_nodes = [self._dragged_node]
                    self._trigger_shake_disconnect(sel_nodes)
                    self._shake_triggered = True

            # Wire hover detection for inserting node or group into a wire:
            can_insert = False
            if isinstance(self._dragged_node, LoopNodeItem):
                can_insert = (len(self._dragged_node.socket_in.connections) == 0 and
                              len(self._dragged_node.socket_done.connections) == 0)
            elif isinstance(self._dragged_node, NodeGroupItem):
                if self._dragged_node.nodes:
                    grp_nodes = set(self._dragged_node.nodes)
                    has_ext = False
                    for gn in self._dragged_node.nodes:
                        socks = [gn.socket_in, gn.socket_done] if isinstance(gn, LoopNodeItem) else (gn.input_sockets + gn.output_sockets)
                        for s in socks:
                            for c in s.connections:
                                other = c.start_socket.node if c.end_socket == s else c.end_socket.node
                                if other not in grp_nodes:
                                    has_ext = True
                                    break
                            if has_ext:
                                break
                        if has_ext:
                            break
                    can_insert = not has_ext
            elif isinstance(self._dragged_node, BaseNodeItem):
                has_in_conn = any(len(s.connections) > 0 for s in self._dragged_node.input_sockets)
                has_out_conn = any(len(s.connections) > 0 for s in self._dragged_node.output_sockets)
                can_insert = (not has_in_conn and not has_out_conn)

            if can_insert:
                candidate = self._find_wire_under_node(self._dragged_node)
                if candidate != self._hovered_wire:
                    if self._hovered_wire:
                        self._hovered_wire.is_drop_target = False
                        self._hovered_wire.update()
                    self._hovered_wire = candidate
                    if self._hovered_wire:
                        self._hovered_wire.is_drop_target = True
                        self._hovered_wire.update()
            else:
                if self._hovered_wire:
                    self._hovered_wire.is_drop_target = False
                    self._hovered_wire.update()
                    self._hovered_wire = None

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._edge_scroll_timer.stop()
        self._edge_scroll_delta = QPointF(0, 0)

        if self._is_cutting and event.button() == Qt.MouseButton.LeftButton:
            self._is_cutting = False
            self._cut_path_points.clear()
            if not self._y_key_held:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            self.viewport().update()
            event.accept()
            return

        if self._is_panning and (event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton)):
            self._is_panning = False
            if self._space_held:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif not self._y_key_held:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        # Houdini A + Drag alignment commit
        if self._a_align_node and self._a_align_start_scene_pos:
            cur_scene_pos = self.mapToScene(event.pos())
            dx = cur_scene_pos.x() - self._a_align_start_scene_pos.x()
            anchor = self._a_align_node
            anchor_y = anchor.pos().y()
            anchor_x = anchor.pos().x()
            anchor_w = anchor.clamp_width if hasattr(anchor, "clamp_width") else getattr(anchor, "width", 150.0)

            # Check if anchor is inside a loop's body nodes
            enclosing_loop = None
            if self.node_scene:
                for ln in self.node_scene.nodes:
                    if isinstance(ln, LoopNodeItem) and anchor in ln.get_body_nodes():
                        enclosing_loop = ln
                        break

            affected_groups = set()
            if getattr(anchor, "group", None):
                affected_groups.add(anchor.group)

            if dx > 25.0:
                # Right drag: Align downstream connected nodes
                downstream = self._get_downstream_nodes(anchor)
                others = [n for n in downstream if n != anchor and isinstance(n, BaseNodeItem)]

                if enclosing_loop:
                    body_set = set(enclosing_loop.get_body_nodes())
                    others = [n for n in others if n in body_set]
                else:
                    others = [n for n in others if not isinstance(n, LoopNodeItem)]

                others.sort(key=lambda n: n.pos().x())
                curr_x = anchor_x + anchor_w + 50.0
                for n in others:
                    n.setPos(curr_x, anchor_y)
                    if hasattr(n, "update_connected_wires"):
                        n.update_connected_wires()
                    nw = n.clamp_width if hasattr(n, "clamp_width") else getattr(n, "width", 150.0)
                    curr_x += nw + 50.0
                    if getattr(n, "group", None):
                        affected_groups.add(n.group)

                for grp in affected_groups:
                    grp.fit_to_nodes()

                self.node_scene.scene_modified.emit()
                self.node_scene.update_loop_bounds()
            elif dx < -25.0:
                # Left drag: Align upstream connected nodes
                upstream = self._get_upstream_nodes(anchor)
                others = [n for n in upstream if n != anchor and isinstance(n, BaseNodeItem)]

                if enclosing_loop:
                    body_set = set(enclosing_loop.get_body_nodes())
                    others = [n for n in others if n in body_set]
                else:
                    others = [n for n in others if not isinstance(n, LoopNodeItem)]

                others.sort(key=lambda n: n.pos().x(), reverse=True)
                curr_right = anchor_x - 50.0
                for n in others:
                    nw = n.clamp_width if hasattr(n, "clamp_width") else getattr(n, "width", 150.0)
                    target_x = curr_right - nw
                    n.setPos(target_x, anchor_y)
                    if hasattr(n, "update_connected_wires"):
                        n.update_connected_wires()
                    curr_right = target_x - 50.0
                    if getattr(n, "group", None):
                        affected_groups.add(n.group)

                for grp in affected_groups:
                    grp.fit_to_nodes()

                self.node_scene.scene_modified.emit()
                self.node_scene.update_loop_bounds()

            self._a_align_node = None
            self._a_align_start_scene_pos = None
            event.accept()
            return

        # Houdini branch drag release
        if self._branch_drag_nodes:
            self._branch_drag_nodes = []
            self._branch_drag_prev_scene_pos = None
            self.node_scene.scene_modified.emit()
            self.node_scene.update_loop_bounds()
            event.accept()
            return

        # Houdini Wire Splice on node drop
        if self._hovered_wire and self._dragged_node:
            wire = self._hovered_wire
            wire.is_drop_target = False
            wire.update()
            self._hovered_wire = None

            src_sock = wire.start_socket
            dst_sock = wire.end_socket
            dst_node = dst_sock.node if dst_sock else None

            if src_sock and dst_sock:
                spliced = False
                if isinstance(self._dragged_node, LoopNodeItem):
                    self.node_scene.remove_connection(wire)
                    self.node_scene.add_connection(src_sock, self._dragged_node.socket_in)
                    self.node_scene.add_connection(self._dragged_node.socket_done, dst_sock)
                    spliced = True
                elif isinstance(self._dragged_node, NodeGroupItem) and self._dragged_node.nodes:
                    grp_nodes = set(self._dragged_node.nodes)
                    in_candidates = []
                    for gn in self._dragged_node.nodes:
                        in_s = gn.socket_in if isinstance(gn, LoopNodeItem) else (gn.input_sockets[0] if gn.input_sockets else None)
                        if in_s:
                            has_int_in = any(c.start_socket and c.start_socket.node in grp_nodes for c in in_s.connections)
                            in_candidates.append((has_int_in, gn.pos().x(), in_s))
                    in_candidates.sort(key=lambda x: (x[0], x[1]))

                    out_candidates = []
                    for gn in self._dragged_node.nodes:
                        out_s = gn.socket_done if isinstance(gn, LoopNodeItem) else (gn.output_sockets[0] if gn.output_sockets else None)
                        if out_s:
                            has_int_out = any(c.end_socket and c.end_socket.node in grp_nodes for c in out_s.connections)
                            out_candidates.append((has_int_out, -gn.pos().x(), out_s))
                    out_candidates.sort(key=lambda x: (x[0], x[1]))

                    if in_candidates and out_candidates:
                        entry_sock = in_candidates[0][2]
                        exit_sock = out_candidates[0][2]
                        self.node_scene.remove_connection(wire)
                        self.node_scene.add_connection(src_sock, entry_sock)
                        self.node_scene.add_connection(exit_sock, dst_sock)
                        spliced = True
                elif isinstance(self._dragged_node, BaseNodeItem) and self._dragged_node.input_sockets and self._dragged_node.output_sockets:
                    self.node_scene.remove_connection(wire)
                    self.node_scene.add_connection(src_sock, self._dragged_node.input_sockets[0])
                    self.node_scene.add_connection(self._dragged_node.output_sockets[0], dst_sock)
                    spliced = True

                # Push destination node and all downstream nodes right to avoid overlap
                if spliced and dst_node:
                    if isinstance(self._dragged_node, NodeGroupItem):
                        dragged_w = self._dragged_node.rect().width()
                    elif isinstance(self._dragged_node, LoopNodeItem):
                        dragged_w = self._dragged_node.clamp_width
                    else:
                        dragged_w = getattr(self._dragged_node, "width", 150.0)

                    node_right = self._dragged_node.pos().x() + dragged_w + 50.0
                    shift_x = max(dragged_w + 50.0, node_right - dst_node.pos().x())

                    downstream = self._get_downstream_nodes(dst_node)

                    # Collect body nodes of all LoopNodeItems in downstream so they aren't moved twice
                    loop_body_nodes = set()
                    for d in downstream:
                        if isinstance(d, LoopNodeItem):
                            loop_body_nodes.update(d.get_body_nodes())

                    # Collect member nodes of all NodeGroupItems in downstream
                    group_member_nodes = set()
                    for d in downstream:
                        if isinstance(d, NodeGroupItem):
                            group_member_nodes.update(d.nodes)

                    for d_node in downstream:
                        # Skip body nodes of loops and member nodes of groups to prevent double movement!
                        if d_node in loop_body_nodes:
                            continue
                        if d_node in group_member_nodes and not isinstance(d_node, LoopNodeItem):
                            continue
                        d_node.setPos(d_node.pos().x() + shift_x, d_node.pos().y())
                        if hasattr(d_node, "update_connected_wires"):
                            d_node.update_connected_wires()

                self.node_scene.scene_modified.emit()
                self.node_scene.update_loop_bounds()

        if self._hovered_wire:
            self._hovered_wire.is_drop_target = False
            self._hovered_wire.update()
            self._hovered_wire = None

        # Handle Ctrl + Click (toggle selection)
        if self._ctrl_candidate_item:
            if not self._is_ctrl_branch_drag:
                # User performed Ctrl + Click (clicked without dragging)
                if self._ctrl_initial_selected:
                    self._ctrl_candidate_item.setSelected(False)
                else:
                    self._ctrl_candidate_item.setSelected(True)
                    self.node_scene._current_selected_node = self._ctrl_candidate_item
                    self.node_scene.node_selected.emit(self._ctrl_candidate_item)
            self._ctrl_candidate_item = None
            self._is_ctrl_branch_drag = False

        # Handle Shift + Click (range selection along graph path)
        if self._shift_candidate_item:
            if not self._is_shift_branch_drag:
                cand_node = self._shift_candidate_item if isinstance(self._shift_candidate_item, BaseNodeItem) else None
                if cand_node and self._last_selected_node and self._last_selected_node != cand_node and cand_node.scene() == self.node_scene:
                    path_nodes = self._find_nodes_between(self._last_selected_node, cand_node)
                    for n in path_nodes:
                        n.setSelected(True)
                    self.node_scene._current_selected_node = cand_node
                    self.node_scene.node_selected.emit(cand_node)
                    self._last_selected_node = cand_node
                else:
                    self._shift_candidate_item.setSelected(True)
                    if cand_node:
                        self._last_selected_node = cand_node
                    self.node_scene._current_selected_node = self._shift_candidate_item
                    self.node_scene.node_selected.emit(self._shift_candidate_item)
            self._shift_candidate_item = None
            self._is_shift_branch_drag = False

        # If user clicked on a node within a multi-selection without dragging, handle click toggle / isolation
        if self._pending_single_selection and self._press_view_pos:
            if (event.pos() - self._press_view_pos).manhattanLength() <= 4:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._pending_single_selection.setSelected(False)
                elif not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                    self.node_scene.clearSelection()
                    self._pending_single_selection.setSelected(True)
                    self.node_scene._current_selected_node = self._pending_single_selection
                    self.node_scene.node_selected.emit(self._pending_single_selection)
            self._pending_single_selection = None
        self._press_view_pos = None

        self._dragged_node = None
        self._shake_samples.clear()
        self._shake_triggered = False

        super().mouseReleaseEvent(event)
        self.node_scene.update_loop_bounds()

        # If user did a Shift + Drag (rubberband) across empty canvas, retain initial selection
        if getattr(self, "_shift_rubberband_initial_selection", None) is not None:
            for item in self._shift_rubberband_initial_selection:
                item.setSelected(True)
            self._shift_rubberband_initial_selection = None

        # Ensure all selected items update their connected wires after multi-drag
        for sel_item in self.node_scene.selectedItems():
            if isinstance(sel_item, BaseNodeItem):
                sel_item.update_connected_wires()

        if event.button() == Qt.MouseButton.LeftButton:
            self.node_scene.scene_modified.emit()

    def keyPressEvent(self, event: QKeyEvent):
        # Space: Pan Navigation with Hand Cursor
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            if not self._is_panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return

        # Tab: Quick Add Node popup menu under cursor
        if event.key() == Qt.Key.Key_Tab:
            global_pos = QCursor.pos()
            view_pos = self.mapFromGlobal(global_pos)
            scene_pos = self.mapToScene(view_pos)
            self._show_quick_add_menu(global_pos, scene_pos)
            event.accept()
            return

        # A key alone: Track held state for A + Drag alignment
        if event.key() == Qt.Key.Key_A and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self._a_key_held = True

        # R key: Frame selected node(s) in middle (or all nodes if none selected)
        if event.key() == Qt.Key.Key_R and not event.modifiers():
            self.frame_selected()
            event.accept()
            return

        # B key: Toggle bypass on selected nodes
        if event.key() == Qt.Key.Key_B and not event.modifiers():
            self.node_scene.toggle_bypass_selected()
            event.accept()
            return

        # Ctrl+A: Select all nodes
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier) and event.key() == Qt.Key.Key_A:
            for n in self.node_scene.nodes:
                n.setSelected(True)
            event.accept()
            return

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
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._is_panning and not self._is_cutting and not self._y_key_held:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.key() == Qt.Key.Key_A:
            self._a_key_held = False

        if event.key() == Qt.Key.Key_Y:
            self._y_key_held = False
            if not self._is_cutting:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        self._space_held = False
        self._a_key_held = False
        self._y_key_held = False
        self._edge_scroll_timer.stop()
        self._edge_scroll_delta = QPointF(0, 0)
        super().focusOutEvent(event)

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

    def frame_selected(self):
        """Frame/fit selected nodes in the middle of the viewport (or all nodes if none selected)."""
        sel_nodes = [item for item in self.node_scene.selectedItems() if isinstance(item, BaseNodeItem)]
        if sel_nodes:
            rect = QRectF()
            for n in sel_nodes:
                rect = rect.united(n.sceneBoundingRect())
            margin = 90.0
            target = rect.adjusted(-margin, -margin, margin, margin)
            self.fitInView(target, Qt.AspectRatioMode.KeepAspectRatio)
            cur_scale = self.transform().m11()
            if cur_scale > 1.3:
                factor = 1.3 / cur_scale
                self.scale(factor, factor)
            elif cur_scale < 0.2:
                factor = 0.2 / cur_scale
                self.scale(factor, factor)
            self.current_zoom = max(0.15, min(3.0, self.transform().m11()))
        else:
            self.fit_all()

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
