"""Behavior ports for mat orbiting and user-direction following."""

from __future__ import annotations

from typing import Protocol

from heikesong.core.models import MatObservation, UserObservation


class MatOrbitController(Protocol):
    def start(self, mat: MatObservation) -> None: ...

    def update(self, mat: MatObservation) -> None: ...

    def cancel(self, reason: str) -> None: ...


class UserDirectionFollower(Protocol):
    def start(self, user: UserObservation) -> None: ...

    def update(self, user: UserObservation) -> None: ...

    def cancel(self, reason: str) -> None: ...
