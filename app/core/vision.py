"""Vision processing engine for desktop automation.
Provides desktop screen capture, interactive snippet selection, and high-speed
template matching using OpenCV (if installed) or pure NumPy FFT cross-correlation.
Uses thread-safe Win32 GDI screen capture to prevent Qt thread violation crashes.
"""

from __future__ import annotations

import os
import time
import math
import ctypes
from ctypes import wintypes
from typing import Optional, Tuple, Dict, Any

import numpy as np
from PyQt6.QtGui import QImage, QColor

# Optional OpenCV acceleration
try:
    import cv2  # type: ignore
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

user32.GetDC.restype = wintypes.HDC
user32.GetDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.restype = ctypes.c_int
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


gdi32.GetDIBits.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.UINT,
]


def capture_screen_win32_bgra(
    region: Optional[Tuple[int, int, int, int]] = None
) -> Tuple[Optional[np.ndarray], int, int, int, int]:
    """Captures desktop screen using Win32 GDI.
    100% thread-safe to call from any background worker thread without Qt GUI crash.
    Returns (bgra_numpy_array, offset_x, offset_y, width, height).
    """
    try:
        if region is not None:
            rx, ry, rw, rh = region
        else:
            rx = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
            ry = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
            rw = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
            rh = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
            if rw <= 0 or rh <= 0:
                rx, ry, rw, rh = 0, 0, 1920, 1080

        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            return None, rx, ry, 0, 0

        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, rw, rh)
        old_bmp = gdi32.SelectObject(hdc_mem, hbmp)

        # SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, rw, rh, hdc_screen, rx, ry, 0x00CC0020)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = rw
        bmi.biHeight = -rh  # Top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB

        buf = (ctypes.c_uint8 * (rw * rh * 4))()
        gdi32.GetDIBits(hdc_mem, hbmp, 0, rh, ctypes.byref(buf), ctypes.byref(bmi), 0)

        # Clean up GDI handles immediately
        gdi32.SelectObject(hdc_mem, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

        arr = np.frombuffer(buf, dtype=np.uint8).reshape((rh, rw, 4))
        return arr, rx, ry, rw, rh
    except Exception:
        return None, 0, 0, 0, 0


def capture_screen(region: Optional[Tuple[int, int, int, int]] = None) -> QImage:
    """Capture desktop screen safely as QImage from Win32 GDI buffer."""
    arr, rx, ry, rw, rh = capture_screen_win32_bgra(region)
    if arr is None or rw <= 0 or rh <= 0:
        return QImage()
    # Format_ARGB32_Premultiplied / Format_RGB32 (byte order B, G, R, A on Windows)
    # Convert numpy array to QImage
    qimg = QImage(arr.data, rw, rh, rw * 4, QImage.Format.Format_ARGB32)
    return qimg.copy()


def bgra_to_gray(bgra: np.ndarray) -> np.ndarray:
    """Converts 4-channel BGRA uint8 array to grayscale uint8 array fast."""
    if HAS_CV2:
        return cv2.cvtColor(bgra, cv2.COLOR_BGRA2GRAY)
    # B:0, G:1, R:2
    # Standard formula: 0.299 R + 0.587 G + 0.114 B
    r = bgra[:, :, 2].astype(np.uint32)
    g = bgra[:, :, 1].astype(np.uint32)
    b = bgra[:, :, 0].astype(np.uint32)
    gray = (r * 77 + g * 150 + b * 29) >> 8
    return gray.astype(np.uint8)


def qimage_to_numpy_gray(qimg: QImage) -> np.ndarray:
    """Convert QImage to 2D numpy uint8 grayscale array."""
    if qimg.isNull():
        return np.zeros((0, 0), dtype=np.uint8)

    if qimg.format() != QImage.Format.Format_Grayscale8:
        gray_img = qimg.convertToFormat(QImage.Format.Format_Grayscale8)
    else:
        gray_img = qimg

    w, h = gray_img.width(), gray_img.height()
    bpl = gray_img.bytesPerLine()
    ptr = gray_img.constBits()
    ptr.setsize(h * bpl)
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, bpl))
    return np.ascontiguousarray(arr[:, :w])


def load_image_as_qimage(image_path_or_qimg: Any) -> Optional[QImage]:
    """Load image from filepath or return as QImage."""
    if not image_path_or_qimg:
        return None
    if isinstance(image_path_or_qimg, QImage):
        return image_path_or_qimg if not image_path_or_qimg.isNull() else None
    if isinstance(image_path_or_qimg, str):
        if not os.path.exists(image_path_or_qimg):
            return None
        img = QImage(image_path_or_qimg)
        if img.isNull():
            return None
        return img
    return None


def match_template_numpy_fft(
    screen_arr: np.ndarray,
    template_arr: np.ndarray,
) -> Tuple[Tuple[int, int], float]:
    """High-speed 2D normalized cross correlation using 2D FFT and integral images.
    Returns ((x, y), max_score) where score is in range [-1.0, 1.0].
    """
    sh, sw = screen_arr.shape
    th, tw = template_arr.shape

    if th > sh or tw > sw or th <= 0 or tw <= 0:
        return ((0, 0), -1.0)

    # Convert to float32
    s_f = screen_arr.astype(np.float32)
    t_f = template_arr.astype(np.float32)

    # Template zero-mean and energy
    t_mean = float(np.mean(t_f))
    t_zero = t_f - t_mean
    t_energy = float(np.sum(t_zero ** 2))
    if t_energy < 1e-4:
        diff = np.abs(s_f[:sh - th + 1, :sw - tw + 1] - t_mean)
        min_idx = np.unravel_index(np.argmin(diff), diff.shape)
        min_diff = float(diff[min_idx])
        score = max(0.0, 1.0 - (min_diff / 255.0))
        return ((int(min_idx[1]), int(min_idx[0])), score)

    fh = sh + th - 1
    fw = sw + tw - 1

    t_flipped = t_zero[::-1, ::-1]

    s_fft = np.fft.rfft2(s_f, (fh, fw))
    t_fft = np.fft.rfft2(t_flipped, (fh, fw))
    raw_corr = np.fft.irfft2(s_fft * t_fft, (fh, fw))

    corr = raw_corr[th - 1:sh, tw - 1:sw]

    s_pad = np.pad(s_f, ((1, 0), (1, 0)), mode="constant")
    s_sq_pad = np.pad(s_f ** 2, ((1, 0), (1, 0)), mode="constant")

    int_s = np.cumsum(np.cumsum(s_pad, axis=0), axis=1)
    int_s_sq = np.cumsum(np.cumsum(s_sq_pad, axis=0), axis=1)

    y0 = np.arange(sh - th + 1)
    y1 = y0 + th
    x0 = np.arange(sw - tw + 1)
    x1 = x0 + tw

    yy0, xx0 = np.meshgrid(y0, x0, indexing="ij")
    yy1, xx1 = np.meshgrid(y1, x1, indexing="ij")

    sum_s = (
        int_s[yy1, xx1]
        - int_s[yy0, xx1]
        - int_s[yy1, xx0]
        + int_s[yy0, xx0]
    )
    sum_s_sq = (
        int_s_sq[yy1, xx1]
        - int_s_sq[yy0, xx1]
        - int_s_sq[yy1, xx0]
        + int_s_sq[yy0, xx0]
    )

    n_pixels = float(th * tw)
    var_s = sum_s_sq - (sum_s ** 2) / n_pixels
    var_s = np.maximum(var_s, 0.0)

    denom = np.sqrt(var_s * t_energy)
    flat_mask = (var_s < 1.0) | (denom < 1e-4)

    ncc = np.zeros_like(corr)
    np.divide(corr, denom, out=ncc, where=~flat_mask)
    ncc = np.nan_to_num(ncc, nan=-1.0, posinf=1.0, neginf=-1.0)
    ncc = np.clip(ncc, -1.0, 1.0)

    max_idx = np.unravel_index(np.argmax(ncc), ncc.shape)
    best_y, best_x = int(max_idx[0]), int(max_idx[1])
    best_score = float(ncc[best_y, best_x])
    if math.isnan(best_score) or math.isinf(best_score):
        best_score = -1.0

    return ((best_x, best_y), best_score)


def match_template(
    screen_arr: np.ndarray,
    template_arr: np.ndarray,
) -> Tuple[Tuple[int, int], float]:
    """Finds best match of template_arr inside screen_arr.
    Returns ((x, y), confidence_score).
    """
    if HAS_CV2:
        try:
            res = cv2.matchTemplate(screen_arr, template_arr, cv2.TM_CCOEFF_NORMED)
            res = np.nan_to_num(res, nan=-1.0, posinf=1.0, neginf=-1.0)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            val = float(max_val)
            if math.isnan(val) or math.isinf(val):
                val = -1.0
            return (max_loc, val)
        except Exception:
            pass

    return match_template_numpy_fft(screen_arr, template_arr)


def find_template_on_screen(
    template_img_or_path: Any,
    confidence: float = 0.8,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int, int, int, float]]:
    """Searches for template on the current desktop screen using thread-safe capture.
    If region is specified (rx, ry, rw, rh), restricts search to that screen area.
    
    Returns (center_x, center_y, width, height, score) or None if score < confidence.
    """
    if not template_img_or_path:
        return None

    try:
        template_qimg = load_image_as_qimage(template_img_or_path)
        if template_qimg is None or template_qimg.isNull():
            return None

        # Thread-safe screen capture using Win32 GDI
        bgra, rx, ry, rw, rh = capture_screen_win32_bgra(region)
        if bgra is None or rw <= 0 or rh <= 0:
            return None

        screen_arr = bgra_to_gray(bgra)
        template_arr = qimage_to_numpy_gray(template_qimg)

        th, tw = template_arr.shape
        sh, sw = screen_arr.shape
        if th > sh or tw > sw or th <= 0 or tw <= 0:
            return None

        (match_x, match_y), score = match_template(screen_arr, template_arr)

        if math.isnan(score) or math.isinf(score) or score < confidence or score <= 0.0:
            return None

        abs_x = rx + match_x
        abs_y = ry + match_y
        center_x = abs_x + tw // 2
        center_y = abs_y + th // 2

        return (center_x, center_y, tw, th, score)
    except Exception:
        return None


def wait_for_template_on_screen(
    template_img_or_path: Any,
    confidence: float = 0.8,
    timeout_sec: float = 10.0,
    poll_interval_sec: float = 0.25,
    region: Optional[Tuple[int, int, int, int]] = None,
    stop_check_fn: Optional[Any] = None,
) -> Optional[Tuple[int, int, int, int, float]]:
    """Polls the screen waiting for template to appear within timeout_sec.
    Returns (center_x, center_y, width, height, score) or None on timeout.
    """
    if not template_img_or_path:
        return None

    # Verify template exists before entering loop
    if isinstance(template_img_or_path, str) and not os.path.exists(template_img_or_path):
        return None

    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if stop_check_fn and stop_check_fn():
            return None

        result = find_template_on_screen(template_img_or_path, confidence, region)
        if result is not None:
            return result

        # Sleep in small slices to remain responsive to stop/pause
        poll_end = time.time() + poll_interval_sec
        while time.time() < poll_end:
            if stop_check_fn and stop_check_fn():
                return None
            time.sleep(0.02)

    return None
