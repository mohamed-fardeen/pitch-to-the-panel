"""
Typed persona catalog — the runtime representation of a persona YAML.

This module defines:

- :class:`OceanProfile` — Big-Five personality traits.
- :class:`Persona` — a single agent persona.
- :class:`PersonaCatalog` — the full catalog of all loaded personas.

These are simple dataclasses, not Pydantic models. We use dataclasses
because:
1. The YAML loader already validates the schema (raises on bad data).
2. We don't need serialization — the API layer returns the dataclass
   as a plain dict.
3. Pydantic adds dependency weight we don't need for a config loader.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OceanProfile:
    """Big-Five personality traits. Each value is 0..1."""

    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5

    def to_dict(self) -> dict[str, float]:
        return {
            "openness": self.openness,
            "conscientiousness": self.conscientiousness,
            "extraversion": self.extraversion,
            "agreeableness": self.agreeableness,
            "neuroticism": self.neuroticism,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> OceanProfile:
        if data is None:
            return cls()
        return cls(
            openness=_clamp(data.get("openness", 0.5)),
            conscientiousness=_clamp(data.get("conscientiousness", 0.5)),
            extraversion=_clamp(data.get("extraversion", 0.5)),
            agreeableness=_clamp(data.get("agreeableness", 0.5)),
            neuroticism=_clamp(data.get("neuroticism", 0.5)),
        )


@dataclass
class Persona:
    """A single agent persona."""

    id: str
    name: str
    role: str
    system_prompt: str
    goal: str = ""
    ocean: OceanProfile = field(default_factory=OceanProfile)
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "system_prompt": self.system_prompt,
            "goal": self.goal,
            "ocean": self.ocean.to_dict(),
            "enabled": self.enabled,
            "config": self.config,
        }

    @property
    def is_hidden(self) -> bool:
        """True if this persona should be hidden from the panel UI."""
        return bool(self.config.get("hidden", False))

    @property
    def color(self) -> str:
        return self.config.get("color", "#64748B")

    @property
    def avatar(self) -> str:
        return self.config.get("avatar", "🧑")

    @property
    def sort_order(self) -> int:
        return int(self.config.get("sort_order", 99))


@dataclass
class PersonaCatalog:
    """The full catalog of all loaded personas."""

    personas: list[Persona] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Build an index for O(1) lookup by id
        self._by_id: dict[str, Persona] = {p.id: p for p in self.personas}

    def get(self, persona_id: str) -> Persona | None:
        return self._by_id.get(persona_id)

    def __contains__(self, persona_id: str) -> bool:
        return persona_id in self._by_id

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.personas)

    def __len__(self) -> int:
        return len(self.personas)

    def visible(self) -> list[Persona]:
        """Return enabled, non-hidden personas (the ones to show in the panel UI)."""
        return [p for p in self.personas if p.enabled and not p.is_hidden]

    def hidden(self) -> list[Persona]:
        """Return enabled but hidden personas (e.g. the strategist)."""
        return [p for p in self.personas if p.enabled and p.is_hidden]

    def to_dict(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.personas]


def _clamp(value: Any) -> float:
    """Clamp a YAML value to 0..1. Defaults to 0.5 on parse failure."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


__all__ = ["OceanProfile", "Persona", "PersonaCatalog"]
