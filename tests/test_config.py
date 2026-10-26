"""
Tests for ConfigManager: persistence, shared positions, macro library,
instance settings, and JSON export/import format.
"""

import os
import json
import tempfile
import unittest
from app.config import ConfigManager, DEFAULT_TIMEFRAMES


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "test_config.json")
        self.cfg = ConfigManager(self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_positions(self):
        positions = self.cfg.get_positions()
        for tf in DEFAULT_TIMEFRAMES:
            self.assertIn(tf, positions)
            self.assertIsNone(positions[tf])

    def test_set_and_get_position(self):
        self.cfg.set_position("M5", 1420, 850)
        positions = self.cfg.get_positions()
        self.assertEqual(positions["M5"], [1420, 850])

        # Test persistence across reloads
        cfg2 = ConfigManager(self.config_path)
        self.assertEqual(cfg2.get_positions()["M5"], [1420, 850])

    def test_macro_save_get_delete(self):
        steps = [
            {"type": "move", "x": 100, "y": 200, "dt": 0},
            {"type": "down", "x": 100, "y": 200, "button": "left", "dt": 50},
            {"type": "up", "x": 100, "y": 200, "button": "left", "dt": 120},
        ]
        self.cfg.save_macro("TestMacro", steps, 120)
        macro = self.cfg.get_macro("TestMacro")
        self.assertIsNotNone(macro)
        self.assertEqual(len(macro["steps"]), 3)
        self.assertEqual(macro["duration"], 120)

        # Test delete
        self.cfg.delete_macro("TestMacro")
        self.assertIsNone(self.cfg.get_macro("TestMacro"))

    def test_macro_export_import_format(self):
        steps = [{"type": "click", "x": 50, "y": 60, "dt": 10}]
        self.cfg.save_macro("Chart Switch", steps, 10)

        export_path = os.path.join(self.temp_dir.name, "export.json")
        count = self.cfg.export_macros_to_file(export_path)
        self.assertEqual(count, 1)

        with open(export_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["type"], "point-clicker-macros")
        self.assertEqual(data["version"], 1)
        self.assertIn("exportedAt", data)
        self.assertIn("Chart Switch", data["macros"])

        # Import into fresh config with collision
        imported = self.cfg.import_macros_from_file(export_path)
        self.assertIn("Chart Switch (2)", imported)
        self.assertIsNotNone(self.cfg.get_macro("Chart Switch (2)"))

    def test_import_with_offset(self):
        steps = [{"type": "click", "x": 100, "y": 200, "dt": 0}]
        temp_import = os.path.join(self.temp_dir.name, "offset_test.json")
        with open(temp_import, "w", encoding="utf-8") as f:
            json.dump({
                "type": "point-clicker-macros",
                "version": 1,
                "macros": {"OffsetMacro": {"steps": steps, "duration": 0}}
            }, f)

        # Import with dx=500, dy=300
        imported = self.cfg.import_macros_from_file(temp_import, offset_x=500, offset_y=300)
        self.assertEqual(len(imported), 1)
        macro = self.cfg.get_macro("OffsetMacro")
        self.assertEqual(macro["steps"][0]["x"], 600)
        self.assertEqual(macro["steps"][0]["y"], 500)


if __name__ == "__main__":
    unittest.main()
