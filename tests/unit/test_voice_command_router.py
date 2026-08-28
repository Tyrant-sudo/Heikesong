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


if __name__ == "__main__":
    unittest.main()
