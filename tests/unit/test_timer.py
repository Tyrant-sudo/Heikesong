from __future__ import annotations

import unittest

from heikesong.services.timer import SessionTimer, TimerState


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class SessionTimerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.timer = SessionTimer(self.clock)

    def test_pause_time_is_not_counted(self) -> None:
        self.timer.start(duration_s=10)
        self.clock.now = 3
        self.timer.pause()
        self.clock.now = 8
        self.timer.resume()
        self.clock.now = 10

        snapshot = self.timer.snapshot()

        self.assertEqual(snapshot.state, TimerState.RUNNING)
        self.assertEqual(snapshot.elapsed_s, 5)
        self.assertEqual(snapshot.remaining_s, 5)

    def test_countdown_finishes_at_zero(self) -> None:
        self.timer.start(duration_s=2)
        self.clock.now = 3

        snapshot = self.timer.snapshot()

        self.assertEqual(snapshot.state, TimerState.FINISHED)
        self.assertEqual(snapshot.elapsed_s, 2)
        self.assertEqual(snapshot.remaining_s, 0)

    def test_stop_freezes_elapsed_time(self) -> None:
        self.timer.start()
        self.clock.now = 4
        self.timer.stop()
        self.clock.now = 9

        snapshot = self.timer.snapshot()

        self.assertEqual(snapshot.state, TimerState.STOPPED)
        self.assertEqual(snapshot.elapsed_s, 4)

    def test_duration_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            self.timer.start(duration_s=0)


if __name__ == "__main__":
    unittest.main()
