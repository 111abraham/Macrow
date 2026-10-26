"""
Build script to compile Macrow Desktop into a standalone .exe using PyInstaller.
Produces a single executable `dist/Macrow.exe` with no external Python dependencies required.
"""

import os
import sys
import subprocess
import shutil

def build_exe():
    print("=" * 60)
    print("Building Macrow Desktop standalone executable...")
    print("=" * 60)

    # Base directory
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # PyInstaller arguments
    icon_path = os.path.join(base_dir, "Macrow icon.ico")
    png_path = os.path.join(base_dir, "Macrow icon.png")

    pyinstaller_args = [
        sys.executable,
        "-m", "PyInstaller",
        "--name=Macrow",
        "--onefile",
        "--windowed",              # No console window
        "--noconfirm",
        "--clean",
        f"--icon={icon_path}",
        f"--add-data={png_path};.",
        f"--add-data={icon_path};.",
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=ctypes",
        "--hidden-import=ctypes.wintypes",
        "--hidden-import=numpy",
        "--hidden-import=cv2",
        "--hidden-import=app.core.vision",
        "--hidden-import=app.ui.assets",
        "--hidden-import=app.ui.node_editor",
        "--hidden-import=app.ui.eye_dropper",
        os.path.join(base_dir, "main.py"),
    ]

    print("Running command:", " ".join(pyinstaller_args))
    result = subprocess.run(pyinstaller_args, cwd=base_dir)

    if result.returncode == 0:
        exe_path = os.path.join(base_dir, "dist", "Macrow.exe")
        print("\n" + "=" * 60)
        print("BUILD SUCCESSFUL!")
        print(f"Standalone executable generated at:\n  {exe_path}")
        print("=" * 60)
        return True
    else:
        print("\nBUILD FAILED with exit code:", result.returncode)
        return False

if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)
