"""
Multi-instance Playback Coordinator & Queue Scheduler.
Because the Windows OS has a single physical cursor, this scheduler coordinates
macro playback across multiple independent instances, preventing cursor conflicts
and providing a graceful FIFO queue for concurrent automation requests.
"""

import threading
from collections import deque


class PlaybackScheduler:
    """Coordinates physical mouse cursor access among multiple Point Clicker instances."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active_instance_id = None
        self.queue = deque()  # list of (instance_id, start_callback)
        self.instance_status_callbacks = {}  # instance_id -> status_callback

    def register_instance(self, instance_id, status_callback):
        with self.lock:
            self.instance_status_callbacks[instance_id] = status_callback

    def unregister_instance(self, instance_id):
        with self.lock:
            self.instance_status_callbacks.pop(instance_id, None)
            self.queue = deque([(iid, cb) for (iid, cb) in self.queue if iid != instance_id])
            if self.active_instance_id == instance_id:
                self.active_instance_id = None
                self._dispatch_next_locked()

    def request_playback(self, instance_id, start_callback):
        """
        Request physical cursor ownership for playback.
        Returns True if granted immediately, False if queued.
        """
        with self.lock:
            if self.active_instance_id is None:
                self.active_instance_id = instance_id
                self._notify_status_locked(instance_id, "PLAYING")
                return True
            elif self.active_instance_id == instance_id:
                return True
            else:
                # Add to queue
                self.queue.append((instance_id, start_callback))
                pos = len(self.queue)
                msg = f"QUEUED (Waiting for Instance {self.active_instance_id} - Pos #{pos})"
                self._notify_status_locked(instance_id, msg)
                return False

    def release_playback(self, instance_id):
        """Release cursor ownership when instance stops or finishes playback."""
        with self.lock:
            if self.active_instance_id == instance_id:
                self.active_instance_id = None
                self._notify_status_locked(instance_id, "IDLE")
                self._dispatch_next_locked()

    def cancel_request(self, instance_id):
        """Remove instance from queue if it was waiting."""
        with self.lock:
            self.queue = deque([(iid, cb) for (iid, cb) in self.queue if iid != instance_id])
            if self.active_instance_id == instance_id:
                self.active_instance_id = None
                self._dispatch_next_locked()
            self._notify_status_locked(instance_id, "IDLE")

    def _dispatch_next_locked(self):
        """Dispatch the next waiting instance from queue."""
        if self.queue and self.active_instance_id is None:
            next_id, start_cb = self.queue.popleft()
            self.active_instance_id = next_id
            self._notify_status_locked(next_id, "PLAYING")
            # Update remaining queued positions
            for pos, (iid, _) in enumerate(self.queue, 1):
                msg = f"QUEUED (Waiting for Instance {next_id} - Pos #{pos})"
                self._notify_status_locked(iid, msg)
            # Trigger callback
            threading.Thread(target=start_cb, daemon=True).start()

    def _notify_status_locked(self, instance_id, status):
        cb = self.instance_status_callbacks.get(instance_id)
        if cb:
            try:
                cb(status)
            except Exception:
                pass


# Global singleton scheduler shared across all instances
GLOBAL_SCHEDULER = PlaybackScheduler()
