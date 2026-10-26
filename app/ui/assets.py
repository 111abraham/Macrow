"""Asset and icon resolver for Macrow Desktop."""

from __future__ import annotations

import os
import sys
from typing import Optional
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap

_cached_icon: Optional[QIcon] = None


def get_asset_path(filename: str = "Macrow icon.png") -> str:
    """Returns absolute path to an asset file in both dev and PyInstaller onefile modes."""
    # 1. PyInstaller temporary extraction folder
    if hasattr(sys, "_MEIPASS"):
        meipass_path = os.path.join(sys._MEIPASS, filename)
        if os.path.exists(meipass_path):
            return meipass_path

    # 2. Project root directory (3 levels up from app/ui/assets.py)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root_path = os.path.join(base_dir, filename)
    if os.path.exists(root_path):
        return root_path

    # 3. Current working directory
    cwd_path = os.path.join(os.getcwd(), filename)
    if os.path.exists(cwd_path):
        return cwd_path

    return filename


def get_app_icon() -> QIcon:
    """Returns multi-resolution QIcon for Macrow desktop and taskbar."""
    global _cached_icon
    if _cached_icon is not None and not _cached_icon.isNull():
        return _cached_icon

    icon = QIcon()
    ico_path = get_asset_path("Macrow icon.ico")
    png_path = get_asset_path("Macrow icon.png")

    if os.path.exists(ico_path):
        icon.addFile(ico_path)
    if os.path.exists(png_path):
        icon.addFile(png_path)

    _cached_icon = icon
    return icon


def get_app_pixmap(size: int = 18) -> QPixmap:
    """Returns scaled QPixmap of the application icon."""
    png_path = get_asset_path("Macrow icon.png")
    if os.path.exists(png_path):
        pix = QPixmap(png_path)
        if not pix.isNull():
            return pix.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return QPixmap()
