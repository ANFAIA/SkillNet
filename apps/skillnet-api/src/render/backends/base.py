"""The render backend seam of §5.4.

Only one dialect ships in this PR (``openui``). The ``Protocol`` and the registry
exist so a second one is a new file plus one registry entry, and so nothing outside
``src/render/backends/`` ever touches dialect text.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.render.kit import UIKit
from src.render.spec import UISpec


@runtime_checkable
class RenderBackend(Protocol):
    """A dialect the LLM can emit and this process can parse."""

    name: str

    def prompt_fragment(self, kit: UIKit) -> str:
        """System-prompt fragment teaching the dialect and the catalogue.

        Generated from the kit — never written by hand twice.
        """
        ...

    def parse(self, raw: str) -> UISpec:
        """Parse a complete program. Raises ``RenderParseError``."""
        ...

    def parse_partial(self, raw: str) -> UISpec:
        """Tolerant parse of incomplete output (streaming).

        Drops the last line when it is half-written. Never raises.
        """
        ...

    def serialize(self, spec: UISpec) -> str:
        """Inverse of ``parse``. For round-trip tests and for fixtures."""
        ...


__all__ = ["RenderBackend"]
