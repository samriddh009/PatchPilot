"""Deterministic verification engine enforcing mathematical ground truth."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from patchpilot.schemas.enums import FailureClassification, VerificationOutcome
from patchpilot.test_runner.runner import TestRunResult


@dataclass
class VerificationVerdict:
    outcome: VerificationOutcome
    baseline_reproduced: bool
    baseline_exit_code: Optional[int]
    baseline_failure_classification: FailureClassification
    baseline_log_snippet: str
    targeted_pass: bool
    targeted_exit_code: Optional[int]
    regression_pass: bool
    regression_exit_code: Optional[int]
    total_tests_run: int
    total_tests_passed: int
    diff_valid: bool
    evidence_summary: Dict[str, Any]
    verdict_explanation: str


class DeterministicVerifier:
    """Sole truth authority for deciding repair success."""

    @classmethod
    def verify(
        cls,
        baseline_result: TestRunResult,
        targeted_result: Optional[TestRunResult],
        regression_result: Optional[TestRunResult],
        diff_text: str,
        source_repo_unmodified: bool,
    ) -> VerificationVerdict:
        # 1. Baseline failure verification
        baseline_reproduced = (
            baseline_result.exit_code != 0
            and baseline_result.failure_classification == FailureClassification.ASSERTION_FAILURE
            and not baseline_result.timed_out
        )

        baseline_snippet = (
            baseline_result.stdout.strip().splitlines()[-3:]
            if baseline_result.stdout
            else (baseline_result.stderr.strip().splitlines()[-3:] if baseline_result.stderr else [])
        )
        snippet_text = "\n".join(baseline_snippet)

        diff_valid = bool(diff_text and diff_text.strip() and len(diff_text.strip().splitlines()) >= 2)

        targeted_pass = bool(
            targeted_result
            and targeted_result.exit_code == 0
            and targeted_result.passed
            and not targeted_result.timed_out
        )

        regression_pass = bool(
            regression_result
            and regression_result.exit_code == 0
            and regression_result.passed
            and regression_result.tests_failed == 0
            and not regression_result.timed_out
        )

        total_run = (
            (targeted_result.tests_run if targeted_result else 0)
            + (regression_result.tests_run if regression_result else 0)
        )
        total_passed = (
            (targeted_result.tests_passed if targeted_result else 0)
            + (regression_result.tests_passed if regression_result else 0)
        )

        # Evaluate complete matrix
        is_verified = (
            baseline_reproduced
            and targeted_pass
            and regression_pass
            and diff_valid
            and source_repo_unmodified
        )

        if is_verified:
            outcome = VerificationOutcome.VERIFIED
            explanation = (
                "Verified: Baseline domain failure reproduced (exit code 1, assertion failure). "
                "Post-patch targeted test and regression test suite passed cleanly (exit code 0). "
                "Non-empty diff applied inside isolated workspace; source repo 100% untouched."
            )
        else:
            outcome = VerificationOutcome.UNRESOLVED
            reasons = []
            if not baseline_reproduced:
                reasons.append(f"Baseline not reproduced as assertion failure (class={baseline_result.failure_classification.value})")
            if not targeted_pass:
                reasons.append("Post-patch targeted test failed or was not executed")
            if not regression_pass:
                reasons.append("Post-patch regression suite failed or timed out")
            if not diff_valid:
                reasons.append("Diff content was empty or invalid")
            if not source_repo_unmodified:
                reasons.append("Source repository integrity check failed")
            explanation = f"Unresolved: {'; '.join(reasons)}."

        evidence_summary = {
            "baseline_exit_code": baseline_result.exit_code,
            "baseline_classification": baseline_result.failure_classification.value,
            "targeted_exit_code": targeted_result.exit_code if targeted_result else None,
            "regression_exit_code": regression_result.exit_code if regression_result else None,
            "diff_valid": diff_valid,
            "source_repo_unmodified": source_repo_unmodified,
            "explanation": explanation,
        }

        return VerificationVerdict(
            outcome=outcome,
            baseline_reproduced=baseline_reproduced,
            baseline_exit_code=baseline_result.exit_code,
            baseline_failure_classification=baseline_result.failure_classification,
            baseline_log_snippet=snippet_text,
            targeted_pass=targeted_pass,
            targeted_exit_code=targeted_result.exit_code if targeted_result else None,
            regression_pass=regression_pass,
            regression_exit_code=regression_result.exit_code if regression_result else None,
            total_tests_run=total_run,
            total_tests_passed=total_passed,
            diff_valid=diff_valid,
            evidence_summary=evidence_summary,
            verdict_explanation=explanation,
        )
