"""
Macro Naming Dialog for Point Clicker Desktop.
Prompts for macro name after recording finishes.
Pre-filled with 'Macro 1', 'Macro 2', etc.
Enter saves, Esc discards.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)
from PyQt6.QtCore import Qt
from app.ui.assets import get_app_icon


class MacroNameDialog(QDialog):
    """Dialog prompting user to name a newly recorded macro."""

    def __init__(self, default_name="Macro 1", step_count=0, duration_ms=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Macro")
        self.setWindowIcon(get_app_icon())
        self.setFixedSize(320, 150)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        duration_sec = duration_ms / 1000.0
        info_lbl = QLabel(f"Recording stopped: <b>{step_count}</b> steps ({duration_sec:.1f}s)")
        layout.addWidget(info_lbl)

        prompt_lbl = QLabel("Enter macro name:")
        layout.addWidget(prompt_lbl)

        self.name_input = QLineEdit(default_name)
        self.name_input.selectAll()
        layout.addWidget(self.name_input)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.discard_btn = QPushButton("Discard")
        self.discard_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.discard_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)

        layout.addLayout(btn_row)

    def _on_save(self):
        name = self.name_input.text().strip()
        if not name:
            name = "Untitled Macro"
        self.name_input.setText(name)
        self.accept()

    def get_macro_name(self):
        return self.name_input.text().strip()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_save()
        else:
            super().keyPressEvent(event)
