"""Pipeline stages and the validated transition map (SPEC Section 2.5.1).

Pure logic, no I/O. Any pair not listed in TRANSITIONS is rejected.
"""

from __future__ import annotations

from . import errors
from .models import Stage

TRANSITIONS: dict[Stage, frozenset[Stage]] = {
    Stage.NEW: frozenset({Stage.CONTACTED, Stage.QUALIFIED, Stage.NURTURE, Stage.LOST}),
    Stage.CONTACTED: frozenset(
        {Stage.QUALIFIED, Stage.NURTURE, Stage.DISCOVERY, Stage.LOST}
    ),
    Stage.QUALIFIED: frozenset(
        {Stage.DISCOVERY, Stage.BOOKED, Stage.NURTURE, Stage.LOST}
    ),
    Stage.NURTURE: frozenset({Stage.CONTACTED, Stage.QUALIFIED, Stage.LOST}),
    Stage.DISCOVERY: frozenset(
        {Stage.BOOKED, Stage.PROPOSAL, Stage.NURTURE, Stage.LOST}
    ),
    Stage.BOOKED: frozenset({Stage.DISCOVERY, Stage.PROPOSAL, Stage.LOST}),
    Stage.PROPOSAL: frozenset({Stage.NEGOTIATION, Stage.BOOKED, Stage.LOST}),
    Stage.NEGOTIATION: frozenset({Stage.WON, Stage.PROPOSAL, Stage.LOST}),
    Stage.WON: frozenset(),
    Stage.LOST: frozenset({Stage.NURTURE}),
}


def parse_stage(raw: str) -> Stage:
    try:
        return Stage(raw)
    except ValueError:
        raise errors.validation(f"Unknown stage: {raw!r}", "stage") from None


def can_transition(from_stage: Stage, to_stage: Stage) -> bool:
    """Same-stage moves are a successful no-op, never an error."""
    if from_stage == to_stage:
        return True
    return to_stage in TRANSITIONS[from_stage]


def validate_transition(from_stage: Stage, to_stage: Stage) -> None:
    if not can_transition(from_stage, to_stage):
        raise LeadPipeTransitionError(from_stage, to_stage)


class LeadPipeTransitionError(errors.LeadPipeError):
    def __init__(self, from_stage: Stage, to_stage: Stage) -> None:
        super().__init__(
            errors.STAGE_TRANSITION_INVALID,
            f"Stage transition {from_stage.value} -> {to_stage.value} is not allowed.",
            "stage",
        )
