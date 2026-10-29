"""
Comprehensive Windows Virtual-Key (VK) Catalog and Name Mappings.
Provides complete coverage for letters (A-Z), numbers (0-9), numpad (0-9, operators),
function keys (F1-F24), navigation, modifiers, symbols, and media keys.
"""

from typing import Dict, List, Tuple, Any, Optional

# Structured grouped catalog for UI dropdowns and categorized selectors
KEY_CATALOG_GROUPS: List[Tuple[str, List[Tuple[str, int]]]] = [
    (
        "Letters (A - Z)",
        [(chr(c), c) for c in range(ord("A"), ord("Z") + 1)],
    ),
    (
        "Numbers (Top Row 0 - 9)",
        [(str(i), ord("0") + i) for i in range(10)],
    ),
    (
        "Numpad (Numeric Keypad)",
        [
            ("Num 0", 0x60),
            ("Num 1", 0x61),
            ("Num 2", 0x62),
            ("Num 3", 0x63),
            ("Num 4", 0x64),
            ("Num 5", 0x65),
            ("Num 6", 0x66),
            ("Num 7", 0x67),
            ("Num 8", 0x68),
            ("Num 9", 0x69),
            ("Num + (Add)", 0x6B),
            ("Num - (Subtract)", 0x6D),
            ("Num * (Multiply)", 0x6A),
            ("Num / (Divide)", 0x6F),
            ("Num . (Decimal)", 0x6E),
            ("Num Enter", 0x0D),
            ("Num Lock", 0x90),
        ],
    ),
    (
        "Function Keys (F1 - F12)",
        [(f"F{i}", 0x70 + (i - 1)) for i in range(1, 13)],
    ),
    (
        "Function Keys Extended (F13 - F24)",
        [(f"F{i}", 0x7C + (i - 13)) for i in range(13, 25)],
    ),
    (
        "Common Navigation & Editing",
        [
            ("Enter (Return)", 0x0D),
            ("Escape", 0x1B),
            ("Tab", 0x09),
            ("Space", 0x20),
            ("Backspace", 0x08),
            ("Delete", 0x2E),
            ("Insert", 0x2D),
            ("Home", 0x24),
            ("End", 0x23),
            ("Page Up", 0x21),
            ("Page Down", 0x22),
        ],
    ),
    (
        "Arrow Keys",
        [
            ("Up Arrow", 0x26),
            ("Down Arrow", 0x28),
            ("Left Arrow", 0x25),
            ("Right Arrow", 0x27),
        ],
    ),
    (
        "Modifiers & System Keys",
        [
            ("Shift", 0x10),
            ("Left Shift", 0xA0),
            ("Right Shift", 0xA1),
            ("Ctrl", 0x11),
            ("Left Ctrl", 0xA2),
            ("Right Ctrl", 0xA3),
            ("Alt", 0x12),
            ("Left Alt", 0xA4),
            ("Right Alt", 0xA5),
            ("Windows Key", 0x5B),
            ("Right Windows Key", 0x5C),
            ("Caps Lock", 0x14),
            ("Scroll Lock", 0x91),
            ("Print Screen", 0x2C),
            ("Pause / Break", 0x13),
            ("Context Menu (Apps)", 0x5D),
        ],
    ),
    (
        "Punctuation & Symbols",
        [
            ("; (Semicolon)", 0xBA),
            ("= (Equal)", 0xBB),
            (", (Comma)", 0xBC),
            ("- (Minus / Dash)", 0xBD),
            (". (Period)", 0xBE),
            ("/ (Slash)", 0xBF),
            ("` (Grave / Tilde)", 0xC0),
            ("[ (Open Bracket)", 0xDB),
            ("\\ (Backslash)", 0xDC),
            ("] (Close Bracket)", 0xDD),
            ("' (Quote)", 0xDE),
        ],
    ),
    (
        "Media & Volume Controls",
        [
            ("Volume Mute", 0xAD),
            ("Volume Down", 0xAE),
            ("Volume Up", 0xAF),
            ("Next Track", 0xB0),
            ("Previous Track", 0xB1),
            ("Stop Media", 0xB2),
            ("Play / Pause Media", 0xB3),
        ],
    ),
]

# Flat mapping of normalized name -> VK code
KEY_NAME_TO_VK: Dict[str, int] = {}
# Mapping of VK code -> standard display name
VK_TO_KEY_NAME: Dict[int, str] = {}

# Explicit canonical names for essential keys to prevent collision overrides
PRIMARY_CANONICAL_NAMES: Dict[int, str] = {
    0x0D: "Enter",
    0x1B: "Escape",
    0x09: "Tab",
    0x20: "Space",
    0x08: "Backspace",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x5B: "Windows",
}

for vk, name in PRIMARY_CANONICAL_NAMES.items():
    VK_TO_KEY_NAME[vk] = name

for category, keys in KEY_CATALOG_GROUPS:
    for name, vk in keys:
        if vk not in VK_TO_KEY_NAME:
            clean_name = name.split(" (")[0].strip()
            VK_TO_KEY_NAME[vk] = clean_name
        # Add primary name
        KEY_NAME_TO_VK[name.lower()] = vk
        # Add clean name
        clean = name.split(" (")[0].strip().lower()
        KEY_NAME_TO_VK[clean] = vk
        KEY_NAME_TO_VK[clean.replace(" ", "")] = vk

# Add common aliases
ALIASES: Dict[str, int] = {
    "return": 0x0D,
    "esc": 0x1B,
    "del": 0x2E,
    "ins": 0x2D,
    "control": 0x11,
    "ctrl": 0x11,
    "alt": 0x12,
    "menu": 0x12,
    "win": 0x5B,
    "cmd": 0x5B,
    "windows": 0x5B,
    "pgup": 0x21,
    "pgdn": 0x22,
    "pageup": 0x21,
    "pagedown": 0x22,
    "prtscr": 0x2C,
    "prtsc": 0x2C,
    "printscreen": 0x2C,
    "pause": 0x13,
    "break": 0x13,
    "caps": 0x14,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "leftarrow": 0x25,
    "rightarrow": 0x27,
    "uparrow": 0x26,
    "downarrow": 0x28,
    "numpad0": 0x60,
    "numpad1": 0x61,
    "numpad2": 0x62,
    "numpad3": 0x63,
    "numpad4": 0x64,
    "numpad5": 0x65,
    "numpad6": 0x66,
    "numpad7": 0x67,
    "numpad8": 0x68,
    "numpad9": 0x69,
    "numpadadd": 0x6B,
    "numpadsubtract": 0x6D,
    "numpadmultiply": 0x6A,
    "numpaddivide": 0x6F,
    "numpaddecimal": 0x6E,
    "numpadenter": 0x0D,
    "+": 0xBB,
    "-": 0xBD,
    "=": 0xBB,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
    ";": 0xBA,
    "'": 0xDE,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    "`": 0xC0,
}

for alias, vk in ALIASES.items():
    KEY_NAME_TO_VK[alias] = vk


def get_vk_for_key(key_input: Any) -> Optional[int]:
    """
    Resolve a key representation to its integer Virtual Key code.
    Accepts:
      - int: Virtual key code directly
      - str: Key name like 'A', 'Enter', 'num 5', 'F5', 'Shift', '13', '0x0D', etc.
    Returns:
      int VK code or None if unresolved.
    """
    if key_input is None:
        return None

    if isinstance(key_input, int):
        return key_input if 1 <= key_input <= 255 else None

    s = str(key_input).strip()
    if not s:
        return None

    # Single character: 'A'-'Z', '0'-'9', or symbols
    if len(s) == 1:
        ch = s.upper()
        if "A" <= ch <= "Z" or "0" <= ch <= "9":
            return ord(ch)
        if s.lower() in KEY_NAME_TO_VK:
            return KEY_NAME_TO_VK[s.lower()]

    # Normalize name lookup
    norm = s.lower().strip()
    if norm in KEY_NAME_TO_VK:
        return KEY_NAME_TO_VK[norm]

    compact = norm.replace(" ", "").replace("_", "")
    if compact in KEY_NAME_TO_VK:
        return KEY_NAME_TO_VK[compact]

    # Decimal or hex integer string for raw VK codes (e.g. "65", "0x41")
    if s.isdigit():
        val = int(s)
        return val if 1 <= val <= 255 else None
    if s.lower().startswith("0x"):
        try:
            val = int(s, 16)
            return val if 1 <= val <= 255 else None
        except ValueError:
            pass

    return None


def get_name_for_vk(vk: int) -> str:
    """Return a clean human-readable name for a given Virtual Key code."""
    try:
        vk_int = int(vk)
    except (ValueError, TypeError):
        return str(vk)

    if vk_int in VK_TO_KEY_NAME:
        return VK_TO_KEY_NAME[vk_int]

    if 0x41 <= vk_int <= 0x5A:
        return chr(vk_int)
    if 0x30 <= vk_int <= 0x39:
        return chr(vk_int)
    if 0x70 <= vk_int <= 0x7B:
        return f"F{vk_int - 0x70 + 1}"

    return f"VK_{vk_int}"
