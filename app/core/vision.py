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


def capture_desktop_composite_qimage(
    region: Optional[Tuple[int, int, int, int]] = None
) -> Tuple[Optional[QImage], int, int, int, int]:
    """Captures desktop screen across all connected monitors using Qt (1:1 native hardware resolution).
    Handles virtual multi-monitor desktop without downscaling or blurring.
    Returns (composite_qimage, offset_x, offset_y, width, height).
    """
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QGuiApplication, QPainter, QImage
        from PyQt6.QtCore import Qt, QPoint, QRect
        from app.core.win32_api import get_screen_physical_rect

        app = QApplication.instance()
        screens = QGuiApplication.screens() if app else []
        if screens:
            if region is not None:
                rx, ry, rw, rh = region
                target_rect = QRect(int(rx), int(ry), int(rw), int(rh))
                center_pt = target_rect.center()
                screen = QGuiApplication.screenAt(center_pt)
                if not screen:
                    screen = QGuiApplication.primaryScreen()
                if screen and rw > 0 and rh > 0:
                    px_left, px_top, px_w, px_h = get_screen_physical_rect(screen)
                    lx = max(0, int(rx - px_left))
                    ly = max(0, int(ry - px_top))
                    pix = screen.grabWindow(0, lx, ly, rw, rh)
                    if not pix.isNull() and pix.width() > 0 and pix.height() > 0:
                        qimg = pix.toImage().convertToFormat(QImage.Format.Format_ARGB32)
                        if qimg.width() != rw or qimg.height() != rh:
                            qimg = qimg.scaled(rw, rh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        return qimg, rx, ry, rw, rh

            # Compute physical virtual screen bounding box across all monitors
            screen_rects = [get_screen_physical_rect(s) for s in screens]
            min_x = min(r[0] for r in screen_rects)
            min_y = min(r[1] for r in screen_rects)
            max_x = max(r[0] + r[2] for r in screen_rects)
            max_y = max(r[1] + r[3] for r in screen_rects)
            vw = max_x - min_x
            vh = max_y - min_y

            if vw > 0 and vh > 0:
                comp = QImage(vw, vh, QImage.Format.Format_ARGB32)
                comp.fill(0)
                p = QPainter(comp)
                for s, (sx, sy, sw, sh) in zip(screens, screen_rects):
                    pix = s.grabWindow(0)
                    p.drawImage(sx - min_x, sy - min_y, pix.toImage())
                p.end()
                if region is not None:
                    rx, ry, rw, rh = region
                    crop_x = int(rx - min_x)
                    crop_y = int(ry - min_y)
                    if 0 <= crop_x < vw and 0 <= crop_y < vh:
                        cropped = comp.copy(crop_x, crop_y, rw, rh)
                        return cropped, rx, ry, rw, rh
                return comp, min_x, min_y, vw, vh
    except Exception:
        pass
    return None, 0, 0, 0, 0


def capture_screen_win32_bgra(
    region: Optional[Tuple[int, int, int, int]] = None
) -> Tuple[Optional[np.ndarray], int, int, int, int]:
    """Captures desktop screen across all connected monitors at 1:1 physical hardware pixels.
    Thread-safe Win32 GDI screen capture is used as primary to avoid Qt GUI thread violations
    and prevent DPI downscaling distortion.
    Returns (bgra_numpy_array, offset_x, offset_y, width, height).
    """
    from app.core.win32_api import init_dpi_awareness
    init_dpi_awareness()

    # 1. Primary: Direct 1:1 Win32 GDI hardware framebuffer capture
    try:
        if region is not None:
            rx, ry, rw, rh = [int(v) for v in region]
            if rw <= 0 or rh <= 0:
                return None, 0, 0, 0, 0
        else:
            rx = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
            ry = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
            rw = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
            rh = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
            if rw <= 0 or rh <= 0:
                rx, ry, rw, rh = 0, 0, 1920, 1080

        hdc_screen = user32.GetDC(None)
        if hdc_screen:
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
        pass

    # 2. Fallback: Qt multi-screen capture
    try:
        qimg, qx, qy, qw, qh = capture_desktop_composite_qimage(region)
        if qimg is not None and not qimg.isNull() and qw > 0 and qh > 0:
            qimg_argb = qimg.convertToFormat(QImage.Format.Format_ARGB32)
            w, h = qimg_argb.width(), qimg_argb.height()
            ptr = qimg_argb.constBits()
            ptr.setsize(qimg_argb.sizeInBytes())
            bpl = qimg_argb.bytesPerLine()
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, bpl))[:, :w * 4].reshape((h, w, 4)).copy()
            return arr, qx, qy, w, h
    except Exception:
        pass

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
    """Convert QImage to 2D numpy uint8 grayscale array safely."""
    if qimg.isNull():
        return np.zeros((0, 0), dtype=np.uint8)

    if qimg.format() != QImage.Format.Format_Grayscale8:
        gray_img = qimg.convertToFormat(QImage.Format.Format_Grayscale8)
    else:
        gray_img = qimg

    w, h = gray_img.width(), gray_img.height()
    bpl = gray_img.bytesPerLine()
    ptr = gray_img.constBits()
    ptr.setsize(gray_img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, bpl))[:, :w].copy()
    return arr


# In-memory template cache: path -> (mtime, gray_numpy_array)
_TEMPLATE_CACHE: Dict[str, Tuple[float, np.ndarray]] = {}


def get_template_gray_cached(template_input: Any) -> Optional[np.ndarray]:
    """Retrieve pre-decoded grayscale numpy array for a template, using in-memory cache to eliminate disk I/O."""
    if template_input is None:
        return None
    if isinstance(template_input, np.ndarray):
        return template_input if len(template_input.shape) == 2 else bgra_to_gray(template_input)
    if isinstance(template_input, QImage):
        return qimage_to_numpy_gray(template_input)
    if isinstance(template_input, str):
        path = template_input.strip()
        if not path or not os.path.exists(path):
            return None
        try:
            mtime = os.path.getmtime(path)
            cached = _TEMPLATE_CACHE.get(path)
            if cached and cached[0] == mtime:
                return cached[1]
            qimg = QImage(path)
            if qimg.isNull():
                return None
            gray = qimage_to_numpy_gray(qimg)
            if gray.size > 0:
                _TEMPLATE_CACHE[path] = (mtime, gray)
                return gray
        except Exception:
            return None
    return None


def parse_template_targets(template_input: Any) -> list:
    """Parse single or multiple template paths (supporting list or semicolon separation for OR conditions)."""
    if isinstance(template_input, (list, tuple)):
        return [t for t in template_input if t]
    if isinstance(template_input, str):
        if ";" in template_input:
            return [t.strip() for t in template_input.split(";") if t.strip()]
        if "," in template_input and not os.path.exists(template_input):
            return [t.strip() for t in template_input.split(",") if t.strip()]
        return [template_input.strip()] if template_input.strip() else []
    return [template_input] if template_input else []


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

    # Fast 2D integral image slice (zero-copy, no huge meshgrid MemoryError on multi-monitor)
    sum_s = (
        int_s[th:sh + 1, tw:sw + 1]
        - int_s[0:sh - th + 1, tw:sw + 1]
        - int_s[th:sh + 1, 0:sw - tw + 1]
        + int_s[0:sh - th + 1, 0:sw - tw + 1]
    )
    sum_s_sq = (
        int_s_sq[th:sh + 1, tw:sw + 1]
        - int_s_sq[0:sh - th + 1, tw:sw + 1]
        - int_s_sq[th:sh + 1, 0:sw - tw + 1]
        + int_s_sq[0:sh - th + 1, 0:sw - tw + 1]
    )

    n_pixels = float(th * tw)
    var_s = sum_s_sq - (sum_s ** 2) / n_pixels
    var_s = np.maximum(var_s, 0.0)

    denom = np.sqrt(var_s * t_energy)
    flat_mask = (var_s < 1.0) | (denom < 1e-4)

    # Initialize with -1.0 so flat areas default to no-correlation
    ncc = np.full(corr.shape, -1.0, dtype=np.float32)
    np.divide(corr, denom, out=ncc, where=~flat_mask)
    ncc = np.nan_to_num(ncc, nan=-1.0, posinf=1.0, neginf=-1.0)
    ncc = np.clip(ncc, -1.0, 1.0)

    max_idx = np.unravel_index(np.argmax(ncc), ncc.shape)
    best_y, best_x = int(max_idx[0]), int(max_idx[1])
    best_score = float(ncc[best_y, best_x])
    if math.isnan(best_score) or math.isinf(best_score):
        best_score = -1.0

    return ((best_x, best_y), best_score)


def match_template_multiscale(
    screen_arr: np.ndarray,
    template_arr: np.ndarray,
    confidence: float = 0.8,
) -> Tuple[Tuple[int, int], float, Tuple[int, int]]:
    """Multi-scale template matching using OpenCV with fallback to numpy FFT.
    Evaluates scales [1.0, 1.25, 0.8, 1.1, 0.9, 1.5, 0.75] to robustly handle Windows DPI scaling.
    Returns ((best_x, best_y), best_score, (matched_w, matched_h)).
    """
    th, tw = template_arr.shape[:2]
    sh, sw = screen_arr.shape[:2]

    if HAS_CV2:
        try:
            # 1. First test 1:1 scale (exact scale)
            res = cv2.matchTemplate(screen_arr, template_arr, cv2.TM_CCOEFF_NORMED)
            res = np.nan_to_num(res, nan=-1.0, posinf=1.0, neginf=-1.0)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            best_score = float(max_val) if not (math.isnan(max_val) or math.isinf(max_val)) else -1.0
            best_loc = max_loc
            best_w, best_h = tw, th

            # If 1:1 match already satisfies confidence, return immediately (avoids redundant scale sweeps)
            if best_score >= confidence:
                return (best_loc, best_score, (best_w, best_h))

            # 2. Multi-scale search (covers Windows display scaling: 125%, 150%, 80%, 110%, etc.)
            scales = [1.25, 0.8, 1.1, 0.9, 1.5, 0.75]
            for s in scales:
                new_w = int(round(tw * s))
                new_h = int(round(th * s))
                if new_w < 8 or new_h < 8 or new_w >= sw or new_h >= sh:
                    continue

                scaled_tmpl = cv2.resize(
                    template_arr,
                    (new_w, new_h),
                    interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_LINEAR,
                )
                s_res = cv2.matchTemplate(screen_arr, scaled_tmpl, cv2.TM_CCOEFF_NORMED)
                s_res = np.nan_to_num(s_res, nan=-1.0, posinf=1.0, neginf=-1.0)
                _, s_max_val, _, s_max_loc = cv2.minMaxLoc(s_res)
                score = float(s_max_val) if not (math.isnan(s_max_val) or math.isinf(s_max_val)) else -1.0

                if score > best_score:
                    best_score = score
                    best_loc = s_max_loc
                    best_w, best_h = new_w, new_h
                    if best_score >= max(0.92, confidence):
                        break

            return (best_loc, best_score, (best_w, best_h))
        except Exception:
            pass

    loc, score = match_template_numpy_fft(screen_arr, template_arr)
    return (loc, score, (tw, th))


def match_template(
    screen_arr: np.ndarray,
    template_arr: np.ndarray,
) -> Tuple[Tuple[int, int], float]:
    """Finds best match of template_arr inside screen_arr.
    Returns ((x, y), confidence_score).
    """
    loc, score, _ = match_template_multiscale(screen_arr, template_arr, confidence=0.8)
    return (loc, score)


def find_template_on_screen(
    template_img_or_path: Any,
    confidence: float = 0.8,
    region: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int, int, int, float]]:
    """Searches for template on the current desktop screen using high-speed cached matching.
    Supports single template path/image or multiple targets (list or semicolon-delimited) for OR logic.
    If region is specified (rx, ry, rw, rh), restricts search to that screen area.
    
    Returns (center_x, center_y, width, height, score) or None if score < confidence.
    """
    targets = parse_template_targets(template_img_or_path)
    if not targets:
        return None

    try:
        # Thread-safe screen capture across all connected monitors (performed ONCE per frame)
        bgra, rx, ry, rw, rh = capture_screen_win32_bgra(region)
        if bgra is None or rw <= 0 or rh <= 0:
            return None

        screen_arr = bgra_to_gray(bgra)
        sh, sw = screen_arr.shape

        best_result: Optional[Tuple[int, int, int, int, float]] = None

        # Test each template in the target list (OR condition matching)
        for tmpl_target in targets:
            template_arr = get_template_gray_cached(tmpl_target)
            if template_arr is None or template_arr.size == 0:
                continue

            th, tw = template_arr.shape
            if th > sh or tw > sw or th <= 0 or tw <= 0:
                continue

            (match_x, match_y), score, (matched_w, matched_h) = match_template_multiscale(
                screen_arr, template_arr, confidence=confidence
            )

            if not math.isnan(score) and not math.isinf(score) and score >= confidence and score > 0.0:
                abs_x = rx + match_x
                abs_y = ry + match_y
                center_x = abs_x + matched_w // 2
                center_y = abs_y + matched_h // 2
                res = (center_x, center_y, matched_w, matched_h, score)
                if best_result is None or score > best_result[4]:
                    best_result = res
                # High-confidence early match exit
                if score >= 0.92:
                    return best_result

        return best_result
    except Exception:
        return None


def wait_for_template_on_screen(
    template_img_or_path: Any,
    confidence: float = 0.8,
    timeout_sec: float = 10.0,
    poll_interval_sec: float = 0.03,
    region: Optional[Tuple[int, int, int, int]] = None,
    stop_check_fn: Optional[Any] = None,
) -> Optional[Tuple[int, int, int, int, float]]:
    """Polls the screen waiting for template (or any of multiple templates) to appear within timeout_sec.
    Uses ultra-low latency 30ms polling interval (~33 FPS) for instant sub-frame responsiveness.
    Returns (center_x, center_y, width, height, score) or None on timeout.
    """
    targets = parse_template_targets(template_img_or_path)
    if not targets:
        return None

    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if stop_check_fn and stop_check_fn():
            return None

        result = find_template_on_screen(template_img_or_path, confidence, region)
        if result is not None:
            return result

        # Sleep in tiny 10ms slices to remain instantly responsive to stop/pause
        poll_end = time.time() + poll_interval_sec
        while time.time() < poll_end:
            if stop_check_fn and stop_check_fn():
                return None
            time.sleep(0.01)

    return None
