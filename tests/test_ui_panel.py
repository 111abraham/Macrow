"""
GUI Integration tests for MacrowPanel.
Tests panel creation, repeat X times spinbox, loop checkbox interactions,
minimize/restore behavior, opacity, edge-mode detection, and scrolling.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QWheelEvent

from app.config import ConfigManager
from app.ui.main_panel import MacrowPanel

# Ensure single QApplication exists for test suite
app = QApplication.instance() or QApplication([])


class TestUIPanel(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cfg_file = os.path.join(self.temp_dir.name, "ui_test_config.json")
        self.cfg = ConfigManager(self.cfg_file)
        self.mock_sim = MagicMock()
        self.panel = MacrowPanel(self.cfg, instance_id=1, simulator=self.mock_sim)

    def tearDown(self):
        self.panel.close()
        self.temp_dir.cleanup()

    def test_panel_initialization(self):
        self.assertIsNotNone(self.panel.title_lbl)
        self.assertEqual(self.panel.title_lbl.text(), "Macrow")
        self.assertIsNotNone(self.panel.help_btn)
        self.assertEqual(self.panel.help_btn.text(), "?")
        self.assertIsNotNone(self.panel.opacity_slider)
        self.assertIsNotNone(self.panel.record_btn)
        self.assertIsNotNone(self.panel.play_btn)
        self.assertIsNotNone(self.panel.repeat_count_spin)
        self.assertEqual(self.panel.repeat_count_spin.value(), 1)

    def test_shortcuts_help_menu(self):
        menu = self.panel._build_shortcuts_menu()
        self.assertIsNotNone(menu)
        action_texts = [a.text() for a in menu.actions()]
        self.assertTrue(any("Record" in t for t in action_texts))
        self.assertTrue(any("Play" in t for t in action_texts))
        self.assertTrue(any("Save" in t for t in action_texts))
        self.assertTrue(any("Undo" in t for t in action_texts))

    def test_repeat_x_times_and_loop_toggle(self):
        # Setting custom repeat count
        self.panel.repeat_count_spin.setValue(5)
        self.assertEqual(self.panel.repeat_count_spin.value(), 5)

        # When loop_check is enabled, repeat_count_spin is disabled
        self.panel.loop_check.setChecked(True)
        self.assertFalse(self.panel.repeat_count_spin.isEnabled())

    def test_node_editor_window_and_inspector(self):
        from app.ui.node_editor import MacroNodeEditorWindow
        from app.ui.node_editor.node_items import ActionNodeItem, IfConditionNodeItem
        from PyQt6.QtWidgets import QSplitter, QPlainTextEdit

        test_steps = [
            {"type": "click", "x": 300, "y": 400, "button": "left", "dt": 100},
            {"type": "type", "value": "Test typing multiline\nline 2", "dt": 200},
            {"type": "if_condition", "var_a": "$count", "operator": "==", "val_b": "5", "dt": 300},
        ]

        editor = MacroNodeEditorWindow("TestMacro", test_steps)
        self.assertIsInstance(editor.splitter, QSplitter)
        self.assertGreaterEqual(editor.inspector.maximumWidth(), 700)
        self.assertLessEqual(editor.inspector.minimumWidth(), 300)

        # Select type node
        type_node = next(n for n in editor.scene.nodes if n.node_type == "type")
        editor.inspector.set_node(type_node)
        # Check that multiline plain text edit exists
        txt_edit = editor.inspector.findChild(QPlainTextEdit)
        self.assertIsNotNone(txt_edit)
        self.assertIn("Test typing multiline", txt_edit.toPlainText())

        editor.close()

        # When loop_check is unchecked, repeat_count_spin is re-enabled
        self.panel.loop_check.setChecked(False)
        self.assertTrue(self.panel.repeat_count_spin.isEnabled())

    def test_minimize_toggle(self):
        # Initial: not minimized
        self.assertFalse(self.panel.isMinimized())

        # Minimize to taskbar
        self.panel.toggle_minimize(True)
        self.assertTrue(bool(self.panel.windowState() & Qt.WindowState.WindowMinimized))

        # Restore
        self.panel.toggle_minimize(False)
        self.assertFalse(bool(self.panel.windowState() & Qt.WindowState.WindowMinimized))

    def test_app_icon_set(self):
        from app.ui.assets import get_app_icon
        icon = get_app_icon()
        self.assertFalse(icon.isNull())
        self.assertFalse(self.panel.windowIcon().isNull())

    def test_opacity_slider_adjusts_window(self):
        self.panel.opacity_slider.setValue(70)
        self.assertAlmostEqual(self.panel.windowOpacity(), 0.70, places=2)
        self.assertAlmostEqual(self.cfg.get_opacity(), 0.70, places=2)

    def test_resizability_and_edge_detection(self):
        self.assertGreaterEqual(self.panel.minimumWidth(), 260)
        self.assertGreaterEqual(self.panel.minimumHeight(), 150)

        w = self.panel.width()
        h = self.panel.height()

        # Bottom-right corner
        self.assertEqual(self.panel._get_resize_mode(QPoint(w - 2, h - 2)), "bottom_right")
        # Bottom edge
        self.assertEqual(self.panel._get_resize_mode(QPoint(w // 2, h - 2)), "bottom")
        # Right edge
        self.assertEqual(self.panel._get_resize_mode(QPoint(w - 2, h // 2)), "right")
        # Center should be None
        self.assertIsNone(self.panel._get_resize_mode(QPoint(w // 2, h // 2)))

    def test_scroll_area_wheel_scroll(self):
        self.assertIsNotNone(self.panel.scroll_area)
        self.assertTrue(self.panel.scroll_area.widgetResizable())

        wheel_event = QWheelEvent(
            QPointF(100, 100),
            QPointF(100, 100),
            QPoint(0, 0),
            QPoint(0, -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        self.panel.wheelEvent(wheel_event)
        self.assertTrue(wheel_event.isAccepted())

    def test_process_recorded_steps_with_default_direct_move(self):
        raw_steps = [
            {"type": "move", "x": 10, "y": 10, "dt": 10},
            {"type": "move", "x": 20, "y": 20, "dt": 20},
            {"type": "move", "x": 30, "y": 30, "dt": 30},
            {"type": "click", "x": 30, "y": 30, "button": "left", "dt": 40},
        ]

        # 1. When default_direct_move is True
        direct_steps = self.panel._process_recorded_steps(raw_steps, default_direct_move=True)
        self.assertEqual(len(direct_steps), 2)  # 1 consolidated move + 1 click
        self.assertEqual(direct_steps[0]["type"], "move")
        self.assertEqual(direct_steps[0]["x"], 30)
        self.assertEqual(direct_steps[0]["y"], 30)
        self.assertTrue(direct_steps[0]["direct_jump"])
        self.assertEqual(len(direct_steps[0]["path_points"]), 3)

        # 2. When default_direct_move is False
        path_steps = self.panel._process_recorded_steps(raw_steps, default_direct_move=False)
        self.assertEqual(len(path_steps), 4)  # All 3 moves preserved + 1 click
        for s in path_steps[:3]:
            self.assertFalse(s.get("direct_jump", True))

    def test_editor_window_save_confirmation_and_toolbar(self):
        from app.ui.node_editor import MacroNodeEditorWindow
        from app.ui.node_editor.node_items import ActionNodeItem

        steps = [{"type": "click", "x": 100, "y": 100, "button": "left", "dt": 50}]
        editor = MacroNodeEditorWindow("TestMacro", steps)

        # Toolbar check: Save button exists, delete button removed for space
        self.assertIsNotNone(editor.save_btn)
        self.assertFalse(hasattr(editor, "delete_btn"))

        # Initially no unsaved changes
        self.assertFalse(editor._has_unsaved_changes)

        # Adding a node sets unsaved changes
        new_node = ActionNodeItem("click", {"x": 200, "y": 200})
        editor.scene.add_node(new_node)
        self.assertTrue(editor._has_unsaved_changes)

        # Saving resets unsaved changes
        editor._save_and_apply(show_notification=False)
        self.assertFalse(editor._has_unsaved_changes)

        editor.close()


if __name__ == "__main__":
    unittest.main()
