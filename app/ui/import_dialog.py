"""
Macro Import Wizard Dialog with Extension Compatibility & Coordinate Alignment.
Allows importing macros exported from the Chrome extension or desktop Point Clicker,
with optional coordinate translation (manual offset or screen reference point picker).
"""

import json
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QGroupBox,
    QListWidget,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from app.ui.trainer import ScreenCoordinatePicker
from app.ui.assets import get_app_icon


class ImportWizardDialog(QDialog):
    """Wizard for importing macros with backward-compatibility coordinate mapping."""

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setWindowTitle("Import Macros Wizard")
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(420, 480)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self.macros_found = {}
        self.picker = ScreenCoordinatePicker()
        self.picker.signals.coordinate_picked.connect(self._on_reference_point_picked)

        self._load_file_preview()
        self._init_ui()

    def _load_file_preview(self):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if "macros" in data and isinstance(data["macros"], dict):
                    self.macros_found = data["macros"]
                else:
                    self.macros_found = {
                        k: v for k, v in data.items() if isinstance(v, dict) and "steps" in v
                    }
        except Exception as e:
            self.macros_found = {}

    def _init_ui(self):
        layout = QVBoxLayout(self)

        info_lbl = QLabel(f"<b>File:</b> {self.filepath.split('/')[-1].split(chr(92))[-1]}")
        count_lbl = QLabel(f"Found <b>{len(self.macros_found)}</b> macro(s) in export file:")
        layout.addWidget(info_lbl)
        layout.addWidget(count_lbl)

        # Macro preview list
        self.list_widget = QListWidget()
        for name, data in self.macros_found.items():
            steps = len(data.get("steps", []))
            dur = data.get("duration", 0) / 1000.0
            self.list_widget.addItem(f"{name} ({steps} steps, {dur:.1f}s)")
        layout.addWidget(self.list_widget)

        # Coordinate Alignment Group
        group = QGroupBox("Coordinate Alignment (Extension Viewport -> Desktop)")
        grp_layout = QVBoxLayout(group)

        self.btn_group = QButtonGroup(self)

        self.radio_none = QRadioButton("Keep original coordinates (no offset)")
        self.radio_none.setChecked(True)
        self.btn_group.addButton(self.radio_none)
        grp_layout.addWidget(self.radio_none)

        self.radio_manual = QRadioButton("Manual coordinate offset (dx, dy):")
        self.btn_group.addButton(self.radio_manual)
        grp_layout.addWidget(self.radio_manual)

        manual_box = QHBoxLayout()
        manual_box.setContentsMargins(20, 0, 0, 0)
        manual_box.addWidget(QLabel("Offset X:"))
        self.spin_x = QSpinBox()
        self.spin_x.setRange(-10000, 30000)
        self.spin_x.setValue(0)
        manual_box.addWidget(self.spin_x)

        manual_box.addWidget(QLabel("Offset Y:"))
        self.spin_y = QSpinBox()
        self.spin_y.setRange(-10000, 30000)
        self.spin_y.setValue(0)
        manual_box.addWidget(self.spin_y)
        grp_layout.addLayout(manual_box)

        self.radio_pick = QRadioButton("Map relative to screen point (e.g. browser origin):")
        self.btn_group.addButton(self.radio_pick)
        grp_layout.addWidget(self.radio_pick)

        pick_box = QHBoxLayout()
        pick_box.setContentsMargins(20, 0, 0, 0)
        self.pick_btn = QPushButton("◎ Click Reference Point on Screen")
        self.pick_btn.clicked.connect(self._start_picker)
        self.pick_status_lbl = QLabel("(Origin: 0, 0)")
        pick_box.addWidget(self.pick_btn)
        pick_box.addWidget(self.pick_status_lbl)
        grp_layout.addLayout(pick_box)

        layout.addWidget(group)

        # Buttons
        btn_box = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.import_btn = QPushButton("Import Macros")
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self.accept)

        btn_box.addStretch()
        btn_box.addWidget(self.cancel_btn)
        btn_box.addWidget(self.import_btn)
        layout.addLayout(btn_box)

    def _start_picker(self):
        self.radio_pick.setChecked(True)
        self.pick_btn.setText("Click screen target...")
        self.picker.start_picking()

    def _on_reference_point_picked(self, x, y):
        self.spin_x.setValue(x)
        self.spin_y.setValue(y)
        self.pick_status_lbl.setText(f"Reference Point: ({x}, {y})")
        self.pick_btn.setText("◎ Re-pick Reference Point")

    def get_offsets(self):
        if self.radio_none.isChecked():
            return 0, 0
        elif self.radio_manual.isChecked() or self.radio_pick.isChecked():
            return self.spin_x.value(), self.spin_y.value()
        return 0, 0
