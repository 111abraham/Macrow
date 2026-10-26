"""
Repeat Clicker Engine for Point Clicker Desktop.
Executes rapid, high-precision mouse clicks at the active saved position.
Maintains click count, respects minimum 20ms safety limit, and provides auto-stop coordination.
"""

import time
import threading
from app.core.input_simulator import InputSimulator


class RepeatClicker:
    """Performs rapid automated clicking at a configured interval and target."""

    def __init__(self, simulator=None):
        self.simulator = simulator or InputSimulator()
        self.is_running = False
        self.interval_ms = 100
        self.target_coords = None
        self.click_count = 0

        self._thread = None
        self._stop_event = threading.Event()
        self.lock = threading.Lock()

        # Callbacks
        self.on_state_changed = None
        self.on_click = None  # (count, x, y)

    def set_target(self, coords):
        """Set the target coordinate (x, y) to click, or None to click current cursor."""
        with self.lock:
            self.target_coords = tuple(coords) if coords else None

    def set_interval(self, ms):
        """Set the repeat interval in ms (minimum 20ms)."""
        with self.lock:
            self.interval_ms = max(20, int(ms))

    def reset_counter(self):
        """Reset the total click count to 0."""
        with self.lock:
            self.click_count = 0
        if self.on_click:
            self.on_click(0, None, None)

    def start(self, target_coords=None, interval_ms=None):
        """Start the repeat clicker."""
        if self.is_running:
            return

        with self.lock:
            if target_coords is not None:
                self.target_coords = tuple(target_coords) if target_coords else None
            if interval_ms is not None:
                self.interval_ms = max(20, int(interval_ms))
            self.is_running = True

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._click_worker, daemon=True)
        self._thread.start()

        if self.on_state_changed:
            self.on_state_changed(True)

    def stop(self):
        """Stop repeat clicking."""
        if not self.is_running:
            return

        self._stop_event.set()
        self.is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
            self._thread = None

        if self.on_state_changed:
            self.on_state_changed(False)

    def _click_worker(self):
        """High-precision click loop using perf_counter."""
        while not self._stop_event.is_set():
            with self.lock:
                target = self.target_coords
                interval_sec = self.interval_ms / 1000.0

            t0 = time.perf_counter()

            if target is not None:
                x, y = target
                self.simulator.click(x, y, button="left", delay=0.005)
            else:
                self.simulator.click(button="left", delay=0.005)

            with self.lock:
                self.click_count += 1
                current_count = self.click_count

            if self.on_click:
                self.on_click(current_count, target[0] if target else None, target[1] if target else None)

            # Sleep remaining time until next click
            elapsed = time.perf_counter() - t0
            sleep_remaining = interval_sec - elapsed
            while sleep_remaining > 0:
                if self._stop_event.is_set():
                    break
                slice_sec = min(sleep_remaining, 0.005)
                time.sleep(slice_sec)
                sleep_remaining = interval_sec - (time.perf_counter() - t0)
