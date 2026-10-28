"""
High-precision OS-level mouse and keyboard input simulation using Win32 SendInput.
All synthetic events are tagged with SYNTHETIC_EXTRA_INFO so the macro recorder
can distinguish real user actions from automated actions without ambiguity.
"""

import time
import ctypes
from ctypes import wintypes
from app.core.win32_api import (
    user32,
    INPUT,
    MOUSEINPUT,
    KEYBDINPUT,
    INPUT_MOUSE,
    INPUT_KEYBOARD,
    MOUSEEVENTF_MOVE,
    MOUSEEVENTF_LEFTDOWN,
    MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP,
    MOUSEEVENTF_MIDDLEDOWN,
    MOUSEEVENTF_MIDDLEUP,
    MOUSEEVENTF_WHEEL,
    MOUSEEVENTF_HWHEEL,
    WHEEL_DELTA,
    KEYEVENTF_KEYUP,
    KEYEVENTF_UNICODE,
    SYNTHETIC_EXTRA_INFO,
    set_cursor_pos,
    get_cursor_pos,
)


class InputSimulator:
    """Simulates real OS mouse clicks, drags, wheel scrolls, and keyboard inputs."""

    def __init__(self):
        # Track currently pressed mouse buttons to ensure clean release
        self.buttons_held = set()
        self.keys_held = set()

    def move_to(self, x, y):
        """Move hardware cursor directly to screen coordinate (x, y)."""
        set_cursor_pos(int(x), int(y))

    def _send_mouse_event(self, flags, data=0):
        """Send a low-level mouse event tagged with our synthetic magic value."""
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.u.mi = MOUSEINPUT(
            dx=0,
            dy=0,
            mouseData=data,
            dwFlags=flags,
            time=0,
            dwExtraInfo=SYNTHETIC_EXTRA_INFO,
        )
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def mouse_down(self, button="left", x=None, y=None):
        """Press down a mouse button at optional coordinate (x, y)."""
        if x is not None and y is not None:
            self.move_to(x, y)

        button = button.lower()
        if button == "left":
            self._send_mouse_event(MOUSEEVENTF_LEFTDOWN)
            self.buttons_held.add("left")
        elif button == "right":
            self._send_mouse_event(MOUSEEVENTF_RIGHTDOWN)
            self.buttons_held.add("right")
        elif button == "middle":
            self._send_mouse_event(MOUSEEVENTF_MIDDLEDOWN)
            self.buttons_held.add("middle")

    def mouse_up(self, button="left", x=None, y=None):
        """Release a mouse button at optional coordinate (x, y)."""
        if x is not None and y is not None:
            self.move_to(x, y)

        button = button.lower()
        if button == "left":
            self._send_mouse_event(MOUSEEVENTF_LEFTUP)
            self.buttons_held.discard("left")
        elif button == "right":
            self._send_mouse_event(MOUSEEVENTF_RIGHTUP)
            self.buttons_held.discard("right")
        elif button == "middle":
            self._send_mouse_event(MOUSEEVENTF_MIDDLEUP)
            self.buttons_held.discard("middle")

    def click(self, x=None, y=None, button="left", delay=0.015):
        """Perform a single click (down -> delay -> up)."""
        if x is not None and y is not None:
            self.move_to(x, y)
        self.mouse_down(button)
        if delay > 0:
            time.sleep(delay)
        self.mouse_up(button)

    def double_click(self, x=None, y=None, button="left", interval=0.05):
        """Perform a double click with proper spacing."""
        self.click(x, y, button)
        time.sleep(interval)
        self.click(x, y, button)

    def mouse_wheel(self, delta_y=0, delta_x=0, x=None, y=None):
        """
        Scroll mouse wheel reliably.
        delta_y > 0 scrolls up, delta_y < 0 scrolls down.
        delta_x > 0 scrolls right, delta_x < 0 scrolls left.
        """
        if x is not None and y is not None:
            self.move_to(int(x), int(y))
            # Settle time so Windows OS hit-tests the window beneath the cursor
            time.sleep(0.02)

        # Break delta_y into standard WHEEL_DELTA (120) increments for maximum application compatibility
        if delta_y != 0:
            sign = 1 if delta_y > 0 else -1
            rem = abs(int(delta_y))
            while rem > 0:
                chunk = min(rem, WHEEL_DELTA)
                self._send_mouse_event(MOUSEEVENTF_WHEEL, data=int(chunk * sign))
                rem -= chunk
                if rem > 0:
                    time.sleep(0.015)

        if delta_x != 0:
            sign = 1 if delta_x > 0 else -1
            rem = abs(int(delta_x))
            while rem > 0:
                chunk = min(rem, WHEEL_DELTA)
                self._send_mouse_event(MOUSEEVENTF_HWHEEL, data=int(chunk * sign))
                rem -= chunk
                if rem > 0:
                    time.sleep(0.015)

    def key_down(self, vk_code):
        """Press down a virtual key code."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki = KEYBDINPUT(
            wVk=int(vk_code),
            wScan=0,
            dwFlags=0,
            time=0,
            dwExtraInfo=SYNTHETIC_EXTRA_INFO,
        )
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self.keys_held.add(int(vk_code))

    def key_up(self, vk_code):
        """Release a virtual key code."""
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.u.ki = KEYBDINPUT(
            wVk=int(vk_code),
            wScan=0,
            dwFlags=KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=SYNTHETIC_EXTRA_INFO,
        )
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        self.keys_held.discard(int(vk_code))

    def type_unicode_char(self, char):
        """Type a single unicode character cleanly via KEYEVENTF_UNICODE."""
        utf16_code = ord(char)
        # Key down
        inp_down = INPUT()
        inp_down.type = INPUT_KEYBOARD
        inp_down.u.ki = KEYBDINPUT(
            wVk=0,
            wScan=utf16_code,
            dwFlags=KEYEVENTF_UNICODE,
            time=0,
            dwExtraInfo=SYNTHETIC_EXTRA_INFO,
        )
        # Key up
        inp_up = INPUT()
        inp_up.type = INPUT_KEYBOARD
        inp_up.u.ki = KEYBDINPUT(
            wVk=0,
            wScan=utf16_code,
            dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=SYNTHETIC_EXTRA_INFO,
        )
        user32.SendInput(1, ctypes.byref(inp_down), ctypes.sizeof(INPUT))
        time.sleep(0.005)
        user32.SendInput(1, ctypes.byref(inp_up), ctypes.sizeof(INPUT))

    def type_text(self, text, char_delay=0.01):
        """Type a string of characters."""
        for ch in text:
            self.type_unicode_char(ch)
            if char_delay > 0:
                time.sleep(char_delay)

    def hotkey(self, combo_str, hold_delay=0.03):
        """Execute a key combination like 'Ctrl+C', 'Alt+Tab', 'Enter', 'Ctrl+Shift+Esc'."""
        vk_map = {
            "ctrl": 0x11, "control": 0x11, "lctrl": 0xA2, "rctrl": 0xA3,
            "alt": 0x12, "menu": 0x12, "lalt": 0xA4, "ralt": 0xA5,
            "shift": 0x10, "lshift": 0xA0, "rshift": 0xA1,
            "win": 0x5B, "windows": 0x5B, "cmd": 0x5B,
            "enter": 0x0D, "return": 0x0D,
            "esc": 0x1B, "escape": 0x1B,
            "tab": 0x09,
            "space": 0x20,
            "backspace": 0x08,
            "delete": 0x2E, "del": 0x2E,
            "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
            "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
        }
        for i in range(1, 13):
            vk_map[f"f{i}"] = 0x70 + (i - 1)

        parts = [p.strip().lower() for p in combo_str.split("+") if p.strip()]
        vks = []
        for part in parts:
            if part in vk_map:
                vks.append(vk_map[part])
            elif len(part) == 1:
                vks.append(ord(part.upper()))

        if not vks:
            return

        # Press keys in order
        for vk in vks:
            self.key_down(vk)
            time.sleep(0.01)

        time.sleep(hold_delay)

        # Release in reverse order
        for vk in reversed(vks):
            self.key_up(vk)
            time.sleep(0.01)

    def release_all_held(self):
        """Safety reset: immediately release any held mouse buttons or keys."""
        held_buttons = list(self.buttons_held)
        for btn in held_buttons:
            self.mouse_up(btn)
        self.buttons_held.clear()

        held_keys = list(self.keys_held)
        for key in held_keys:
            self.key_up(key)
        self.keys_held.clear()
