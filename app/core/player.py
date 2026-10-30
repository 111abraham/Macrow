"""
Macro Playback Engine for Point Clicker Desktop.
Replays recorded mouse moves, clicks, drags, wheels, and keystrokes with accurate
timing, pause/resume time tracking, speed scaling, loop repetition, and safety resets.
"""

import time
import threading
from app.core.input_simulator import InputSimulator
from app.core.vision import find_template_on_screen, wait_for_template_on_screen
from app.core.key_catalog import get_vk_for_key


class MacroPlayer:
    """Executes a sequence of macro steps with precise timing control."""

    STATE_IDLE = "IDLE"
    STATE_PLAYING = "PLAYING"
    STATE_PAUSED = "PAUSED"
    STATE_STOPPED = "STOPPED"

    def __init__(self, simulator=None):
        self.simulator = simulator or InputSimulator()
        self.state = self.STATE_IDLE
        self.state_lock = threading.Lock()

        self._thread = None
        self._stop_requested = threading.Event()
        self._pause_requested = threading.Event()
        self._resume_event = threading.Event()
        self._resume_event.set()

        # Playback configuration
        self.steps = []
        self.speed = 1.0
        self.repeat = False
        self.repeat_count = 1
        self.variables = {}

        # Callbacks
        self.on_state_changed = None
        self.on_progress = None
        self.on_pass_progress = None  # (current_pass, total_passes) - 0 if infinite
        self.on_cursor_action = None  # (x, y, action_type) for visual indicator

    def is_playing(self):
        with self.state_lock:
            return self.state in (self.STATE_PLAYING, self.STATE_PAUSED)

    def is_paused(self):
        with self.state_lock:
            return self.state == self.STATE_PAUSED

    def play(self, steps, speed=1.0, repeat=False, repeat_count=1):
        """Start playing back the provided macro steps."""
        self.stop()  # Clean up any existing playback

        if not steps:
            return False

        with self.state_lock:
            self.steps = list(steps)
            self.speed = max(0.25, min(3.0, float(speed)))
            self.repeat = bool(repeat)
            self.repeat_count = max(1, int(repeat_count))
            self.state = self.STATE_PLAYING

        self._stop_requested.clear()
        self._pause_requested.clear()
        self._resume_event.set()

        self._thread = threading.Thread(target=self._playback_worker, daemon=True)
        self._thread.start()

        if self.on_state_changed:
            self.on_state_changed(self.state)
        return True

    def pause(self):
        """Pause playback, preserving position and held buttons."""
        with self.state_lock:
            if self.state == self.STATE_PLAYING:
                self.state = self.STATE_PAUSED
                self._resume_event.clear()
                self._pause_requested.set()
                if self.on_state_changed:
                    self.on_state_changed(self.state)

    def resume(self):
        """Resume playback from paused state."""
        with self.state_lock:
            if self.state == self.STATE_PAUSED:
                self.state = self.STATE_PLAYING
                self._pause_requested.clear()
                self._resume_event.set()
                if self.on_state_changed:
                    self.on_state_changed(self.state)

    def stop(self):
        """Stop playback immediately and release any held buttons/keys."""
        with self.state_lock:
            if self.state in (self.STATE_IDLE, self.STATE_STOPPED):
                return
            self.state = self.STATE_STOPPED

        self._stop_requested.set()
        self._resume_event.set()  # Unblock thread if paused

        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        self.simulator.release_all_held()

        with self.state_lock:
            self.state = self.STATE_IDLE

        if self.on_state_changed:
            self.on_state_changed(self.state)

    def set_repeat(self, repeat):
        """Update repeat state while running. Turning off lets current pass finish."""
        self.repeat = bool(repeat)

    def _playback_worker(self):
        """Worker thread executing macro steps."""
        try:
            current_pass = 0
            while not self._stop_requested.is_set():
                current_pass += 1
                if self.on_pass_progress:
                    tot = 0 if self.repeat else self.repeat_count
                    self.on_pass_progress(current_pass, tot)

                self._execute_single_pass()

                if self._stop_requested.is_set():
                    break

                # If infinite repeat enabled, continue; otherwise check if reached repeat_count
                if self.repeat:
                    time.sleep(0.05)
                    continue
                elif current_pass < self.repeat_count:
                    time.sleep(0.05)
                    continue
                else:
                    break
        finally:
            self.simulator.release_all_held()
            with self.state_lock:
                self.state = self.STATE_IDLE
            if self.on_state_changed:
                self.on_state_changed(self.state)

    def _execute_single_pass(self):
        steps = self.steps
        total_steps = len(steps)
        if total_steps == 0:
            return

        has_branching = any(
            "found_next" in s
            or "miss_next" in s
            or "body_next" in s
            or s.get("type") in ("loop_count", "if_condition")
            for s in steps
        )
        if has_branching:
            self._execute_graph_pass(steps)
        else:
            self._execute_linear_pass(steps)

    def _execute_linear_pass(self, steps):
        total_steps = len(steps)
        base_time = time.perf_counter()
        speed = self.speed

        for i, step in enumerate(steps):
            if self._stop_requested.is_set():
                break

            # If step is bypassed, skip execution without delay
            if step.get("bypassed", False):
                if self.on_progress:
                    self.on_progress(i + 1, total_steps)
                continue

            # Handle Pause / Resume timing
            if self._pause_requested.is_set():
                pause_start = time.perf_counter()
                self._resume_event.wait()
                if self._stop_requested.is_set():
                    break
                # Adjust base_time by the duration of the pause
                pause_duration = time.perf_counter() - pause_start
                base_time += pause_duration

            target_dt_ms = step.get("dt", 0)
            scaled_target_sec = (target_dt_ms / 1000.0) / speed
            now_sec = time.perf_counter() - base_time

            wait_sec = scaled_target_sec - now_sec
            if wait_sec > 0:
                # Sleep in small slices to remain responsive to stop/pause
                while wait_sec > 0:
                    if self._stop_requested.is_set():
                        return
                    if self._pause_requested.is_set():
                        break
                    slice_sec = min(wait_sec, 0.015)
                    time.sleep(slice_sec)
                    wait_sec = scaled_target_sec - (time.perf_counter() - base_time)

            if self._stop_requested.is_set():
                break

            # Execute the step (linear pass already waited target_dt_ms, so delay step does not double-sleep)
            if step.get("type") != "delay":
                self._execute_step(step)

            if self.on_progress:
                self.on_progress(i + 1, total_steps)

    def _execute_graph_pass(self, steps):
        step_map = {s["id"]: s for s in steps if "id" in s}
        curr_step = steps[0]
        step_count = 0
        max_steps = 100000
        loop_counters = {}
        has_infinite = any(s.get("type") == "loop_count" and s.get("infinite", False) for s in steps)

        while curr_step and not self._stop_requested.is_set() and (has_infinite or step_count < max_steps):
            step_count += 1

            # Pause handling
            if self._pause_requested.is_set():
                self._resume_event.wait()
                if self._stop_requested.is_set():
                    break

            # If node is bypassed, skip execution and route to next connection
            if curr_step.get("bypassed", False):
                if self.on_progress:
                    self.on_progress(min(step_count, len(steps)), len(steps))
                if curr_step.get("type") == "loop_count":
                    next_id = curr_step.get("next")
                elif "found_next" in curr_step or "miss_next" in curr_step:
                    next_id = curr_step.get("found_next") or curr_step.get("miss_next")
                else:
                    next_id = curr_step.get("next")
                if not next_id:
                    break
                curr_step = step_map.get(next_id)
                continue

            # Special state handling for Loop (Repeat Zone) node
            if curr_step.get("type") == "loop_count":
                lid = curr_step.get("id")
                is_infinite = bool(curr_step.get("infinite", False))
                target_count = self._resolve_coord(curr_step.get("count", 5), default=5)
                var_name = str(curr_step.get("var_name", "i")).lstrip("$")

                iter_count = loop_counters.get(lid, 0)
                if is_infinite or iter_count < target_count:
                    self.variables[var_name] = iter_count
                    self.variables[f"${var_name}"] = iter_count
                    loop_counters[lid] = iter_count + 1
                    next_id = curr_step.get("body_next") or curr_step.get("next")
                else:
                    loop_counters[lid] = 0
                    next_id = curr_step.get("next")

                if self.on_progress:
                    self.on_progress(min(step_count, len(steps)), len(steps))
                if not next_id:
                    break
                curr_step = step_map.get(next_id)
                continue

            # Execute the current step
            cond_res = self._execute_step(curr_step)

            if self.on_progress:
                self.on_progress(min(step_count, len(steps)), len(steps))

            if self._stop_requested.is_set():
                break

            # Inter-step interval (if not delay node)
            if curr_step.get("type") != "delay":
                time.sleep(max(0.005, 0.030 / self.speed))

            # Determine next step
            if "found_next" in curr_step or "miss_next" in curr_step:
                next_id = curr_step.get("found_next") if cond_res else curr_step.get("miss_next")
                if curr_step.get("break_loop_on_found", False) and cond_res:
                    loop_counters.clear()
            else:
                next_id = curr_step.get("next")

            if not next_id:
                break

            curr_step = step_map.get(next_id)

    def _resolve_coord(self, val, default=None):
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return int(val)
        val_str = str(val).strip()
        if val_str.startswith("$"):
            k = val_str.lstrip("$")
            res = self.variables.get(k, self.variables.get(val_str, default))
            try:
                return int(float(res))
            except (ValueError, TypeError):
                return default
        try:
            return int(float(val_str))
        except (ValueError, TypeError):
            return default

    def _resolve_val(self, val, default=0):
        if val is None:
            return default
        if isinstance(val, (int, float)):
            return val
        val_str = str(val).strip()
        if val_str.startswith("$"):
            k = val_str.lstrip("$")
            res = self.variables.get(k, self.variables.get(val_str, default))
            return self._resolve_val(res, default=default)
        try:
            return int(val_str) if "." not in val_str else float(val_str)
        except (ValueError, TypeError):
            return val_str

    def _resolve_vk(self, step):
        vk = step.get("vk")
        if vk is not None:
            try:
                vk_int = int(vk)
                if 1 <= vk_int <= 255:
                    return vk_int
            except (ValueError, TypeError):
                pass
        key_name = step.get("key")
        if key_name:
            return get_vk_for_key(key_name)
        return None

    def _execute_step(self, step):
        if step.get("_unplugged", False):
            return False
        if step.get("bypassed", False):
            return True

        st_type = step.get("type", "")
        raw_x = step.get("x")
        raw_y = step.get("y")
        x = self._resolve_coord(raw_x, None) if raw_x is not None else None
        y = self._resolve_coord(raw_y, None) if raw_y is not None else None
        btn = step.get("button", "left")

        # Notify visual indicator if coordinate action
        if x is not None and y is not None and self.on_cursor_action:
            self.on_cursor_action(int(x), int(y), st_type)

        if st_type == "move":
            if x is not None and y is not None:
                self.simulator.move_to(x, y)
            return True

        elif st_type == "down":
            self.simulator.mouse_down(btn, x, y)
            return True

        elif st_type == "up":
            self.simulator.mouse_up(btn, x, y)
            return True

        elif st_type == "click":
            self.simulator.click(x, y, btn)
            return True

        elif st_type == "dblclick":
            self.simulator.double_click(x, y, btn)
            return True

        elif st_type == "wheel":
            raw_dx = step.get("deltaX", 0)
            raw_dy = step.get("deltaY", 0)
            dx = self._resolve_coord(raw_dx, default=0)
            dy = self._resolve_coord(raw_dy, default=0)
            self.simulator.mouse_wheel(dy, dx, x, y)
            return True

        elif st_type == "type":
            val = step.get("value", "")
            if val:
                self.simulator.type_text(val)
            return True

        elif st_type in ("key_press", "key"):
            vk = self._resolve_vk(step)
            if vk is not None:
                self.simulator.key_press(vk)
            return True

        elif st_type == "key_down":
            vk = self._resolve_vk(step)
            if vk is not None:
                self.simulator.key_down(vk)
                hold_dur = self._resolve_coord(step.get("hold_duration", 0), default=0)
                auto_repeat = bool(step.get("auto_repeat", False))
                if hold_dur > 0:
                    wait_sec = (hold_dur / 1000.0) / self.speed
                    start_t = time.perf_counter()
                    last_pulse = start_t
                    while (time.perf_counter() - start_t) < wait_sec:
                        if self._stop_requested.is_set():
                            self.simulator.key_up(vk)
                            return False
                        if self._pause_requested.is_set():
                            self._resume_event.wait()
                            if self._stop_requested.is_set():
                                self.simulator.key_up(vk)
                                return False
                        now = time.perf_counter()
                        if auto_repeat and (now - last_pulse) >= 0.045:
                            self.simulator.key_down(vk)
                            last_pulse = now
                        time.sleep(0.010)
                    self.simulator.key_up(vk)
            return True

        elif st_type == "key_up":
            vk = self._resolve_vk(step)
            if vk is not None:
                self.simulator.key_up(vk)
            return True

        elif st_type == "delay":
            dur_raw = step.get("duration", 0)
            dur_ms = self._resolve_coord(dur_raw, default=0)
            if dur_ms > 0:
                wait_sec = (dur_ms / 1000.0) / self.speed
                start_t = time.perf_counter()
                while (time.perf_counter() - start_t) < wait_sec:
                    if self._stop_requested.is_set():
                        return False
                    if self._pause_requested.is_set():
                        self._resume_event.wait()
                        if self._stop_requested.is_set():
                            return False
                    rem = wait_sec - (time.perf_counter() - start_t)
                    time.sleep(min(max(0.001, rem), 0.015))
            return True

        elif st_type in ("find_image", "wait_image", "wait", "waitforimage"):
            try:
                template_path = step.get("template", "")
                confidence = float(step.get("confidence", 0.85))
                action = str(step.get("action", "none")).lower().replace(" ", "")
                btn = step.get("button", "left")
                is_wait = st_type in ("wait_image", "wait", "waitforimage")
                speed_factor = max(0.01, self.speed)
                timeout_sec = (float(step.get("timeout", 5.0)) / speed_factor) if is_wait else 0.5
                region = step.get("region")

                res = wait_for_template_on_screen(
                    template_path,
                    confidence=confidence,
                    timeout_sec=timeout_sec,
                    poll_interval_sec=0.03,
                    region=region,
                    stop_check_fn=lambda: self._stop_requested.is_set(),
                )

                if res is not None:
                    cx, cy, _, _, _ = res
                    if self.on_cursor_action:
                        self.on_cursor_action(cx, cy, "vision_found")
                    if action in ("click",):
                        self.simulator.click(cx, cy, btn)
                    elif action in ("move",):
                        self.simulator.move_to(cx, cy)
                    elif action in ("dblclick", "doubleclick"):
                        self.simulator.double_click(cx, cy, btn)
                    elif action in ("none",):
                        pass
                    return True
                else:
                    return False
            except Exception:
                return False

        elif st_type == "math_op":
            var_name = str(step.get("var_name", "var")).lstrip("$")
            op = step.get("operation", "set")
            raw_val = step.get("value", "0")
            resolved_val = self._resolve_val(raw_val, default=0)
            if op == "set":
                self.variables[var_name] = resolved_val
                self.variables[f"${var_name}"] = resolved_val
            elif op == "increment":
                cur_v = self._resolve_val(self.variables.get(var_name, self.variables.get(f"${var_name}", 0)), default=0)
                new_v = cur_v + 1
                self.variables[var_name] = new_v
                self.variables[f"${var_name}"] = new_v
            elif op == "decrement":
                cur_v = self._resolve_val(self.variables.get(var_name, self.variables.get(f"${var_name}", 0)), default=0)
                new_v = cur_v - 1
                self.variables[var_name] = new_v
                self.variables[f"${var_name}"] = new_v
            elif op == "add":
                cur_v = self._resolve_val(self.variables.get(var_name, self.variables.get(f"${var_name}", 0)), default=0)
                add_v = self._resolve_val(raw_val, default=0)
                try:
                    new_v = cur_v + add_v
                except TypeError:
                    new_v = f"{cur_v}{add_v}"
                self.variables[var_name] = new_v
                self.variables[f"${var_name}"] = new_v
            elif op == "subtract":
                cur_v = self._resolve_val(self.variables.get(var_name, self.variables.get(f"${var_name}", 0)), default=0)
                sub_v = self._resolve_val(raw_val, default=0)
                try:
                    new_v = cur_v - sub_v
                except Exception:
                    new_v = cur_v
                self.variables[var_name] = new_v
                self.variables[f"${var_name}"] = new_v
            elif op == "multiply":
                cur_v = self._resolve_val(self.variables.get(var_name, self.variables.get(f"${var_name}", 0)), default=0)
                mul_v = self._resolve_val(raw_val, default=1)
                try:
                    new_v = cur_v * mul_v
                except Exception:
                    new_v = cur_v
                self.variables[var_name] = new_v
                self.variables[f"${var_name}"] = new_v
            elif op == "random":
                import random
                min_v = self._resolve_coord(step.get("min_val", 1), default=1)
                max_v = self._resolve_coord(step.get("max_val", 100), default=100)
                new_v = random.randint(min(min_v, max_v), max(min_v, max_v))
                self.variables[var_name] = new_v
                self.variables[f"${var_name}"] = new_v
            return True

        elif st_type == "pixel_color":
            from PyQt6.QtGui import QGuiApplication, QColor
            from PyQt6.QtCore import QPoint
            px = self._resolve_coord(step.get("x", 0), default=0)
            py = self._resolve_coord(step.get("y", 0), default=0)
            target_hex = step.get("color", "#FFFFFF")
            target_col = QColor(target_hex)
            tolerance = self._resolve_coord(step.get("tolerance", 15), default=15)

            matches = False
            pt = QPoint(px, py)
            screen = QGuiApplication.screenAt(pt)
            if not screen:
                screen = QGuiApplication.primaryScreen()
            if screen:
                geo = screen.geometry()
                lx = int(px - geo.x())
                ly = int(py - geo.y())
                cur_img = screen.grabWindow(0, lx, ly, 1, 1).toImage()
                if not cur_img.isNull() and cur_img.width() > 0 and cur_img.height() > 0:
                    c = cur_img.pixelColor(0, 0)
                    diff = (
                        abs(c.red() - target_col.red())
                        + abs(c.green() - target_col.green())
                        + abs(c.blue() - target_col.blue())
                    )
                    matches = diff <= (tolerance * 3)
                    self.variables["$pixel_match"] = matches
                    if self.on_cursor_action and matches:
                        self.on_cursor_action(px, py, "pixel_matched")
            return matches

        elif st_type == "if_condition":
            var_a_raw = str(step.get("var_a", ""))
            val_b_raw = str(step.get("val_b", ""))
            op = step.get("operator", "==")

            if var_a_raw.startswith("$"):
                key = var_a_raw.lstrip("$")
                var_a = self.variables.get(key, self.variables.get(var_a_raw, ""))
            else:
                var_a = var_a_raw

            if val_b_raw.startswith("$"):
                key = val_b_raw.lstrip("$")
                val_b = self.variables.get(key, self.variables.get(val_b_raw, ""))
            else:
                val_b = val_b_raw

            res = False
            try:
                fa = float(var_a)
                fb = float(val_b)
                if op == "==": res = (fa == fb)
                elif op == "!=": res = (fa != fb)
                elif op == ">": res = (fa > fb)
                elif op == "<": res = (fa < fb)
                elif op == ">=": res = (fa >= fb)
                elif op == "<=": res = (fa <= fb)
            except (ValueError, TypeError):
                sa = str(var_a)
                sb = str(val_b)
                if op == "==": res = (sa == sb)
                elif op == "!=": res = (sa != sb)
                elif op == "contains": res = (sb in sa)
                elif op == "is empty": res = (len(sa.strip()) == 0)

            self.variables["$last_condition"] = res
            return res

        elif st_type == "hotkey":
            combo = step.get("combo", "")
            cad_action = step.get("cad_action", "taskmgr")
            if combo:
                self.simulator.hotkey(combo, cad_action=cad_action)
            return True

        elif st_type == "stop_playback":
            self.stop()
            return False

        return True
