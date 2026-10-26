"""
Main entry point for Macrow Desktop Automation.
Sets up DPI awareness, manages application instances, registers global hotkeys,
and handles emergency failsafe stops.
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from app.core.win32_api import init_dpi_awareness
from app.core.input_simulator import InputSimulator
from app.core.hotkeys import GlobalHotkeyManager
from app.core.scheduler import GLOBAL_SCHEDULER
from app.config import ConfigManager
from app.ui.assets import get_app_icon
from app.ui.main_panel import MacrowPanel, PointClickerPanel


class MacrowApp:
    """Application controller managing shared state, hotkeys, and instances."""

    def __init__(self):
        # 1. Enable per-monitor DPI awareness and Windows Taskbar AppUserModelID
        init_dpi_awareness()
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Macrow.DesktopAutomation.App.1.0")
        except Exception:
            pass

        # 2. Initialize Qt Application with custom Macrow icon
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Macrow")
        self.app.setWindowIcon(get_app_icon())
        self.app.setQuitOnLastWindowClosed(False)

        # 3. Core managers
        self.config = ConfigManager("config.json")
        self.simulator = InputSimulator()
        self.hotkeys = GlobalHotkeyManager()

        # 4. Instances registry
        self.instances = {}
        self.next_instance_id = 1

        # 5. Wire global hotkeys
        self._init_hotkeys()

    def _init_hotkeys(self):
        self.hotkeys.on_kill_switch = self.emergency_stop
        self.hotkeys.on_record_toggle = self.toggle_active_record
        self.hotkeys.on_play_toggle = self.toggle_active_play
        self.hotkeys.on_stop_playback = self.stop_all_playback
        self.hotkeys.start()

    def spawn_instance(self, instance_id=None):
        if instance_id is None:
            instance_id = self.next_instance_id
            self.next_instance_id += 1

        panel = MacrowPanel(self.config, instance_id=instance_id, simulator=self.simulator)
        panel.new_window_requested.connect(self.spawn_instance)
        panel.destroyed.connect(lambda _, i=str(instance_id): self._on_instance_destroyed(i))
        self.instances[str(instance_id)] = panel
        panel.show()
        return panel

    def _on_instance_destroyed(self, instance_id):
        if instance_id in self.instances:
            del self.instances[instance_id]
        if not self.instances:
            self.app.quit()

    def emergency_stop(self):
        """Emergency stop (Alt+S or F12): safely stops playback and recording without closing the program."""
        print(">>> EMERGENCY STOP ACTIVATED (Alt+S / F12) <<<")
        self.simulator.release_all_held()
        for iid, panel in list(self.instances.items()):
            try:
                panel.stop_playback()
                if panel.recorder.is_recording:
                    panel.recorder.stop()
                    panel.record_btn.setText("● Record Macro")
                    panel.record_btn.setStyleSheet("")
                    panel.record_status_lbl.setText("0 steps")
            except Exception as e:
                print(f"Error stopping instance {iid}: {e}")

    def toggle_active_record(self):
        # Trigger on first/primary instance
        if self.instances:
            inst = next(iter(self.instances.values()))
            inst.toggle_recording()

    def toggle_active_play(self):
        if self.instances:
            inst = next(iter(self.instances.values()))
            if inst.player.is_playing():
                inst.toggle_pause()
            else:
                inst.start_playback()

    def stop_all_playback(self):
        for panel in self.instances.values():
            panel.stop_playback()

    def run(self):
        # Spawn primary instance
        self.spawn_instance(1)

        try:
            return self.app.exec()
        finally:
            self.hotkeys.stop()
            self.simulator.release_all_held()


def main():
    macrow_app = MacrowApp()
    sys.exit(macrow_app.run())


if __name__ == "__main__":
    main()
