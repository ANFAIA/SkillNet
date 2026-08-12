"""Capability ports used by Didact families without coupling them to infrastructure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PortDeclined:
    reason: str


@runtime_checkable
class EvaluationPort(Protocol):
    async def evaluate(self, definition: dict, submission: dict) -> dict | PortDeclined: ...


@runtime_checkable
class PersistencePort(Protocol):
    async def load(self) -> dict: ...
    async def save(self, state: dict) -> dict: ...


@runtime_checkable
class EventsPort(Protocol):
    async def record(self, event_type: str, payload: dict) -> None: ...


@runtime_checkable
class MediaPort(Protocol):
    async def resolve(self, media_ref: str) -> dict | PortDeclined: ...


@runtime_checkable
class SimulationPort(Protocol):
    async def transition(self, definition: dict, state: dict, action: str) -> dict | PortDeclined: ...


@runtime_checkable
class ExecutionPort(Protocol):
    async def execute(self, definition: dict, submission: dict) -> dict | PortDeclined: ...


PORT_NAMES = frozenset({"evaluation", "persistence", "events", "media", "simulation", "execution"})


class ActivityPortRegistry:
    """Explicit runtime wiring. An absent adapter is a decline, never a fake success."""

    def __init__(self, **ports: object) -> None:
        unknown = set(ports) - PORT_NAMES
        if unknown:
            raise ValueError(f"Unknown activity ports: {sorted(unknown)}")
        self._ports = dict(ports)

    def has(self, name: str) -> bool:
        return name in self._ports

    def get(self, name: str) -> object | None:
        return self._ports.get(name)

    def missing(self, required: list[str]) -> list[str]:
        return sorted(name for name in required if not self.has(name))
