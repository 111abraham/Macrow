import unittest
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPointF

if QApplication.instance() is None:
    app = QApplication(sys.argv)

from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.node_items import (
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
from app.ui.node_editor.node_view import NodeView
from app.ui.node_editor.graph_compiler import macro_to_graph, graph_to_macro
from app.ui.node_editor.node_group import NodeGroupItem


class TestNodeEditor(unittest.TestCase):
    def setUp(self):
        self.scene = NodeScene()

    def test_start_node_and_action_node(self):
        start = StartNodeItem()
        self.scene.add_node(start, QPointF(50, 100))
        self.assertEqual(len(start.output_sockets), 1)
        self.assertEqual(len(start.input_sockets), 0)

        click_node = ActionNodeItem("click", {"x": 500, "y": 300, "button": "left"})
        self.scene.add_node(click_node, QPointF(300, 100))
        self.assertEqual(len(click_node.input_sockets), 1)
        self.assertEqual(len(click_node.output_sockets), 1)

        # Wire start to click
        conn = self.scene.add_connection(start.output_sockets[0], click_node.input_sockets[0])
        self.assertIsNotNone(conn)
        self.assertEqual(len(self.scene.connections), 1)

    def test_vision_node_sockets(self):
        vnode = VisionNodeItem("find_image", {"template": "test.png", "confidence": 0.9})
        self.scene.add_node(vnode)
        self.assertEqual(len(vnode.input_sockets), 1)
        self.assertEqual(len(vnode.output_sockets), 2)  # Found and Not Found
        self.assertEqual(vnode.properties["confidence"], 0.9)

    def test_duplication(self):
        node = ActionNodeItem("click", {"x": 100, "y": 200})
        self.scene.add_node(node, QPointF(100, 100))
        node.setSelected(True)

        dups = self.scene.duplicate_selected()
        self.assertEqual(len(dups), 1)
        dup_node = dups[0]
        self.assertEqual(dup_node.properties["x"], 100)
        self.assertEqual(dup_node.properties["y"], 200)
        self.assertEqual(dup_node.pos().x(), 140)
        self.assertEqual(dup_node.pos().y(), 140)

    def test_grouping(self):
        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n2 = ActionNodeItem("move", {"x": 20, "y": 20})
        self.scene.add_node(n1, QPointF(100, 100))
        self.scene.add_node(n2, QPointF(300, 100))

        n1.setSelected(True)
        n2.setSelected(True)

        grp = self.scene.group_selected()
        self.assertIsNotNone(grp)
        self.assertEqual(len(grp.nodes), 2)
        self.assertEqual(n1.group, grp)
        self.assertEqual(n2.group, grp)

    def test_macro_to_graph_and_compile(self):
        original_steps = [
            {"type": "click", "x": 150, "y": 250, "button": "left", "dt": 100},
            {"type": "delay", "duration": 500, "dt": 600},
            {"type": "type", "value": "hello world", "dt": 800},
            {"type": "find_image", "template": "btn.png", "confidence": 0.85, "action": "click", "button": "left", "timeout": 5.0, "dt": 1000},
        ]

        macro_to_graph(original_steps, self.scene)

        # Start node + 4 action/vision nodes = 5 nodes
        self.assertEqual(len(self.scene.nodes), 5)
        # 4 connections between consecutive nodes
        self.assertEqual(len(self.scene.connections), 4)

        compiled = graph_to_macro(self.scene)
        self.assertEqual(len(compiled), 4)
        self.assertEqual(compiled[0]["type"], "click")
        self.assertEqual(compiled[0]["x"], 150)
        self.assertEqual(compiled[1]["type"], "delay")
        self.assertEqual(compiled[1]["duration"], 500)
        self.assertEqual(compiled[2]["type"], "type")
        self.assertEqual(compiled[2]["value"], "hello world")
        self.assertEqual(compiled[3]["type"], "wait_image")
        self.assertEqual(compiled[3]["template"], "btn.png")

    def test_essential_logic_nodes(self):
        if_node = IfConditionNodeItem(properties={"var_a": "$count", "operator": ">=", "val_b": "10"})
        self.scene.add_node(if_node)
        self.assertEqual(len(if_node.input_sockets), 1)
        self.assertEqual(len(if_node.output_sockets), 2)  # True and False

        math_node = MathNodeItem(properties={"var_name": "count", "operation": "increment"})
        self.scene.add_node(math_node)
        self.assertEqual(len(math_node.input_sockets), 1)
        self.assertEqual(len(math_node.output_sockets), 1)

        pixel_node = PixelColorNodeItem(properties={"x": 500, "y": 400, "color": "#00FF00", "tolerance": 10})
        self.scene.add_node(pixel_node)
        self.assertEqual(len(pixel_node.output_sockets), 2)  # Match and Mismatch

        hotkey_node = HotkeyNodeItem(properties={"combo": "Ctrl+V"})
        self.scene.add_node(hotkey_node)
        self.assertEqual(hotkey_node.properties["combo"], "Ctrl+V")

        loop_node = LoopNodeItem(properties={"count": 10, "var_name": "idx"})
        self.scene.add_node(loop_node)
        self.assertEqual(len(loop_node.output_sockets), 2)  # Body and Done

        stop_node = StopNodeItem()
        self.scene.add_node(stop_node)
        self.assertEqual(len(stop_node.output_sockets), 0)

    def test_fit_all_view(self):
        view = NodeView(self.scene)
        view.resize(800, 600)
        start = StartNodeItem()
        self.scene.add_node(start, QPointF(50, 50))
        n1 = ActionNodeItem("click", {"x": 100, "y": 200})
        self.scene.add_node(n1, QPointF(1200, 800))

        # Test framing entire graph
        view.fit_all()
        self.assertGreater(view.current_zoom, 0.0)

    def test_recorded_down_up_pairing_into_click(self):
        recorded = [
            {"type": "down", "x": 640, "y": 480, "button": "left", "dt": 100},
            {"type": "up", "x": 640, "y": 480, "button": "left", "dt": 180, "is_click": True},
        ]
        macro_to_graph(recorded, self.scene)

        # Start node + 1 paired click node = 2 nodes total (instead of 2 separate disjoint down/up nodes!)
        self.assertEqual(len(self.scene.nodes), 2)
        click_node = self.scene.nodes[1]
        self.assertEqual(click_node.node_type, "click")
        self.assertEqual(click_node.properties["x"], 640)
        self.assertEqual(click_node.properties["y"], 480)

    def test_all_action_types_editable_in_inspector(self):
        from app.ui.node_editor.inspector import PropertyInspector
        inspector = PropertyInspector(self.scene)

        # Test key_down node
        k_node = ActionNodeItem("key_down", {"vk": 13})
        inspector.set_node(k_node)
        self.assertGreater(inspector.content_layout.count(), 1)

        # Test wheel node
        w_node = ActionNodeItem("wheel", {"deltaY": 120})
        inspector.set_node(w_node)
        self.assertGreater(inspector.content_layout.count(), 1)

        # Test generic 'action' node
        gen_node = ActionNodeItem("action", {"x": 200, "y": 300})
        inspector.set_node(gen_node)
        self.assertGreater(inspector.content_layout.count(), 1)

    def test_mouse_move_trajectory_and_direct_jump(self):
        # 5 consecutive recorded move steps
        moves = [
            {"type": "move", "x": 100, "y": 100, "dt": 100},
            {"type": "move", "x": 110, "y": 105, "dt": 140},
            {"type": "move", "x": 120, "y": 110, "dt": 180},
            {"type": "move", "x": 130, "y": 115, "dt": 220},
            {"type": "move", "x": 150, "y": 130, "dt": 260},
        ]

        # 1. Test macro_to_graph with default_direct_move=True
        macro_to_graph(moves, self.scene, default_direct_move=True)
        # Should create Start node + 1 consolidated Move node
        self.assertEqual(len(self.scene.nodes), 2)
        move_node = self.scene.nodes[1]
        self.assertEqual(move_node.node_type, "move")
        self.assertEqual(move_node.properties["x"], 150)
        self.assertEqual(move_node.properties["y"], 130)
        self.assertEqual(len(move_node.properties["path_points"]), 5)
        self.assertTrue(move_node.properties["direct_jump"])
        self.assertIn("Direct", move_node.get_summary_text())

        # Compile back to macro with direct_jump=True -> 1 step
        compiled_direct = graph_to_macro(self.scene)
        self.assertEqual(len(compiled_direct), 1)
        self.assertEqual(compiled_direct[0]["type"], "move")
        self.assertEqual(compiled_direct[0]["x"], 150)
        self.assertEqual(compiled_direct[0]["y"], 130)

        # 2. Toggle direct_jump to False
        move_node.properties["direct_jump"] = False
        self.assertIn("Path (5 pts)", move_node.get_summary_text())

        # Compile back to macro with direct_jump=False -> all 5 steps replayed!
        compiled_path = graph_to_macro(self.scene)
        self.assertEqual(len(compiled_path), 5)
        self.assertEqual(compiled_path[0]["x"], 100)
        self.assertEqual(compiled_path[-1]["x"], 150)
        self.assertEqual(compiled_path[-1]["y"], 130)

    def test_move_node_direct_jump_checkbox_in_inspector(self):
        from app.ui.node_editor.inspector import PropertyInspector
        from PyQt6.QtWidgets import QCheckBox

        inspector = PropertyInspector(self.scene)
        move_node = ActionNodeItem("move", {
            "x": 300,
            "y": 400,
            "direct_jump": True,
            "path_points": [
                {"type": "move", "x": 280, "y": 380, "dt": 50},
                {"type": "move", "x": 300, "y": 400, "dt": 100},
            ]
        })
        self.scene.add_node(move_node)
        inspector.set_node(move_node)

        # Find direct jump checkbox inside inspector
        chk_direct = inspector.findChild(QCheckBox, "DirectJumpCheckbox")
        if not chk_direct:
            for cb in inspector.findChildren(QCheckBox):
                if "Direct Jump" in cb.text():
                    chk_direct = cb
                    break
        self.assertIsNotNone(chk_direct)
        self.assertTrue(chk_direct.isChecked())

        # Toggle checkbox off
        chk_direct.setChecked(False)
        self.assertFalse(move_node.properties["direct_jump"])

    def test_undo_redo_manager(self):
        from app.ui.node_editor.undo_manager import UndoManager

        undo_mgr = UndoManager(self.scene)
        self.assertFalse(undo_mgr.can_undo())
        self.assertFalse(undo_mgr.can_redo())

        # Base state with StartNode
        start = StartNodeItem()
        self.scene.add_node(start)
        undo_mgr.push_state()
        self.assertFalse(undo_mgr.can_undo())  # Single state cannot be undone

        # Add click node
        n1 = ActionNodeItem("click", {"x": 200, "y": 300})
        self.scene.add_node(n1)
        undo_mgr.push_state()
        self.assertTrue(undo_mgr.can_undo())
        self.assertEqual(len(self.scene.nodes), 2)

        # Undo -> restores to 1 node
        self.assertTrue(undo_mgr.undo())
        self.assertEqual(len(self.scene.nodes), 1)
        self.assertTrue(undo_mgr.can_redo())

        # Redo -> restores to 2 nodes
        self.assertTrue(undo_mgr.redo())
        self.assertEqual(len(self.scene.nodes), 2)
        self.assertEqual(self.scene.nodes[1].properties["x"], 200)

    def test_undo_redo_in_editor_window(self):
        from app.ui.node_editor import MacroNodeEditorWindow

        steps = [
            {"type": "click", "x": 100, "y": 100, "dt": 50},
            {"type": "move", "x": 200, "y": 200, "dt": 100},
        ]
        editor = MacroNodeEditorWindow("UndoTestMacro", steps)
        initial_node_count = len(editor.scene.nodes)
        self.assertGreater(initial_node_count, 1)

        # Add an action node
        editor._add_action_node("delay")
        self.assertEqual(len(editor.scene.nodes), initial_node_count + 1)
        self.assertTrue(editor.undo_manager.can_undo())

        # Trigger Ctrl+Z undo
        editor._on_undo()
        self.assertEqual(len(editor.scene.nodes), initial_node_count)

        # Trigger Ctrl+Y redo
        editor._on_redo()
        self.assertEqual(len(editor.scene.nodes), initial_node_count + 1)

        editor._has_unsaved_changes = False
        editor.close()

    def test_socket_snapping_and_unplugging(self):
        n1 = ActionNodeItem("click", {"x": 100, "y": 100})
        n2 = ActionNodeItem("move", {"x": 200, "y": 200})
        self.scene.add_node(n1, QPointF(50, 100))
        self.scene.add_node(n2, QPointF(250, 100))

        # Test socket snap target state
        out_sock = n1.output_sockets[0]
        in_sock = n2.input_sockets[0]

        self.assertFalse(in_sock.is_snap_target)
        in_sock.set_snap_target(True)
        self.assertTrue(in_sock.is_snap_target)
        in_sock.set_snap_target(False)
        self.assertFalse(in_sock.is_snap_target)

        # Wire n1 to n2
        conn = self.scene.add_connection(out_sock, in_sock)
        self.assertIsNotNone(conn)
        self.assertTrue(in_sock.has_connections())
        self.assertEqual(len(self.scene.connections), 1)

        # Disconnect all wires from in_sock (Unplugging)
        in_sock.disconnect_all()
        self.assertFalse(in_sock.has_connections())
        self.assertEqual(len(self.scene.connections), 0)

    def test_copy_paste_nodes(self):
        n1 = ActionNodeItem("click", {"x": 120, "y": 240, "button": "left"})
        v1 = VisionNodeItem("find_image", {"template": "icon.png", "confidence": 0.95})
        self.scene.add_node(n1, QPointF(100, 100))
        self.scene.add_node(v1, QPointF(350, 100))

        # Wire n1 to v1
        self.scene.add_connection(n1.output_sockets[0], v1.input_sockets[0])
        self.assertEqual(len(self.scene.connections), 1)

        # Select both nodes
        n1.setSelected(True)
        v1.setSelected(True)

        copied_count = self.scene.copy_selected()
        self.assertEqual(copied_count, 2)

        # Paste
        pasted = self.scene.paste_clipboard(offset_step=QPointF(50, 50))
        self.assertEqual(len(pasted), 2)
        # Total nodes: 2 original + 2 pasted = 4
        self.assertEqual(len(self.scene.nodes), 4)
        # Internal connection between n1 and v1 was duplicated between the new nodes
        self.assertEqual(len(self.scene.connections), 2)

        p_n1 = next((n for n in pasted if isinstance(n, ActionNodeItem)), None)
        p_v1 = next((n for n in pasted if isinstance(n, VisionNodeItem)), None)
        self.assertIsNotNone(p_n1)
        self.assertIsNotNone(p_v1)
        self.assertEqual(p_n1.properties["x"], 120)
        self.assertEqual(p_v1.properties["confidence"], 0.95)

    def test_vision_node_persistence_and_sockets(self):
        from app.ui.node_editor.undo_manager import serialize_scene, deserialize_scene

        start = StartNodeItem()
        vnode = VisionNodeItem("find_image", {
            "template": "logo.png",
            "confidence": 0.88,
            "action": "doubleclick",
            "button": "left",
            "timeout": 8.0,
        })
        success_node = ActionNodeItem("click", {"x": 500, "y": 500})
        miss_node = ActionNodeItem("move", {"x": 100, "y": 100})
        unplugged_node = ActionNodeItem("delay", {"duration": 1000})

        self.scene.add_node(start, QPointF(50, 100))
        self.scene.add_node(vnode, QPointF(250, 100))
        self.scene.add_node(success_node, QPointF(500, 50))
        self.scene.add_node(miss_node, QPointF(500, 200))
        self.scene.add_node(unplugged_node, QPointF(750, 100))

        # Connect Start -> Vision
        self.scene.add_connection(start.output_sockets[0], vnode.input_sockets[0])
        # Connect Vision socket 0 ("Found") -> success_node
        self.scene.add_connection(vnode.output_sockets[0], success_node.input_sockets[0])
        # Connect Vision socket 1 ("Not Found" / Miss) -> miss_node
        self.scene.add_connection(vnode.output_sockets[1], miss_node.input_sockets[0])
        # unplugged_node remains unplugged

        self.assertEqual(len(self.scene.connections), 3)

        # Serialize full graph data
        graph_data = serialize_scene(self.scene)

        # Deserialize into brand new scene
        new_scene = NodeScene()
        deserialize_scene(new_scene, graph_data)

        self.assertEqual(len(new_scene.nodes), 5)
        self.assertEqual(len(new_scene.connections), 3)

        new_vnode = next(n for n in new_scene.nodes if isinstance(n, VisionNodeItem))
        self.assertEqual(new_vnode.properties["template"], "logo.png")
        self.assertEqual(new_vnode.properties["confidence"], 0.88)
        self.assertEqual(new_vnode.properties["action"], "doubleclick")
        self.assertEqual(new_vnode.properties["timeout"], 8.0)

        # Verify output socket 0 connects to success_node
        self.assertEqual(len(new_vnode.output_sockets[0].connections), 1)
        self.assertIsInstance(new_vnode.output_sockets[0].connections[0].end_socket.node, ActionNodeItem)
        self.assertEqual(new_vnode.output_sockets[0].connections[0].end_socket.node.properties["x"], 500)

        # Verify output socket 1 ("Miss") is PRESERVED on socket 1 and NOT swapped to socket 0!
        self.assertEqual(len(new_vnode.output_sockets[1].connections), 1)
        self.assertEqual(new_vnode.output_sockets[1].connections[0].end_socket.node.properties["x"], 100)

        # Verify unplugged node is still in the scene and has NO connections!
        new_unplugged = next(n for n in new_scene.nodes if n.node_type == "delay")
        self.assertEqual(len(new_unplugged.input_sockets[0].connections), 0)
        self.assertEqual(len(new_unplugged.output_sockets[0].connections), 0)

    def test_vision_node_playback_safety(self):
        from app.core.player import MacroPlayer
        from app.core.input_simulator import InputSimulator

        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)

        # Execute macro steps containing vision node with missing template
        steps = [
            {"type": "find_image", "template": "non_existent_icon.png", "confidence": 0.85, "dt": 10},
            {"type": "wait_image", "template": "", "confidence": 0.85, "timeout": 0.1, "dt": 20},
        ]

        # Must not crash!
        player.play(steps, repeat=False, repeat_count=1)
        player._thread.join(timeout=3.0)
        self.assertFalse(player.is_playing())

    def test_floating_nodes_excluded_from_compilation_and_execution(self):
        start = StartNodeItem()
        connected_click = ActionNodeItem("click", {"x": 200, "y": 200})
        floating_click = ActionNodeItem("click", {"x": 800, "y": 800})
        floating_delay = ActionNodeItem("delay", {"duration": 1000})

        self.scene.add_node(start, QPointF(50, 50))
        self.scene.add_node(connected_click, QPointF(200, 50))
        self.scene.add_node(floating_click, QPointF(400, 300))
        self.scene.add_node(floating_delay, QPointF(600, 300))

        # Only connect start -> connected_click
        self.scene.add_connection(start.output_sockets[0], connected_click.input_sockets[0])

        compiled = graph_to_macro(self.scene)
        # Only connected_click must be compiled into executable steps!
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["x"], 200)
        self.assertEqual(compiled[0]["y"], 200)

        # Floating nodes must NOT be in compiled steps
        types_and_coords = [(s.get("type"), s.get("x")) for s in compiled]
        self.assertNotIn(("click", 800), types_and_coords)
        self.assertNotIn(("delay", None), types_and_coords)

    def test_knife_tool_slices_wires(self):
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QPoint

        n1 = ActionNodeItem("click", {"x": 100, "y": 100})
        n2 = ActionNodeItem("click", {"x": 300, "y": 100})
        self.scene.add_node(n1, QPointF(50, 100))
        self.scene.add_node(n2, QPointF(350, 100))

        conn = self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])
        self.assertIsNotNone(conn)
        self.assertEqual(len(self.scene.connections), 1)

        view = NodeView(self.scene)
        view.resize(600, 400)
        view.show()

        # Hold Y and slice across connection line (wire spans from x=240 to x=350 at y=156)
        view._y_key_held = True
        p1 = view.mapFromScene(QPointF(295, 50))
        p2 = view.mapFromScene(QPointF(295, 250))

        press_ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(p1), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        view.mousePressEvent(press_ev)
        self.assertTrue(view._is_cutting)

        move_ev = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(p2), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        view.mouseMoveEvent(move_ev)

        release_ev = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(p2), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        view.mouseReleaseEvent(release_ev)

        # Wire must be sliced and removed!
        self.assertEqual(len(self.scene.connections), 0)

    def test_alt_drag_duplication(self):
        from PyQt6.QtGui import QMouseEvent

        node = ActionNodeItem("click", {"x": 150, "y": 250})
        self.scene.add_node(node, QPointF(100, 100))
        node.setSelected(True)

        dups = self.scene.duplicate_selected_in_place()
        self.assertEqual(len(dups), 1)
        self.assertEqual(len(self.scene.nodes), 2)
        # Duplicate is at the exact same location ready to be dragged
        self.assertEqual(dups[0].pos().x(), 100.0)
        self.assertEqual(dups[0].pos().y(), 100.0)
        self.assertTrue(dups[0].isSelected())
        self.assertFalse(node.isSelected())

        # Also test via NodeView mousePressEvent with AltModifier
        view = NodeView(self.scene)
        view.resize(500, 500)
        view.show()

        # Click on node position with AltModifier
        pt = view.mapFromScene(QPointF(150, 120))
        alt_press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(pt),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.AltModifier,
        )
        view.mousePressEvent(alt_press)
        # Another duplicate must be created by view interaction!
        self.assertEqual(len(self.scene.nodes), 3)

    def test_vision_branching_when_action_is_none(self):
        from unittest.mock import patch
        from app.core.player import MacroPlayer
        from app.core.input_simulator import InputSimulator

        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)

        start = StartNodeItem()
        vnode = VisionNodeItem("find_image", {
            "template": "logo.png",
            "action": "none",
            "confidence": 0.85,
        })
        node_found = ActionNodeItem("click", {"x": 777, "y": 777})
        node_miss = ActionNodeItem("click", {"x": 333, "y": 333})

        self.scene.add_node(start, QPointF(50, 100))
        self.scene.add_node(vnode, QPointF(200, 100))
        self.scene.add_node(node_found, QPointF(450, 50))
        self.scene.add_node(node_miss, QPointF(450, 200))

        # Start -> Vision
        self.scene.add_connection(start.output_sockets[0], vnode.input_sockets[0])
        # Vision Found -> node_found
        self.scene.add_connection(vnode.output_sockets[0], node_found.input_sockets[0])
        # Vision Miss -> node_miss
        self.scene.add_connection(vnode.output_sockets[1], node_miss.input_sockets[0])

        compiled = graph_to_macro(self.scene)
        self.assertEqual(len(compiled), 3)

        # Case 1: Template IS found -> should execute found branch (x=777) and NOT miss branch
        executed_clicks = []
        sim.click = lambda x, y, btn="left": executed_clicks.append((x, y))

        with patch("app.core.player.wait_for_template_on_screen", return_value=(500, 500, 50, 50, 0.9)):
            player.play(compiled, speed=3.0, repeat=False, repeat_count=1)
            player._thread.join(timeout=3.0)

        # Because action="none", vision node itself does NOT click.
        # But Found branch was taken, so node_found clicked (777, 777)!
        self.assertEqual(executed_clicks, [(777, 777)])

        # Case 2: Template NOT found -> should execute miss branch (x=333) and NOT found branch
        executed_clicks.clear()
        with patch("app.core.player.wait_for_template_on_screen", return_value=None):
            player.play(compiled, speed=3.0, repeat=False, repeat_count=1)
            player._thread.join(timeout=3.0)

        self.assertEqual(executed_clicks, [(333, 333)])

    def test_wait_image_branching_when_action_is_none(self):
        from unittest.mock import patch
        from app.core.player import MacroPlayer
        from app.core.input_simulator import InputSimulator

        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)

        start = StartNodeItem()
        vnode = VisionNodeItem("wait_image", {
            "template": "btn.png",
            "action": "none",
            "timeout": 2.0,
            "confidence": 0.85,
        })
        node_found = ActionNodeItem("click", {"x": 888, "y": 888})
        node_miss = ActionNodeItem("click", {"x": 444, "y": 444})

        self.scene.add_node(start, QPointF(50, 100))
        self.scene.add_node(vnode, QPointF(200, 100))
        self.scene.add_node(node_found, QPointF(450, 50))
        self.scene.add_node(node_miss, QPointF(450, 200))

        # Start -> Vision
        self.scene.add_connection(start.output_sockets[0], vnode.input_sockets[0])
        # Vision Found -> node_found
        self.scene.add_connection(vnode.output_sockets[0], node_found.input_sockets[0])
        # Vision Miss -> node_miss
        self.scene.add_connection(vnode.output_sockets[1], node_miss.input_sockets[0])

        compiled = graph_to_macro(self.scene)
        self.assertEqual(len(compiled), 3)

        executed_clicks = []
        sim.click = lambda x, y, btn="left": executed_clicks.append((x, y))

        # Case 1: Template IS found -> should execute found branch (x=888)
        with patch("app.core.player.wait_for_template_on_screen", return_value=(200, 200, 30, 30, 0.95)):
            player.play(compiled, speed=3.0, repeat=False, repeat_count=1)
            player._thread.join(timeout=3.0)

        self.assertEqual(executed_clicks, [(888, 888)])

        # Case 2: Template NOT found -> should execute miss branch (x=444)
        executed_clicks.clear()
        with patch("app.core.player.wait_for_template_on_screen", return_value=None):
            player.play(compiled, speed=3.0, repeat=False, repeat_count=1)
            player._thread.join(timeout=3.0)

        self.assertEqual(executed_clicks, [(444, 444)])

    def test_toggle_bypass_selected(self):
        """Test B key bypass toggling, serialization, and deserialization."""
        n1 = ActionNodeItem("click", {"x": 100, "y": 100})
        n2 = ActionNodeItem("move", {"x": 200, "y": 200})
        self.scene.add_node(n1)
        self.scene.add_node(n2)

        # Initially not bypassed
        self.assertFalse(n1.bypassed)
        self.assertFalse(n2.bypassed)

        # Select n1 and toggle bypass
        n1.setSelected(True)
        count = self.scene.toggle_bypass_selected()
        self.assertEqual(count, 1)
        self.assertTrue(n1.bypassed)
        self.assertEqual(n1.properties.get("bypassed"), True)

        # Toggle again -> unbypass
        self.scene.toggle_bypass_selected()
        self.assertFalse(n1.bypassed)
        self.assertEqual(n1.properties.get("bypassed"), False)

    def test_bypassed_node_playback_skipping(self):
        """Test that bypassed nodes are skipped during playback."""
        from app.core.player import MacroPlayer
        from app.core.input_simulator import InputSimulator

        sim = InputSimulator()
        player = MacroPlayer(sim)

        executed = []
        sim.click = lambda x, y, btn="left": executed.append((x, y))

        steps = [
            {"id": "s1", "type": "click", "x": 100, "y": 100, "bypassed": True, "dt": 10},
            {"id": "s2", "type": "click", "x": 200, "y": 200, "bypassed": False, "dt": 20},
            {"id": "s3", "type": "click", "x": 300, "y": 300, "bypassed": True, "dt": 30},
        ]

        player.play(steps, speed=5.0, repeat=False, repeat_count=1)
        player._thread.join(timeout=2.0)

        # Only the non-bypassed click (200, 200) should have executed
        self.assertEqual(executed, [(200, 200)])

    def test_loop_node_execution(self):
        """Test that loop_count iterates N times via body_next and then exits to next (Done)."""
        from app.core.player import MacroPlayer
        from app.core.input_simulator import InputSimulator

        sim = InputSimulator()
        player = MacroPlayer(sim)

        loop_indices = []
        def mock_click(x, y, btn="left"):
            # Record loop index stored in variables
            loop_indices.append(player.variables.get("i"))

        sim.click = mock_click

        # Start -> Loop -> Body -> Click -> wires back to Loop -> Done -> Click (Done)
        steps = [
            {
                "id": "loop_1",
                "type": "loop_count",
                "count": 3,
                "var_name": "i",
                "body_next": "click_body",
                "next": "click_done",
                "dt": 10,
            },
            {
                "id": "click_body",
                "type": "click",
                "x": 50,
                "y": 50,
                "next": "loop_1",  # Wire back to loop
                "dt": 20,
            },
            {
                "id": "click_done",
                "type": "click",
                "x": 999,
                "y": 999,
                "next": None,
                "dt": 30,
            },
        ]

        player.play(steps, speed=10.0, repeat=False, repeat_count=1)
        player._thread.join(timeout=3.0)

        # Loop body should have executed 3 times with indices 0, 1, 2, then click_done (index remained 2 or done)
        self.assertEqual(loop_indices[:3], [0, 1, 2])
        self.assertEqual(len(loop_indices), 4)

    def test_vision_node_default_action_none(self):
        """Test that wait_image node defaults to action 'none'."""
        vnode = VisionNodeItem()
        self.assertEqual(vnode.properties.get("action"), "none")

    def test_wheel_node_coordinates_and_simulation(self):
        """Test wheel node preserves coordinates and simulates standard WHEEL_DELTA notches."""
        from app.ui.node_editor.graph_compiler import graph_to_macro

        start = StartNodeItem()
        wheel = ActionNodeItem("wheel", {"deltaY": -360, "x": 640, "y": 480})
        self.scene.add_node(start, QPointF(50, 100))
        self.scene.add_node(wheel, QPointF(200, 100))
        self.scene.add_connection(start.output_sockets[0], wheel.input_sockets[0])

        compiled = graph_to_macro(self.scene)
        self.assertEqual(len(compiled), 1)
        step = compiled[0]
        self.assertEqual(step["type"], "wheel")
        self.assertEqual(step["deltaY"], -360)
        self.assertEqual(step["x"], 640)
        self.assertEqual(step["y"], 480)

    def test_loop_node_dual_input_sockets(self):
        """Test LoopNodeItem has two explicit inputs (In and Loop In) and two outputs (Body and Done)."""
        loop = LoopNodeItem()
        self.scene.add_node(loop, QPointF(100, 100))
        self.assertEqual(len(loop.input_sockets), 2)
        self.assertEqual(len(loop.output_sockets), 2)
        # Sockets: input_sockets[0] = In, input_sockets[1] = Loop In
        self.assertIn("In", loop.input_sockets[0].name)
        self.assertIn("Loop", loop.input_sockets[1].name)
        self.assertIn("Body", loop.output_sockets[0].name)
        self.assertIn("Done", loop.output_sockets[1].name)

    def test_auto_heal_on_node_delete(self):
        """Test deleting an inline node automatically heals the connection across predecessor and successor."""
        node_a = ActionNodeItem("click", {"x": 100, "y": 100})
        node_b = ActionNodeItem("delay", {"duration": 500})
        node_c = ActionNodeItem("type", {"value": "test"})

        self.scene.add_node(node_a, QPointF(50, 100))
        self.scene.add_node(node_b, QPointF(250, 100))
        self.scene.add_node(node_c, QPointF(450, 100))

        # A -> B -> C
        self.scene.add_connection(node_a.output_sockets[0], node_b.input_sockets[0])
        self.scene.add_connection(node_b.output_sockets[0], node_c.input_sockets[0])
        self.assertEqual(len(self.scene.connections), 2)

        # Select only B and delete
        self.scene.clearSelection()
        node_b.setSelected(True)
        self.scene.delete_selected()

        # B should be gone
        self.assertNotIn(node_b, self.scene.nodes)
        # Wire should have auto-healed: A -> C
        self.assertEqual(len(self.scene.connections), 1)
        remaining_conn = self.scene.connections[0]
        self.assertEqual(remaining_conn.start_socket.node, node_a)
        self.assertEqual(remaining_conn.end_socket.node, node_c)

    def test_shake_to_disconnect_and_heal(self):
        """Test shaking an inline node disconnects it and heals predecessor -> successor."""
        view = NodeView(self.scene)

        node_a = ActionNodeItem("click", {"x": 100, "y": 100})
        node_b = ActionNodeItem("delay", {"duration": 300})
        node_c = ActionNodeItem("click", {"x": 200, "y": 200})

        self.scene.add_node(node_a, QPointF(50, 100))
        self.scene.add_node(node_b, QPointF(250, 100))
        self.scene.add_node(node_c, QPointF(450, 100))

        self.scene.add_connection(node_a.output_sockets[0], node_b.input_sockets[0])
        self.scene.add_connection(node_b.output_sockets[0], node_c.input_sockets[0])
        self.assertEqual(len(self.scene.connections), 2)

        # Trigger shake disconnect on node_b
        view._trigger_shake_disconnect(node_b)

        # Node B should now have 0 connections
        self.assertEqual(len(node_b.input_sockets[0].connections), 0)
        self.assertEqual(len(node_b.output_sockets[0].connections), 0)

        # Predecessor A should now be healed directly to successor C
        self.assertEqual(len(self.scene.connections), 1)
        healed_conn = self.scene.connections[0]
        self.assertEqual(healed_conn.start_socket.node, node_a)
        self.assertEqual(healed_conn.end_socket.node, node_c)

    def test_houdini_wire_drop_auto_insert(self):
        """Test dropping an unconnected node onto an existing wire splices wire and pushes downstream right."""
        view = NodeView(self.scene)

        node_a = ActionNodeItem("click", {"x": 10, "y": 10})
        node_c = ActionNodeItem("type", {"value": "done"})
        self.scene.add_node(node_a, QPointF(0, 100))
        self.scene.add_node(node_c, QPointF(300, 100))

        wire = self.scene.add_connection(node_a.output_sockets[0], node_c.input_sockets[0])
        self.assertEqual(len(self.scene.connections), 1)

        # Create new unattached node positioned between A and C
        node_b = ActionNodeItem("delay", {"duration": 200})
        self.scene.add_node(node_b, QPointF(150, 100))

        # Simulate hover and release onto wire
        view._hovered_wire = wire
        view._dragged_node = node_b

        # Simulate release
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent, QPoint
        rel_ev = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(150, 100),
            QPointF(150, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseReleaseEvent(rel_ev)

        # Now wire should be spliced: A -> B -> C (2 connections)
        self.assertEqual(len(self.scene.connections), 2)
        self.assertEqual(node_b.input_sockets[0].connections[0].start_socket.node, node_a)
        self.assertEqual(node_b.output_sockets[0].connections[0].end_socket.node, node_c)

        # Node C should have been pushed to the right to avoid overlapping node B
        self.assertGreater(node_c.pos().x(), node_b.pos().x() + node_b.width)

    def test_houdini_a_drag_alignment(self):
        """Test A + Drag aligns downstream branch when dragged right, and upstream branch when dragged left."""
        view = NodeView(self.scene)

        node_a = ActionNodeItem("click", {"x": 10, "y": 10})
        node_b = ActionNodeItem("delay", {"duration": 100})
        node_c = ActionNodeItem("type", {"value": "c"})

        # Scatter nodes with irregular Y coordinates
        self.scene.add_node(node_a, QPointF(50, 200))
        self.scene.add_node(node_b, QPointF(200, 350))
        self.scene.add_node(node_c, QPointF(400, 50))

        self.scene.add_connection(node_a.output_sockets[0], node_b.input_sockets[0])
        self.scene.add_connection(node_b.output_sockets[0], node_c.input_sockets[0])

        # Test A + Drag Right on node_a:
        view._a_key_held = True
        view._a_align_node = node_a
        view._a_align_start_scene_pos = QPointF(50, 200)

        # Release with dx = +100 (dragged right)
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent
        rel_ev = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(150, 200),
            QPointF(150, 200),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseReleaseEvent(rel_ev)

        # Node B and Node C should now be horizontally aligned to Node A's Y coordinate (200)
        self.assertEqual(node_a.pos().y(), 200)
        self.assertEqual(node_b.pos().y(), 200)
        self.assertEqual(node_c.pos().y(), 200)
        # And spaced neatly left to right
        self.assertLess(node_a.pos().x(), node_b.pos().x())
        self.assertLess(node_b.pos().x(), node_c.pos().x())

    def test_branch_traversal_methods(self):
        """Test _get_downstream_nodes and _get_upstream_nodes."""
        view = NodeView(self.scene)

        node_1 = ActionNodeItem("click")
        node_2 = ActionNodeItem("delay")
        node_3 = ActionNodeItem("type")

        self.scene.add_node(node_1, QPointF(0, 0))
        self.scene.add_node(node_2, QPointF(200, 0))
        self.scene.add_node(node_3, QPointF(400, 0))

        self.scene.add_connection(node_1.output_sockets[0], node_2.input_sockets[0])
        self.scene.add_connection(node_2.output_sockets[0], node_3.input_sockets[0])

        downstream_1 = view._get_downstream_nodes(node_1)
        self.assertEqual(downstream_1, [node_1, node_2, node_3])

        downstream_2 = view._get_downstream_nodes(node_2)
        self.assertEqual(downstream_2, [node_2, node_3])

        upstream_3 = view._get_upstream_nodes(node_3)
        self.assertEqual(upstream_3, [node_3, node_2, node_1])

    def test_loop_default_infinite(self):
        """Test that LoopNodeItem defaults to infinite=True and reflects in summary text."""
        loop = LoopNodeItem()
        self.assertTrue(loop.properties.get("infinite", False))
        self.assertIn("Infinite", loop.get_summary_text())

    def test_loop_auto_cycle_compilation(self):
        """Test that the end of a loop body sequence auto-cycles without requiring a backward wire."""
        start = StartNodeItem()
        loop = LoopNodeItem()
        click_1 = ActionNodeItem("click", {"x": 10, "y": 10})
        click_2 = ActionNodeItem("click", {"x": 20, "y": 20})
        exit_step = ActionNodeItem("delay", {"duration": 100})

        self.scene.add_node(start, QPointF(0, 100))
        self.scene.add_node(loop, QPointF(150, 100))
        self.scene.add_node(click_1, QPointF(350, 100))
        self.scene.add_node(click_2, QPointF(550, 100))
        self.scene.add_node(exit_step, QPointF(350, 250))

        # Wire: Start -> Loop (In)
        self.scene.add_connection(start.output_sockets[0], loop.input_sockets[0])
        # Wire: Loop (Body) -> Click 1 -> Click 2 (NO backward wire from Click 2!)
        self.scene.add_connection(loop.output_sockets[0], click_1.input_sockets[0])
        self.scene.add_connection(click_1.output_sockets[0], click_2.input_sockets[0])
        # Wire: Loop (Done) -> Exit Step
        self.scene.add_connection(loop.output_sockets[1], exit_step.input_sockets[0])

        compiled = graph_to_macro(self.scene)
        step_map = {s["id"]: s for s in compiled}

        loop_step = step_map[loop.id]
        click_2_step = step_map[click_2.id]

        # Click 2 should have auto-cycled its next back to loop.id!
        self.assertEqual(click_2_step["next"], loop.id)
        # Loop body_next points to click_1, next points to exit_step
        self.assertEqual(loop_step["body_next"], click_1.id)
        self.assertEqual(loop_step["next"], exit_step.id)

    def test_loop_break_out_pattern(self):
        """Test that an inner condition inside a loop can break out directly to the exit step."""
        from app.core.player import MacroPlayer
        from unittest.mock import MagicMock
        import time

        sim = MagicMock()
        player = MacroPlayer(simulator=sim)

        executed_steps = []
        def mock_click(x, y, button="left"):
            executed_steps.append((x, y))

        sim.click = mock_click

        # Loop (Count=10) -> Click (x=1, y=1) -> If condition ($var == 2) -> True: Break to Exit Click (x=999, y=999)
        #                                                                 -> False: Cycle back to Loop
        steps = [
            {
                "id": "loop_1",
                "type": "loop_count",
                "count": 10,
                "infinite": False,
                "var_name": "i",
                "body_next": "action_click",
                "next": "done_click",
                "dt": 10,
            },
            {
                "id": "action_click",
                "type": "click",
                "x": 1,
                "y": 1,
                "next": "cond_check",
                "dt": 10,
            },
            {
                "id": "cond_check",
                "type": "if_condition",
                "var_a": "$i",
                "operator": "==",
                "val_b": "2",
                "found_next": "done_click",  # Break out directly to Done!
                "miss_next": "loop_1",       # Keep cycling
                "dt": 10,
            },
            {
                "id": "done_click",
                "type": "click",
                "x": 999,
                "y": 999,
                "next": None,
                "dt": 10,
            },
        ]

        player.play(steps, speed=10.0, repeat=False, repeat_count=1)
        player._thread.join(timeout=3.0)

        # Body click (1, 1) runs for i=0, i=1, i=2 (3 times), then condition is True on i=2 and breaks out to (999, 999)!
        self.assertEqual(executed_steps.count((1, 1)), 3)
        self.assertEqual(executed_steps[-1], (999, 999))

    def test_c_clamp_dynamic_bounds_and_sync_move(self):
        """Test that C-Clamp LoopNodeItem dynamically calculates bounds for body nodes and moves in sync."""
        loop = LoopNodeItem()
        click_1 = ActionNodeItem("click", {"x": 100, "y": 100})
        click_2 = ActionNodeItem("click", {"x": 200, "y": 200})

        self.scene.add_node(loop, QPointF(50, 50))
        self.scene.add_node(click_1, QPointF(150, 50))
        self.scene.add_node(click_2, QPointF(400, 50))

        # Before wiring body: clamp is default size
        self.assertEqual(len(loop.get_body_nodes()), 0)
        initial_w = loop.clamp_width

        # Wire: Loop (Body) -> click_1 -> click_2
        self.scene.add_connection(loop.output_sockets[0], click_1.input_sockets[0])
        self.scene.add_connection(click_1.output_sockets[0], click_2.input_sockets[0])

        body_nodes = loop.get_body_nodes()
        self.assertEqual(body_nodes, [click_1, click_2])

        # Trigger clamp bounds update
        loop.update_clamp_bounds()
        self.assertGreater(loop.clamp_width, initial_w)

        # Move the loop clamp by (30, 20)
        orig_c1_x = click_1.pos().x()
        orig_c1_y = click_1.pos().y()
        loop.setPos(loop.pos() + QPointF(30, 20))

        # Enclosed body nodes should have moved in sync!
        self.assertEqual(click_1.pos().x(), orig_c1_x + 30)
        self.assertEqual(click_1.pos().y(), orig_c1_y + 20)

    def test_wait_image_loop_until_found_auto_route(self):
        """Test compiling Wait for Image with break_loop_on_found auto-routes found to exit and miss to loop."""
        start = StartNodeItem()
        loop = LoopNodeItem()
        vnode = VisionNodeItem(properties={"break_loop_on_found": True, "template": "btn.png"})
        done_step = ActionNodeItem("click", {"x": 888, "y": 888})

        self.scene.add_node(start, QPointF(0, 100))
        self.scene.add_node(loop, QPointF(100, 100))
        self.scene.add_node(vnode, QPointF(300, 100))
        self.scene.add_node(done_step, QPointF(550, 200))

        self.scene.add_connection(start.output_sockets[0], loop.input_sockets[0])
        self.scene.add_connection(loop.output_sockets[0], vnode.input_sockets[0])
        self.scene.add_connection(loop.output_sockets[1], done_step.input_sockets[0])

        compiled = graph_to_macro(self.scene)
        step_map = {s["id"]: s for s in compiled}

        v_step = step_map[vnode.id]
        self.assertTrue(v_step["break_loop_on_found"])
        # Should auto-route found_next to done_step.id, and miss_next back to loop.id
        self.assertEqual(v_step["found_next"], done_step.id)
        self.assertEqual(v_step["miss_next"], loop.id)


    def test_loop_node_paint_and_qpainterpath(self):
        """Test that LoopNodeItem paints cleanly without crashing (QPainterPath imported)."""
        from PyQt6.QtGui import QPainter, QImage
        loop = LoopNodeItem()
        self.scene.add_node(loop, QPointF(100, 100))
        img = QImage(300, 300, QImage.Format.Format_ARGB32)
        img.fill(0)
        painter = QPainter(img)
        # Should not throw NameError: name 'QPainterPath' is not defined
        loop.paint(painter, None, None)
        painter.end()

    def test_input_simulator_extended_keys_and_hotkey(self):
        """Test InputSimulator hotkey handling for Delete, Ctrl+Shift+Esc, and Ctrl+Alt+Delete."""
        from app.core.input_simulator import InputSimulator, EXTENDED_KEYS
        sim = InputSimulator()
        self.assertIn(0x2E, EXTENDED_KEYS)  # VK_DELETE
        self.assertIn(0x26, EXTENDED_KEYS)  # VK_UP
        # Should execute without error
        sim.hotkey("Delete")
        sim.hotkey("Ctrl+Shift+Esc")
        sim.hotkey("Ctrl+Alt+Delete")

    def test_pixel_color_node_properties_and_execution(self):
        """Test PixelColorNodeItem coordinate and color properties."""
        from app.core.player import MacroPlayer
        node = PixelColorNodeItem(properties={"x": 100, "y": 200, "color": "#000000", "tolerance": 15})
        self.assertEqual(node.properties["x"], 100)
        self.assertEqual(node.properties["y"], 200)
        self.assertEqual(node.properties["color"], "#000000")

        # Player step execution should evaluate safely without crashing
        player = MacroPlayer(None)
        res = player._execute_step({"type": "pixel_color", "x": 0, "y": 0, "color": "#000000", "tolerance": 50})
        self.assertIsInstance(res, bool)


if __name__ == "__main__":
    unittest.main()
