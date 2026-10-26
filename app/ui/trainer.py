"""
Coordinate Trainer and Manual Coordinate Dialog for Point Clicker Desktop.
Captures screen coordinates when user clicks ◎ and then clicks anywhere on screen,
or allows manual entry via double-click.
"""

import threading
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from app.ui.assets import get_app_icon
from app.core.win32_api import (
    user32,
    kernel32,
    HOOKPROC,
    MSLLHOOKSTRUCT,
    WH_MOUSE_LL,
    WM_QUIT,
    WM_LBUTTONDOWN,
    SYNTHETIC_EXTRA_INFO,
)


class PickerSignals(QObject):
    coordinate_picked = pyqtSignal(int, int)
    cancelled = pyqtSignal()


class ScreenCoordinatePicker:
    """One-shot global mouse click listener to pick screen coordinates."""

    def __init__(self):
        self.signals = PickerSignals()
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._proc = None
        self._active = False

    def start_picking(self):
        """Begin listening for the next screen click."""
        if self._active:
            return
        self._active = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def cancel(self):
        """Cancel picking without saving coordinates."""
        if not self._active:
            return
        self._active = False
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.signals.cancelled.emit()

    def _worker(self):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._proc = HOOKPROC(self._hook_callback)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._active = False

    def _hook_callback(self, nCode, wParam, lParam):
        if nCode >= 0 and self._active:
            struct = MSLLHOOKSTRUCT.from_address(lParam)
            # Ignore synthetic events
            if struct.dwExtraInfo != SYNTHETIC_EXTRA_INFO:
                if wParam == WM_LBUTTONDOWN:
                    x = int(struct.pt.x)
                    y = int(struct.pt.y)
                    self._active = False
                    user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
                    self.signals.coordinate_picked.emit(x, y)
                    # Allow click to pass through to target application
                    return user32.CallNextHookEx(None, nCode, wParam, lParam)

        return user32.CallNextHookEx(None, nCode, wParam, lParam)


class ManualCoordinateDialog(QDialog):
    """Dialog allowing user to type X and Y coordinates manually for a timeframe."""

    def __init__(self, timeframe, current_x=0, current_y=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Coordinates - {timeframe}")
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(280, 160)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        info_lbl = QLabel(f"Set screen coordinates for <b>{timeframe}</b>:")
        layout.addWidget(info_lbl)

        coord_row = QHBoxLayout()

        x_lbl = QLabel("X:")
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-10000, 30000)
        self.x_spin.setValue(int(current_x or 0))

        y_lbl = QLabel("Y:")
        self.y_spin = QSpinBox()
        self.y_spin.setRange(-10000, 30000)
        self.y_spin.setValue(int(current_y or 0))

        coord_row.addWidget(x_lbl)
        coord_row.addWidget(self.x_spin)
        coord_row.addWidget(y_lbl)
        coord_row.addWidget(self.y_spin)
        layout.addLayout(coord_row)

        btn_row = QHBoxLayout()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(self.clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        self.cleared = False

    def _on_clear(self):
        self.cleared = True
        self.accept()

    def get_coordinates(self):
        if self.cleared:
            return None, None
        return self.x_spin.value(), self.y_spin.value()
