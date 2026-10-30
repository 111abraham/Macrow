"""Interactive viewport for the node graph canvas."""

from __future__ import annotations

import math
import time
from typing import Optional, List
from PyQt6.QtCore import Qt, QRectF, QPointF, QPoint
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
    MathNodeItem,
    PixelColorNodeItem,
    HotkeyNodeItem,
    LoopNodeItem,
    StopNodeItem,
)
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

        # 2. Ctrl / Shift branch dragging
        self._branch_drag_nodes: List[BaseNodeItem] = []
        self._branch_drag_prev_scene_pos: Optional[QPointF] = None

        # 3. Shake to disconnect tracker
        self._dragged_node: Optional[BaseNodeItem] = None
        self._shake_samples: List[tuple[float, float, float]] = []
        self._shake_triggered: bool = False

        # 4. Wire drop candidate
        self._hovered_wire: Optional[NodeConnection] = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _get_node_at(self, pos: QPoint) -> Optional[BaseNodeItem]:
        item = self.itemAt(pos)
        curr = item
        while curr:
            if isinstance(curr, BaseNodeItem):
                return curr
            curr = curr.parentItem()
        return None

    def _get_downstream_nodes(self, start_node: BaseNodeItem) -> List[BaseNodeItem]:
        visited = set()
        queue = [start_node]
        result = []
        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            result.append(curr)
            for sock in curr.output_sockets:
                for conn in sock.connections:
                    if conn.end_socket and conn.end_socket.node and conn.end_socket.node not in visited:
                        queue.append(conn.end_socket.node)
        return result

    def _get_upstream_nodes(self, start_node: BaseNodeItem) -> List[BaseNodeItem]:
        visited = set()
        queue = [start_node]
        result = []
        while queue:
            curr = queue.pop(0)
            if curr in visited:
                continue
            visited.add(curr)
            result.append(curr)
            for sock in curr.input_sockets:
                for conn in sock.connections:
                    if conn.start_socket and conn.start_socket.node and conn.start_socket.node not in visited:
                        queue.append(conn.start_socket.node)
        return result

    def _find_wire_under_node(self, node: BaseNodeItem) -> Optional[NodeConnection]:
        node_rect = node.sceneBoundingRect()
        for conn in self.node_scene.connections:
            if conn.start_socket and conn.end_socket:
                if conn.start_socket.node != node and conn.end_socket.node != node:
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
        menu.addAction("🔀 If / Compare Condition", lambda: add_node_item(IfConditionNodeItem()))
        menu.addAction("🎨 Pixel Color Check", lambda: add_node_item(PixelColorNodeItem()))
        menu.addAction("🔢 Math / Variable", lambda: add_node_item(MathNodeItem()))

        menu.addSeparator()
        menu.addSection("VISION AI & CONTROL")
        menu.addAction("⏱ Wait For Image (AI Screen)", lambda: add_node_item(VisionNodeItem()))
        menu.addAction("🎯 Loop Until Image Found", lambda: add_node_item(VisionNodeItem(properties={"break_loop_on_found": True})))
        menu.addAction("⏹ Stop Playback", lambda: add_node_item(StopNodeItem()))

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

    def _trigger_shake_disconnect(self, node: BaseNodeItem):
        """Disconnects all wires connected to node. If inline, heals connections between upstream and downstream."""
        incoming = [
            c.start_socket for sock in node.input_sockets for c in sock.connections
            if c.start_socket and c.start_socket.node != node
        ]
        outgoing = [
            c.end_socket for sock in node.output_sockets for c in sock.connections
            if c.end_socket and c.end_socket.node != node
        ]

        # Disconnect all existing connections on node
        to_remove = []
        for sock in node.input_sockets + node.output_sockets:
            for conn in list(sock.connections):
                if conn not in to_remove:
                    to_remove.append(conn)
        for conn in to_remove:
            self.node_scene.remove_connection(conn)

        # Heal inline connection between predecessor and successor
        for in_sock, out_sock in zip(incoming, outgoing):
            if in_sock and out_sock:
                self.node_scene.add_connection(in_sock, out_sock)

        self.node_scene.scene_modified.emit()

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

        # 5. Houdini Gestures on Nodes:
        if event.button() == Qt.MouseButton.LeftButton:
            target_node = self._get_node_at(event.pos())
            if target_node:
                # A + Drag: Align branch horizontally
                if self._a_key_held:
                    self._a_align_node = target_node
                    self._a_align_start_scene_pos = self.mapToScene(event.pos())
                    event.accept()
                    return

                # Ctrl + Drag: Move downstream branch (all nodes connected to right)
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._branch_drag_nodes = self._get_downstream_nodes(target_node)
                    self._branch_drag_prev_scene_pos = self.mapToScene(event.pos())
                    self.node_scene.clearSelection()
                    for n in self._branch_drag_nodes:
                        n.setSelected(True)
                    event.accept()
                    return

                # Shift + Drag: Move upstream branch (all nodes connected to left)
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._branch_drag_nodes = self._get_upstream_nodes(target_node)
                    self._branch_drag_prev_scene_pos = self.mapToScene(event.pos())
                    self.node_scene.clearSelection()
                    for n in self._branch_drag_nodes:
                        n.setSelected(True)
                    event.accept()
                    return

                # Normal node drag: track for shake disconnect and wire auto-insert
                self._dragged_node = target_node
                now = time.time()
                self._shake_samples = [(now, target_node.pos().x(), target_node.pos().y())]
                self._shake_triggered = False

                # Ensure clicking a node immediately focuses and updates Property Inspector
                if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                    sel = self.node_scene.selectedItems()
                    if len(sel) > 1 or (len(sel) == 1 and sel[0] is not target_node):
                        self.node_scene.clearSelection()
                        target_node.setSelected(True)
                self.node_scene._current_selected_node = target_node
                self.node_scene.node_selected.emit(target_node)
            else:
                # Clicked empty canvas: clear selection and empty inspector
                from app.ui.node_editor.node_socket import NodeSocketItem
                if not isinstance(raw_item, NodeSocketItem) and not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
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

        # Houdini Ctrl / Shift branch dragging
        if self._branch_drag_nodes and self._branch_drag_prev_scene_pos:
            cur_scene_pos = self.mapToScene(event.pos())
            delta = cur_scene_pos - self._branch_drag_prev_scene_pos
            self._branch_drag_prev_scene_pos = cur_scene_pos
            for n in self._branch_drag_nodes:
                n.setPos(n.pos() + delta)
                n.update_connected_wires()
            event.accept()
            return

        super().mouseMoveEvent(event)

        # Shake detection and wire drop target detection during node drag
        if self._dragged_node and not self._is_cutting and not self._is_panning:
            now = time.time()
            cur_pos = self._dragged_node.pos()
            self._shake_samples = [s for s in self._shake_samples if now - s[0] <= 0.45]
            self._shake_samples.append((now, cur_pos.x(), cur_pos.y()))

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
                    self._trigger_shake_disconnect(self._dragged_node)
                    self._shake_triggered = True

            # Wire hover detection for inserting node into a wire:
            # Check if this node is unconnected on its primary in/out sockets
            has_in_conn = any(len(s.connections) > 0 for s in self._dragged_node.input_sockets)
            has_out_conn = any(len(s.connections) > 0 for s in self._dragged_node.output_sockets)
            if not has_in_conn and not has_out_conn:
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
            anchor_w = anchor.width

            if dx > 25.0:
                # Right drag: Align downstream connected nodes
                downstream = self._get_downstream_nodes(anchor)
                others = [n for n in downstream if n != anchor]
                others.sort(key=lambda n: n.pos().x())
                curr_x = anchor_x + anchor_w + 50.0
                for n in others:
                    n.setPos(curr_x, anchor_y)
                    n.update_connected_wires()
                    curr_x += n.width + 50.0
                self.node_scene.scene_modified.emit()
            elif dx < -25.0:
                # Left drag: Align upstream connected nodes
                upstream = self._get_upstream_nodes(anchor)
                others = [n for n in upstream if n != anchor]
                others.sort(key=lambda n: n.pos().x(), reverse=True)
                curr_right = anchor_x - 50.0
                for n in others:
                    target_x = curr_right - n.width
                    n.setPos(target_x, anchor_y)
                    n.update_connected_wires()
                    curr_right = target_x - 50.0
                self.node_scene.scene_modified.emit()

            self._a_align_node = None
            self._a_align_start_scene_pos = None
            event.accept()
            return

        # Houdini branch drag release
        if self._branch_drag_nodes:
            self._branch_drag_nodes = []
            self._branch_drag_prev_scene_pos = None
            self.node_scene.scene_modified.emit()
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

            if src_sock and dst_sock and self._dragged_node.input_sockets and self._dragged_node.output_sockets:
                self.node_scene.remove_connection(wire)
                self.node_scene.add_connection(src_sock, self._dragged_node.input_sockets[0])
                self.node_scene.add_connection(self._dragged_node.output_sockets[0], dst_sock)

                # Push destination node and all downstream nodes right to avoid overlap
                if dst_node:
                    node_right = self._dragged_node.pos().x() + self._dragged_node.width + 50.0
                    shift_x = max(self._dragged_node.width + 50.0, node_right - dst_node.pos().x())
                    downstream = self._get_downstream_nodes(dst_node)
                    for d_node in downstream:
                        d_node.setPos(d_node.pos().x() + shift_x, d_node.pos().y())
                        d_node.update_connected_wires()

                self.node_scene.scene_modified.emit()

        if self._hovered_wire:
            self._hovered_wire.is_drop_target = False
            self._hovered_wire.update()
            self._hovered_wire = None

        self._dragged_node = None
        self._shake_samples.clear()
        self._shake_triggered = False

        super().mouseReleaseEvent(event)
        self.node_scene.update_loop_bounds()
        if event.button() == Qt.MouseButton.LeftButton:
            self.node_scene.scene_modified.emit()

    def keyPressEvent(self, event: QKeyEvent):
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
        if event.key() == Qt.Key.Key_A:
            self._a_key_held = False

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
