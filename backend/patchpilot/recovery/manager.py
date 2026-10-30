"""Bounded recovery manager enforcing max 1 retry loop with diagnostic formulation."""

from patchpilot import config
from patchpilot.schemas.enums import RepairStatus


class RecoveryBudgetExhaustedException(Exception):
    """Raised when recovery budget is exceeded."""


class BoundedRecoveryManager:
    """Manages single-attempt recovery diagnostic formulation and backtrack safety."""

    MAX_ATTEMPTS = config.MAX_RECOVERY_ATTEMPTS  # 1

    @classmethod
    def can_recover(cls, current_attempts: int) -> bool:
        """Check whether another recovery attempt is permitted."""
        return current_attempts < cls.MAX_ATTEMPTS

    @classmethod
    def format_syntax_error_diagnostic(cls, errors: list[str]) -> str:
        """Formulate feedback prompt when patch application or validation fails."""
        err_msg = "; ".join(errors)
        return (
            f"The proposed unified diff failed validation or application.\n"
            f"Errors: {err_msg}\n"
            f"Please ensure file paths exist, context lines match the target file exactly, "
            f"and hunk line numbers (@@ -start,count +start,count @@) are accurate."
        )

    @classmethod
    def format_regression_diagnostic(cls, target_test: str, regression_stdout: str) -> str:
        """Formulate feedback prompt when patch breaks regression suite."""
        lines = regression_stdout.strip().splitlines()[-10:] if regression_stdout else ["Regression tests failed."]
        summary = "\n".join(lines)
        return (
            f"The proposed patch resolved the targeted issue ({target_test}), "
            f"but introduced a regression in other tests.\n"
            f"Regression Suite Failure Summary:\n{summary}\n"
            f"Please revise your patch to fix the target test WITHOUT breaking other functionality."
        )
