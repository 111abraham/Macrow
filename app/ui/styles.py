"""
Modern dark styling for Point Clicker Desktop panel.
Sleek, high-contrast, compact, and optimized for floating always-on-top visibility.
"""

DARK_THEME_QSS = """
QWidget {
    background-color: #121316;
    color: #e4e4e7;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 12px;
}

/* Frameless Panel Container */
#MainContainer {
    background-color: #121316;
    border: 1.5px solid #3f3f46;
    border-radius: 8px;
}
#MainContainer:hover {
    border-color: #52525b;
}

/* Title Bar */
#TitleBar {
    background-color: #18181b;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    border-bottom: 1px solid #27272a;
    padding: 4px 8px;
    min-height: 32px;
}

#AppTitle {
    font-weight: 700;
    font-size: 12px;
    color: #38bdf8;
    letter-spacing: 0.5px;
}

#CoordsPill {
    background-color: #27272a;
    color: #a1a1aa;
    font-family: "Consolas", monospace;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid #3f3f46;
}

/* Title Buttons */
#TitleBtn {
    background-color: transparent;
    color: #a1a1aa;
    border: none;
    border-radius: 4px;
    font-size: 13px;
    font-weight: bold;
    min-width: 24px;
    min-height: 22px;
    padding: 0;
}
#TitleBtn:hover {
    background-color: #27272a;
    color: #fafafa;
}
#CloseBtn:hover {
    background-color: #ef4444;
    color: #ffffff;
}

/* Scroll Area */
QScrollArea {
    border: none;
    background-color: transparent;
}
QScrollBar:vertical {
    border: none;
    background: #18181b;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #52525b;
    min-height: 25px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #38bdf8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

/* Footer / Resize Grip */
#FooterBar {
    background-color: #18181b;
    border-bottom-left-radius: 8px;
    border-bottom-right-radius: 8px;
    border-top: 1px solid #27272a;
    padding: 2px 6px;
    min-height: 20px;
}

#FooterHint {
    font-size: 10px;
    color: #71717a;
    font-family: "Consolas", monospace;
}

QSizeGrip {
    width: 16px;
    height: 16px;
    background-color: transparent;
}

/* Section Cards / GroupBoxes */
QGroupBox {
    background-color: #18181b;
    border: 1px solid #27272a;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: 600;
    font-size: 11px;
    color: #94a3b8;
    text-transform: uppercase;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    background-color: #18181b;
    color: #38bdf8;
}

/* Buttons */
QPushButton {
    background-color: #27272a;
    color: #f4f4f5;
    border: 1px solid #3f3f46;
    border-radius: 5px;
    padding: 4px 10px;
    font-weight: 500;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #3f3f46;
    border-color: #52525b;
}
QPushButton:pressed {
    background-color: #18181b;
}
QPushButton:disabled {
    background-color: #1c1c1f;
    color: #52525b;
    border-color: #27272a;
}

/* Action Specific Buttons */
#RecordBtn {
    background-color: #881337;
    color: #ffe4e6;
    border-color: #be123c;
    font-weight: 600;
}
#RecordBtn:hover {
    background-color: #9f1239;
    border-color: #f43f5e;
}
#RecordingActiveBtn {
    background-color: #e11d48;
    color: #ffffff;
    border-color: #fb7185;
    font-weight: 700;
}

#PlayBtn {
    background-color: #064e3b;
    color: #a7f3d0;
    border-color: #059669;
    font-weight: 600;
}
#PlayBtn:hover {
    background-color: #047857;
    border-color: #10b981;
}

#StopBtn {
    background-color: #27272a;
    color: #f87171;
    border-color: #451a1a;
}
#StopBtn:hover {
    background-color: #7f1d1d;
    color: #fecaca;
}

#CustomizeBtn {
    background-color: #1e293b;
    color: #38bdf8;
    border: 1px solid #0369a1;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 4px;
}
#CustomizeBtn:hover {
    background-color: #0284c7;
    color: #ffffff;
    border-color: #38bdf8;
}

#RepeatClickBtnActive {
    background-color: #0284c7;
    color: #ffffff;
    border-color: #38bdf8;
    font-weight: 600;
}

/* Timeframe Row */
.TimeframeRow {
    background-color: #1e1e24;
    border: 1px solid #27272a;
    border-radius: 4px;
    padding: 3px 6px;
}
.TimeframeRow:hover {
    background-color: #26262e;
    border-color: #3f3f46;
}
.TimeframeRowActive {
    background-color: #162a22;
    border: 1px solid #10b981;
}

#TrainerBtn {
    background-color: #27272a;
    color: #a1a1aa;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 13px;
    min-width: 24px;
    min-height: 20px;
}
#TrainerBtn:hover {
    background-color: #38bdf8;
    color: #09090b;
    border-color: #38bdf8;
}
#TrainerBtnActive {
    background-color: #f59e0b;
    color: #000000;
    font-weight: bold;
    border-color: #d97706;
}

/* Input Fields & Spinners */
QLineEdit, QComboBox {
    background-color: #1f1f23;
    color: #f4f4f5;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    padding: 3px 6px;
    min-height: 22px;
}

QSpinBox, QDoubleSpinBox {
    background-color: #1f1f23;
    color: #ffffff;
    border: 1px solid #3f3f46;
    border-radius: 4px;
    padding-left: 8px;
    padding-right: 28px;
    padding-top: 2px;
    padding-bottom: 2px;
    min-height: 24px;
    font-size: 13px;
    font-weight: 600;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #38bdf8;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    border-left: 1px solid #3f3f46;
    border-bottom: 1px solid #27272a;
    background-color: #27272a;
    border-top-right-radius: 3px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: #3f3f46;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    border-left: 1px solid #3f3f46;
    background-color: #27272a;
    border-bottom-right-radius: 3px;
}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #3f3f46;
}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QComboBox:focus {
    border: 1px solid #38bdf8;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}

/* Sliders */
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: #27272a;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #38bdf8;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #fafafa;
    border: 1px solid #38bdf8;
    width: 12px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 6px;
}

/* Checkboxes */
QCheckBox {
    spacing: 6px;
    color: #d4d4d8;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3f3f46;
    border-radius: 3px;
    background-color: #1f1f23;
}
QCheckBox::indicator:checked {
    background-color: #38bdf8;
    border-color: #38bdf8;
}

/* Status Badges */
#StatusBadge {
    font-family: "Consolas", monospace;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    background-color: #27272a;
    color: #a1a1aa;
}
#StatusBadgeWarning {
    background-color: #451a03;
    color: #fde047;
    border: 1px solid #ca8a04;
}
#StatusBadgeRunning {
    background-color: #064e3b;
    color: #6ee7b7;
    border: 1px solid #059669;
}
"""
