"""
Global Hotkey and Safety Manager for Point Clicker Desktop.
Listens globally for emergency kill-switch (Ctrl+Alt+Esc), mouse corner failsafe,
and quick shortcuts (Record toggle, Play/Pause, Stop) even when the app is not focused.
"""

import threading
import ctypes
from ctypes import wintypes
from app.core.win32_api import (
    user32,
    kernel32,
    HOOKPROC,
    KBDLLHOOKSTRUCT,
    MSLLHOOKSTRUCT,
    WH_KEYBOARD_LL,
    WH_MOUSE_LL,
    WM_QUIT,
    WM_KEYDOWN,
    WM_SYSKEYDOWN,
    WM_MOUSEMOVE,
    SYNTHETIC_EXTRA_INFO,
)

VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_SHIFT = 0x10
VK_S = 0x53
VK_Q = 0x51
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_F12 = 0x7B


class GlobalHotkeyManager:
    """Listens globally for shortcuts and the emergency kill switch."""

    def __init__(self):
        self._thread = None
        self._thread_id = None
        self._kbd_hook = None
        self._kbd_proc = None
        self._ready_event = threading.Event()
        self.is_running = False

        # Callbacks
        self.on_kill_switch = None
        self.on_record_toggle = None
        self.on_play_toggle = None
        self.on_stop_playback = None

    def start(self):
        """Start global hotkey listener."""
        if self.is_running:
            return
        self.is_running = True
        self._ready_event.clear()
        self._thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

    def stop(self):
        """Stop global hotkey listener."""
        if not self.is_running:
            return
        self.is_running = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    def _is_ctrl_down(self):
        return bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)

    def _is_alt_down(self):
        return bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)

    def _hook_loop(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._kbd_proc = HOOKPROC(self._low_level_kbd_proc)

        self._kbd_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._kbd_proc, None, 0
        )

        self._ready_event.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._kbd_hook:
            user32.UnhookWindowsHookEx(self._kbd_hook)
            self._kbd_hook = None

    def _low_level_kbd_proc(self, nCode, wParam, lParam):
        try:
            if nCode >= 0:
                struct = KBDLLHOOKSTRUCT.from_address(lParam)
                # Check key down / syskey down
                if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    vk = struct.vkCode
                    ctrl = self._is_ctrl_down()
                    alt = self._is_alt_down()

                    # Emergency Stop (2-key shortcut Alt+S or Ctrl+Q, F12, or Ctrl+Alt+Esc)
                    is_stop = (
                        (alt and vk == VK_S)
                        or (ctrl and vk == VK_Q)
                        or (vk == VK_F12)
                        or (vk == VK_ESCAPE and (ctrl and alt))
                    )
                    if is_stop:
                        if self.on_kill_switch:
                            threading.Thread(target=self.on_kill_switch, daemon=True).start()
                        return 1  # Intercept

                    # F9 or Ctrl+F9: Toggle Record
                    if vk == VK_F9 and (ctrl or not alt):
                        if self.on_record_toggle:
                            threading.Thread(target=self.on_record_toggle, daemon=True).start()

                    # F8 or Ctrl+F8: Toggle Play/Pause
                    elif vk == VK_F8 and (ctrl or not alt):
                        if self.on_play_toggle:
                            threading.Thread(target=self.on_play_toggle, daemon=True).start()

                    # F7 or Ctrl+F7: Stop Playback
                    elif vk == VK_F7 and (ctrl or not alt):
                        if self.on_stop_playback:
                            threading.Thread(target=self.on_stop_playback, daemon=True).start()
        except Exception:
            pass

        return user32.CallNextHookEx(self._kbd_hook, nCode, wParam, lParam)
