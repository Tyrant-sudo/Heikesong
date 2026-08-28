import unittest

from heikesong.behavior.person_head_tracker import (
    HeadTrackingConfig,
    HeadTrackingDecision,
    PersonHeadTracker,
)


class PersonHeadTrackerTests(unittest.TestCase):
    def test_holds_target_inside_deadband(self) -> None:
        tracker = PersonHeadTracker(HeadTrackingConfig(target_pitch_rad=0.0))
        tracker.observe(center_x_px=230.0, confidence=0.8, now_s=1.0)

        output = tracker.update(now_s=1.1)

        self.assertEqual(HeadTrackingDecision.HOLD, output.decision)
        self.assertEqual(0.0, output.target_yaw_rad)
        self.assertEqual(0.0, output.target_pitch_rad)

    def test_adjustment_is_step_and_angle_limited(self) -> None:
        tracker = PersonHeadTracker()
        for index in range(10):
            now = float(index)
            tracker.observe(center_x_px=0.0, confidence=0.8, now_s=now)
            output = tracker.update(now_s=now)

        self.assertIn(
            output.decision,
            (HeadTrackingDecision.ADJUST, HeadTrackingDecision.HOLD),
        )
        self.assertEqual(0.18, output.target_yaw_rad)

    def test_stops_after_target_timeout(self) -> None:
        tracker = PersonHeadTracker()
        tracker.observe(center_x_px=100.0, confidence=0.8, now_s=1.0)

        output = tracker.update(now_s=2.1)

        self.assertEqual(HeadTrackingDecision.STOP, output.decision)

    def test_ignores_low_confidence_observation(self) -> None:
        tracker = PersonHeadTracker()
        tracker.observe(center_x_px=100.0, confidence=0.2, now_s=1.0)

        output = tracker.update(now_s=1.0)

        self.assertEqual(HeadTrackingDecision.STOP, output.decision)

    def test_filters_detection_jitter_before_steering(self) -> None:
        tracker = PersonHeadTracker(
            HeadTrackingConfig(
                deadband_px=0.0,
                smoothing_alpha=0.25,
                maximum_slew_rad_per_s=10.0,
                maximum_step_rad=1.0,
            )
        )
        tracker.observe(center_x_px=100.0, confidence=0.8, now_s=1.0)
        tracker.observe(center_x_px=300.0, confidence=0.8, now_s=1.1)

        output = tracker.update(now_s=1.1)

        self.assertAlmostEqual(0.108, output.target_yaw_rad)

    def test_limits_turn_rate_using_elapsed_time(self) -> None:
        tracker = PersonHeadTracker(
            HeadTrackingConfig(
                deadband_px=0.0,
                maximum_slew_rad_per_s=0.1,
                nominal_update_period_s=0.2,
                maximum_step_rad=1.0,
                maximum_yaw_rad=1.0,
            )
        )
        tracker.observe(center_x_px=0.0, confidence=0.8, now_s=1.0)

        first = tracker.update(now_s=1.0)
        second = tracker.update(now_s=1.1)

        self.assertAlmostEqual(0.02, first.target_yaw_rad)
        self.assertAlmostEqual(0.03, second.target_yaw_rad)

    def test_requests_complete_look_up_pose_in_one_update(self) -> None:
        tracker = PersonHeadTracker(
            HeadTrackingConfig(
                target_pitch_rad=-0.16,
            )
        )
        tracker.observe(center_x_px=240.0, confidence=0.8, now_s=1.0)

        output = tracker.update(now_s=1.0)

        self.assertEqual(HeadTrackingDecision.ADJUST, output.decision)
        self.assertEqual(0.0, output.target_yaw_rad)
        self.assertAlmostEqual(-0.16, output.target_pitch_rad)

    def test_tracks_face_vertically_from_keypoint_center(self) -> None:
        tracker = PersonHeadTracker()
        tracker.observe(
            center_x_px=240.0,
            center_y_px=55.0,
            confidence=0.8,
            now_s=1.0,
        )

        output = tracker.update(now_s=1.0)

        self.assertEqual(HeadTrackingDecision.ADJUST, output.decision)
        self.assertAlmostEqual(-0.12, output.target_pitch_rad)
        self.assertAlmostEqual(80.0, output.vertical_error_px)


if __name__ == "__main__":
    unittest.main()
