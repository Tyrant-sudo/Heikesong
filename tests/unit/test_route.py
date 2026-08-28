import math
import unittest

from heikesong.safety.keepout import KeepoutZone
from heikesong.safety.route import (
    plan_corner_bypass,
    plan_full_orbit,
    polyline_minimum_clearance,
)


class CornerBypassTests(unittest.TestCase):
    def test_right_bypass_stays_outside_expanded_zone(self):
        zone = KeepoutZone(((-1.0, -1.0), (-1.0, -3.0), (1.0, -3.0), (1.0, -1.0)))
        start = (0.0, 0.0)

        plan = plan_corner_bypass(zone, start, -math.pi / 2, side="right")

        points = (start,) + plan.waypoints
        self.assertTrue(all(zone.segment_allowed(a, b) for a, b in zip(points, points[1:])))
        self.assertGreaterEqual(polyline_minimum_clearance(points, zone.boundary), 0.18)
        self.assertLess(plan.waypoints[0][0], 0.0)

    def test_rejects_start_inside_zone(self):
        zone = KeepoutZone(((-1.0, -1.0), (-1.0, 1.0), (1.0, 1.0), (1.0, -1.0)))
        with self.assertRaisesRegex(ValueError, "inside"):
            plan_corner_bypass(zone, (0.0, 0.0), 0.0)


class FullOrbitTests(unittest.TestCase):
    def setUp(self):
        self.zone = KeepoutZone(
            ((-1.0, -1.0), (-1.0, -3.0), (1.0, -3.0), (1.0, -1.0))
        )
        self.start = (0.0, 0.0)

    def test_right_orbit_is_closed_and_stays_outside_margin(self):
        plan = plan_full_orbit(
            self.zone,
            self.start,
            -math.pi / 2,
            side="right",
            extra_margin_m=0.2,
        )

        points = (self.start,) + plan.waypoints
        self.assertEqual(plan.waypoints[0], plan.waypoints[-1])
        self.assertEqual(len(plan.waypoints), 6)
        self.assertLess(plan.waypoints[1][0], 0.0)
        self.assertTrue(
            all(self.zone.segment_allowed(a, b) for a, b in zip(points, points[1:]))
        )
        self.assertGreaterEqual(
            polyline_minimum_clearance(points, self.zone.boundary), 0.19
        )

    def test_left_orbit_starts_on_opposite_side(self):
        right = plan_full_orbit(self.zone, self.start, -math.pi / 2, side="right")
        left = plan_full_orbit(self.zone, self.start, -math.pi / 2, side="left")

        self.assertLess(right.waypoints[1][0], 0.0)
        self.assertGreater(left.waypoints[1][0], 0.0)

    def test_rejects_start_inside_zone(self):
        with self.assertRaisesRegex(ValueError, "inside"):
            plan_full_orbit(self.zone, (0.0, -2.0), 0.0)


if __name__ == "__main__":
    unittest.main()
