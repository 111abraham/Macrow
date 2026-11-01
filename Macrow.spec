# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:/anti gravity experimenting folder/desktop auto clicker gemini/main.py'],
    pathex=[],
    binaries=[],
    datas=[('D:/anti gravity experimenting folder/desktop auto clicker gemini/Macrow icon.png', '.'), ('D:/anti gravity experimenting folder/desktop auto clicker gemini/Macrow icon.ico', '.')],
    hiddenimports=['PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'ctypes', 'ctypes.wintypes', 'numpy', 'cv2', 'app.core.vision', 'app.ui.assets', 'app.ui.node_editor', 'app.ui.eye_dropper'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Macrow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:/anti gravity experimenting folder/desktop auto clicker gemini/Macrow icon.ico'],
)
