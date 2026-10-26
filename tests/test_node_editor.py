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
        chk_direct = inspector.findChild(QCheckBox)
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


if __name__ == "__main__":
    unittest.main()
