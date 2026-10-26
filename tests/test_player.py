"""
Tests for MacroPlayer: speed scaling, pause/resume timing, loop repetition, and safety stop.
"""

import time
import unittest
from unittest.mock import MagicMock
from app.core.player import MacroPlayer


class TestMacroPlayer(unittest.TestCase):
    def setUp(self):
        self.mock_sim = MagicMock()
        self.mock_sim.buttons_held = set()
        self.mock_sim.keys_held = set()
        self.player = MacroPlayer(simulator=self.mock_sim)

    def test_single_pass_execution(self):
        steps = [
            {"type": "move", "x": 100, "y": 150, "dt": 0},
            {"type": "down", "x": 100, "y": 150, "button": "left", "dt": 20},
            {"type": "up", "x": 100, "y": 150, "button": "left", "dt": 40},
        ]
        self.player.play(steps, speed=2.0, repeat=False)

        # Wait for playback worker to finish
        for _ in range(50):
            if not self.player.is_playing():
                break
            time.sleep(0.02)

        self.assertFalse(self.player.is_playing())
        self.mock_sim.move_to.assert_called_with(100, 150)
        self.mock_sim.mouse_down.assert_called_with("left", 100, 150)
        self.mock_sim.mouse_up.assert_called_with("left", 100, 150)

    def test_pause_and_resume(self):
        steps = [
            {"type": "move", "x": 10, "y": 10, "dt": 0},
            {"type": "move", "x": 50, "y": 50, "dt": 150},
            {"type": "move", "x": 100, "y": 100, "dt": 300},
        ]
        self.player.play(steps, speed=1.0, repeat=False)
        time.sleep(0.05)
        self.player.pause()
        self.assertTrue(self.player.is_paused())

        time.sleep(0.1)
        self.player.resume()
        self.assertFalse(self.player.is_paused())

        # Wait for completion
        for _ in range(50):
            if not self.player.is_playing():
                break
            time.sleep(0.02)

        self.assertFalse(self.player.is_playing())

    def test_stop_releases_held(self):
        steps = [
            {"type": "down", "x": 200, "y": 200, "button": "left", "dt": 0},
            {"type": "move", "x": 400, "y": 400, "dt": 500},
        ]
        self.player.play(steps, speed=1.0, repeat=False)
        time.sleep(0.03)
        self.player.stop()

        self.assertFalse(self.player.is_playing())
        self.mock_sim.release_all_held.assert_called()

    def test_repeat_count_repetition(self):
        steps = [{"type": "move", "x": 50, "y": 50, "dt": 0}]
        passes = []
        self.player.on_pass_progress = lambda cur, tot: passes.append((cur, tot))

        self.player.play(steps, speed=2.0, repeat=False, repeat_count=3)

        for _ in range(50):
            if not self.player.is_playing():
                break
            time.sleep(0.02)

        self.assertFalse(self.player.is_playing())
        self.assertEqual(len(passes), 3)
        self.assertEqual(passes[-1], (3, 3))

    def test_wait_image_miss_branching(self):
        # When wait_image template is not found (e.g. non-existent file), it must route to miss_next
        steps = [
            {
                "id": "wait_step",
                "type": "wait_image",
                "template": "non_existent_file.png",
                "timeout": 0.05,
                "found_next": "found_action",
                "miss_next": "miss_action",
            },
            {
                "id": "found_action",
                "type": "click",
                "x": 100,
                "y": 100,
                "button": "left",
            },
            {
                "id": "miss_action",
                "type": "click",
                "x": 300,
                "y": 400,
                "button": "left",
            },
        ]
        self.player._execute_graph_pass(steps)
        # Verify that only miss_action was clicked, not found_action
        self.mock_sim.click.assert_called_once_with(300, 400, "left")

    def test_unplugged_node_skipped(self):
        steps = [
            {"id": "step1", "type": "click", "x": 50, "y": 50, "button": "left", "next": "step2"},
            {"id": "step2", "type": "click", "x": 60, "y": 60, "button": "left", "_unplugged": True},
        ]
        self.player._execute_graph_pass(steps)
        self.mock_sim.click.assert_called_once_with(50, 50, "left")


if __name__ == "__main__":
    unittest.main()
