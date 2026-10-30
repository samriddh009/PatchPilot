"""State machine validator enforcing deterministic linear transitions."""

from typing import Dict, Set

from patchpilot.schemas.enums import RepairStatus


class InvalidStateTransitionException(Exception):
    """Raised when an illegal state transition is attempted."""


class RepairStateMachine:
    """Enforces deterministic lifecycle transitions for software repairs."""

    # Valid transitions map
    VALID_TRANSITIONS: Dict[RepairStatus, Set[RepairStatus]] = {
        RepairStatus.QUEUED: {RepairStatus.INSPECTING, RepairStatus.FAILED, RepairStatus.CANCELLED},
        RepairStatus.INSPECTING: {RepairStatus.REPRODUCING, RepairStatus.FAILED, RepairStatus.CANCELLED},
        RepairStatus.REPRODUCING: {RepairStatus.PATCHING, RepairStatus.UNRESOLVED, RepairStatus.FAILED, RepairStatus.CANCELLED},
        RepairStatus.PATCHING: {RepairStatus.TESTING, RepairStatus.RECOVERING, RepairStatus.UNRESOLVED, RepairStatus.FAILED, RepairStatus.CANCELLED},
        RepairStatus.TESTING: {RepairStatus.VERIFYING, RepairStatus.RECOVERING, RepairStatus.UNRESOLVED, RepairStatus.FAILED, RepairStatus.CANCELLED},
        RepairStatus.VERIFYING: {
            RepairStatus.AWAITING_APPROVAL,
            RepairStatus.VERIFIED,
            RepairStatus.RECOVERING,
            RepairStatus.UNRESOLVED,
            RepairStatus.FAILED,
            RepairStatus.CANCELLED,
        },
        RepairStatus.RECOVERING: {RepairStatus.PATCHING, RepairStatus.UNRESOLVED, RepairStatus.FAILED, RepairStatus.CANCELLED},
        RepairStatus.AWAITING_APPROVAL: {
            RepairStatus.EXPORTING,
            RepairStatus.VERIFIED,
            RepairStatus.UNRESOLVED,
            RepairStatus.FAILED,
            RepairStatus.CANCELLED,
        },
        RepairStatus.EXPORTING: {RepairStatus.VERIFIED, RepairStatus.FAILED, RepairStatus.CANCELLED},
        # Terminal states have no valid subsequent transitions
        RepairStatus.VERIFIED: set(),
        RepairStatus.UNRESOLVED: set(),
        RepairStatus.FAILED: set(),
        RepairStatus.CANCELLED: set(),
    }

    @classmethod
    def can_transition(cls, from_status: RepairStatus, to_status: RepairStatus) -> bool:
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def validate_transition(cls, from_status: RepairStatus, to_status: RepairStatus) -> None:
        if not cls.can_transition(from_status, to_status):
            raise InvalidStateTransitionException(
                f"Illegal state transition from '{from_status.value}' to '{to_status.value}'."
            )
