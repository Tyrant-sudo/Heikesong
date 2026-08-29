from heikesong.behavior.v2_session import (
    TriggerSource,
    V2ModeState,
    V2SessionCoordinator,
    V2Task,
)


def test_tasks_are_blocked_until_yoga_mode_starts() -> None:
    coordinator = V2SessionCoordinator()
    decision = coordinator.request_task(
        V2Task.DOWNWARD_DOG, TriggerSource.VOICE, 0.0
    )
    assert decision.action == "ignored"
    assert coordinator.enter_mode().action == "mode_started"
    assert coordinator.state is V2ModeState.ACTIVE


def test_voice_and_visual_share_one_running_task_gate() -> None:
    coordinator = V2SessionCoordinator()
    coordinator.enter_mode()
    visual = coordinator.request_task(
        V2Task.DOWNWARD_DOG, TriggerSource.VISUAL, 1.0, "downward-dog-1"
    )
    assert visual.action == "run_task"
    duplicate = coordinator.request_task(
        V2Task.DOWNWARD_DOG, TriggerSource.VOICE, 1.1
    )
    assert duplicate.action == "ignored"
    coordinator.finish_task(2.0)
    repeated_visual = coordinator.request_task(
        V2Task.DOWNWARD_DOG, TriggerSource.VISUAL, 10.0, "downward-dog-1"
    )
    assert repeated_visual.action == "ignored"


def test_end_during_task_waits_for_safe_completion_then_high_five() -> None:
    coordinator = V2SessionCoordinator()
    coordinator.enter_mode()
    coordinator.request_task(V2Task.PUSH_UP, TriggerSource.VOICE, 0.0)
    assert coordinator.request_end().action == "end_deferred"
    decision = coordinator.finish_task(2.0)
    assert decision.action == "run_task"
    assert decision.task is V2Task.HIGH_FIVE_RIGHT
    assert coordinator.state is V2ModeState.TASK_RUNNING
    assert coordinator.finish_task(4.0).action == "mode_ended"
    assert coordinator.state is V2ModeState.IDLE


def test_end_while_active_runs_high_five_immediately() -> None:
    coordinator = V2SessionCoordinator()
    coordinator.enter_mode()
    decision = coordinator.request_end()
    assert decision.action == "run_task"
    assert decision.task is V2Task.HIGH_FIVE_RIGHT


def test_support_watch_is_a_peer_task() -> None:
    coordinator = V2SessionCoordinator()
    coordinator.enter_mode()
    decision = coordinator.request_task(
        V2Task.SUPPORT_WATCH, TriggerSource.VISUAL, 5.0, "stationary-1"
    )
    assert decision.action == "run_task"
    assert decision.task is V2Task.SUPPORT_WATCH


def test_seated_countdown_is_separate_from_visual_support() -> None:
    coordinator = V2SessionCoordinator()
    coordinator.enter_mode()
    decision = coordinator.request_task(
        V2Task.SEATED_COUNTDOWN, TriggerSource.VOICE, 5.0
    )
    assert decision.action == "run_task"
    assert decision.task is V2Task.SEATED_COUNTDOWN
