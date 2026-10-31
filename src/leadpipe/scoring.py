"""Deterministic scoring model (SPEC Section 2.4). Pure logic, no I/O.

The total is always computed here, server-side. A total supplied by a
caller is never accepted: the input model forbids unknown fields and this
module validates the eight components exhaustively.
"""

from __future__ import annotations

from . import errors
from .models import Band

# field -> (min, max), in sheet column order
COMPONENT_RANGES: dict[str, tuple[int, int]] = {
    "problem": (0, 20),
    "fit": (0, 20),
    "value": (0, 15),
    "size": (0, 10),
    "pay": (0, 10),
    "access": (0, 10),
    "urgency": (0, 10),
    "activity": (0, 5),
}

COMPONENT_FIELDS = tuple(COMPONENT_RANGES.keys())


def validate_components(scores: object) -> dict[str, int]:
    """Validate the eight component judgements; return them as ints."""
    if not isinstance(scores, dict):
        raise errors.validation(
            "scores must be an object of eight components", "scores"
        )
    unknown = sorted(set(scores) - set(COMPONENT_RANGES))
    if unknown:
        raise errors.validation(
            f"Unknown score component(s): {', '.join(unknown)}", "scores"
        )
    missing = [f for f in COMPONENT_RANGES if f not in scores]
    if missing:
        raise errors.validation(
            f"Missing score component(s): {', '.join(missing)}", "scores"
        )
    validated: dict[str, int] = {}
    for field, (low, high) in COMPONENT_RANGES.items():
        value = scores[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise errors.validation(
                f"Score component {field!r} must be an integer", f"scores.{field}"
            )
        if value < low or value > high:
            raise errors.validation(
                f"Score component {field!r} must be between {low} and {high}",
                f"scores.{field}",
            )
        validated[field] = value
    return validated


def compute_total(components: dict[str, int]) -> int:
    return sum(components[f] for f in COMPONENT_FIELDS)


def band_for(total: int) -> Band:
    """HOT 80-100, WARM 65-79, NURTURE 50-64, below 50 is LOW."""
    if total >= 80:
        return Band.HOT
    if total >= 65:
        return Band.WARM
    if total >= 50:
        return Band.NURTURE
    return Band.LOW


def score(scores: object) -> tuple[dict[str, int], int, Band]:
    """Validate, total and band in one call."""
    components = validate_components(scores)
    total = compute_total(components)
    return components, total, band_for(total)


def components_from_row(row: dict) -> dict[str, int] | None:
    """Rebuild components from a stored lead row, or None if unscored.

    Used so a hand-edited Sheet can never produce an inconsistent total:
    totals and bands are recomputed from components on every read.
    """
    components: dict[str, int] = {}
    for field in COMPONENT_FIELDS:
        raw = row.get(f"score_{field}", "")
        if raw in ("", None):
            return None
        try:
            components[field] = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
    return components
