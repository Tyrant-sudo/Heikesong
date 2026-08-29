"""Two-stage offline voice command routing for Vbot interactions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    keywords: tuple[str, ...]
    cooldown_seconds: float = 15.0


@dataclass(frozen=True)
class CommandDecision:
    action: str
    command: str | None = None
    reason: str = ""


class VoiceCommandRouter:
    """Requires a wake keyword before accepting one registered command."""

    def __init__(
        self,
        specs: tuple[CommandSpec, ...],
        wake_keywords: tuple[str, ...] = ("佳佳", "伽伽", "Jiajia", "jiajia"),
        arm_seconds: float = 10.0,
        prewake_grace_seconds: float = 6.0,
    ) -> None:
        if arm_seconds <= 0 or prewake_grace_seconds < 0:
            raise ValueError("command window durations are invalid")
        self.arm_seconds = arm_seconds
        self.prewake_grace_seconds = prewake_grace_seconds
        self.wake_keywords = frozenset(wake_keywords)
        self.armed_until_s: float | None = None
        self.pending_prewake: tuple[CommandSpec, float] | None = None
        self.cooldown_until_s: dict[str, float] = {}
        self._commands: dict[str, CommandSpec] = {}
        names: set[str] = set()
        for spec in specs:
            if not spec.name or spec.name in names:
                raise ValueError(f"invalid or duplicate command name: {spec.name!r}")
            if spec.cooldown_seconds < 0 or not spec.keywords:
                raise ValueError(f"invalid command spec: {spec.name}")
            names.add(spec.name)
            for keyword in spec.keywords:
                if not keyword or keyword in self._commands:
                    raise ValueError(f"duplicate or empty keyword: {keyword!r}")
                self._commands[keyword] = spec

    def handle(
        self,
        keyword: str,
        now_s: float,
        allow_without_wake: bool = False,
    ) -> CommandDecision:
        if keyword in self.wake_keywords:
            self.armed_until_s = now_s + self.arm_seconds
            if self.pending_prewake is not None:
                spec, detected_at_s = self.pending_prewake
                self.pending_prewake = None
                if (
                    now_s - detected_at_s <= self.prewake_grace_seconds
                    and now_s >= self.cooldown_until_s.get(spec.name, 0.0)
                ):
                    self.armed_until_s = None
                    self.cooldown_until_s[spec.name] = (
                        now_s + spec.cooldown_seconds
                    )
                    return CommandDecision("execute_after_wake", spec.name)
            return CommandDecision("wake_ack", reason="command window armed")

        spec = self._commands.get(keyword)
        if spec is None:
            return CommandDecision("ignored", reason="unregistered keyword")
        if allow_without_wake:
            if now_s < self.cooldown_until_s.get(spec.name, 0.0):
                return CommandDecision(
                    "ignored", spec.name, "command cooldown is active"
                )
            self.armed_until_s = None
            self.pending_prewake = None
            self.cooldown_until_s[spec.name] = now_s + spec.cooldown_seconds
            return CommandDecision("execute", spec.name)
        if self.armed_until_s is None or now_s > self.armed_until_s:
            self.armed_until_s = None
            self.pending_prewake = (spec, now_s)
            return CommandDecision(
                "ignored", spec.name, "waiting briefly for wake keyword"
            )
        if now_s < self.cooldown_until_s.get(spec.name, 0.0):
            return CommandDecision("ignored", spec.name, "command cooldown is active")

        self.armed_until_s = None
        self.cooldown_until_s[spec.name] = now_s + spec.cooldown_seconds
        return CommandDecision("execute", spec.name)

    def expire(self, now_s: float) -> bool:
        if (
            self.pending_prewake is not None
            and now_s - self.pending_prewake[1] > self.prewake_grace_seconds
        ):
            self.pending_prewake = None
        if self.armed_until_s is None or now_s <= self.armed_until_s:
            return False
        self.armed_until_s = None
        return True


def v1_command_specs() -> tuple[CommandSpec, ...]:
    return (
        CommandSpec("yoga_start", ("瑜伽功能", "瑜伽模式")),
        CommandSpec("yoga_end", ("结束啦",), cooldown_seconds=0.0),
        CommandSpec("downward_dog", ("下犬式",), cooldown_seconds=5.0),
        CommandSpec("push_up", ("俯卧撑",), cooldown_seconds=5.0),
        CommandSpec(
            "lay_down_and_watch",
            ("趴下看人", "趴下看我", "坐下看人", "坐下看我"),
            cooldown_seconds=30.0,
        ),
        CommandSpec("take_photo", ("拍照",), cooldown_seconds=5.0),
        CommandSpec(
            "countdown_10s",
            ("倒计时", "十秒倒计时", "开始倒数"),
            cooldown_seconds=5.0,
        ),
        CommandSpec("person_orbit", ("绕圈",), cooldown_seconds=10.0),
    )
