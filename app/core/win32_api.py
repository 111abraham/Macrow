"""
Win32 low-level API declarations, types, structures, and helper functions
used across Point Clicker Desktop for input simulation, hooks, and DPI awareness.
"""

import ctypes
from ctypes import wintypes
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Magic extra_info identifier used on all synthetic input sent by Point Clicker:
# 'PCLK' in hex (0x50434C4B)
SYNTHETIC_EXTRA_INFO = 0x50434C4B

# Constants
WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

WHEEL_DELTA = 120

# Virtual screen metrics
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

# Window styles
GWL_STYLE = -16
GWL_EXSTYLE = -20
ES_PASSWORD = 0x0020

# Window Extended Styles for Click-Through / Overlay / Taskbar
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

# Standard window styles for DWM and taskbar management
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

# SetWindowPos flags
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


# Structures
POINT = wintypes.POINT


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTunion),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LRESULT = ctypes.c_ssize_t

HOOKPROC = ctypes.WINFUNCTYPE(
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

# Function prototypes
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL

user32.SendInput.argtypes = [
    wintypes.UINT,
    ctypes.POINTER(INPUT),
    ctypes.c_int,
]
user32.SendInput.restype = wintypes.UINT

user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
user32.SetWindowsHookExW.restype = wintypes.HHOOK

user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.UnhookWindowsHookEx.restype = wintypes.BOOL

user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.CallNextHookEx.restype = LRESULT

user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
]
user32.GetMessageW.restype = wintypes.BOOL

user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.PostThreadMessageW.restype = wintypes.BOOL

user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = wintypes.HWND

user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG

user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG

user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT

kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def init_dpi_awareness():
    """Ensure process is Per-Monitor V2 DPI aware for 1:1 pixel coordinates across monitors."""
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return True
    except Exception:
        pass
    try:
        shcore = ctypes.windll.shcore
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        shcore.SetProcessDpiAwareness(2)
        return True
    except Exception:
        pass
    return False


def get_cursor_pos():
    """Return current cursor position (x, y) as tuple of ints."""
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return int(pt.x), int(pt.y)


def set_cursor_pos(x, y):
    """Set cursor position using Windows SetCursorPos."""
    return bool(user32.SetCursorPos(int(x), int(y)))


def is_point_in_own_process(x, y, own_pid=None):
    """Check if the given screen coordinate belongs to our own application process."""
    if own_pid is None:
        own_pid = os.getpid()
    pt = POINT(int(x), int(y))
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == own_pid


def is_active_control_password():
    """
    Check if the active/focused window or control has password masking (e.g. ES_PASSWORD style).
    This protects sensitive credentials from being recorded.
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        # Get point under cursor or foreground window style
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if style & ES_PASSWORD:
            return True
        # Check window class name if it indicates password
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        cls_name = buf.value.lower()
        if "password" in cls_name:
            return True
    except Exception:
        pass
    return False


def set_window_click_through(hwnd, enable=True):
    """
    Toggles WS_EX_TRANSPARENT style on a window.
    When enabled, all mouse clicks, moves, and drags pass completely through the window
    to whatever application is underneath, making the window see-through and click-through.
    """
    try:
        ex_style = user32.GetWindowLongW(int(hwnd), GWL_EXSTYLE)
        if enable:
            user32.SetWindowLongW(
                int(hwnd),
                GWL_EXSTYLE,
                ex_style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            )
        else:
            user32.SetWindowLongW(int(hwnd), GWL_EXSTYLE, ex_style & ~WS_EX_TRANSPARENT)
        return True
    except Exception as e:
        print(f"Error toggling click-through on {hwnd}: {e}")
        return False


def setup_app_window(hwnd: int) -> bool:
    """
    Configure a window (including frameless windows) as a first-class Windows application window.
    Applies WS_EX_APPWINDOW to extended style and WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU
    to standard style.
    This guarantees:
      - Appears on the Windows taskbar with its own icon.
      - Minimizes directly into the taskbar without leaving a 160x24 residual box at bottom-left.
      - Integrates properly with the Windows DWM taskbar shell.
    """
    try:
        h = wintypes.HWND(int(hwnd))
        ex_style = user32.GetWindowLongW(h, GWL_EXSTYLE)
        user32.SetWindowLongW(h, GWL_EXSTYLE, ex_style | WS_EX_APPWINDOW)

        style = user32.GetWindowLongW(h, GWL_STYLE)
        user32.SetWindowLongW(h, GWL_STYLE, style | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)

        user32.SetWindowPos(h, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        return True
    except Exception as e:
        return False


def set_window_topmost(hwnd: int, topmost: bool = True) -> bool:
    """Toggle topmost status for a window via Win32 SetWindowPos."""
    try:
        h = wintypes.HWND(int(hwnd))
        insert_after = wintypes.HWND(HWND_TOPMOST if topmost else HWND_NOTOPMOST)
        return bool(user32.SetWindowPos(h, insert_after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))
    except Exception:
        return False

