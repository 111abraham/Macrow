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

    def test_find_template_nan_safe(self):
        # Non-existent or flat template search returns None rather than fake match
        res = find_template_on_screen("", confidence=0.85)
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
