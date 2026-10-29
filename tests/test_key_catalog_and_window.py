"""
Unit and integration tests for the Comprehensive Key Catalog,
Discrete Key Nodes (key_press, key_down, key_up), InputSimulator,
and MacroPlayer key execution.
"""

import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF

from app.core.key_catalog import (
    KEY_CATALOG_GROUPS,
    KEY_NAME_TO_VK,
    VK_TO_KEY_NAME,
    get_vk_for_key,
    get_name_for_vk,
)
from app.core.input_simulator import InputSimulator, EXTENDED_KEYS
from app.core.player import MacroPlayer
from app.ui.node_editor.node_items import ActionNodeItem, StartNodeItem
from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.graph_compiler import macro_to_graph, graph_to_macro

app = QApplication.instance() or QApplication([])


class TestKeyCatalog(unittest.TestCase):
    def test_letters_coverage(self):
        for c in range(ord("A"), ord("Z") + 1):
            letter = chr(c)
            self.assertEqual(get_vk_for_key(letter), c)
            self.assertEqual(get_vk_for_key(letter.lower()), c)
            self.assertEqual(get_name_for_vk(c), letter)

    def test_numbers_top_row_coverage(self):
        for i in range(10):
            s = str(i)
            vk = ord("0") + i
            self.assertEqual(get_vk_for_key(s), vk)
            self.assertEqual(get_name_for_vk(vk), s)

    def test_numpad_keys_coverage(self):
        # Digits 0-9
        for i in range(10):
            vk = 0x60 + i
            self.assertEqual(get_vk_for_key(f"Num {i}"), vk)
            self.assertEqual(get_vk_for_key(f"numpad{i}"), vk)
        # Operators
        self.assertEqual(get_vk_for_key("Num +"), 0x6B)
        self.assertEqual(get_vk_for_key("Num -"), 0x6D)
        self.assertEqual(get_vk_for_key("Num *"), 0x6A)
        self.assertEqual(get_vk_for_key("Num /"), 0x6F)
        self.assertEqual(get_vk_for_key("Num ."), 0x6E)
        self.assertEqual(get_vk_for_key("Num Lock"), 0x90)
        self.assertIn(0x6F, EXTENDED_KEYS)

    def test_function_keys_coverage(self):
        for i in range(1, 13):
            self.assertEqual(get_vk_for_key(f"F{i}"), 0x70 + (i - 1))
            self.assertEqual(get_vk_for_key(f"f{i}"), 0x70 + (i - 1))
        # F13-F24
        for i in range(13, 25):
            self.assertEqual(get_vk_for_key(f"F{i}"), 0x7C + (i - 13))

    def test_navigation_and_modifiers(self):
        self.assertEqual(get_vk_for_key("Enter"), 0x0D)
        self.assertEqual(get_vk_for_key("Return"), 0x0D)
        self.assertEqual(get_vk_for_key("Escape"), 0x1B)
        self.assertEqual(get_vk_for_key("Esc"), 0x1B)
        self.assertEqual(get_vk_for_key("Tab"), 0x09)
        self.assertEqual(get_vk_for_key("Space"), 0x20)
        self.assertEqual(get_vk_for_key("Backspace"), 0x08)
        self.assertEqual(get_vk_for_key("Delete"), 0x2E)
        self.assertEqual(get_vk_for_key("Insert"), 0x2D)
        self.assertEqual(get_vk_for_key("Shift"), 0x10)
        self.assertEqual(get_vk_for_key("Ctrl"), 0x11)
        self.assertEqual(get_vk_for_key("Alt"), 0x12)
        self.assertEqual(get_vk_for_key("Windows"), 0x5B)

    def test_symbols_coverage(self):
        self.assertEqual(get_vk_for_key(";"), 0xBA)
        self.assertEqual(get_vk_for_key("="), 0xBB)
        self.assertEqual(get_vk_for_key(","), 0xBC)
        self.assertEqual(get_vk_for_key("-"), 0xBD)
        self.assertEqual(get_vk_for_key("."), 0xBE)
        self.assertEqual(get_vk_for_key("/"), 0xBF)
        self.assertEqual(get_vk_for_key("`"), 0xC0)
        self.assertEqual(get_vk_for_key("["), 0xDB)
        self.assertEqual(get_vk_for_key("\\"), 0xDC)
        self.assertEqual(get_vk_for_key("]"), 0xDD)
        self.assertEqual(get_vk_for_key("'"), 0xDE)


class TestKeyNodesAndCompilation(unittest.TestCase):
    def test_action_node_item_key_versions(self):
        node_tap = ActionNodeItem("key_press", {"key": "A", "vk": 65})
        self.assertIn("Tap Key: A", node_tap.get_summary_text())
        self.assertEqual(node_tap.title, "⌨ Key Press (Tap)")

        node_down = ActionNodeItem("key_down", {"key": "Shift", "vk": 16})
        self.assertIn("Hold Key: Shift", node_down.get_summary_text())
        self.assertEqual(node_down.title, "⌨ Key Down (Hold)")

        node_up = ActionNodeItem("key_up", {"key": "Shift", "vk": 16})
        self.assertIn("Release Key: Shift", node_up.get_summary_text())
        self.assertEqual(node_up.title, "⌨ Key Up (Release)")

    def test_graph_compilation_and_roundtrip(self):
        scene = NodeScene()
        start_node = StartNodeItem()
        node_tap = ActionNodeItem("key_press", {"key": "Enter", "vk": 13})
        node_down = ActionNodeItem("key_down", {"key": "Ctrl", "vk": 17})
        node_up = ActionNodeItem("key_up", {"key": "Ctrl", "vk": 17})

        scene.add_node(start_node, QPointF(0, 100))
        scene.add_node(node_tap, QPointF(200, 100))
        scene.add_node(node_down, QPointF(400, 100))
        scene.add_node(node_up, QPointF(600, 100))

        scene.add_connection(start_node.output_sockets[0], node_tap.input_sockets[0])
        scene.add_connection(node_tap.output_sockets[0], node_down.input_sockets[0])
        scene.add_connection(node_down.output_sockets[0], node_up.input_sockets[0])

        steps = graph_to_macro(scene)
        self.assertEqual(len(steps), 3)

        self.assertEqual(steps[0]["type"], "key_press")
        self.assertEqual(steps[0]["key"], "Enter")
        self.assertEqual(steps[0]["vk"], 13)

        self.assertEqual(steps[1]["type"], "key_down")
        self.assertEqual(steps[1]["key"], "Ctrl")
        self.assertEqual(steps[1]["vk"], 17)

        self.assertEqual(steps[2]["type"], "key_up")
        self.assertEqual(steps[2]["key"], "Ctrl")
        self.assertEqual(steps[2]["vk"], 17)

        # Decompile back to graph
        new_scene = NodeScene()
        macro_to_graph(steps, new_scene)
        self.assertEqual(len(new_scene.nodes), 4)  # 1 Start node + 3 Action nodes
        types = [n.node_type for n in new_scene.nodes[1:]]
        self.assertEqual(types, ["key_press", "key_down", "key_up"])


class TestSimulatorAndPlayerKeyExecution(unittest.TestCase):
    def test_simulator_key_press_call(self):
        sim = InputSimulator()
        sim.key_down = MagicMock()
        sim.key_up = MagicMock()

        sim.key_press(65, delay=0.001)
        sim.key_down.assert_called_once_with(65)
        sim.key_up.assert_called_once_with(65)

    def test_player_key_steps_execution(self):
        mock_sim = MagicMock()
        player = MacroPlayer(simulator=mock_sim)

        # 1. key_press step with key name
        step_tap = {"type": "key_press", "key": "A"}
        player._execute_step(step_tap)
        mock_sim.key_press.assert_called_with(65)

        # 2. key_down step with vk
        step_down = {"type": "key_down", "vk": 16}
        player._execute_step(step_down)
        mock_sim.key_down.assert_called_with(16)

        # 3. key_up step with key name
        step_up = {"type": "key_up", "key": "Shift"}
        player._execute_step(step_up)
        mock_sim.key_up.assert_called_with(16)

        # 4. legacy "key" step alias
        step_legacy = {"type": "key", "key": "Enter"}
        player._execute_step(step_legacy)
        mock_sim.key_press.assert_called_with(13)


if __name__ == "__main__":
    unittest.main()
