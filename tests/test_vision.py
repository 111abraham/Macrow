import unittest
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage, QPainter, QColor
import sys

# Ensure QApplication exists for QImage
if QApplication.instance() is None:
    app = QApplication(sys.argv)

from app.core.vision import (
    match_template_numpy_fft,
    match_template,
    qimage_to_numpy_gray,
    capture_screen_win32_bgra,
    find_template_on_screen,
    wait_for_template_on_screen,
)


class TestVision(unittest.TestCase):
    def test_numpy_fft_template_match(self):
        # Create a 200x200 screen
        screen = np.full((200, 200), 50, dtype=np.uint8)
        # Create a 30x30 textured template
        template = np.full((30, 30), 180, dtype=np.uint8)
        template[5:15, 5:15] = 250
        template[15:25, 15:25] = 20

        # Place template at x=75, y=45
        screen[45:75, 75:105] = template

        (best_x, best_y), score = match_template_numpy_fft(screen, template)
        self.assertEqual(best_x, 75)
        self.assertEqual(best_y, 45)
        self.assertGreaterEqual(score, 0.99)

    def test_qimage_conversion(self):
        qimg = QImage(50, 40, QImage.Format.Format_RGB32)
        qimg.fill(QColor(100, 100, 100))
        arr = qimage_to_numpy_gray(qimg)
        self.assertEqual(arr.shape, (40, 50))
        self.assertEqual(arr.dtype, np.uint8)

    def test_capture_screen_win32_bgra(self):
        arr, rx, ry, rw, rh = capture_screen_win32_bgra(region=(0, 0, 80, 80))
        self.assertIsNotNone(arr)
        self.assertEqual(rw, 80)
        self.assertEqual(rh, 80)
        self.assertEqual(arr.shape, (80, 80, 4))
        self.assertEqual(arr.dtype, np.uint8)

    def test_find_template_missing_file_safe(self):
        # Must return None without crashing or raising unhandled exceptions
        res = find_template_on_screen("non_existent_file_path_12345.png")
        self.assertIsNone(res)
        res_empty = find_template_on_screen("")
        self.assertIsNone(res_empty)

    def test_wait_for_template_missing_file_safe(self):
        res = wait_for_template_on_screen("non_existent_file.png", timeout_sec=0.1)
        self.assertIsNone(res)
        res_empty = wait_for_template_on_screen("", timeout_sec=0.1)
        self.assertIsNone(res_empty)

    def test_numpy_fft_nan_protection(self):
        # Blank / flat screen should not return NaN score or crash
        screen = np.zeros((100, 100), dtype=np.uint8)
        tmpl = np.zeros((20, 20), dtype=np.uint8)
        (x, y), score = match_template_numpy_fft(screen, tmpl)
        self.assertFalse(np.isnan(score))
        self.assertFalse(np.isinf(score))

    def test_multiscale_match(self):
        # Create a 200x200 screen
        screen = np.full((200, 200), 50, dtype=np.uint8)
        # Create a 30x30 textured template
        template = np.full((30, 30), 180, dtype=np.uint8)
        template[5:15, 5:15] = 250
        template[15:25, 15:25] = 20

        # Place template at x=80, y=50
        screen[50:80, 80:110] = template

        # Match at scale 1.0
        loc, score = match_template(screen, template)
        self.assertIsNotNone(loc)
        self.assertEqual(loc[0], 80)
        self.assertEqual(loc[1], 50)
        self.assertGreaterEqual(score, 0.98)

    def test_find_template_nan_safe(self):
        # Non-existent or flat template search returns None rather than fake match
        res = find_template_on_screen("", confidence=0.85)
        self.assertIsNone(res)

    def test_parse_template_targets(self):
        from app.core.vision import parse_template_targets
        # Semicolon delimited string
        targets = parse_template_targets("path1.png; path2.png ;  path3.png")
        self.assertEqual(targets, ["path1.png", "path2.png", "path3.png"])
        # List input
        targets_list = parse_template_targets(["a.png", "b.png"])
        self.assertEqual(targets_list, ["a.png", "b.png"])
        # Empty string
        self.assertEqual(parse_template_targets(""), [])

    def test_capture_desktop_composite_qimage_region(self):
        from app.core.vision import capture_desktop_composite_qimage
        # Capture a 64x64 region at (50, 50)
        qimg, rx, ry, rw, rh = capture_desktop_composite_qimage((50, 50, 64, 64))
        if qimg is not None:
            self.assertEqual(rw, 64)
            self.assertEqual(rh, 64)
            self.assertEqual(rx, 50)
            self.assertEqual(ry, 50)
            self.assertEqual(qimg.width(), 64)
            self.assertEqual(qimg.height(), 64)

    def test_region_highlight_overlay(self):
        from app.ui.indicator import RegionHighlightOverlay
        overlay = RegionHighlightOverlay()
        overlay.show_region(120, 150, 240, 180, label="Test Region", color_hex="#10B981")
        self.assertEqual(overlay.x(), 120)
        self.assertEqual(overlay.y(), 150)
        self.assertEqual(overlay.width(), 240)
        self.assertEqual(overlay.height(), 180)
        self.assertEqual(overlay.label_text, "Test Region")
        self.assertTrue(overlay.isVisible())

        # Test small box adapts badge
        overlay.show_region(50, 60, 45, 25, label="Mini")
        self.assertEqual(overlay.width(), 45)
        self.assertEqual(overlay.height(), 25)

        overlay.hide_overlay()
        self.assertFalse(overlay.isVisible())
        overlay.close()


if __name__ == "__main__":
    unittest.main()
