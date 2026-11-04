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
from app.core.player import MacroPlayer


from PyQt6.QtGui import QMouseEvent, QKeyEvent

class MockMouseEvent:
    def __init__(self, button=Qt.MouseButton.LeftButton, buttons=None, pos=QPointF(0, 0), scene_pos=QPointF(0, 0)):
        self._button = button
        self._buttons = buttons if buttons is not None else button
        self._pos = pos
        self._scene_pos = scene_pos

    def button(self):
        return self._button

    def buttons(self):
        return self._buttons

    def pos(self):
        return self._pos

    def scenePos(self):
        return self._scene_pos

    def accept(self):
        pass


class TestNodeEditor(unittest.TestCase):
    def setUp(self):
        self.scene = NodeScene()
        self.view = NodeView(self.scene)

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
        import unittest.mock as mock
        from app.core.input_simulator import InputSimulator, EXTENDED_KEYS
        sim = InputSimulator()
        self.assertIn(0x2E, EXTENDED_KEYS)  # VK_DELETE
        self.assertIn(0x26, EXTENDED_KEYS)  # VK_UP
        # Should execute without error
        sim.hotkey("Delete")
        with mock.patch("subprocess.Popen") as mock_popen:
            sim.hotkey("Ctrl+Shift+Esc")
            sim.hotkey("Ctrl+Alt+Delete", cad_action="taskmgr")
            mock_popen.assert_called_with(["taskmgr.exe"], shell=True)

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

    def test_variable_parameters_in_inspector_and_player(self):
        """Test variable parameters across inspector controls, compiler, and player."""
        from app.ui.node_editor.inspector import PropertyInspector
        from app.ui.node_editor.graph_compiler import graph_to_macro
        from app.core.player import MacroPlayer

        inspector = PropertyInspector(self.scene)

        # 1. Action Node with variable coordinates ($x, $y)
        click_node = ActionNodeItem("click", {"x": "$x", "y": "$y", "button": "left"})
        self.scene.add_node(click_node)
        inspector.set_node(click_node)
        self.assertEqual(click_node.properties["x"], "$x")
        self.assertEqual(click_node.properties["y"], "$y")

        # 2. Delay Node with variable duration ($wait)
        delay_node = ActionNodeItem("delay", {"duration": "$wait"})
        self.scene.add_node(delay_node)
        inspector.set_node(delay_node)

        # 3. Wheel Node with variable position and delta ($dy)
        wheel_node = ActionNodeItem("wheel", {"x": "$x", "y": "$y", "deltaY": "$dy"})
        self.scene.add_node(wheel_node)
        inspector.set_node(wheel_node)

        # 4. Math Node with variable assignment
        math_node = MathNodeItem(properties={"var_name": "y", "operation": "add", "value": "$step"})
        self.scene.add_node(math_node)
        inspector.set_node(math_node)

        # 5. If Node with variables
        if_node = IfConditionNodeItem(properties={"var_a": "$count", "operator": ">=", "val_b": "$limit"})
        self.scene.add_node(if_node)
        inspector.set_node(if_node)

        # 6. Pixel Color Node with variables
        pix_node = PixelColorNodeItem(properties={"x": "$px", "y": "$py", "color": "#10B981", "tolerance": 20})
        self.scene.add_node(pix_node)
        inspector.set_node(pix_node)

        # 7. Loop Node with variable count
        loop_node = LoopNodeItem(properties={"count": "$total", "infinite": False, "var_name": "row"})
        self.scene.add_node(loop_node)
        inspector.set_node(loop_node)

        # Compiler should compile without ValueError
        start_node = StartNodeItem()
        self.scene.add_node(start_node)
        self.scene.add_connection(start_node.output_sockets[0], click_node.input_sockets[0])
        steps = graph_to_macro(self.scene)
        self.assertIsInstance(steps, list)
        self.assertGreater(len(steps), 0)
        self.assertEqual(steps[0]["x"], "$x")
        self.assertEqual(steps[0]["y"], "$y")

        # Player should resolve variables dynamically
        player = MacroPlayer(None)
        player.variables["x"] = 550
        player.variables["$y"] = 320
        player.variables["step"] = 60

        # Math op resolution: y = y + step -> 320 + 60 = 380
        player._execute_step({"type": "math_op", "var_name": "y", "operation": "add", "value": "$step"})
        self.assertEqual(player.variables["y"], 380)

        # Coord resolution
        self.assertEqual(player._resolve_coord("$x"), 550)
        self.assertEqual(player._resolve_coord("$y"), 380)

    def test_param_input_type_badge_and_menu(self):
        """Test parameter input data type options, wheel adjustment, and variable menu."""
        from app.ui.node_editor.inspector import PropertyInspector
        from PyQt6.QtWidgets import QPushButton, QLineEdit
        from PyQt6.QtGui import QWheelEvent
        from PyQt6.QtCore import QPointF, QPoint

        inspector = PropertyInspector(self.scene)
        self.assertEqual(inspector.scene, self.scene)

        captured_vals = []
        widget, edit = inspector._create_param_input(
            current_val=500,
            on_change_callback=lambda v: captured_vals.append(v),
            default_type="int"
        )
        self.assertEqual(edit.text(), "500")

        # Check type button
        btn_type = widget.findChild(QPushButton)
        self.assertIsNotNone(btn_type)
        self.assertIn("Int", btn_type.text())

        # Test setting a variable switches type badge to Var
        edit.setText("$custom_var")
        self.assertIn("Var", btn_type.text())
        self.assertIn("$custom_var", captured_vals)

        # Test wheel event increment on numeric value
        edit.setText("100")
        wheel_event = QWheelEvent(
            QPointF(10, 10), QPointF(10, 10),
            QPoint(0, 0), QPoint(0, 120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False
        )
        edit.wheelEvent(wheel_event)
        self.assertEqual(edit.text(), "101")

    def test_nested_loop_movement_stability(self):
        """Test moving a loop containing another loop does not double-move or displace inner nodes."""
        loop_outer = LoopNodeItem()
        self.scene.add_node(loop_outer, QPointF(100, 100))

        loop_inner = LoopNodeItem()
        self.scene.add_node(loop_inner, QPointF(200, 200))

        action_inner = ActionNodeItem("click", {"x": 10, "y": 10})
        self.scene.add_node(action_inner, QPointF(300, 300))

        self.scene.add_connection(loop_outer.socket_body, loop_inner.socket_in)
        self.scene.add_connection(loop_inner.socket_body, action_inner.input_sockets[0])

        # Outer loop body nodes should contain inner loop, but NOT inner loop's private children
        self.assertEqual(len(loop_outer.get_body_nodes()), 1)
        self.assertEqual(loop_outer.get_body_nodes()[0], loop_inner)
        self.assertEqual(len(loop_inner.get_body_nodes()), 1)
        self.assertEqual(loop_inner.get_body_nodes()[0], action_inner)

        # Move outer loop by (50, 50)
        loop_outer.setPos(loop_outer.pos() + QPointF(50, 50))
        self.assertEqual(loop_outer.pos(), QPointF(150, 150))
        self.assertEqual(loop_inner.pos(), QPointF(250, 250))
        # Inner action must move by exactly (50, 50), not (100, 100)!
        self.assertEqual(action_inner.pos(), QPointF(350, 350))

        # Move inner loop directly by (25, 25)
        loop_inner.setPos(loop_inner.pos() + QPointF(25, 25))
        self.assertEqual(loop_outer.pos(), QPointF(150, 150))
        self.assertEqual(loop_inner.pos(), QPointF(275, 275))
        self.assertEqual(action_inner.pos(), QPointF(375, 375))

    def test_macro_wide_custom_variable_memory(self):
        """Test custom variables added to any node are remembered across macro and available in inspector dropdowns."""
        from app.ui.node_editor.inspector import PropertyInspector
        from app.ui.node_editor.undo_manager import serialize_scene, deserialize_scene

        # 1. Register custom variable in scene
        self.scene.register_custom_variable("$player_gold")
        self.assertIn("$player_gold", self.scene.custom_variables)

        # 2. Check inspector known variables lists it
        inspector = PropertyInspector(self.scene)
        known = inspector._get_known_variables()
        self.assertIn("$player_gold", known)

        # 3. Add node with embedded variable in properties
        move_node = ActionNodeItem("move", {"x": "$target_x", "y": 300})
        self.scene.add_node(move_node)
        known_after = inspector._get_known_variables()
        self.assertIn("$target_x", known_after)

        # 4. Serialization / Deserialization preserves macro-wide custom variables
        snapshot = serialize_scene(self.scene)
        self.assertIn("custom_variables", snapshot)
        self.assertIn("$player_gold", snapshot["custom_variables"])

        new_scene = NodeScene()
        deserialize_scene(new_scene, snapshot)
        self.assertIn("$player_gold", new_scene.custom_variables)
        self.assertIn("$target_x", new_scene.custom_variables)

    def test_hotkey_preset_and_inspector_no_flicker(self):
        """Test HotkeyNodeItem preset synchronization and PropertyInspector stability without layout flicker."""
        from app.ui.node_editor.inspector import PropertyInspector
        from PyQt6.QtWidgets import QComboBox, QLineEdit

        hotkey = HotkeyNodeItem(properties={"combo": "Ctrl+Shift+Esc"})
        self.scene.add_node(hotkey, QPointF(100, 100))

        inspector = PropertyInspector(self.scene)
        inspector.set_node(hotkey)

        # Find combo_preset and verify it synchronized to Ctrl+Shift+Esc
        combo_boxes = inspector.findChildren(QComboBox)
        preset_combo = combo_boxes[0]
        self.assertIn("Ctrl+Shift+Esc", preset_combo.currentText())

        # Test set_node on already selected node does not destroy/rebuild content
        child_count_before = len(inspector.content_widget.findChildren(object))
        inspector.set_node(hotkey, force=False)
        child_count_after = len(inspector.content_widget.findChildren(object))
        self.assertEqual(child_count_before, child_count_after)

    def test_all_preset_examples_load_successfully(self):
        """Test all 5 varied multi-node example presets load cleanly and encompass all node types."""
        from app.ui.node_editor.editor_window import MacroNodeEditorWindow

        win = MacroNodeEditorWindow(macro_name="test_macro", macro_steps=[])
        presets = ["form_filler", "game_bot", "drag_drop_sorter", "key_strummer_clipboard", "nested_grid_scanner"]

        all_seen_types = set()
        for p in presets:
            win._load_example_preset(p, confirm=False)
            self.assertGreater(len(win.scene.nodes), 3)
            self.assertGreater(len(win.scene.connections), 2)
            for n in win.scene.nodes:
                all_seen_types.add(n.node_type)
                # Check bounding rect and layout do not crash
                self.assertGreater(n.width, 0)
                self.assertGreater(n.height, 0)

        # Verify key variety covered
        self.assertIn("start", all_seen_types)
        self.assertIn("click", all_seen_types)
        self.assertIn("dblclick", all_seen_types)
        self.assertIn("down", all_seen_types)
        self.assertIn("up", all_seen_types)
        self.assertIn("move", all_seen_types)
        self.assertIn("delay", all_seen_types)
        self.assertIn("type", all_seen_types)
        self.assertIn("key_down", all_seen_types)
        self.assertIn("key_up", all_seen_types)
        self.assertIn("wheel", all_seen_types)
        self.assertIn("hotkey", all_seen_types)
        self.assertIn("loop_count", all_seen_types)
        self.assertIn("if_condition", all_seen_types)
        self.assertIn("pixel_color", all_seen_types)
        self.assertIn("math_op", all_seen_types)
        self.assertIn("stop_playback", all_seen_types)
        self.assertIn("wait_image", all_seen_types)

    def test_vision_node_multi_template_or(self):
        vnode = VisionNodeItem()
        # Add single template
        vnode.update_template("cactus1.png")
        self.assertEqual(vnode.properties["template"], "cactus1.png")

        # Append 2nd template variant (OR logic)
        vnode.update_template("cactus2.png", append=True)
        self.assertEqual(vnode.properties["template"], "cactus1.png;cactus2.png")
        self.assertIn("2 Imgs (OR)", vnode.get_summary_text())

        # Append 3rd template variant
        vnode.update_template("cactus3.png", append=True)
        self.assertEqual(vnode.properties["template"], "cactus1.png;cactus2.png;cactus3.png")
        self.assertIn("3 Imgs (OR)", vnode.get_summary_text())

        # Remove variant
        vnode.remove_template_variant("cactus2.png")
        self.assertEqual(vnode.properties["template"], "cactus1.png;cactus3.png")
        self.assertIn("2 Imgs (OR)", vnode.get_summary_text())

    def test_action_node_key_down_hold_summary(self):
        anode = ActionNodeItem("key_down", {"key": "Space", "vk": 32, "hold_duration": 5000, "auto_repeat": True})
        summary = anode.get_summary_text()
        self.assertIn("5000ms", summary)
        self.assertIn("[Repeat]", summary)

    def test_key_down_auto_repeat_default_true(self):
        node = ActionNodeItem("key_down")
        self.assertTrue(node.properties.get("auto_repeat"))
        self.assertEqual(node.properties.get("hold_duration"), 0)

    def test_pixel_color_node_region_properties_and_summary(self):
        pnode = PixelColorNodeItem()
        # Default single coordinate mode
        self.assertFalse(pnode.properties["use_region"])
        self.assertIn("Pos:", pnode.get_summary_text())

        # Switch to bounding box region mode
        pnode.properties["use_region"] = True
        pnode.properties["region_x"] = 320
        pnode.properties["region_y"] = 240
        pnode.properties["region_w"] = 150
        pnode.properties["region_h"] = 120
        pnode.properties["color"] = "#E11D48"
        pnode.properties["tolerance"] = 20

        summary = pnode.get_summary_text()
        self.assertIn("Box: (320, 240) 150x120", summary)
        self.assertIn("#E11D48", summary)
        self.assertIn("±20", summary)

        # Clone preserves region properties
        cloned = pnode.clone()
        self.assertTrue(cloned.properties["use_region"])
        self.assertEqual(cloned.properties["region_w"], 150)

    def test_pixel_color_graph_compilation_with_bounding_box(self):
        scene = NodeScene()
        start = StartNodeItem()
        pnode = PixelColorNodeItem(properties={
            "use_region": True,
            "region_x": 400,
            "region_y": 300,
            "region_w": 200,
            "region_h": 150,
            "color": "#10B981",
            "tolerance": 18,
        })
        scene.add_node(start, QPointF(0, 0))
        scene.add_node(pnode, QPointF(200, 0))
        scene.add_connection(start.output_sockets[0], pnode.input_sockets[0])

        steps = graph_to_macro(scene)
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step["type"], "pixel_color")
        self.assertTrue(step["use_region"])
        self.assertEqual(step["region_x"], 400)
        self.assertEqual(step["region_y"], 300)
        self.assertEqual(step["region_w"], 200)
        self.assertEqual(step["region_h"], 150)
        self.assertEqual(step["color"], "#10B981")
        self.assertEqual(step["tolerance"], 18)

    def test_inspector_pixel_color_region_overlay_live_highlight(self):
        from app.ui.node_editor.inspector import PropertyInspector
        scene = NodeScene()
        inspector = PropertyInspector(scene)
        pnode = PixelColorNodeItem(properties={
            "use_region": False,
            "region_x": 350,
            "region_y": 250,
            "region_w": 180,
            "region_h": 120,
            "color": "#D946EF",
        })
        scene.add_node(pnode)

        # 1. Initially use_region is False, overlay is hidden
        inspector.set_node(pnode)
        self.assertFalse(inspector.region_overlay.isVisible())

        # 2. Toggle use_region to True -> overlay shows and moves to bounding box
        from app.ui.indicator import logical_rect_to_physical
        pnode.properties["use_region"] = True
        inspector._update_region_overlay(pnode)
        self.assertTrue(inspector.region_overlay.isVisible())
        px, py, pw, ph = logical_rect_to_physical(inspector.region_overlay.geometry())
        self.assertEqual(px, 350)
        self.assertEqual(py, 250)
        self.assertEqual(pw, 180)
        self.assertEqual(ph, 120)

        # 3. Live update coordinates -> overlay moves immediately
        pnode.properties["region_x"] = 520
        pnode.properties["region_y"] = 410
        inspector._update_region_overlay(pnode)
        u_px, u_py, _, _ = logical_rect_to_physical(inspector.region_overlay.geometry())
        self.assertEqual(u_px, 520)
        self.assertEqual(u_py, 410)

        # 4. Deselection -> overlay hides
        inspector.set_node(None)
        self.assertFalse(inspector.region_overlay.isVisible())

        # 5. Selecting a non-region node -> overlay stays hidden
        action_node = ActionNodeItem(action_type="delay")
        inspector.set_node(action_node)
        self.assertFalse(inspector.region_overlay.isVisible())

        # Clean up
        inspector.region_overlay.close()

    def test_safe_overlay_color_distance(self):
        from app.ui.indicator import get_safe_overlay_color
        # Test across various shades (dark, bright, vibrant, gray)
        for hex_code in ["#535353", "#FFFFFF", "#000000", "#FF0000", "#00FF00", "#0000FF", "#38BDF8"]:
            safe, corner, target = get_safe_overlay_color(hex_code)
            self.assertTrue(safe.isValid())
            self.assertTrue(corner.isValid())
            self.assertTrue(target.isValid())
            dist = abs(safe.red() - target.red()) + abs(safe.green() - target.green()) + abs(safe.blue() - target.blue())
            corner_dist = abs(corner.red() - target.red()) + abs(corner.green() - target.green()) + abs(corner.blue() - target.blue())
            # Manhattan distance should be comfortably large (> 120) to prevent false positives
            self.assertGreater(dist, 120, f"Distance {dist} too low for {hex_code}")
            self.assertGreater(corner_dist, 120, f"Corner distance {corner_dist} too low for {hex_code}")

    def test_region_highlight_interactive_drag_sync(self):
        from app.ui.node_editor.inspector import PropertyInspector
        scene = NodeScene()
        inspector = PropertyInspector(scene)
        pnode = PixelColorNodeItem(properties={
            "use_region": True,
            "region_x": 100,
            "region_y": 120,
            "region_w": 200,
            "region_h": 150,
            "color": "#38BDF8",
        })
        scene.add_node(pnode)
        inspector.set_node(pnode)

        # Trigger overlay region change signal (simulating drag / resize)
        inspector.region_overlay.region_changed.emit(140, 160, 250, 190)

        self.assertEqual(pnode.properties["region_x"], 140)
        self.assertEqual(pnode.properties["region_y"], 160)
        self.assertEqual(pnode.properties["region_w"], 250)
        self.assertEqual(pnode.properties["region_h"], 190)
        if inspector.edit_rx:
            self.assertEqual(inspector.edit_rx.text(), "140")
            self.assertEqual(inspector.edit_ry.text(), "160")
            self.assertEqual(inspector.edit_rw.text(), "250")
            self.assertEqual(inspector.edit_rh.text(), "190")

        inspector.region_overlay.close()

    def test_coordinate_eye_dropper_multi_overlay_init(self):
        from app.ui.eye_dropper import CoordinateEyeDropper
        dropper = CoordinateEyeDropper(parent=None)
        # Should create overlays matching connected screens
        self.assertGreaterEqual(len(dropper.overlays), 1)

        picked_data = []
        dropper.coord_picked.connect(lambda x, y, h, rgb: picked_data.append((x, y, h, rgb)))
        dropper.commit(123, 456, "#AABBCC", (170, 187, 204))

        self.assertEqual(len(picked_data), 1)
        self.assertEqual(picked_data[0], (123, 456, "#AABBCC", (170, 187, 204)))
        self.assertEqual(dropper.cur_x, 123)
        self.assertEqual(dropper.cur_y, 456)
        self.assertEqual(dropper.cur_hex, "#AABBCC")

    def test_badge_overlay_strictly_outside_bounding_box(self):
        from app.ui.indicator import RegionHighlightOverlay
        overlay = RegionHighlightOverlay()
        # Test box located at (200, 200, 150, 100)
        overlay.show_region(200, 200, 150, 100, label="Dino Sensor", color_hex="#FFA500")

        box_rect = overlay.geometry()
        badge_rect = overlay.badge_overlay.geometry()

        # The badge must be visible and placed outside the box
        self.assertTrue(overlay.badge_overlay.isVisible())
        self.assertFalse(box_rect.intersects(badge_rect), "Badge must not overlap or sit inside the search box!")
        # Placed directly above the box
        self.assertLessEqual(badge_rect.bottom(), box_rect.top())

        overlay.hide_overlay()
        self.assertFalse(overlay.badge_overlay.isVisible())
        overlay.close()

    def test_click_node_selection_synchronization(self):
        from app.ui.node_editor.inspector import PropertyInspector
        scene = NodeScene()
        node1 = ActionNodeItem("click", {"x": 100, "y": 200})
        node2 = ActionNodeItem("delay", {"duration": 750})
        scene.add_node(node1)
        scene.add_node(node2)

        inspector = PropertyInspector(scene)
        # Select node 1
        scene.node_selected.emit(node1)
        self.assertIs(inspector.current_node, node1)

        # Direct selection of node 2 without clicking off
        scene.node_selected.emit(node2)
        self.assertIs(inspector.current_node, node2)

    def test_live_node_execution_highlighting(self):
        from app.ui.node_editor.editor_window import MacroNodeEditorWindow
        from app.ui.node_editor.node_items import BaseNodeItem
        steps = [
            {"type": "click", "x": 100, "y": 200, "id": "step_a"},
            {"type": "delay", "duration": 50, "id": "step_b"},
        ]
        win = MacroNodeEditorWindow("TestHighlight", steps)
        nodes = [item for item in win.scene.items() if isinstance(item, BaseNodeItem)]
        self.assertGreaterEqual(len(nodes), 2)
        n_a = next(n for n in nodes if n.id == "step_a")
        n_b = next(n for n in nodes if n.id == "step_b")

        self.assertFalse(n_a.is_executing)
        self.assertFalse(n_b.is_executing)

        # Set step_a executing
        win.set_executing_node_id("step_a")
        self.assertTrue(n_a.is_executing)
        self.assertFalse(n_b.is_executing)

        # Transition to step_b executing
        win.set_executing_node_id("step_b")
        self.assertFalse(n_a.is_executing)
        self.assertTrue(n_b.is_executing)

        # Clear execution highlight
        win.set_executing_node_id(None)
        self.assertFalse(n_a.is_executing)
        self.assertFalse(n_b.is_executing)
        win.close()

    def test_player_step_executing_callback(self):
        from app.core.input_simulator import InputSimulator
        from app.core.player import MacroPlayer
        import time

        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)
        executing_events = []
        player.on_step_executing = lambda sid, idx, s: executing_events.append((sid, idx))

        steps = [
            {"type": "delay", "duration": 10, "dt": 10, "id": "node_1"},
            {"type": "delay", "duration": 10, "dt": 20, "id": "node_2"},
        ]
        player.play(steps, repeat=False, repeat_count=1)
        player._thread.join(timeout=3.0)

        # First steps executed, then cleared on finish with (None, -1)
        step_ids = [e[0] for e in executing_events]
        self.assertIn("node_1", step_ids)
        self.assertIn("node_2", step_ids)
        self.assertEqual(step_ids[-1], None)

    def test_screen_snipper_timer_and_crosshair_init(self):
        from app.ui.snippet_tool import ScreenSnipper
        from PyQt6.QtCore import QPoint
        snipper = ScreenSnipper()
        self.assertTrue(hasattr(snipper, "track_timer"))
        self.assertTrue(snipper.track_timer.isActive())
        self.assertGreaterEqual(len(snipper.overlays), 1)

        ov = snipper.overlays[0]
        # Overlay must have FramelessWindowHint and WindowStaysOnTopHint
        flags = ov.windowFlags()
        self.assertTrue(flags & Qt.WindowType.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowType.WindowStaysOnTopHint)

        # Crosshair update via cursor point
        ov.update_cursor_at(ov.screen_geo.center())
        self.assertIsNotNone(ov.current_pos)

        # Test finish_selection
        ov.start_pos = QPoint(10, 10)
        ov.current_pos = QPoint(60, 60)
        ov.is_selecting = True

        # Test paintEvent with active selection cutout (QRegion clipping)
        from PyQt6.QtGui import QPaintEvent
        from PyQt6.QtCore import QRect
        pe = QPaintEvent(QRect(0, 0, ov.width(), ov.height()))
        ov.paintEvent(pe)

        captured_data = []
        snipper.region_captured.connect(lambda x, y, w, h: captured_data.append((x, y, w, h)))
        ov.finish_selection(QPoint(60, 60))
        self.assertEqual(len(captured_data), 1)
        self.assertEqual(captured_data[0][2], int(round(50 * ov.dpr)))
        self.assertEqual(captured_data[0][3], int(round(50 * ov.dpr)))

        snipper.reject()
        self.assertFalse(snipper.track_timer.isActive())

    def test_eye_dropper_and_snipper_dpi_geometry(self):
        from app.ui.eye_dropper import CoordinateEyeDropper
        from app.ui.snippet_tool import ScreenSnipper
        from PyQt6.QtGui import QGuiApplication
        from PyQt6.QtCore import QPoint

        screens = QGuiApplication.screens()
        self.assertGreaterEqual(len(screens), 1)

        # 1. Eye Dropper overlay geometry matches Qt screen geometry
        dropper = CoordinateEyeDropper()
        for ov in dropper.overlays:
            self.assertEqual(ov.geometry(), ov.screen_geo)
            self.assertEqual(ov.dpr, ov.screen_obj.devicePixelRatio())
            # Test cursor mapping
            center_pt = ov.screen_geo.center()
            ov.update_cursor_at(center_pt)
            self.assertTrue(ov.has_cursor)
            self.assertEqual(ov.local_x, center_pt.x() - ov.screen_geo.x())
            self.assertEqual(ov.local_y, center_pt.y() - ov.screen_geo.y())
            # Hardware pixel is scaled by DPR
            expected_img_x = int(round(ov.local_x * ov.dpr))
            expected_global_x = ov.phys_rect[0] + expected_img_x
            self.assertEqual(ov.global_x, expected_global_x)
        dropper.reject()

        # 2. Snipper overlay geometry matches Qt screen geometry
        snipper = ScreenSnipper()
        for ov in snipper.overlays:
            self.assertEqual(ov.geometry(), ov.screen_geo)
            self.assertEqual(ov.dpr, ov.screen_obj.devicePixelRatio())
        snipper.reject()

    def test_compare_node_creation_and_compilation(self):
        from app.ui.node_editor.node_items import CompareNodeItem
        node = CompareNodeItem(properties={
            "var_a": "$hp",
            "op_a": "<",
            "val_a": "50",
            "logic_gate": "OR",
            "enable_cond_b": True,
            "var_b": "$mana",
            "op_b": "<",
            "val_b": "20",
        })
        self.assertEqual(node.properties["var_a"], "$hp")
        self.assertEqual(node.properties["logic_gate"], "OR")
        self.scene.add_node(node)
        self.assertIn("True", [s.name for s in node.output_sockets])
        self.assertIn("False", [s.name for s in node.output_sockets])

        # Test clone
        cloned = node.clone()
        self.assertEqual(cloned.properties["logic_gate"], "OR")

        # Test compilation
        steps = graph_to_macro(self.scene)
        # Even floating, lets test macro_to_graph
        macro_steps = [{
            "type": "compare",
            "var_a": "$hp",
            "op_a": "<",
            "val_a": "50",
            "logic_gate": "AND",
            "enable_cond_b": True,
            "var_b": "$stamina",
            "op_b": ">",
            "val_b": "10",
        }]
        scene2 = NodeScene()
        macro_to_graph(macro_steps, scene2)
        compare_nodes = [n for n in scene2.nodes if isinstance(n, CompareNodeItem)]
        self.assertEqual(len(compare_nodes), 1)
        self.assertEqual(compare_nodes[0].properties["logic_gate"], "AND")

    def test_compare_node_player_evaluation(self):
        from app.core.input_simulator import InputSimulator
        from app.core.player import MacroPlayer
        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)

        # Set variables
        player.variables["hp"] = 30
        player.variables["mana"] = 100

        # Test OR logic (hp < 50 OR mana < 50) -> True
        step_or = {
            "type": "compare",
            "var_a": "$hp",
            "op_a": "<",
            "val_a": "50",
            "logic_gate": "OR",
            "enable_cond_b": True,
            "var_b": "$mana",
            "op_b": "<",
            "val_b": "50",
        }
        res_or = player._execute_step(step_or)
        self.assertTrue(res_or)

        # Test AND logic (hp < 50 AND mana < 50) -> False (since mana is 100)
        step_and = {
            "type": "compare",
            "var_a": "$hp",
            "op_a": "<",
            "val_a": "50",
            "logic_gate": "AND",
            "enable_cond_b": True,
            "var_b": "$mana",
            "op_b": "<",
            "val_b": "50",
        }
        res_and = player._execute_step(step_and)
        self.assertFalse(res_and)

    def test_timer_node_creation_and_compilation(self):
        from app.ui.node_editor.node_items import TimerNodeItem
        node = TimerNodeItem(properties={
            "timer_name": "boss_cooldown",
            "mode": "check",
            "threshold_ms": 5000,
            "auto_reset": True,
        })
        self.assertEqual(node.properties["timer_name"], "boss_cooldown")
        self.scene.add_node(node)
        self.assertIn("Elapsed", [s.name for s in node.output_sockets])
        self.assertIn("Waiting", [s.name for s in node.output_sockets])

        # Test round-trip compilation
        macro_steps = [{
            "type": "timer",
            "timer_name": "boss_cooldown",
            "mode": "check",
            "threshold_ms": 5000,
            "auto_reset": True,
        }]
        scene2 = NodeScene()
        macro_to_graph(macro_steps, scene2)
        t_nodes = [n for n in scene2.nodes if isinstance(n, TimerNodeItem)]
        self.assertEqual(len(t_nodes), 1)
        self.assertEqual(t_nodes[0].properties["timer_name"], "boss_cooldown")

    def test_timer_node_player_execution(self):
        from app.core.input_simulator import InputSimulator
        from app.core.player import MacroPlayer
        import time

        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)

        # 1. Reset mode
        step_reset = {"type": "timer", "timer_name": "test_t", "mode": "reset"}
        self.assertTrue(player._execute_step(step_reset))
        self.assertIn("test_t", player.timers)

        # 2. Check mode before elapsed (threshold = 5000ms) -> False
        step_check = {"type": "timer", "timer_name": "test_t", "mode": "check", "threshold_ms": 5000, "auto_reset": False}
        res = player._execute_step(step_check)
        self.assertFalse(res)

        # Artificially age the timer by 6 seconds
        player.timers["test_t"] = time.perf_counter() - 6.0

        # 3. Check mode after threshold met -> True
        step_check_reset = {"type": "timer", "timer_name": "test_t", "mode": "check", "threshold_ms": 5000, "auto_reset": True}
        res2 = player._execute_step(step_check_reset)
        self.assertTrue(res2)

        # 4. Read mode
        step_read = {"type": "timer", "timer_name": "test_t", "mode": "read", "var_name": "elapsed_val"}
        self.assertTrue(player._execute_step(step_read))
        self.assertIn("elapsed_val", player.variables)

    def test_multi_node_selection_drag_together(self):
        from app.ui.node_editor.node_view import NodeView
        from PyQt6.QtTest import QTest
        from PyQt6.QtCore import Qt

        view = NodeView(self.scene)
        view.resize(800, 600)

        n1 = ActionNodeItem("click", {"x": 100, "y": 100})
        n1.setPos(100, 100)
        self.scene.add_node(n1)

        n2 = ActionNodeItem("click", {"x": 300, "y": 300})
        n2.setPos(300, 300)
        self.scene.add_node(n2)

        # Select both nodes (orange highlight)
        n1.setSelected(True)
        n2.setSelected(True)
        self.assertEqual(len(self.scene.selectedItems()), 2)

        # Drag n1 by (60, 60)
        p1 = view.mapFromScene(120, 120)
        p2 = view.mapFromScene(180, 180)

        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
        self.assertEqual(len(self.scene.selectedItems()), 2)
        QTest.mouseMove(view.viewport(), p2)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p2)

        # Both nodes should have moved together by 60px
        self.assertEqual(n1.pos().x(), 160.0)
        self.assertEqual(n1.pos().y(), 160.0)
        self.assertEqual(n2.pos().x(), 360.0)
        self.assertEqual(n2.pos().y(), 360.0)
        self.assertEqual(len(self.scene.selectedItems()), 2)

    def test_ai_vision_node_graph_compilation(self):
        from app.ui.node_editor.node_items import AIVisionNodeItem, StartNodeItem
        from app.ui.node_editor.graph_compiler import macro_to_graph, graph_to_macro

        start = StartNodeItem()
        self.scene.add_node(start)

        ai_node = AIVisionNodeItem(properties={
            "prompt": "Find blue button and click it",
            "mode": "multi_step",
            "server_url": "http://localhost:11434/v1",
            "model_name": "ui-tars-7b",
            "max_steps": 6,
            "mock_fallback": True,
        })
        self.scene.add_node(ai_node)
        self.scene.add_connection(start.output_sockets[0], ai_node.input_sockets[0])

        self.assertEqual(ai_node.properties["prompt"], "Find blue button and click it")
        self.assertIn("ui-tars-7b", ai_node.properties["model_name"])

        # Test serialization
        compiled = graph_to_macro(self.scene)
        ai_steps = [s for s in compiled if s.get("type") == "ai_vision"]
        self.assertEqual(len(ai_steps), 1)
        self.assertEqual(ai_steps[0]["prompt"], "Find blue button and click it")
        self.assertEqual(ai_steps[0]["max_steps"], 6)

        # Test deserialization
        self.scene.clear()
        macro_to_graph(compiled, self.scene)
        restored = [n for n in self.scene.nodes if isinstance(n, AIVisionNodeItem)]
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0].properties["prompt"], "Find blue button and click it")

    def test_ai_vision_player_execution(self):
        from app.core.input_simulator import InputSimulator
        from app.core.player import MacroPlayer

        sim = InputSimulator()
        player = MacroPlayer(simulator=sim)

        step = {
            "type": "ai_vision",
            "prompt": "Click search and type hello",
            "mode": "multi_step",
            "max_steps": 2,
            "mock_fallback": True,
        }
        res = player._execute_step(step)
        self.assertTrue(res)
        self.assertEqual(player.variables.get("$ai_found"), 1)
        self.assertGreater(player.variables.get("$ai_steps_taken", 0), 0)

    def test_config_import_preserves_graph_data(self):
        import tempfile
        import json
        import os
        from app.config import ConfigManager

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "config.json")
            cfg = ConfigManager(config_file=cfg_path)

            export_file = os.path.join(tmpdir, "export.json")
            sample_payload = {
                "macros": {
                    "TestMacro": {
                        "steps": [{"type": "click", "x": 100, "y": 100}],
                        "duration": 500,
                        "graph_data": {
                            "nodes": [{"id": "n1", "type": "click", "x": 50, "y": 50}],
                            "connections": [],
                        }
                    }
                }
            }
            with open(export_file, "w", encoding="utf-8") as f:
                json.dump(sample_payload, f)

            imported = cfg.import_macros_from_file(export_file)
            self.assertIn("TestMacro", imported)
            macro_obj = cfg.data["macros"]["TestMacro"]
            self.assertIn("graph_data", macro_obj)
            self.assertEqual(len(macro_obj["graph_data"]["nodes"]), 1)

    def test_sticky_note_item_properties_and_collapse(self):
        from app.ui.node_editor.node_items import StickyNoteNodeItem
        note = StickyNoteNodeItem(properties={
            "text": "test note content",
            "color": "#E5D875",
            "width": 240.0,
            "height": 180.0,
            "collapsed": False,
        })
        self.assertEqual(note.width, 240.0)
        self.assertEqual(note.height, 180.0)
        self.assertFalse(note.collapsed)
        self.assertEqual(note.properties["text"], "test note content")

        # Test collapse toggle
        note.toggle_collapse()
        self.assertTrue(note.collapsed)
        self.assertTrue(note.properties["collapsed"])
        b_rect = note.boundingRect()
        self.assertEqual(b_rect.height(), 32.0)  # 24 + 8 compact pill strip

        # Test re-expand toggle
        note.toggle_collapse()
        self.assertFalse(note.collapsed)
        self.assertFalse(note.properties["collapsed"])

        # Test resize
        note.set_size(300.0, 220.0)
        self.assertEqual(note.width, 300.0)
        self.assertEqual(note.height, 220.0)

        # Test text update
        note.set_text("updated note")
        self.assertEqual(note.properties["text"], "updated note")

    def test_sticky_note_serialization_and_deserialization(self):
        from app.ui.node_editor.node_items import StickyNoteNodeItem
        from app.ui.node_editor.undo_manager import serialize_scene, deserialize_scene

        note = StickyNoteNodeItem(properties={
            "text": "Workflow explanation",
            "color": "#7DD3FC",
            "width": 250.0,
            "height": 190.0,
            "collapsed": True,
        })
        self.scene.add_node(note, QPointF(100, 100))
        data = serialize_scene(self.scene)

        # Deserialize into new scene
        new_scene = NodeScene()
        deserialize_scene(new_scene, data)
        self.assertEqual(len(new_scene.nodes), 1)
        restored = new_scene.nodes[0]
        self.assertIsInstance(restored, StickyNoteNodeItem)
        self.assertEqual(restored.properties["text"], "Workflow explanation")
        self.assertEqual(restored.properties["color"], "#7DD3FC")
        self.assertEqual(restored.width, 250.0)
        self.assertEqual(restored.height, 190.0)
        self.assertTrue(restored.collapsed)

    def test_sticky_note_ignored_in_graph_compilation(self):
        from app.ui.node_editor.node_items import StickyNoteNodeItem
        start = StartNodeItem()
        act = ActionNodeItem("click", {"x": 500, "y": 500})
        note = StickyNoteNodeItem(properties={"text": "Documentation only"})

        self.scene.add_node(start, QPointF(50, 100))
        self.scene.add_node(act, QPointF(250, 100))
        self.scene.add_node(note, QPointF(150, 300))

        self.scene.add_connection(start.output_sockets[0], act.input_sockets[0])
        compiled = graph_to_macro(self.scene)

        # Sticky note has no sockets, so compiled sequence contains only Start -> Action (1 macro step)
        self.assertEqual(len(compiled), 1)
        self.assertEqual(compiled[0]["type"], "click")

    def test_selection_changed_single_node_emission(self):
        from app.ui.node_editor.node_items import ActionNodeItem
        n1 = ActionNodeItem("click", {"x": 100, "y": 100})
        n2 = ActionNodeItem("move", {"x": 200, "y": 200})
        self.scene.add_node(n1, QPointF(100, 100))
        self.scene.add_node(n2, QPointF(300, 100))

        emitted = []
        self.scene.node_selected.connect(lambda n: emitted.append(n))

        # Select n1
        self.scene.clearSelection()
        n1.setSelected(True)
        self.assertEqual(self.scene._current_selected_node, n1)

        # Select n2
        self.scene.clearSelection()
        n2.setSelected(True)
        self.assertEqual(self.scene._current_selected_node, n2)

    def test_win32_physical_coordinates_and_gdi_capture(self):
        from app.core.win32_api import get_screen_physical_rect, set_cursor_pos, get_cursor_pos
        from app.core.vision import capture_screen_win32_bgra
        from PyQt6.QtGui import QGuiApplication

        screens = QGuiApplication.screens()
        self.assertGreater(len(screens), 0)

        for s in screens:
            rect = get_screen_physical_rect(s)
            self.assertEqual(len(rect), 4)
            self.assertGreater(rect[2], 0)  # width > 0
            self.assertGreater(rect[3], 0)  # height > 0

        # Test small GDI capture region
        bgra, rx, ry, rw, rh = capture_screen_win32_bgra(region=(0, 0, 50, 50))
        self.assertIsNotNone(bgra)
        self.assertEqual(bgra.shape, (50, 50, 4))
        self.assertEqual(rw, 50)
        self.assertEqual(rh, 50)

    def test_resolve_coord_arithmetic_expressions(self):
        from app.core.player import MacroPlayer
        player = MacroPlayer()
        player.variables = {
            "found_x": 400,
            "$found_x": 400,
            "found_y": 600,
            "$found_y": 600,
            "offset": 50,
            "$offset": 50,
        }

        # Literal integers & numbers
        self.assertEqual(player._resolve_coord(122), 122)
        self.assertEqual(player._resolve_coord("642"), 642)
        self.assertEqual(player._resolve_coord(None, default=99), 99)

        # Direct variable lookup
        self.assertEqual(player._resolve_coord("$found_x"), 400)
        self.assertEqual(player._resolve_coord("found_y"), 600)

        # Arithmetic offsets
        self.assertEqual(player._resolve_coord("$found_x + 50"), 450)
        self.assertEqual(player._resolve_coord("$found_y - 25"), 575)
        self.assertEqual(player._resolve_coord("$found_x + $offset"), 450)
        self.assertEqual(player._resolve_coord("$found_x * 2 + 10"), 810)
        self.assertEqual(player._resolve_coord("($found_x + 100) / 2"), 250)

    def test_vision_node_variable_recording_and_compilation(self):
        from unittest.mock import patch
        from app.core.player import MacroPlayer
        from app.ui.node_editor.node_items import StartNodeItem, VisionNodeItem
        from app.ui.node_editor.graph_compiler import graph_to_macro

        self.scene.clear()
        start = StartNodeItem()
        self.scene.add_node(start)

        vnode = VisionNodeItem(properties={
            "save_coords": True,
            "var_x": "target_x",
            "var_y": "target_y",
        })
        self.scene.add_node(vnode)
        self.scene.add_connection(start.output_sockets[0], vnode.input_sockets[0])

        steps = graph_to_macro(self.scene)
        vstep = next(s for s in steps if s.get("type") == "wait_image")
        self.assertTrue(vstep.get("save_coords"))
        self.assertEqual(vstep.get("var_x"), "target_x")
        self.assertEqual(vstep.get("var_y"), "target_y")

        # Player execution with mocked template detection
        player = MacroPlayer()
        mock_detection = (350, 420, 50, 50, 0.95)
        with patch("app.core.player.wait_for_template_on_screen", return_value=mock_detection):
            ret = player._execute_step(vstep)
            self.assertTrue(ret)
            # Custom variables
            self.assertEqual(player.variables.get("target_x"), 350)
            self.assertEqual(player.variables.get("target_y"), 420)
            # Standard convenience variables
            self.assertEqual(player.variables.get("$found_x"), 350)
            self.assertEqual(player.variables.get("$found_y"), 420)
            self.assertEqual(player.variables.get("$image_found"), 1)

    def test_action_node_modifier_and_input_simulator(self):
        from app.ui.node_editor.node_items import StartNodeItem, ActionNodeItem
        from app.ui.node_editor.graph_compiler import graph_to_macro
        from app.core.input_simulator import InputSimulator

        self.scene.clear()
        start = StartNodeItem()
        self.scene.add_node(start)

        click_node = ActionNodeItem(action_type="click", properties={
            "x": 122,
            "y": 642,
            "button": "left",
            "modifier": "shift",
        })
        self.scene.add_node(click_node)
        self.scene.add_connection(start.output_sockets[0], click_node.input_sockets[0])

        summary = click_node.get_summary_text()
        self.assertIn("Shift+Click", summary)

        steps = graph_to_macro(self.scene)
        step = next(s for s in steps if s.get("type") == "click")
        self.assertEqual(step.get("modifier"), "shift")
        self.assertEqual(step.get("x"), 122)
        self.assertEqual(step.get("y"), 642)

        # Test InputSimulator Shift key handling
        sim = InputSimulator()
        sim.key_down(16)  # VK_SHIFT
        self.assertIn(16, sim.keys_held)

        # Calling key_up on Shift must cleanly remove 16 and not leave stuck keys
        sim.key_up(16)
        self.assertNotIn(16, sim.keys_held)
        self.assertNotIn(160, sim.keys_held)
        self.assertNotIn(161, sim.keys_held)

    def test_resolve_coord_expressions_and_bare_variables(self):
        """Test that MacroPlayer._resolve_coord handles bare variable names, $ prefixes, and arithmetic."""
        player = MacroPlayer()
        player.variables = {
            "found_x": 450,
            "$found_x": 450,
            "found_y": 320,
            "$found_y": 320,
            "i": 5,
            "$i": 5,
        }

        # Bare variables
        self.assertEqual(player._resolve_coord("found_x"), 450)
        self.assertEqual(player._resolve_coord("found_y"), 320)

        # $ variables
        self.assertEqual(player._resolve_coord("$found_x"), 450)
        self.assertEqual(player._resolve_coord("$found_y"), 320)

        # Expressions with bare variables
        self.assertEqual(player._resolve_coord("found_x + 50"), 500)
        self.assertEqual(player._resolve_coord("found_y - 20"), 300)
        self.assertEqual(player._resolve_coord("i * 10 + 2"), 52)

        # Expressions with $ variables
        self.assertEqual(player._resolve_coord("$found_x + 35"), 485)
        self.assertEqual(player._resolve_coord("$found_y - 10"), 310)

        # Direct numbers
        self.assertEqual(player._resolve_coord(780), 780)
        self.assertEqual(player._resolve_coord("920"), 920)

    def test_loop_body_nodes_branch_drag_isolation(self):
        """Test that dragging nodes inside a Loop repeat zone does NOT move or include LoopNodeItem."""
        from app.ui.node_editor.node_view import NodeView
        from app.ui.node_editor.node_items import LoopNodeItem, ActionNodeItem
        from PyQt6.QtCore import QPointF

        view = NodeView(self.scene)
        loop_node = LoopNodeItem(properties={"count": 5})
        loop_node.setPos(100, 100)
        self.scene.add_node(loop_node)

        node1 = ActionNodeItem("click", {"x": 10, "y": 20})
        node1.setPos(150, 150)
        self.scene.add_node(node1)

        node2 = ActionNodeItem("delay", {"duration": 200})
        node2.setPos(250, 150)
        self.scene.add_node(node2)

        # Wire: Loop.socket_body -> node1 -> node2 -> Loop.socket_repeat
        self.scene.add_connection(loop_node.socket_body, node1.input_sockets[0])
        self.scene.add_connection(node1.output_sockets[0], node2.input_sockets[0])
        self.scene.add_connection(node2.output_sockets[0], loop_node.socket_repeat)

        # 1. Downstream from node1 should only be [node1, node2], NOT loop_node
        downstream = view._get_downstream_nodes(node1)
        self.assertIn(node1, downstream)
        self.assertIn(node2, downstream)
        self.assertNotIn(loop_node, downstream)

        # 2. Upstream from node2 should only be [node2, node1], NOT loop_node
        upstream = view._get_upstream_nodes(node2)
        self.assertIn(node1, upstream)
        self.assertIn(node2, upstream)
        self.assertNotIn(loop_node, upstream)

        # 3. Simulate Ctrl+Drag on node1
        initial_loop_pos = QPointF(loop_node.pos())
        view._branch_drag_nodes = view._get_downstream_nodes(node1)
        view._branch_drag_prev_scene_pos = QPointF(150, 150)

        # Move mouse
        delta = QPointF(40, 20)
        for n in view._branch_drag_nodes:
            n.setPos(n.pos() + delta)
        view.node_scene.update_loop_bounds()

        # Verify loop bracket position remained strictly anchored
        self.assertEqual(loop_node.pos(), initial_loop_pos)
        self.assertEqual(node1.pos(), QPointF(190, 170))
        self.assertEqual(node2.pos(), QPointF(290, 170))

    def test_browse_template_replacement_crash_proof(self):
        """Test that browsing and replacing a template image is crash-proof and handles dialogs safely."""
        from unittest.mock import patch
        import tempfile
        import os
        from app.ui.node_editor.inspector import PropertyInspector
        from app.ui.node_editor.node_items import VisionNodeItem
        from PyQt6.QtWidgets import QMessageBox, QPushButton

        inspector = PropertyInspector(self.scene)
        vnode = VisionNodeItem()

        # Create temporary dummy template image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1, \
             tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
            orig_path = f1.name
            new_path = f2.name

        try:
            vnode.properties["template"] = orig_path
            inspector.set_node(vnode)

            # Find browse button
            btn_browse = None
            for child in inspector.findChildren(QPushButton):
                if "Browse" in child.text():
                    btn_browse = child
                    break
            self.assertIsNotNone(btn_browse, "Browse button should exist in inspector")

            # Mock QFileDialog to return new_path, and QMessageBox to click 'Replace'
            orig_add_btn = QMessageBox.addButton
            def fake_add_btn(box_self, text, role):
                btn = orig_add_btn(box_self, text, role)
                if "Replace" in text:
                    box_self._chosen_btn = btn
                return btn

            with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(new_path, "Images (*.png)")):
                with patch.object(QMessageBox, "addButton", fake_add_btn), \
                     patch.object(QMessageBox, "exec", return_value=0), \
                     patch.object(QMessageBox, "clickedButton", lambda box_self: getattr(box_self, "_chosen_btn", None)):
                    btn_browse.click()

            # Verify that template was replaced with the new snippet path
            self.assertTrue(os.path.basename(new_path) in vnode.properties["template"] or "snippet_" in vnode.properties["template"])
        finally:
            if os.path.exists(orig_path):
                os.remove(orig_path)
            if os.path.exists(new_path):
                os.remove(new_path)

    def test_ctrl_click_selection_toggle(self):
        """Test that Ctrl + Click toggles selection: adds unselected node, deselects already selected node."""
        from app.ui.node_editor.node_view import NodeView
        from app.ui.node_editor.node_items import ActionNodeItem
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QPointF, Qt

        view = NodeView(self.scene)
        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n2 = ActionNodeItem("click", {"x": 100, "y": 10})
        n3 = ActionNodeItem("click", {"x": 200, "y": 10})
        self.scene.add_node(n1)
        self.scene.add_node(n2)
        self.scene.add_node(n3)

        # 1. Select n1 normally
        n1.setSelected(True)
        self.assertTrue(n1.isSelected())
        self.assertFalse(n2.isSelected())

        # 2. Ctrl + Click on n2: n2 becomes selected, n1 stays selected
        view._ctrl_candidate_item = n2
        view._ctrl_initial_selected = False
        view._is_ctrl_branch_drag = False

        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(100, 10),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
        )
        view.mouseReleaseEvent(release_event)
        self.assertTrue(n1.isSelected())
        self.assertTrue(n2.isSelected())

        # 3. Ctrl + Click again on n2: n2 becomes deselected, n1 stays selected
        view._ctrl_candidate_item = n2
        view._ctrl_initial_selected = True
        view._is_ctrl_branch_drag = False
        view.mouseReleaseEvent(release_event)
        self.assertTrue(n1.isSelected())
        self.assertFalse(n2.isSelected())

    def test_multi_node_shake_disconnect_and_heal(self):
        """Test that shaking multiple inline nodes removes them and heals connection across the gap."""
        from app.ui.node_editor.node_view import NodeView
        from app.ui.node_editor.node_items import ActionNodeItem

        view = NodeView(self.scene)
        n0 = ActionNodeItem("click", {"x": 0, "y": 0})
        n1 = ActionNodeItem("delay", {"duration": 50})
        n2 = ActionNodeItem("delay", {"duration": 100})
        n3 = ActionNodeItem("delay", {"duration": 150})
        n4 = ActionNodeItem("click", {"x": 500, "y": 0})

        for n in (n0, n1, n2, n3, n4):
            self.scene.add_node(n)

        # Connect n0 -> n1 -> n2 -> n3 -> n4
        self.scene.add_connection(n0.output_sockets[0], n1.input_sockets[0])
        self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])
        self.scene.add_connection(n2.output_sockets[0], n3.input_sockets[0])
        self.scene.add_connection(n3.output_sockets[0], n4.input_sockets[0])
        self.assertEqual(len(self.scene.connections), 4)

        # Shake multiple selected nodes: n1, n2, n3
        view._trigger_shake_disconnect([n1, n2, n3])

        # All intermediate connections should be removed
        for n in (n1, n2, n3):
            self.assertEqual(len(n.input_sockets[0].connections), 0)
            self.assertEqual(len(n.output_sockets[0].connections), 0)

        # The connection should heal directly from n0 -> n4
        self.assertEqual(len(self.scene.connections), 1)
        healed_conn = self.scene.connections[0]
        self.assertEqual(healed_conn.start_socket.node, n0)
        self.assertEqual(healed_conn.end_socket.node, n4)

    def test_group_inside_repeat_zone_movement_and_selection(self):
        """Test that group node moves with repeat zone, is resizable and renamable."""
        from app.ui.node_editor.node_items import LoopNodeItem, ActionNodeItem
        from app.ui.node_editor.node_group import NodeGroupItem
        from app.ui.node_editor.inspector import PropertyInspector
        from PyQt6.QtCore import QPointF

        loop = LoopNodeItem(properties={"count": 3})
        loop.setPos(100, 100)
        self.scene.add_node(loop)

        # Create a group frame inside the repeat zone
        group = self.scene.add_group(title="Work Steps")
        group.setPos(140, 140)
        group.setRect(0, 0, 260, 160)

        action_in_grp = ActionNodeItem("click", {"x": 20, "y": 20})
        action_in_grp.setPos(160, 180)
        self.scene.add_node(action_in_grp)
        group.add_node(action_in_grp)

        # Connect loop body to action_in_grp
        self.scene.add_connection(loop.socket_body, action_in_grp.input_sockets[0])
        self.scene.add_connection(action_in_grp.output_sockets[0], loop.socket_repeat)

        # 1. Moving repeat zone moves group node
        initial_grp_pos = QPointF(group.pos())
        delta = QPointF(80, 50)
        loop.setPos(loop.pos() + delta)

        self.assertEqual(group.pos(), initial_grp_pos + delta)
        self.assertEqual(action_in_grp.pos(), QPointF(240, 230))

        # 2. Group node is resizable
        self.assertTrue(group.get_resize_grip_rect().isValid())
        group.setRect(0, 0, 320, 220)
        self.assertEqual(group.rect().width(), 320)
        self.assertEqual(group.rect().height(), 220)

        # 3. Group node is renamable
        group.set_title("Updated Batch")
        self.assertEqual(group.title, "Updated Batch")

        # 4. Group node in PropertyInspector
        inspector = PropertyInspector(self.scene)
        inspector.set_node(group)
        self.assertEqual(inspector.current_node, group)

    def test_edge_auto_panning_timer_and_delta(self):
        """Test that dragging nodes or cables to viewport edges triggers smooth auto-panning."""
        from app.ui.node_editor.node_view import NodeView
        from app.ui.node_editor.node_items import ActionNodeItem

        view = NodeView(self.scene)
        view.resize(800, 600)
        n = ActionNodeItem("click", {"x": 100, "y": 100})
        self.scene.add_node(n)
        n.setSelected(True)
        view._dragged_node = n

        # Move mouse near left edge (x=10)
        ev_left = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(10, 300),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseMoveEvent(ev_left)
        self.assertTrue(view._edge_scroll_timer.isActive())
        self.assertLess(view._edge_scroll_delta.x(), 0.0)

        # Move mouse to center (x=400, y=300) -> edge scrolling stops
        ev_center = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(400, 300),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseMoveEvent(ev_center)
        self.assertFalse(view._edge_scroll_timer.isActive())
        self.assertEqual(view._edge_scroll_delta.x(), 0.0)

        # Release mouse stops timer
        ev_rel = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(400, 300),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseReleaseEvent(ev_rel)
        self.assertFalse(view._edge_scroll_timer.isActive())

    def test_space_navigation_hand_cursor(self):
        """Test Space + Drag navigation changes cursor to open and closed hand."""
        from app.ui.node_editor.node_view import NodeView
        view = NodeView(self.scene)

        # 1. Press Space alone -> OpenHandCursor
        ev_sp_press = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        view.keyPressEvent(ev_sp_press)
        self.assertTrue(view._space_held)
        self.assertEqual(view.cursor().shape(), Qt.CursorShape.OpenHandCursor)

        # 2. Left click while Space held -> Panning & ClosedHandCursor
        ev_mouse_press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(200, 200),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mousePressEvent(ev_mouse_press)
        self.assertTrue(view._is_panning)
        self.assertEqual(view.cursor().shape(), Qt.CursorShape.ClosedHandCursor)

        # 3. Mouse release -> Still OpenHandCursor because Space is still held
        ev_mouse_rel = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(250, 250),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mouseReleaseEvent(ev_mouse_rel)
        self.assertFalse(view._is_panning)
        self.assertEqual(view.cursor().shape(), Qt.CursorShape.OpenHandCursor)

        # 4. Release Space -> ArrowCursor
        ev_sp_rel = QKeyEvent(QKeyEvent.Type.KeyRelease, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        view.keyReleaseEvent(ev_sp_rel)
        self.assertFalse(view._space_held)
        self.assertEqual(view.cursor().shape(), Qt.CursorShape.ArrowCursor)

    def test_shift_click_range_selection(self):
        """Test that clicking node A, then Shift+clicking node B selects all nodes in between."""
        from app.ui.node_editor.node_view import NodeView
        from app.ui.node_editor.node_items import ActionNodeItem

        view = NodeView(self.scene)
        n1 = ActionNodeItem("click", {"x": 0, "y": 0})
        n2 = ActionNodeItem("delay", {"duration": 100})
        n3 = ActionNodeItem("delay", {"duration": 200})
        n4 = ActionNodeItem("click", {"x": 400, "y": 0})

        for n in (n1, n2, n3, n4):
            self.scene.add_node(n)

        # Connect n1 -> n2 -> n3 -> n4
        self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])
        self.scene.add_connection(n2.output_sockets[0], n3.input_sockets[0])
        self.scene.add_connection(n3.output_sockets[0], n4.input_sockets[0])

        # 1. Normal click on n1
        view._last_selected_node = n1
        n1.setSelected(True)

        # 2. Shift + Click on n4
        view._shift_candidate_item = n4
        view._is_shift_branch_drag = False
        release_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(400, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ShiftModifier,
        )
        view.mouseReleaseEvent(release_event)

        # All 4 nodes along the path should be selected
        self.assertTrue(n1.isSelected())
        self.assertTrue(n2.isSelected())
        self.assertTrue(n3.isSelected())
        self.assertTrue(n4.isSelected())

    def test_ctrl_drag_downstream_excludes_enclosing_repeat_node(self):
        """Test that Ctrl+Drag on a node inside a repeat zone does not pull the repeat zone itself."""
        from app.ui.node_editor.node_view import NodeView
        from app.ui.node_editor.node_items import LoopNodeItem, ActionNodeItem

        view = NodeView(self.scene)
        loop = LoopNodeItem(properties={"count": 5})
        loop.setPos(100, 100)
        self.scene.add_node(loop)

        n1 = ActionNodeItem("click", {"x": 160, "y": 150})
        n1.setPos(160, 150)
        n2 = ActionNodeItem("delay", {"duration": 50})
        n2.setPos(260, 150)
        self.scene.add_node(n1)
        self.scene.add_node(n2)

        self.scene.add_connection(loop.socket_body, n1.input_sockets[0])
        self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])
        self.scene.add_connection(n2.output_sockets[0], loop.socket_repeat)

        downstream = view._get_downstream_nodes(n1)
        self.assertIn(n1, downstream)
        self.assertIn(n2, downstream)
        self.assertNotIn(loop, downstream)

    def test_repeat_zone_in_canvas_resizing_and_compression(self):
        """Test that repeat zone has resize grip and proportionally compresses / expands space between nodes."""
        from app.ui.node_editor.node_items import LoopNodeItem, ActionNodeItem
        from PyQt6.QtCore import QPointF
        from PyQt6.QtWidgets import QGraphicsSceneMouseEvent

        loop = LoopNodeItem(properties={"count": 3})
        loop.setPos(100, 100)
        loop.clamp_width = 300.0
        loop.clamp_height = 200.0
        self.scene.add_node(loop)

        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n1.setPos(150, 150)
        n2 = ActionNodeItem("click", {"x": 20, "y": 20})
        n2.setPos(250, 180)
        self.scene.add_node(n1)
        self.scene.add_node(n2)
        self.scene.add_connection(loop.socket_body, n1.input_sockets[0])
        self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])
        self.scene.add_connection(n2.output_sockets[0], loop.socket_repeat)

        # Grip exists on bottom right
        grip = loop.get_resize_grip_rect()
        self.assertTrue(grip.isValid())
        self.assertGreater(grip.right(), 270)

        # 1. Start resize drag
        ev_press = MockMouseEvent(
            button=Qt.MouseButton.LeftButton,
            pos=grip.center(),
            scene_pos=loop.pos() + grip.center(),
        )
        loop.mousePressEvent(ev_press)
        self.assertTrue(loop._is_resizing)

        # 2. Drag resize by +100px width, +50px height
        ev_move = MockMouseEvent(
            button=Qt.MouseButton.LeftButton,
            pos=grip.center() + QPointF(100, 50),
            scene_pos=loop.pos() + grip.center() + QPointF(100, 50),
        )
        loop.mouseMoveEvent(ev_move)

        self.assertGreater(loop.clamp_width, 350.0)
        self.assertGreater(n2.pos().x(), 250.0)  # Node space expanded!

        # 3. Release resize
        ev_rel = MockMouseEvent(button=Qt.MouseButton.LeftButton)
        loop.mouseReleaseEvent(ev_rel)
        self.assertFalse(loop._is_resizing)

    def test_group_in_canvas_resizing_and_compression(self):
        """Test that group frame proportionally compresses / expands space between enclosed nodes."""
        from app.ui.node_editor.node_group import NodeGroupItem
        from app.ui.node_editor.node_items import ActionNodeItem
        from PyQt6.QtCore import QPointF

        group = NodeGroupItem(title="Test Group")
        group.setPos(50, 50)
        group.setRect(0, 0, 300, 200)
        self.scene.addItem(group)
        self.scene.groups.append(group)

        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n1.setPos(100, 100)
        n2 = ActionNodeItem("click", {"x": 20, "y": 20})
        n2.setPos(200, 150)
        self.scene.add_node(n1)
        self.scene.add_node(n2)
        group.add_node(n1)
        group.add_node(n2)

        # Start resize drag
        grip = group.get_resize_grip_rect()
        ev_press = MockMouseEvent(
            button=Qt.MouseButton.LeftButton,
            pos=grip.center(),
            scene_pos=group.pos() + grip.center(),
        )
        group.mousePressEvent(ev_press)
        self.assertTrue(group._is_resizing)

        # Compress width from 300 to 150 (half width)
        ev_move = MockMouseEvent(
            button=Qt.MouseButton.LeftButton,
            pos=grip.center() - QPointF(150, 50),
            scene_pos=group.pos() + grip.center() - QPointF(150, 50),
        )
        group.mouseMoveEvent(ev_move)

        # Space between nodes should be compressed
        dx_after = n2.pos().x() - n1.pos().x()
        self.assertLess(dx_after, 100.0)

        ev_rel = MockMouseEvent(button=Qt.MouseButton.LeftButton)
        group.mouseReleaseEvent(ev_rel)
        self.assertFalse(group._is_resizing)

    def test_group_selected_no_nesting_on_click_away(self):
        """Test that grouping nodes twice or clicking away never creates duplicate nested groups."""
        from app.ui.node_editor.node_items import ActionNodeItem

        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n2 = ActionNodeItem("click", {"x": 20, "y": 20})
        self.scene.add_node(n1)
        self.scene.add_node(n2)

        n1.setSelected(True)
        n2.setSelected(True)
        g1 = self.scene.group_selected()
        self.assertIsNotNone(g1)
        self.assertEqual(len(self.scene.groups), 1)

        # Regrouping same nodes does not create a second group
        n1.setSelected(True)
        n2.setSelected(True)
        g2 = self.scene.group_selected()
        self.assertEqual(g1, g2)
        self.assertEqual(len(self.scene.groups), 1)

        # Clicking away clears selection without leaving zombie groups
        self.scene.clearSelection()
        self.assertEqual(len(self.scene.groups), 1)

    def test_node_group_z_value_behind_loop(self):
        """Test that NodeGroupItem zValue is below LoopNodeItem and regular nodes."""
        from app.ui.node_editor.node_group import NodeGroupItem
        from app.ui.node_editor.node_items import LoopNodeItem, ActionNodeItem

        grp = NodeGroupItem("Test Group")
        loop = LoopNodeItem()
        action = ActionNodeItem("click", {"x": 100, "y": 100})

        self.assertLess(grp.zValue(), loop.zValue())
        self.assertLess(loop.zValue(), action.zValue())

    def test_group_member_drag_no_flyout(self):
        """Test that dragging a group when a member node is selected does not move the member twice."""
        from app.ui.node_editor.node_group import NodeGroupItem
        from app.ui.node_editor.node_items import ActionNodeItem

        n1 = ActionNodeItem("click", {"x": 50, "y": 50})
        self.scene.add_node(n1, QPointF(50, 50))
        group = self.scene.add_group(nodes=[n1])

        # If n1 is selected in scene:
        n1.setSelected(True)
        init_pos = n1.pos()

        # Simulate dragging group by delta (20, 30)
        group._last_drag_pos = QPointF(100, 100)
        ev_move = MockMouseEvent(
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
            pos=QPointF(120, 130),
            scene_pos=QPointF(120, 130),
        )
        group.mouseMoveEvent(ev_move)

        # Because n1 was selected, group.mouseMoveEvent should NOT add an extra delta
        # (Qt's base move handles selected items)
        self.assertEqual(n1.pos(), init_pos)

    def test_group_color_and_geometry_serialization(self):
        """Test that group color, rect, and position are preserved through serialize/deserialize."""
        from app.ui.node_editor.undo_manager import serialize_scene, deserialize_scene
        from app.ui.node_editor.node_items import ActionNodeItem
        from PyQt6.QtGui import QColor

        n1 = ActionNodeItem("click", {"x": 50, "y": 50})
        self.scene.add_node(n1, QPointF(50, 50))
        custom_color = QColor(245, 158, 11)  # Amber
        grp = self.scene.add_group(title="Custom Group", nodes=[n1], color=custom_color)
        grp.setPos(120, 80)
        grp.setRect(0, 0, 450, 320)

        data = serialize_scene(self.scene)
        self.assertEqual(len(data["groups"]), 1)
        self.assertEqual(data["groups"][0]["color"], custom_color.name())
        self.assertEqual(data["groups"][0]["pos"], [120, 80])
        self.assertEqual(data["groups"][0]["rect"], [0, 0, 450, 320])

        # Deserialize into empty scene
        new_scene = NodeScene()
        deserialize_scene(new_scene, data)
        self.assertEqual(len(new_scene.groups), 1)
        restored_grp = new_scene.groups[0]
        self.assertEqual(restored_grp.title, "Custom Group")
        self.assertEqual(restored_grp.color.name(), custom_color.name())
        self.assertEqual(restored_grp.pos(), QPointF(120, 80))
        self.assertEqual(restored_grp.rect().width(), 450)
        self.assertEqual(restored_grp.rect().height(), 320)

    def test_cross_macro_clipboard_with_groups(self):
        """Test copying nodes and groups preserves groups across scenes."""
        from app.ui.node_editor.node_items import ActionNodeItem
        from PyQt6.QtGui import QColor

        n1 = ActionNodeItem("click", {"x": 100, "y": 100})
        n2 = ActionNodeItem("click", {"x": 200, "y": 100})
        self.scene.add_node(n1, QPointF(100, 100))
        self.scene.add_node(n2, QPointF(200, 100))
        grp = self.scene.add_group(title="Exported", nodes=[n1, n2], color=QColor("#ec4899"))

        n1.setSelected(True)
        n2.setSelected(True)
        grp.setSelected(True)

        copied_count = self.scene.copy_selected()
        self.assertEqual(copied_count, 2)

        # Paste into another scene
        scene2 = NodeScene()
        pasted_nodes = scene2.paste_clipboard(offset_step=QPointF(50, 50))
        self.assertEqual(len(pasted_nodes), 2)
        self.assertEqual(len(scene2.groups), 1)
        self.assertEqual(scene2.groups[0].title, "Exported")
        self.assertEqual(scene2.groups[0].color.name(), "#ec4899")

    def test_shake_disconnect_loop_preserves_internal_nodes(self):
        """Shaking repeat node disconnects external in/done sockets, heals external wire, keeps body intact."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        start = ActionNodeItem("click", {"x": 10, "y": 10})
        loop = LoopNodeItem(properties={"count": 5})
        body_node = ActionNodeItem("click", {"x": 50, "y": 50})
        after = ActionNodeItem("click", {"x": 100, "y": 100})

        self.scene.add_node(start, QPointF(0, 100))
        self.scene.add_node(loop, QPointF(200, 100))
        self.scene.add_node(body_node, QPointF(250, 150))
        self.scene.add_node(after, QPointF(500, 100))

        # Wire: start -> loop.socket_in; loop.socket_body -> body_node; loop.socket_done -> after
        conn_in = self.scene.add_connection(start.output_sockets[0], loop.socket_in)
        conn_body = self.scene.add_connection(loop.socket_body, body_node.input_sockets[0])
        conn_done = self.scene.add_connection(loop.socket_done, after.input_sockets[0])

        self.assertEqual(len(self.scene.connections), 3)

        # Trigger shake disconnect on loop
        self.view._trigger_shake_disconnect([loop])

        # loop.socket_body wire must still be connected!
        self.assertIn(conn_body, self.scene.connections)
        self.assertEqual(len(loop.socket_body.connections), 1)

        # External wires must be disconnected from loop
        self.assertEqual(len(loop.socket_in.connections), 0)
        self.assertEqual(len(loop.socket_done.connections), 0)

        # A healed connection between start and after must exist!
        healed = [
            c for c in self.scene.connections
            if c.start_socket == start.output_sockets[0] and c.end_socket == after.input_sockets[0]
        ]
        self.assertEqual(len(healed), 1)

    def test_loop_wire_splice_drop(self):
        """Dragging an unconnected loop onto a wire splices into socket_in and socket_done."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        n1 = ActionNodeItem("click", {"x": 0, "y": 0})
        n2 = ActionNodeItem("click", {"x": 200, "y": 0})
        loop = LoopNodeItem(properties={"count": 3})

        self.scene.add_node(n1, QPointF(0, 100))
        self.scene.add_node(n2, QPointF(400, 100))
        self.scene.add_node(loop, QPointF(150, 90))

        wire = self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])

        self.view._hovered_wire = wire
        self.view._dragged_node = loop

        # Release mouse to commit splice
        ev_rel = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(150, 90),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.view.mouseReleaseEvent(ev_rel)

        # wire is spliced: n1 -> loop.socket_in, and loop.socket_done -> n2
        self.assertNotIn(wire, self.scene.connections)
        self.assertEqual(len(loop.socket_in.connections), 1)
        self.assertEqual(loop.socket_in.connections[0].start_socket, n1.output_sockets[0])
        self.assertEqual(len(loop.socket_done.connections), 1)
        self.assertEqual(loop.socket_done.connections[0].end_socket, n2.input_sockets[0])

    def test_ctrl_and_shift_drag_downstream_upstream_on_group(self):
        """Test that _get_downstream_nodes and _get_upstream_nodes handle NodeGroupItem."""
        from app.ui.node_editor.node_items import ActionNodeItem

        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n2 = ActionNodeItem("click", {"x": 20, "y": 20})
        n3 = ActionNodeItem("click", {"x": 30, "y": 30})

        self.scene.add_node(n1, QPointF(0, 0))
        self.scene.add_node(n2, QPointF(200, 0))
        self.scene.add_node(n3, QPointF(400, 0))

        self.scene.add_connection(n1.output_sockets[0], n2.input_sockets[0])
        self.scene.add_connection(n2.output_sockets[0], n3.input_sockets[0])

        grp1 = self.scene.add_group("G1", nodes=[n1])
        grp2 = self.scene.add_group("G2", nodes=[n3])

        # Downstream from grp1 should include grp1, n1, n2, n3, and grp2
        down = self.view._get_downstream_nodes(grp1)
        self.assertIn(grp1, down)
        self.assertIn(n1, down)
        self.assertIn(n2, down)
        self.assertIn(n3, down)
        self.assertIn(grp2, down)

        # Upstream from grp2 should include grp2, n3, n2, n1, and grp1
        up = self.view._get_upstream_nodes(grp2)
        self.assertIn(grp2, up)
        self.assertIn(n3, up)
        self.assertIn(n2, up)
        self.assertIn(n1, up)
        self.assertIn(grp1, up)

    def test_multi_group_selection_and_drag(self):
        """Test that selecting multiple groups and dragging moves all groups and their member nodes in sync."""
        from app.ui.node_editor.node_items import ActionNodeItem

        n1 = ActionNodeItem("click", {"x": 10, "y": 10})
        n2 = ActionNodeItem("click", {"x": 50, "y": 50})
        self.scene.add_node(n1, QPointF(10, 10))
        self.scene.add_node(n2, QPointF(50, 50))
        grp1 = self.scene.add_group(title="Group 1", nodes=[n1, n2])

        n3 = ActionNodeItem("click", {"x": 300, "y": 10})
        n4 = ActionNodeItem("click", {"x": 350, "y": 50})
        self.scene.add_node(n3, QPointF(300, 10))
        self.scene.add_node(n4, QPointF(350, 50))
        grp2 = self.scene.add_group(title="Group 2", nodes=[n3, n4])

        grp1.setSelected(True)
        grp2.setSelected(True)

        delta = QPointF(50, 40)
        # Move both selected groups via Qt itemChange / position change
        grp1.setPos(grp1.pos() + delta)
        grp2.setPos(grp2.pos() + delta)

        # Assert all member nodes moved by exactly the delta
        self.assertEqual(n1.pos(), QPointF(60, 50))
        self.assertEqual(n2.pos(), QPointF(100, 90))
        self.assertEqual(n3.pos(), QPointF(350, 50))
        self.assertEqual(n4.pos(), QPointF(400, 90))

    def test_align_inside_repeat_node_and_group(self):
        """Test that A+Drag alignment inside repeat node or group aligns properly without crashing."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        loop = LoopNodeItem(properties={"count": 5})
        self.scene.add_node(loop, QPointF(0, 0))

        b1 = ActionNodeItem("click", {"x": 50, "y": 100})
        b2 = ActionNodeItem("delay", {"duration": 100})
        b3 = ActionNodeItem("click", {"x": 250, "y": 180})
        self.scene.add_node(b1, QPointF(50, 100))
        self.scene.add_node(b2, QPointF(150, 140))
        self.scene.add_node(b3, QPointF(250, 180))

        # Wire loop -> b1 -> b2 -> b3 -> repeat
        self.scene.add_connection(loop.socket_body, b1.input_sockets[0])
        self.scene.add_connection(b1.output_sockets[0], b2.input_sockets[0])
        self.scene.add_connection(b2.output_sockets[0], b3.input_sockets[0])
        self.scene.add_connection(b3.output_sockets[0], loop.socket_repeat)

        grp = self.scene.add_group("Loop Group", nodes=[b1, b2, b3])

        # Simulate A + Drag on b1 to align downstream nodes horizontally
        self.view._a_key_held = True
        self.view._a_align_node = b1
        self.view._a_align_start_scene_pos = QPointF(50, 100)

        # Drag 100px to the right to trigger downstream horizontal alignment
        ev_rel = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(150, 100),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.view.mouseReleaseEvent(ev_rel)

        # Ensure b2 and b3 are aligned on the Y line of b1
        self.assertEqual(b2.pos().y(), b1.pos().y())
        self.assertEqual(b3.pos().y(), b1.pos().y())
        # Ensure b2 is to the right of b1, and b3 is to the right of b2
        self.assertGreater(b2.pos().x(), b1.pos().x())
        self.assertGreater(b3.pos().x(), b2.pos().x())
        # Group and loop bounds must have updated
        self.assertTrue(grp.rect().isValid())

    def test_repeat_node_inside_group_movement_and_bounds(self):
        """Test that repeat node inside group moves in sync without double movement, and group fits properly."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        loop = LoopNodeItem(properties={"count": 3})
        body_node = ActionNodeItem("click", {"x": 50, "y": 50})
        self.scene.add_node(loop, QPointF(100, 100))
        self.scene.add_node(body_node, QPointF(150, 150))
        self.scene.add_connection(loop.socket_body, body_node.input_sockets[0])
        self.scene.add_connection(body_node.output_sockets[0], loop.socket_repeat)

        # Enclosing group containing the loop and its body node
        grp = self.scene.add_group("Parent Group", nodes=[loop, body_node])
        init_loop_pos = loop.pos()
        init_body_pos = body_node.pos()

        # Drag parent group by (60, 40)
        delta = QPointF(60, 40)
        grp.setPos(grp.pos() + delta)

        # Loop and body node must move by EXACTLY delta (no double-movement)
        self.assertEqual(loop.pos(), init_loop_pos + delta)
        self.assertEqual(body_node.pos(), init_body_pos + delta)

        # Moving the loop independently inside the group should expand/fit the group
        loop.setPos(loop.pos() + QPointF(100, 50))
        self.assertTrue(grp.rect().contains(grp.mapFromScene(loop.sceneBoundingRect().bottomRight())))

    def test_shake_disconnect_group_preserves_internal_nodes_and_heals_wire(self):
        """Test shaking a group separates it, heals through-wire, and keeps internal nodes/wires intact."""
        from app.ui.node_editor.node_items import ActionNodeItem

        n_start = ActionNodeItem("click", {"x": 10, "y": 10})
        n_g1 = ActionNodeItem("delay", {"duration": 50})
        n_g2 = ActionNodeItem("delay", {"duration": 100})
        n_end = ActionNodeItem("click", {"x": 500, "y": 10})

        self.scene.add_node(n_start, QPointF(0, 100))
        self.scene.add_node(n_g1, QPointF(200, 100))
        self.scene.add_node(n_g2, QPointF(350, 100))
        self.scene.add_node(n_end, QPointF(600, 100))

        # Wire: start -> g1 -> g2 -> end
        c_in = self.scene.add_connection(n_start.output_sockets[0], n_g1.input_sockets[0])
        c_mid = self.scene.add_connection(n_g1.output_sockets[0], n_g2.input_sockets[0])
        c_out = self.scene.add_connection(n_g2.output_sockets[0], n_end.input_sockets[0])

        grp = self.scene.add_group("Shaken Group", nodes=[n_g1, n_g2])

        # Shake group
        self.view._trigger_shake_disconnect([grp])

        # Internal connection between g1 and g2 MUST still exist!
        self.assertIn(c_mid, self.scene.connections)
        self.assertIn(n_g1, grp.nodes)
        self.assertIn(n_g2, grp.nodes)

        # External connections to start and end must be gone
        self.assertNotIn(c_in, self.scene.connections)
        self.assertNotIn(c_out, self.scene.connections)

        # Healed connection between start and end must exist!
        healed = [
            c for c in self.scene.connections
            if c.start_socket == n_start.output_sockets[0] and c.end_socket == n_end.input_sockets[0]
        ]
        self.assertEqual(len(healed), 1)

    def test_drag_node_splice_before_loop_pushes_loop_preserving_internal_node_positions(self):
        """Test splicing node before loop pushes loop right without altering relative positions of body nodes."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        start = ActionNodeItem("click", {"x": 0, "y": 0})
        loop = LoopNodeItem(properties={"count": 5})
        body1 = ActionNodeItem("delay", {"duration": 50})
        body2 = ActionNodeItem("click", {"x": 200, "y": 200})
        new_node = ActionNodeItem("delay", {"duration": 100})

        self.scene.add_node(start, QPointF(0, 100))
        self.scene.add_node(loop, QPointF(200, 100))
        self.scene.add_node(body1, QPointF(250, 150))
        self.scene.add_node(body2, QPointF(350, 180))
        self.scene.add_node(new_node, QPointF(150, 90))

        wire = self.scene.add_connection(start.output_sockets[0], loop.socket_in)
        self.scene.add_connection(loop.socket_body, body1.input_sockets[0])
        self.scene.add_connection(body1.output_sockets[0], body2.input_sockets[0])
        self.scene.add_connection(body2.output_sockets[0], loop.socket_repeat)

        rel1_before = body1.pos() - loop.pos()
        rel2_before = body2.pos() - loop.pos()
        init_loop_x = loop.pos().x()

        # Simulate wire splice of new_node onto wire
        self.view._hovered_wire = wire
        self.view._dragged_node = new_node

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QEvent
        ev_rel = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(150, 90),
            QPointF(150, 90),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.view.mouseReleaseEvent(ev_rel)

        # Wire must be spliced
        self.assertNotIn(wire, self.scene.connections)
        self.assertEqual(len(loop.socket_in.connections), 1)
        self.assertEqual(loop.socket_in.connections[0].start_socket, new_node.output_sockets[0])

        # Loop must be pushed to the right
        self.assertGreater(loop.pos().x(), init_loop_x)

        # Relative location of body nodes inside loop must be EXACTLY preserved
        rel1_after = body1.pos() - loop.pos()
        rel2_after = body2.pos() - loop.pos()
        self.assertEqual(rel1_after, rel1_before)
        self.assertEqual(rel2_after, rel2_before)

    def test_container_boundary_containment_and_shake_free(self):
        """Test that nodes cannot be dragged past loop/group boundaries, but shake frees them."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        loop = LoopNodeItem(properties={"count": 3})
        body_node = ActionNodeItem("click", {"x": 50, "y": 50})
        self.scene.add_node(loop, QPointF(200, 200))
        self.scene.add_node(body_node, QPointF(260, 260))
        self.scene.add_connection(loop.socket_body, body_node.input_sockets[0])

        # Try dragging body_node outside to the left past loop spine
        body_node.setPos(QPointF(50, 260))
        min_allowed_x = loop.pos().x() + loop.spine_width + 8.0
        self.assertGreaterEqual(body_node.pos().x(), min_allowed_x)

        # Try dragging body_node above loop header
        body_node.setPos(QPointF(260, 50))
        min_allowed_y = loop.pos().y() + loop.header_height + 8.0
        self.assertGreaterEqual(body_node.pos().y(), min_allowed_y)

        # Test group boundary containment
        normal_node = ActionNodeItem("click", {"x": 10, "y": 10})
        self.scene.add_node(normal_node, QPointF(500, 500))
        grp = self.scene.add_group("Containment Group", nodes=[normal_node])

        # Try dragging normal_node outside to the left past group frame
        normal_node.setPos(QPointF(100, normal_node.pos().y()))
        self.assertGreaterEqual(normal_node.pos().x(), grp.pos().x() + 8.0)

        # Shake normal_node free from group
        self.view._trigger_shake_disconnect([normal_node])
        self.assertIsNone(normal_node.group)

        # Now normal_node can freely move anywhere
        normal_node.setPos(QPointF(100, 100))
        self.assertEqual(normal_node.pos(), QPointF(100, 100))

    def test_tab_auto_plug_from_pulled_socket(self):
        """Test Houdini-style Tab auto-plug when pulling a wire and picking a node."""
        from app.ui.node_editor.node_items import ActionNodeItem
        from unittest.mock import patch
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtCore import QPoint

        node_a = ActionNodeItem("click", {"x": 10, "y": 10})
        self.scene.add_node(node_a, QPointF(100, 100))

        # 1. Output socket auto-plug
        with patch.object(QMenu, "exec", lambda m, pos=None: [a for a in m.actions() if not a.isSeparator()][0].trigger()):
            self.view._show_quick_add_menu(
                QPoint(100, 100),
                QPointF(350, 100),
                auto_connect_socket=node_a.output_sockets[0]
            )

        created_nodes = [n for n in self.scene.nodes if n is not node_a]
        self.assertEqual(len(created_nodes), 1)
        new_node = created_nodes[0]
        self.assertTrue(any(c.start_socket == node_a.output_sockets[0] and c.end_socket == new_node.input_sockets[0] for c in self.scene.connections))

        # 2. Input socket auto-plug
        with patch.object(QMenu, "exec", lambda m, pos=None: [a for a in m.actions() if not a.isSeparator()][0].trigger()):
            self.view._show_quick_add_menu(
                QPoint(100, 100),
                QPointF(50, 100),
                auto_connect_socket=node_a.input_sockets[0]
            )
        created_nodes2 = [n for n in self.scene.nodes if n not in (node_a, new_node)]
        self.assertEqual(len(created_nodes2), 1)
        new_node2 = created_nodes2[0]
        self.assertTrue(any(c.start_socket == new_node2.output_sockets[0] and c.end_socket == node_a.input_sockets[0] for c in self.scene.connections))

    def test_group_node_four_wall_containment(self):
        """Test that nodes cannot leak out of left, top, right, or bottom walls of a group."""
        from app.ui.node_editor.node_items import ActionNodeItem

        node = ActionNodeItem("click", {"x": 10, "y": 10})
        self.scene.add_node(node, QPointF(200, 200))
        grp = self.scene.add_group("Strict Box", nodes=[node])
        grp.setPos(150, 150)
        grp.setRect(0, 0, 300, 200)

        # Try dragging past right wall
        node.setPos(QPointF(1000, 200))
        max_allowed_x = grp.pos().x() + grp.rect().width() - node.width - 8.0
        self.assertLessEqual(node.pos().x(), max_allowed_x + 0.1)

        # Try dragging past bottom wall
        node.setPos(QPointF(200, 1000))
        max_allowed_y = grp.pos().y() + grp.rect().height() - node.height - 8.0
        self.assertLessEqual(node.pos().y(), max_allowed_y + 0.1)

        # Try dragging past left wall
        node.setPos(QPointF(-100, 200))
        min_allowed_x = grp.pos().x() + 8.0
        self.assertGreaterEqual(node.pos().x(), min_allowed_x - 0.1)

        # Try dragging past top wall
        node.setPos(QPointF(200, -100))
        min_allowed_y = grp.pos().y() + grp.header_height + 8.0
        self.assertGreaterEqual(node.pos().y(), min_allowed_y - 0.1)

    def test_group_inside_repeat_node_cavity_containment(self):
        """Test that a group node inside a repeat node cannot leak out of top or left cavity walls."""
        from app.ui.node_editor.node_items import LoopNodeItem, ActionNodeItem

        loop = LoopNodeItem(properties={"count": 3})
        self.scene.add_node(loop, QPointF(100, 100))

        grp_node = ActionNodeItem("click", {"x": 10, "y": 10})
        self.scene.add_node(grp_node, QPointF(160, 160))
        self.scene.add_connection(loop.socket_body, grp_node.input_sockets[0])
        self.scene.add_connection(grp_node.output_sockets[0], loop.socket_repeat)

        grp = self.scene.add_group("Inner Box", nodes=[grp_node])
        grp.setPos(150, 140)
        grp.setRect(0, 0, 250, 150)

        # Try dragging grp past left spine of loop
        grp.setPos(QPointF(20, 140))
        min_allowed_x = loop.pos().x() + loop.spine_width + 8.0
        self.assertGreaterEqual(grp.pos().x(), min_allowed_x - 0.1)

        # Try dragging grp above loop header
        grp.setPos(QPointF(150, 20))
        min_allowed_y = loop.pos().y() + loop.header_height + 8.0
        self.assertGreaterEqual(grp.pos().y(), min_allowed_y - 0.1)

    def test_a_drag_alignment_with_repeat_nodes_on_line(self):
        """Test that A+Drag aligns along the line through repeat nodes without altering inner body layout."""
        from app.ui.node_editor.node_items import ActionNodeItem, LoopNodeItem

        node1 = ActionNodeItem("click")
        loop = LoopNodeItem(properties={"count": 3})
        body_node = ActionNodeItem("delay", {"duration": 100})
        node2 = ActionNodeItem("click")

        self.scene.add_node(node1, QPointF(50, 200))
        self.scene.add_node(loop, QPointF(300, 350))
        self.scene.add_node(body_node, QPointF(350, 420))
        self.scene.add_node(node2, QPointF(700, 100))

        # Main line: node1 -> loop -> node2
        self.scene.add_connection(node1.output_sockets[0], loop.socket_in)
        self.scene.add_connection(loop.socket_done, node2.input_sockets[0])
        # Loop body: loop.socket_body -> body_node -> loop.socket_repeat
        self.scene.add_connection(loop.socket_body, body_node.input_sockets[0])
        self.scene.add_connection(body_node.output_sockets[0], loop.socket_repeat)

        rel_body_x = body_node.pos().x() - loop.pos().x()
        rel_body_y = body_node.pos().y() - loop.pos().y()

        # Simulate A+Drag right starting from node1
        self.view._a_align_node = node1
        self.view._a_align_start_scene_pos = QPointF(50, 200)

        release_pos = self.view.mapFromScene(QPointF(100, 200))
        ev_align = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(release_pos),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.view.mouseReleaseEvent(ev_align)

        # Loop should now be aligned on the Y axis of node1 (y=200)
        self.assertEqual(loop.pos().y(), 200.0)
        # Node2 should be downstream of loop
        self.assertGreater(node2.pos().x(), loop.pos().x() + loop.clamp_width)
        self.assertEqual(node2.pos().y(), 200.0)
        # Internal body node relative offset inside loop must be preserved!
        new_rel_body_x = body_node.pos().x() - loop.pos().x()
        new_rel_body_y = body_node.pos().y() - loop.pos().y()
        self.assertAlmostEqual(rel_body_x, new_rel_body_x, delta=1.0)
        self.assertAlmostEqual(rel_body_y, new_rel_body_y, delta=1.0)

    def test_wire_splicing_atomic_undo_and_no_unwanted_push(self):
        """Test dropping a node on a wire splices cleanly with atomic undo and no push if space exists."""
        from app.ui.node_editor.node_items import ActionNodeItem

        node_a = ActionNodeItem("click")
        node_b = ActionNodeItem("click")
        node_mid = ActionNodeItem("delay", {"duration": 50})

        self.scene.add_node(node_a, QPointF(100, 100))
        self.scene.add_node(node_b, QPointF(800, 100))  # Far away: 700px gap
        conn = self.scene.add_connection(node_a.output_sockets[0], node_b.input_sockets[0])

        self.scene.add_node(node_mid, QPointF(350, 105))  # Ample space: mid right is ~500 < 800

        init_b_pos = QPointF(node_b.pos())

        # Simulate drop splice
        self.view._hovered_wire = conn
        self.view._dragged_node = node_mid

        ev_splice = QMouseEvent(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(0, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.view.mouseReleaseEvent(ev_splice)

        # Connections spliced
        self.assertTrue(any(c.start_socket == node_a.output_sockets[0] and c.end_socket == node_mid.input_sockets[0] for c in self.scene.connections))
        self.assertTrue(any(c.start_socket == node_mid.output_sockets[0] and c.end_socket == node_b.input_sockets[0] for c in self.scene.connections))
        # Node B should NOT have been shoved because 350 + width + 50 < 800
        self.assertEqual(node_b.pos(), init_b_pos)
        # Node mid Y was snapped to horizontal line (100)
        self.assertEqual(node_mid.pos().y(), 100.0)


if __name__ == "__main__":
    unittest.main()
