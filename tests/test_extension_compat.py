"""
Tests for Chrome Extension Point Clicker backward compatibility.
Verifies loading extension JSON format, step attributes, wheel delta compatibility,
typing steps, and viewport-to-desktop coordinate translation.
"""

import os
import json
import tempfile
import unittest
from app.config import ConfigManager


class TestExtensionCompatibility(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")
        self.cfg = ConfigManager(self.config_path)

        # Sample JSON matching the exact export from Point Clicker Chrome extension
        self.extension_json = {
            "type": "point-clicker-macros",
            "version": 1,
            "exportedAt": "2026-08-15T14:30:00.000Z",
            "macros": {
                "TradingView 15m Switch": {
                    "steps": [
                        {"type": "move", "x": 120, "y": 45, "dt": 0},
                        {"type": "down", "x": 120, "y": 45, "button": "left", "dt": 100},
                        {"type": "up", "x": 120, "y": 45, "button": "left", "dt": 180, "is_click": True},
                        {"type": "wheel", "x": 300, "y": 300, "deltaX": 0, "deltaY": 120, "deltaMode": 0, "dt": 350},
                        {"type": "type", "x": 300, "y": 300, "value": "AAPL", "dt": 600}
                    ],
                    "duration": 600
                }
            }
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extension_import_without_offset(self):
        ext_file = os.path.join(self.temp_dir.name, "extension_export.json")
        with open(ext_file, "w", encoding="utf-8") as f:
            json.dump(self.extension_json, f)

        imported = self.cfg.import_macros_from_file(ext_file)
        self.assertIn("TradingView 15m Switch", imported)

        macro = self.cfg.get_macro("TradingView 15m Switch")
        self.assertEqual(len(macro["steps"]), 5)
        self.assertEqual(macro["steps"][0]["x"], 120)
        self.assertEqual(macro["steps"][0]["y"], 45)
        self.assertEqual(macro["steps"][3]["type"], "wheel")
        self.assertEqual(macro["steps"][3]["deltaY"], 120)
        self.assertEqual(macro["steps"][4]["value"], "AAPL")

    def test_extension_import_with_viewport_offset(self):
        # Suppose the user's browser viewport starts at desktop coordinate (350, 180)
        ext_file = os.path.join(self.temp_dir.name, "extension_export.json")
        with open(ext_file, "w", encoding="utf-8") as f:
            json.dump(self.extension_json, f)

        imported = self.cfg.import_macros_from_file(ext_file, offset_x=350, offset_y=180)
        self.assertEqual(len(imported), 1)

        macro = self.cfg.get_macro("TradingView 15m Switch")
        # Step 0 was (120, 45) -> becomes (120+350, 45+180) = (470, 225)
        self.assertEqual(macro["steps"][0]["x"], 470)
        self.assertEqual(macro["steps"][0]["y"], 225)


if __name__ == "__main__":
    unittest.main()
