from __future__ import annotations

import unittest

try:
    import cv2
    import numpy as np

    from heikesong.perception.ground_projection import (
        CameraIntrinsics,
        MatProjectionError,
        project_mat_boundary_to_world,
        select_stable_boundary_cluster,
    )
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, "OpenCV vision extra is not installed")
class GroundProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.intrinsics = CameraIntrinsics(162.143151, 162.143151, 239.5, 134.5)
        self.object_points = np.asarray(
            [[-0.9, -0.4, 0.0], [0.9, -0.4, 0.0], [0.9, 0.4, 0.0], [-0.9, 0.4, 0.0]],
            dtype=np.float64,
        )
        self.rotation_camera_from_mat = np.asarray(
            [[0.2, 0.9797959, 0.0], [0.0, 0.0, 1.0], [0.9797959, -0.2, 0.0]],
            dtype=np.float64,
        )
        self.translation_camera_from_mat = np.asarray([0.4, 0.48, 2.5])
        self.rotation_world_from_camera = np.asarray(
            [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]],
            dtype=np.float64,
        )

    def test_recovers_horizontal_mat_pose_and_dimensions(self) -> None:
        rvec, _ = cv2.Rodrigues(self.rotation_camera_from_mat)
        image_points, _ = cv2.projectPoints(
            self.object_points,
            rvec,
            self.translation_camera_from_mat,
            self.intrinsics.matrix(),
            None,
        )

        result = project_mat_boundary_to_world(
            image_points.reshape(4, 2),
            self.intrinsics,
            self.rotation_world_from_camera,
            np.asarray([1.0, 2.0, 0.5]),
        )

        self.assertGreater(result.gravity_alignment, 0.99)
        self.assertLess(result.reprojection_rms_px, 0.01)
        self.assertEqual(sorted((result.first_edge_m, result.second_edge_m)), [0.8, 1.8])
        edges = [
            np.linalg.norm(np.asarray(result.boundary_world[(i + 1) % 4]) - result.boundary_world[i])
            for i in range(4)
        ]
        self.assertAlmostEqual(max(edges), 1.8, places=4)
        self.assertAlmostEqual(min(edges), 0.8, places=4)

    def test_rejects_plane_that_is_not_aligned_with_world_ground(self) -> None:
        object_points = self.object_points
        image_points, _ = cv2.projectPoints(
            object_points,
            np.zeros(3),
            np.asarray([0.0, 0.0, 3.0]),
            self.intrinsics.matrix(),
            None,
        )

        with self.assertRaises(MatProjectionError):
            project_mat_boundary_to_world(
                image_points.reshape(4, 2),
                self.intrinsics,
                np.asarray(
                    [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                    dtype=np.float64,
                ),
                np.zeros(3),
            )

    def test_stable_cluster_ignores_outlier_frames_without_relaxing_limit(self) -> None:
        base = np.asarray(
            [[-0.9, -0.4, 0.0], [0.9, -0.4, 0.0], [0.9, 0.4, 0.0], [-0.9, 0.4, 0.0]]
        )
        samples = [base + np.asarray([index * 0.005, 0.0, 0.0]) for index in range(10)]
        samples.insert(0, base + np.asarray([0.5, 0.5, 0.0]))
        samples.insert(5, base + np.asarray([-0.4, 0.4, 0.0]))

        cluster = select_stable_boundary_cluster(
            samples,
            required_inliers=10,
            maximum_deviation=0.15,
        )

        self.assertIsNotNone(cluster)
        self.assertEqual(cluster.inlier_count, 10)
        self.assertLessEqual(cluster.maximum_deviation, 0.15)


if __name__ == "__main__":
    unittest.main()
