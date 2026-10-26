"""
Low-level OS Macro Recorder for Point Clicker Desktop.
Captures real OS mouse moves, clicks, drags, mouse wheels, and keyboard typing
using WH_MOUSE_LL and WH_KEYBOARD_LL hooks.
Filters synthetic events and own-process UI interactions.
"""

import time
import math
import threading
import ctypes
from ctypes import wintypes
from app.core.win32_api import (
    user32,
    kernel32,
    HOOKPROC,
    MSLLHOOKSTRUCT,
    KBDLLHOOKSTRUCT,
    WH_MOUSE_LL,
    WH_KEYBOARD_LL,
    WM_QUIT,
    WM_MOUSEMOVE,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_RBUTTONDOWN,
    WM_RBUTTONUP,
    WM_MBUTTONDOWN,
    WM_MBUTTONUP,
    WM_MOUSEWHEEL,
    WM_MOUSEHWHEEL,
    WM_KEYDOWN,
    WM_KEYUP,
    WM_SYSKEYDOWN,
    WM_SYSKEYUP,
    SYNTHETIC_EXTRA_INFO,
    is_point_in_own_process,
    is_active_control_password,
)

MAX_STEPS_DEFAULT = 6000
MOVE_THROTTLE_IDLE_SEC = 0.040   # ~40ms throttle when not dragging
MOVE_THROTTLE_DRAG_SEC = 0.016   # ~16ms throttle while dragging
WHEEL_THROTTLE_SEC = 0.016       # ~16ms throttle for wheel events


class MacroRecorder:
    """Records global system input events into a reproducible sequence of steps."""

    def __init__(self, own_pid=None, max_steps=MAX_STEPS_DEFAULT):
        self.own_pid = own_pid
        self.max_steps = max_steps

        self.is_recording = False
        self.start_time = None
        self.steps = []
        self.steps_lock = threading.Lock()

        # Throttling and tracking state
        self.last_move_time = 0.0
        self.last_move_x = None
        self.last_move_y = None
        self.last_wheel_time = 0.0
        self.buttons_held = set()

        # Click detection tracking
        self.last_down_event = None  # (time, x, y, button)
        self.last_click_event = None # (time, x, y, button)

        # Hook thread management
        self._thread = None
        self._thread_id = None
        self._mouse_hook = None
        self._kbd_hook = None
        self._mouse_proc = None
        self._kbd_proc = None
        self._ready_event = threading.Event()

        # Callbacks
        self.on_step_count_changed = None
        self.on_max_steps_reached = None

    def start(self):
        """Start capturing global input events."""
        if self.is_recording:
            return

        with self.steps_lock:
            self.steps.clear()
            self.buttons_held.clear()
            self.last_move_time = 0.0
            self.last_move_x = None
            self.last_move_y = None
            self.last_wheel_time = 0.0
            self.last_down_event = None
            self.last_click_event = None

        self.is_recording = True
        self.start_time = time.perf_counter()

        self._ready_event.clear()
        self._thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

    def stop(self):
        """Stop capturing and return the recorded steps and total duration in ms."""
        if not self.is_recording:
            return self.get_steps(), 0

        self.is_recording = False

        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        total_duration = 0
        with self.steps_lock:
            if self.steps:
                total_duration = self.steps[-1].get("dt", 0)
            result_steps = list(self.steps)

        return result_steps, total_duration

    def get_steps(self):
        with self.steps_lock:
            return list(self.steps)

    def get_step_count(self):
        with self.steps_lock:
            return len(self.steps)

    def _get_dt(self):
        if not self.start_time:
            return 0
        return int((time.perf_counter() - self.start_time) * 1000)

    def _add_step(self, step):
        with self.steps_lock:
            if len(self.steps) >= self.max_steps:
                if self.is_recording:
                    self.is_recording = False
                    if self.on_max_steps_reached:
                        threading.Thread(target=self.on_max_steps_reached, daemon=True).start()
                return

            self.steps.append(step)
            count = len(self.steps)

        if self.on_step_count_changed:
            self.on_step_count_changed(count)

    def _hook_loop(self):
        """Background Windows message loop hosting the low-level hooks."""
        self._thread_id = kernel32.GetCurrentThreadId()

        self._mouse_proc = HOOKPROC(self._low_level_mouse_proc)
        self._kbd_proc = HOOKPROC(self._low_level_kbd_proc)

        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc, None, 0
        )
        self._kbd_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._kbd_proc, None, 0
        )

        self._ready_event.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._mouse_hook:
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        if self._kbd_hook:
            user32.UnhookWindowsHookEx(self._kbd_hook)
            self._kbd_hook = None

    def _low_level_mouse_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and self.is_recording:
            struct = MSLLHOOKSTRUCT.from_address(lParam)

            # 1. Ignore synthetic events sent by our simulator / repeat clicker
            if struct.dwExtraInfo == SYNTHETIC_EXTRA_INFO:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            x = int(struct.pt.x)
            y = int(struct.pt.y)

            # 2. Ignore clicks and interactions on Point Clicker's own panel UI
            if is_point_in_own_process(x, y, self.own_pid):
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            now = time.perf_counter()
            dt = self._get_dt()

            # Handle Mouse Move
            if wParam == WM_MOUSEMOVE:
                throttle = MOVE_THROTTLE_DRAG_SEC if self.buttons_held else MOVE_THROTTLE_IDLE_SEC
                if (now - self.last_move_time) >= throttle:
                    if x != self.last_move_x or y != self.last_move_y:
                        step = {
                            "type": "move",
                            "x": x,
                            "y": y,
                            "dt": dt,
                        }
                        if self.buttons_held:
                            step["buttons"] = sorted(list(self.buttons_held))
                        self._add_step(step)
                        self.last_move_time = now
                        self.last_move_x = x
                        self.last_move_y = y

            # Handle Button Down
            elif wParam in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                btn = "left" if wParam == WM_LBUTTONDOWN else ("right" if wParam == WM_RBUTTONDOWN else "middle")
                self.buttons_held.add(btn)
                self.last_down_event = (now, x, y, btn)

                self._add_step({
                    "type": "down",
                    "x": x,
                    "y": y,
                    "button": btn,
                    "dt": dt,
                })

            # Handle Button Up
            elif wParam in (WM_LBUTTONUP, WM_RBUTTONUP, WM_MBUTTONUP):
                btn = "left" if wParam == WM_LBUTTONUP else ("right" if wParam == WM_RBUTTONUP else "middle")
                self.buttons_held.discard(btn)

                # Check if this qualifies as a click: within 6px and 600ms of down
                is_click = False
                is_dblclick = False
                if self.last_down_event and self.last_down_event[3] == btn:
                    down_time, down_x, down_y, _ = self.last_down_event
                    dist = math.hypot(x - down_x, y - down_y)
                    time_diff = now - down_time
                    if dist <= 6.0 and time_diff <= 0.60:
                        is_click = True
                        # Check double click: if previous click was on same button within 500ms and 6px
                        if self.last_click_event and self.last_click_event[3] == btn:
                            prev_time, prev_x, prev_y, _ = self.last_click_event
                            if math.hypot(x - prev_x, y - prev_y) <= 6.0 and (now - prev_time) <= 0.50:
                                is_dblclick = True
                                self.last_click_event = None
                            else:
                                self.last_click_event = (now, x, y, btn)
                        else:
                            self.last_click_event = (now, x, y, btn)

                self._add_step({
                    "type": "up",
                    "x": x,
                    "y": y,
                    "button": btn,
                    "dt": dt,
                    "is_click": is_click,
                    "is_dblclick": is_dblclick,
                })

            # Handle Mouse Wheel
            elif wParam in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                if (now - self.last_wheel_time) >= WHEEL_THROTTLE_SEC:
                    high_word = ctypes.c_short(struct.mouseData >> 16).value
                    delta_y = high_word if wParam == WM_MOUSEWHEEL else 0
                    delta_x = high_word if wParam == WM_MOUSEHWHEEL else 0
                    self._add_step({
                        "type": "wheel",
                        "x": x,
                        "y": y,
                        "deltaX": delta_x,
                        "deltaY": delta_y,
                        "deltaMode": 0,
                        "dt": dt,
                    })
                    self.last_wheel_time = now

        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _low_level_kbd_proc(self, nCode, wParam, lParam):
        if nCode >= 0 and self.is_recording:
            struct = KBDLLHOOKSTRUCT.from_address(lParam)

            if struct.dwExtraInfo == SYNTHETIC_EXTRA_INFO:
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            # Check if active control is a password field
            if is_active_control_password():
                # Redact password keystrokes for user privacy & security
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            dt = self._get_dt()
            vk = int(struct.vkCode)
            scan = int(struct.scanCode)
            is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)

            # Record key down / key up
            self._add_step({
                "type": "key_up" if is_up else "key_down",
                "vk": vk,
                "scan": scan,
                "dt": dt,
            })

        return user32.CallNextHookEx(None, nCode, wParam, lParam)
