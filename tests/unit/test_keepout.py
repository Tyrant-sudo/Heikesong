from __future__ import annotations

import unittest

from heikesong.safety.keepout import (
    KeepoutMotionGate,
    KeepoutZone,
    Motion2D,
    Pose2D,
)


class KeepoutZoneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.zone = KeepoutZone(((-0.9, -0.4), (0.9, -0.4), (0.9, 0.4), (-0.9, 0.4)))

    def test_expansion_adds_requested_clearance(self) -> None:
        expanded = self.zone.expanded(0.4)

        xs = [point[0] for point in expanded.boundary]
        ys = [point[1] for point in expanded.boundary]
        self.assertAlmostEqual(min(xs), -1.3)
        self.assertAlmostEqual(max(xs), 1.3)
        self.assertAlmostEqual(min(ys), -0.8)
        self.assertAlmostEqual(max(ys), 0.8)

    def test_rejects_segment_crossing_or_starting_inside_zone(self) -> None:
        self.assertFalse(self.zone.segment_allowed((-2.0, 0.0), (2.0, 0.0)))
        self.assertFalse(self.zone.segment_allowed((0.0, 0.0), (2.0, 0.0)))
        self.assertTrue(self.zone.segment_allowed((-2.0, 1.0), (2.0, 1.0)))

    def test_occupancy_grid_marks_inside_cells(self) -> None:
        grid = self.zone.occupancy_grid(resolution=0.1, outer_margin_m=0.1)

        self.assertEqual(len(grid.data), grid.width * grid.height)
        self.assertIn(100, grid.data)
        self.assertIn(0, grid.data)

    def test_motion_gate_rejects_predicted_crossing(self) -> None:
        gate = KeepoutMotionGate(self.zone, prediction_horizon_s=2.0)

        self.assertFalse(
            gate.command_allowed(Pose2D(-1.2, 0.0, 0.0), Motion2D(0.5, 0.0, 0.0))
        )
        self.assertTrue(
            gate.command_allowed(Pose2D(-1.2, 1.0, 0.0), Motion2D(0.5, 0.0, 0.0))
        )

    def test_motion_gate_allows_rotation_outside_zone(self) -> None:
        gate = KeepoutMotionGate(self.zone)

        self.assertTrue(
            gate.command_allowed(Pose2D(-1.2, 0.0, 0.0), Motion2D(0.0, 0.0, 0.5))
        )


if __name__ == "__main__":
    unittest.main()
