import unittest

from heikesong.behavior.yoga_interactions import YogaInteractionController


class RecordingRobot:
    def __init__(self, calls: list[tuple[str, str, str | None]]) -> None:
        self.calls = calls

    def perform_downward_dog_combo(self, correlation_id: str) -> None:
        self.calls.append(("downward_dog", correlation_id, None))

    def perform_push_up(self, correlation_id: str) -> None:
        self.calls.append(("push_up", correlation_id, None))

    def sit_and_watch_user(self, correlation_id: str) -> None:
        self.calls.append(("sit_and_watch", correlation_id, None))

    def lay_down_and_watch_user(self, correlation_id: str) -> None:
        self.calls.append(("lay_down_and_watch", correlation_id, None))

    def celebrate_happy(self, correlation_id: str) -> None:
        self.calls.append(("happy", correlation_id, None))

    def stop_motion(self, reason: str) -> None:
        self.calls.append(("stop", reason, None))


class RecordingDisplay:
    def __init__(self, calls: list[tuple[str, str, str | None]]) -> None:
        self.calls = calls

    def blink_then_flash(self, correlation_id: str) -> None:
        self.calls.append(("blink_flash", correlation_id, None))


class RecordingVoice:
    def __init__(self, calls: list[tuple[str, str, str | None]]) -> None:
        self.calls = calls

    def speak(self, text: str, correlation_id: str) -> None:
        self.calls.append(("speak", correlation_id, text))


class FailingHappyRobot(RecordingRobot):
    def celebrate_happy(self, correlation_id: str) -> None:
        raise RuntimeError("happy action rejected")


class YogaInteractionControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.controller = YogaInteractionController(
            RecordingRobot(self.calls),
            RecordingDisplay(self.calls),
            RecordingVoice(self.calls),
        )

    def test_routes_required_motion_actions_with_correlation_id(self) -> None:
        self.controller.perform_downward_dog("pose-1")
        self.controller.perform_push_up("pose-2")
        self.controller.sit_and_watch_user("pose-3")
        self.controller.lay_down_and_watch_user("pose-4")

        self.assertEqual(
            [
                ("downward_dog", "pose-1", None),
                ("push_up", "pose-2", None),
                ("sit_and_watch", "pose-3", None),
                ("lay_down_and_watch", "pose-4", None),
            ],
            self.calls,
        )

    def test_yoga_keyword_runs_blink_happy_and_spoken_feedback(self) -> None:
        handled = self.controller.handle_voice_command(
            " 瑜伽功能！ ", "session-1"
        )

        self.assertTrue(handled)
        self.assertEqual(
            [
                ("blink_flash", "session-1", None),
                ("happy", "session-1", None),
                ("speak", "session-1", "瑜伽开始了"),
            ],
            self.calls,
        )

    def test_unrelated_command_has_no_side_effects(self) -> None:
        self.assertFalse(self.controller.handle_voice_command("开始运动", "session-2"))
        self.assertEqual([], self.calls)

    def test_keyword_matches_inside_a_longer_recognition_result(self) -> None:
        self.assertTrue(
            self.controller.handle_voice_command(
                "我们现在开始做瑜伽吧", "session-keyword"
            )
        )
        self.assertEqual("blink_flash", self.calls[0][0])

    def test_jiajia_alias_runs_the_same_start_feedback(self) -> None:
        self.assertTrue(
            self.controller.handle_voice_command("伽伽", "session-alias")
        )
        self.assertEqual(
            ["blink_flash", "happy", "speak"],
            [call[0] for call in self.calls],
        )

    def test_duplicate_correlation_id_does_not_repeat_effects(self) -> None:
        self.assertTrue(
            self.controller.handle_voice_command("机器狗瑜伽功能测试", "session-4")
        )
        self.assertTrue(
            self.controller.handle_voice_command("机器狗瑜伽功能测试", "session-4")
        )
        self.assertTrue(self.controller.perform_push_up("pose-4"))
        self.assertFalse(self.controller.perform_push_up("pose-4"))

        self.assertEqual(1, sum(call[0] == "blink_flash" for call in self.calls))
        self.assertEqual(1, sum(call[0] == "happy" for call in self.calls))
        self.assertEqual(1, sum(call[0] == "speak" for call in self.calls))
        self.assertEqual(1, sum(call[0] == "push_up" for call in self.calls))

    def test_rejects_empty_correlation_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "correlation_id"):
            self.controller.perform_downward_dog("")

    def test_failed_happy_action_does_not_announce_success(self) -> None:
        controller = YogaInteractionController(
            FailingHappyRobot(self.calls),
            RecordingDisplay(self.calls),
            RecordingVoice(self.calls),
        )

        with self.assertRaisesRegex(RuntimeError, "happy action rejected"):
            controller.handle_voice_command("机器狗瑜伽功能测试", "session-3")

        self.assertEqual([("blink_flash", "session-3", None)], self.calls)


if __name__ == "__main__":
    unittest.main()
