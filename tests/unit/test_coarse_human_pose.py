from heikesong.perception.coarse_human_pose import (
    CocoKeypoint,
    CoarsePoseConfig,
    CoarsePoseFrame,
    CoarsePoseLabel,
    CoarsePoseTracker,
    PoseKeypoint,
    RaisedHandSide,
)


def frame(points: dict[int, tuple[float, float]], now: float) -> CoarsePoseFrame:
    keypoints = [PoseKeypoint(50.0, 50.0, -1.0) for _ in range(17)]
    for index, (x, y) in points.items():
        keypoints[index] = PoseKeypoint(x, y, 5.0)
    return CoarsePoseFrame(
        tuple(keypoints), 20.0, 20.0, 460.0, 250.0, 0.9, now
    )


DOWNWARD_DOG = {
    CocoKeypoint.LEFT_SHOULDER: (150.0, 150.0),
    CocoKeypoint.LEFT_WRIST: (90.0, 210.0),
    CocoKeypoint.LEFT_HIP: (260.0, 70.0),
    CocoKeypoint.LEFT_KNEE: (330.0, 145.0),
    CocoKeypoint.LEFT_ANKLE: (390.0, 210.0),
}

PUSH_UP = {
    CocoKeypoint.LEFT_SHOULDER: (100.0, 150.0),
    CocoKeypoint.LEFT_WRIST: (100.0, 215.0),
    CocoKeypoint.LEFT_HIP: (250.0, 155.0),
    CocoKeypoint.LEFT_KNEE: (330.0, 160.0),
    CocoKeypoint.LEFT_ANKLE: (420.0, 165.0),
}


def test_downward_dog_emits_once_per_continuous_pose() -> None:
    tracker = CoarsePoseTracker(CoarsePoseConfig(pose_hold_seconds=1.0))
    assert tracker.update(frame(DOWNWARD_DOG, 0.0)).pose_trigger is None
    observation = tracker.update(frame(DOWNWARD_DOG, 1.1))
    assert observation.label is CoarsePoseLabel.DOWNWARD_DOG
    assert observation.pose_trigger is CoarsePoseLabel.DOWNWARD_DOG
    assert tracker.update(frame(DOWNWARD_DOG, 2.0)).pose_trigger is None


def test_push_up_is_coarsely_classified() -> None:
    tracker = CoarsePoseTracker(CoarsePoseConfig(pose_hold_seconds=0.5))
    tracker.update(frame(PUSH_UP, 0.0))
    observation = tracker.update(frame(PUSH_UP, 0.6))
    assert observation.label is CoarsePoseLabel.PUSH_UP
    assert observation.pose_trigger is CoarsePoseLabel.PUSH_UP


def test_push_up_allows_ankle_outside_low_camera_frame() -> None:
    partial_push_up = dict(PUSH_UP)
    partial_push_up.pop(CocoKeypoint.LEFT_ANKLE)
    tracker = CoarsePoseTracker(CoarsePoseConfig(pose_hold_seconds=0.5))
    tracker.update(frame(partial_push_up, 0.0))
    observation = tracker.update(frame(partial_push_up, 0.6))
    assert observation.label is CoarsePoseLabel.PUSH_UP
    assert observation.pose_trigger is CoarsePoseLabel.PUSH_UP


def test_push_up_allows_lower_body_outside_low_camera_frame() -> None:
    upper_body_push_up = dict(PUSH_UP)
    upper_body_push_up.pop(CocoKeypoint.LEFT_KNEE)
    upper_body_push_up.pop(CocoKeypoint.LEFT_ANKLE)
    tracker = CoarsePoseTracker(CoarsePoseConfig(pose_hold_seconds=0.5))
    tracker.update(frame(upper_body_push_up, 0.0))
    observation = tracker.update(frame(upper_body_push_up, 0.6))
    assert observation.label is CoarsePoseLabel.PUSH_UP
    assert observation.pose_trigger is CoarsePoseLabel.PUSH_UP


def test_upper_body_push_up_can_fall_back_to_elbow() -> None:
    upper_body_push_up = dict(PUSH_UP)
    upper_body_push_up.pop(CocoKeypoint.LEFT_KNEE)
    upper_body_push_up.pop(CocoKeypoint.LEFT_ANKLE)
    upper_body_push_up.pop(CocoKeypoint.LEFT_WRIST)
    upper_body_push_up[CocoKeypoint.LEFT_ELBOW] = (115.0, 205.0)
    observation = CoarsePoseTracker().update(frame(upper_body_push_up, 0.0))
    assert observation.label is CoarsePoseLabel.PUSH_UP


def test_brief_keypoint_dropout_does_not_reset_pose_hold() -> None:
    tracker = CoarsePoseTracker(
        CoarsePoseConfig(
            pose_hold_seconds=0.5,
            pose_dropout_grace_seconds=0.2,
        )
    )
    tracker.update(frame(PUSH_UP, 0.0))
    tracker.update(frame({}, 0.1))
    observation = tracker.update(frame(PUSH_UP, 0.6))
    assert observation.label is CoarsePoseLabel.PUSH_UP
    assert observation.pose_trigger is CoarsePoseLabel.PUSH_UP


def test_long_keypoint_dropout_resets_pose_hold() -> None:
    tracker = CoarsePoseTracker(
        CoarsePoseConfig(
            pose_hold_seconds=0.5,
            pose_dropout_grace_seconds=0.2,
        )
    )
    tracker.update(frame(PUSH_UP, 0.0))
    observation = tracker.update(frame({}, 0.3))
    assert observation.label is CoarsePoseLabel.UNKNOWN
    assert tracker.update(frame(PUSH_UP, 0.6)).pose_trigger is None


def test_upright_person_is_not_push_up() -> None:
    upright = {
        CocoKeypoint.LEFT_SHOULDER: (220.0, 70.0),
        CocoKeypoint.LEFT_HIP: (230.0, 140.0),
        CocoKeypoint.LEFT_KNEE: (235.0, 195.0),
        CocoKeypoint.LEFT_ANKLE: (240.0, 235.0),
    }
    observation = CoarsePoseTracker().update(frame(upright, 0.0))
    assert observation.label is CoarsePoseLabel.UNKNOWN


def test_stationary_person_triggers_support_once_then_rearms_after_motion() -> None:
    tracker = CoarsePoseTracker(
        CoarsePoseConfig(pose_hold_seconds=99.0, stationary_hold_seconds=2.0)
    )
    tracker.update(frame(PUSH_UP, 0.0))
    tracker.update(frame(PUSH_UP, 0.5))
    assert tracker.update(frame(PUSH_UP, 2.1)).support_trigger
    assert not tracker.update(frame(PUSH_UP, 3.0)).support_trigger

    moved = {index: (x + 80.0, y) for index, (x, y) in PUSH_UP.items()}
    tracker.update(frame(moved, 3.5))
    tracker.update(frame(moved, 4.0))
    assert tracker.update(frame(moved, 6.1)).support_trigger


def test_raised_hand_side_is_reported() -> None:
    points = dict(PUSH_UP)
    points[CocoKeypoint.LEFT_WRIST] = (90.0, 80.0)
    observation = CoarsePoseTracker().update(frame(points, 0.0))
    assert observation.raised_hand is RaisedHandSide.LEFT
