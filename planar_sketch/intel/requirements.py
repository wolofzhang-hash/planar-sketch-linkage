from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Requirement:
    """A minimal schema for the user's design intent.

    Keep this small and stable: the UI collects these fields, and future
    recommenders/synthesis backends can use them.
    """

    # High-level task
    task: str  # e.g. "door", "path", "function", "rigid_guidance"

    # Optional mechanism family filter (kept intentionally simple).
    # - "any": allow all concepts
    # - "cam": cam / follower concepts
    # - "4bar": four-bar family
    # - "6bar": six-bar family
    # - "slider_rail": slider / rail / slotted-link family
    mechanism_family: str = "any"

    # Optional hints
    open_angle_deg: float | None = None
    prefer_fewer_links: bool = True
    prefer_compact: bool = True
    notes: str = ""
