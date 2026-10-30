"""Tests for deterministic verification engine and ground-truth matrix."""

import pytest
from patchpilot.schemas.enums import FailureClassification, VerificationOutcome
from patchpilot.test_runner.runner import TestRunResult
from patchpilot.verifier.engine import DeterministicVerifier


def make_test_result(
    exit_code: int,
    passed: bool,
    classification: FailureClassification = FailureClassification.NONE,
    tests_run: int = 1,
    tests_passed: int = 1,
    tests_failed: int = 0,
    timed_out: bool = False,
) -> TestRunResult:
    return TestRunResult(
        exit_code=exit_code,
        passed=passed,
        failure_classification=classification,
        stdout="Test output",
        stderr="",
        tests_run=tests_run,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        duration_ms=100,
        timed_out=timed_out,
    )


def test_verifier_all_pass_yields_verified():
    baseline = make_test_result(
        exit_code=1,
        passed=False,
        classification=FailureClassification.ASSERTION_FAILURE,
        tests_run=1,
        tests_passed=0,
        tests_failed=1,
    )
    targeted = make_test_result(
        exit_code=0,
        passed=True,
        classification=FailureClassification.NONE,
        tests_run=1,
        tests_passed=1,
        tests_failed=0,
    )
    regression = make_test_result(
        exit_code=0,
        passed=True,
        classification=FailureClassification.NONE,
        tests_run=5,
        tests_passed=5,
        tests_failed=0,
    )
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1,1 +1,1 @@\n-old\n+new"

    verdict = DeterministicVerifier.verify(
        baseline_result=baseline,
        targeted_result=targeted,
        regression_result=regression,
        diff_text=diff,
        source_repo_unmodified=True,
    )

    assert verdict.outcome == VerificationOutcome.VERIFIED
    assert verdict.baseline_reproduced is True
    assert verdict.targeted_pass is True
    assert verdict.regression_pass is True
    assert verdict.diff_valid is True
    assert "Verified" in verdict.verdict_explanation


def test_verifier_fails_if_baseline_is_not_assertion():
    # If baseline failed due to import error or runner crash, bug is NOT reproduced
    baseline = make_test_result(
        exit_code=2,
        passed=False,
        classification=FailureClassification.IMPORT_ERROR,
    )
    targeted = make_test_result(exit_code=0, passed=True)
    regression = make_test_result(exit_code=0, passed=True)
    diff = "--- a/f\n+++ b/f\n"

    verdict = DeterministicVerifier.verify(
        baseline_result=baseline,
        targeted_result=targeted,
        regression_result=regression,
        diff_text=diff,
        source_repo_unmodified=True,
    )

    assert verdict.outcome == VerificationOutcome.UNRESOLVED
    assert verdict.baseline_reproduced is False
    assert "Baseline not reproduced" in verdict.verdict_explanation


def test_verifier_fails_if_regression_broken():
    baseline = make_test_result(
        exit_code=1,
        passed=False,
        classification=FailureClassification.ASSERTION_FAILURE,
    )
    targeted = make_test_result(exit_code=0, passed=True)
    # Regression tests failed
    regression = make_test_result(
        exit_code=1,
        passed=False,
        classification=FailureClassification.ASSERTION_FAILURE,
        tests_failed=1,
    )
    diff = "--- a/f\n+++ b/f\n@@ -1 +1 @@"

    verdict = DeterministicVerifier.verify(
        baseline_result=baseline,
        targeted_result=targeted,
        regression_result=regression,
        diff_text=diff,
        source_repo_unmodified=True,
    )

    assert verdict.outcome == VerificationOutcome.UNRESOLVED
    assert verdict.regression_pass is False


def test_verifier_fails_if_source_repo_tampered():
    baseline = make_test_result(
        exit_code=1,
        passed=False,
        classification=FailureClassification.ASSERTION_FAILURE,
    )
    targeted = make_test_result(exit_code=0, passed=True)
    regression = make_test_result(exit_code=0, passed=True)
    diff = "--- a/f\n+++ b/f\n@@ -1 +1 @@"

    verdict = DeterministicVerifier.verify(
        baseline_result=baseline,
        targeted_result=targeted,
        regression_result=regression,
        diff_text=diff,
        source_repo_unmodified=False,  # Tampered!
    )

    assert verdict.outcome == VerificationOutcome.UNRESOLVED
    assert "Source repository integrity check failed" in verdict.verdict_explanation
