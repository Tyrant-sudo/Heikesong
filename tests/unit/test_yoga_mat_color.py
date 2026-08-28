from __future__ import annotations

import unittest

try:
    import cv2
    import numpy as np

    from heikesong.perception.yoga_mat_color import ColorYogaMatDetector
except ImportError:
    cv2 = None
    np = None
    ColorYogaMatDetector = None


@unittest.skipIf(cv2 is None, "OpenCV vision extra is not installed")
class ColorYogaMatDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = ColorYogaMatDetector()

    def test_detects_complete_calibrated_quadrilateral(self) -> None:
        frame = np.full((270, 480, 3), (98, 102, 104), dtype=np.uint8)
        polygon = np.asarray([[180, 220], [220, 185], [270, 185], [315, 220]])
        cv2.fillConvexPoly(frame, polygon, (135, 135, 151))

        result = self.detector.detect(frame)

        self.assertTrue(result.detected)
        self.assertEqual(len(result.boundary), 4)
        self.assertIsNotNone(result.center)

    def test_rejects_mat_clipped_by_bottom_edge(self) -> None:
        frame = np.full((270, 480, 3), (98, 102, 104), dtype=np.uint8)
        polygon = np.asarray([[170, 269], [215, 215], [270, 215], [330, 269]])
        cv2.fillConvexPoly(frame, polygon, (135, 135, 151))

        result = self.detector.detect(frame)

        self.assertFalse(result.detected)
        self.assertEqual(result.boundary, ())

    def test_rejects_frame_without_mat(self) -> None:
        frame = np.full((270, 480, 3), (98, 102, 104), dtype=np.uint8)

        result = self.detector.detect(frame)

        self.assertFalse(result.detected)
        self.assertIsNone(result.center)


if __name__ == "__main__":
    unittest.main()
