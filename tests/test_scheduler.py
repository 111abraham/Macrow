"""
Tests for PlaybackScheduler: mouse cursor lock, FIFO queuing, and multi-instance concurrency.
"""

import unittest
from app.core.scheduler import PlaybackScheduler


class TestPlaybackScheduler(unittest.TestCase):
    def setUp(self):
        self.scheduler = PlaybackScheduler()

    def test_immediate_grant(self):
        granted = self.scheduler.request_playback("1", lambda: None)
        self.assertTrue(granted)
        self.assertEqual(self.scheduler.active_instance_id, "1")

        # Releasing
        self.scheduler.release_playback("1")
        self.assertIsNone(self.scheduler.active_instance_id)

    def test_queuing_and_dispatch(self):
        # Instance 1 gets cursor
        self.scheduler.request_playback("1", lambda: None)

        dispatched = []
        def on_instance_2_dispatch():
            dispatched.append(2)

        # Instance 2 requests -> must be queued
        granted2 = self.scheduler.request_playback("2", on_instance_2_dispatch)
        self.assertFalse(granted2)
        self.assertEqual(len(self.scheduler.queue), 1)

        # Instance 1 finishes and releases
        self.scheduler.release_playback("1")

        # Verify instance 2 is now active
        self.assertEqual(self.scheduler.active_instance_id, "2")
        import time
        time.sleep(0.05)
        self.assertIn(2, dispatched)


if __name__ == "__main__":
    unittest.main()
