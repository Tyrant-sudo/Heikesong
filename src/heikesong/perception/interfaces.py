"""Replaceable V1 perception interfaces.

Concrete CV models belong behind these ports so that tests can use recordings
or fakes without changing the behavior layer.
"""

from __future__ import annotations

from typing import Protocol

from heikesong.core.models import MatObservation, PoseObservation, UserObservation


class YogaMatDetector(Protocol):
    def detect(self, frame: object) -> MatObservation: ...


class UserLocator(Protocol):
    def locate(self, frame: object, mat: MatObservation | None) -> UserObservation: ...


class DownwardDogDetector(Protocol):
    def detect(self, frame: object) -> PoseObservation: ...
