"""
Persistent configuration and shared state management for Point Clicker Desktop.
Handles shared positions, macro library, per-instance settings, and JSON export/import
with full backward compatibility with the Chrome extension format.
"""

import json
import os
import copy
from datetime import datetime
from threading import Lock

DEFAULT_TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]

DEFAULT_CONFIG = {
    "version": 1,
    "positions": {tf: None for tf in DEFAULT_TIMEFRAMES},
    "active_position": "M1",
    "repeat_interval_ms": 100,
    "panel_opacity": 0.95,
    "macros": {},
    "instances": {
        "1": {
            "x": 120,
            "y": 120,
            "width": 320,
            "height": 520,
            "minimized": False,
            "selected_macro": None,
            "speed": 1.0,
            "repeat": False,
        }
    },
    "hotkeys": {
        "kill_switch": "Ctrl+Alt+Esc",
        "record_toggle": "Ctrl+F9",
        "play_toggle": "Ctrl+F8",
        "stop_playback": "Ctrl+F7",
    },
    "editor_settings": {
        "default_direct_move": True,
    },
}


class ConfigManager:
    """Manages application settings, shared macro library, and persistence."""

    def __init__(self, config_file="config.json"):
        self.config_file = os.path.abspath(config_file)
        self.lock = Lock()
        self.data = copy.deepcopy(DEFAULT_CONFIG)
        self.callbacks = []
        self.load()

    def add_change_listener(self, callback):
        """Register a callback when shared state changes."""
        self.callbacks.append(callback)

    def _notify_listeners(self):
        for cb in self.callbacks:
            try:
                cb(self.data)
            except Exception:
                pass

    def load(self):
        """Load configuration from disk, falling back to defaults."""
        with self.lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    # Merge with default structure to prevent missing keys
                    for key, val in DEFAULT_CONFIG.items():
                        if key not in loaded:
                            loaded[key] = copy.deepcopy(val)
                    # Ensure all default timeframes exist
                    for tf in DEFAULT_TIMEFRAMES:
                        if tf not in loaded["positions"]:
                            loaded["positions"][tf] = None
                    self.data = loaded
                except Exception as e:
                    print(f"Warning: Failed to load {self.config_file}: {e}")
                    self.data = copy.deepcopy(DEFAULT_CONFIG)
            else:
                self.data = copy.deepcopy(DEFAULT_CONFIG)
                self.save_locked()

    def save(self):
        """Thread-safe save to disk."""
        with self.lock:
            self.save_locked()
        self._notify_listeners()

    def save_locked(self):
        try:
            temp_path = self.config_file + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.config_file):
                os.replace(temp_path, self.config_file)
            else:
                os.rename(temp_path, self.config_file)
        except Exception as e:
            print(f"Error saving config to {self.config_file}: {e}")

    # Positions
    def get_positions(self):
        with self.lock:
            return copy.deepcopy(self.data.get("positions", {}))

    def set_position(self, timeframe, x, y):
        with self.lock:
            if x is None or y is None:
                self.data["positions"][timeframe] = None
            else:
                self.data["positions"][timeframe] = [int(x), int(y)]
        self.save()

    def get_active_position(self):
        with self.lock:
            tf = self.data.get("active_position", "M1")
            coords = self.data.get("positions", {}).get(tf)
            return tf, coords

    def set_active_position(self, timeframe):
        with self.lock:
            self.data["active_position"] = timeframe
        self.save()

    # Repeat Interval
    def get_repeat_interval(self):
        with self.lock:
            return max(20, self.data.get("repeat_interval_ms", 100))

    def set_repeat_interval(self, ms):
        with self.lock:
            self.data["repeat_interval_ms"] = max(20, int(ms))
        self.save()

    # Opacity
    def get_opacity(self):
        with self.lock:
            return float(self.data.get("panel_opacity", 0.95))

    def set_opacity(self, val):
        with self.lock:
            self.data["panel_opacity"] = max(0.20, min(1.0, float(val)))
        self.save()

    # Instance settings
    def get_instance_settings(self, instance_id):
        iid = str(instance_id)
        with self.lock:
            insts = self.data.setdefault("instances", {})
            if iid not in insts:
                insts[iid] = {
                    "x": 100 + (int(iid) - 1) * 40,
                    "y": 100 + (int(iid) - 1) * 40,
                    "width": 320,
                    "height": 520,
                    "minimized": False,
                    "selected_macro": None,
                    "speed": 1.0,
                    "repeat": False,
                }
            else:
                if "width" not in insts[iid]:
                    insts[iid]["width"] = 320
                if "height" not in insts[iid]:
                    insts[iid]["height"] = 520
            return copy.deepcopy(insts[iid])

    def update_instance_settings(self, instance_id, **kwargs):
        iid = str(instance_id)
        with self.lock:
            insts = self.data.setdefault("instances", {})
            if iid not in insts:
                insts[iid] = {}
            for k, v in kwargs.items():
                insts[iid][k] = v
        self.save()

    # Macros
    def get_macros(self):
        with self.lock:
            return copy.deepcopy(self.data.get("macros", {}))

    def get_macro(self, name):
        with self.lock:
            macro = self.data.get("macros", {}).get(name)
            return copy.deepcopy(macro) if macro else None

    def save_macro(self, name, steps, duration=None, graph_data=None):
        if duration is None and steps:
            duration = steps[-1].get("dt", 0) if steps else 0
        with self.lock:
            macros = self.data.setdefault("macros", {})
            macro_obj = {"steps": copy.deepcopy(steps), "duration": int(duration or 0)}
            if graph_data:
                macro_obj["graph_data"] = copy.deepcopy(graph_data)
            elif name in macros and isinstance(macros[name], dict) and "graph_data" in macros[name]:
                macro_obj["graph_data"] = copy.deepcopy(macros[name]["graph_data"])
            macros[name] = macro_obj
        self.save()

    def delete_macro(self, name):
        with self.lock:
            macros = self.data.get("macros", {})
            if name in macros:
                del macros[name]
        self.save()

    def generate_next_macro_name(self):
        with self.lock:
            macros = self.data.get("macros", {})
            idx = 1
            while f"Macro {idx}" in macros:
                idx += 1
            return f"Macro {idx}"

    def get_editor_setting(self, key, default=None):
        with self.lock:
            es = self.data.get("editor_settings", {})
            return es.get(key, default)

    def set_editor_setting(self, key, value):
        with self.lock:
            es = self.data.setdefault("editor_settings", {})
            es[key] = value
        self.save()

    # Export & Import
    def export_macros_to_file(self, target_filepath):
        """Export all macros in the exact format defined in the specifications."""
        with self.lock:
            export_payload = {
                "type": "point-clicker-macros",
                "version": 1,
                "exportedAt": datetime.utcnow().isoformat() + "Z",
                "macros": copy.deepcopy(self.data.get("macros", {})),
            }
        with open(target_filepath, "w", encoding="utf-8") as f:
            json.dump(export_payload, f, indent=2, ensure_ascii=False)
        return len(export_payload["macros"])

    def import_macros_from_file(self, source_filepath, offset_x=0, offset_y=0):
        """
        Import macros from a JSON file.
        On collision, keeps existing and renames imported macro with (2), (3)...
        Applies offset_x, offset_y to steps to translate coordinates if imported from browser extension.
        Returns list of imported macro names.
        """
        with open(source_filepath, "r", encoding="utf-8") as f:
            payload = json.load(f)

        imported_macros = {}
        if isinstance(payload, dict):
            if "macros" in payload and isinstance(payload["macros"], dict):
                imported_macros = payload["macros"]
            else:
                # Direct dict of macros
                imported_macros = {
                    k: v
                    for k, v in payload.items()
                    if isinstance(v, dict) and "steps" in v
                }

        imported_names = []
        with self.lock:
            macros = self.data.setdefault("macros", {})

            for name, content in imported_macros.items():
                steps = content.get("steps", [])
                duration = content.get("duration", 0)

                # Apply coordinate offset if provided
                if offset_x != 0 or offset_y != 0:
                    adjusted_steps = []
                    for step in steps:
                        st = copy.deepcopy(step)
                        if "x" in st and st["x"] is not None:
                            st["x"] = int(st["x"] + offset_x)
                        if "y" in st and st["y"] is not None:
                            st["y"] = int(st["y"] + offset_y)
                        adjusted_steps.append(st)
                    steps = adjusted_steps

                # Resolve name collision
                target_name = name
                collision_index = 2
                while target_name in macros:
                    target_name = f"{name} ({collision_index})"
                    collision_index += 1

                macro_entry = {
                    "steps": copy.deepcopy(steps),
                    "duration": duration,
                }
                if "graph_data" in content and content["graph_data"]:
                    macro_entry["graph_data"] = copy.deepcopy(content["graph_data"])

                macros[target_name] = macro_entry
                imported_names.append(target_name)

        self.save()
        return imported_names
