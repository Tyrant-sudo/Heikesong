from __future__ import annotations

import unittest

from heikesong.behavior.person_orbit import (
    OrbitDecision,
    PersonDetection,
    PersonOrbitPolicy,
    infer_facing_orbit_direction,
)


def person(area: float, center: float, confidence: float = 0.8) -> PersonDetection:
    return PersonDetection(area, center, confidence)


class PersonOrbitPolicyTests(unittest.TestCase):
    def test_infers_orbit_direction_from_profile_face(self) -> None:
        left = [(100.0, 40.0, 0.9)] + [(0.0, 0.0, 0.0)] * 2 + [
            (130.0, 45.0, 0.8),
            (0.0, 0.0, 0.0),
        ]
        right = [(160.0, 40.0, 0.9)] + [(0.0, 0.0, 0.0)] * 2 + [
            (130.0, 45.0, 0.8),
            (0.0, 0.0, 0.0),
        ]
        self.assertEqual(1, infer_facing_orbit_direction(left, 200.0))
        self.assertEqual(-1, infer_facing_orbit_direction(right, 200.0))

    def test_rejects_frontal_or_uncertain_face_direction(self) -> None:
        frontal = [(132.0, 40.0, 0.9)] + [(0.0, 0.0, 0.0)] * 2 + [
            (130.0, 45.0, 0.8),
            (134.0, 45.0, 0.8),
        ]
        self.assertIsNone(infer_facing_orbit_direction(frontal, 200.0))
    def test_selects_largest_central_person(self) -> None:
        policy = PersonOrbitPolicy()

        selected = policy.start(
            [person(8000, 40), person(3000, 220), person(5000, 280)],
            now_s=1.0,
            direction=1,
            duration_s=6.0,
        )

        self.assertEqual(280, selected.center_x_px)

    def test_rejects_start_without_central_target(self) -> None:
        policy = PersonOrbitPolicy()

        with self.assertRaisesRegex(ValueError, "no central person"):
            policy.start(
                [person(5000, 20)], now_s=1.0, direction=1, duration_s=6.0
            )

    def test_tracks_nearest_center_instead_of_largest_bystander(self) -> None:
        policy = PersonOrbitPolicy()
        policy.start(
            [person(4000, 250)], now_s=1.0, direction=1, duration_s=6.0
        )

        output = policy.update(
            [person(20000, 40), person(2500, 265)], now_s=1.1
        )

        self.assertEqual(OrbitDecision.MOVE, output.decision)
        self.assertEqual(265, output.target.center_x_px)

    def test_left_orbit_uses_left_lateral_and_visual_yaw(self) -> None:
        policy = PersonOrbitPolicy()
        policy.start(
            [person(4000, 240)], now_s=1.0, direction=1, duration_s=6.0
        )

        output = policy.update([person(4000, 290)], now_s=1.1)

        self.assertEqual(0.30, output.linear_y_mps)
        self.assertAlmostEqual(-0.50, output.angular_z_rps)

    def test_holds_brief_detection_gap_then_stops(self) -> None:
        policy = PersonOrbitPolicy()
        policy.start(
            [person(4000, 240)], now_s=1.0, direction=1, duration_s=6.0
        )

        self.assertEqual(OrbitDecision.HOLD, policy.update([], now_s=1.4).decision)
        self.assertEqual(OrbitDecision.STOP, policy.update([], now_s=1.7).decision)

    def test_completes_at_requested_duration(self) -> None:
        policy = PersonOrbitPolicy()
        policy.start(
            [person(4000, 240)], now_s=1.0, direction=-1, duration_s=3.0
        )

        output = policy.update([person(4000, 240)], now_s=4.0)

        self.assertEqual(OrbitDecision.COMPLETE, output.decision)


if __name__ == "__main__":
    unittest.main()
