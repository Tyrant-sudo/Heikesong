import unittest

from heikesong.behavior.voice_command_router import VoiceCommandRouter, v1_command_specs


class VoiceCommandRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = VoiceCommandRouter(v1_command_specs(), arm_seconds=10.0)

    def test_wake_then_command_executes_and_consumes_window(self) -> None:
        self.assertEqual("wake_ack", self.router.handle("佳佳", 10.0).action)
        decision = self.router.handle("下犬式", 11.0)
        self.assertEqual(("execute", "downward_dog"), (decision.action, decision.command))
        self.assertEqual("ignored", self.router.handle("拍照", 12.0).action)

    def test_command_requires_unexpired_wake_window(self) -> None:
        self.router.handle("伽伽", 2.0)
        decision = self.router.handle("俯卧撑", 12.1)
        self.assertEqual("waiting briefly for wake keyword", decision.reason)

    def test_aliases_route_to_lay_down_and_watch(self) -> None:
        for index, keyword in enumerate(("趴下看人", "趴下看我", "坐下看人", "坐下看我")):
            now = index * 40.0
            self.router.handle("佳佳", now)
            decision = self.router.handle(keyword, now + 1.0)
            self.assertEqual("lay_down_and_watch", decision.command)

    def test_cooldown_is_per_command(self) -> None:
        self.router.handle("佳佳", 0.0)
        self.router.handle("拍照", 1.0)
        self.router.handle("佳佳", 2.0)
        self.assertEqual("ignored", self.router.handle("拍照", 3.0).action)
        self.router.handle("佳佳", 4.0)
        self.assertEqual("execute", self.router.handle("下犬式", 5.0).action)

    def test_expire_reports_transition_once(self) -> None:
        self.router.handle("佳佳", 3.0)
        self.assertFalse(self.router.expire(13.0))
        self.assertTrue(self.router.expire(13.1))
        self.assertFalse(self.router.expire(14.0))

    def test_command_detected_just_before_wake_executes_after_ack(self) -> None:
        early = self.router.handle("拍照", 20.0)
        self.assertEqual("waiting briefly for wake keyword", early.reason)
        decision = self.router.handle("佳佳", 25.0)
        self.assertEqual(
            ("execute_after_wake", "take_photo"),
            (decision.action, decision.command),
        )

    def test_stale_prewake_command_is_not_executed(self) -> None:
        self.router.handle("拍照", 20.0)
        decision = self.router.handle("佳佳", 26.1)
        self.assertEqual("wake_ack", decision.action)

    def test_countdown_aliases_route_to_ten_second_countdown(self) -> None:
        for index, keyword in enumerate(("倒计时", "十秒倒计时")):
            now = index * 10.0
            self.router.handle("佳佳", now)
            decision = self.router.handle(keyword, now + 1.0)
            self.assertEqual(
                ("execute", "countdown_10s"),
                (decision.action, decision.command),
            )

    def test_yoga_mode_alias_is_backward_compatible(self) -> None:
        for index, keyword in enumerate(("瑜伽功能", "瑜伽模式")):
            now = index * 20.0
            self.router.handle("佳佳", now)
            decision = self.router.handle(keyword, now + 1.0)
            self.assertEqual(("execute", "yoga_start"), (decision.action, decision.command))

    def test_commands_can_skip_wake_inside_active_mode(self) -> None:
        decision = self.router.handle("下犬式", 10.0, allow_without_wake=True)
        self.assertEqual(("execute", "downward_dog"), (decision.action, decision.command))

    def test_pose_voice_cooldown_is_short_for_demo_retries(self) -> None:
        first = self.router.handle("俯卧撑", 10.0, allow_without_wake=True)
        blocked = self.router.handle("俯卧撑", 14.9, allow_without_wake=True)
        retried = self.router.handle("俯卧撑", 15.0, allow_without_wake=True)
        self.assertEqual("execute", first.action)
        self.assertEqual("ignored", blocked.action)
        self.assertEqual("execute", retried.action)

    def test_end_command_is_registered(self) -> None:
        decision = self.router.handle("结束啦", 10.0, allow_without_wake=True)
        self.assertEqual(("execute", "yoga_end"), (decision.action, decision.command))

    def test_start_countdown_alias_runs_countdown_task(self) -> None:
        decision = self.router.handle("开始倒数", 10.0, allow_without_wake=True)
        self.assertEqual(
            ("execute", "countdown_10s"),
            (decision.action, decision.command),
        )

    def test_orbit_command_is_registered(self) -> None:
        decision = self.router.handle("绕圈", 10.0, allow_without_wake=True)
        self.assertEqual(
            ("execute", "person_orbit"),
            (decision.action, decision.command),
        )


if __name__ == "__main__":
    unittest.main()
