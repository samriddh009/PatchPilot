"""Tests for bounded recovery manager and diagnostic formulation."""

import pytest
from patchpilot.recovery.manager import BoundedRecoveryManager


def test_recovery_budget_strictly_bounded():
    assert BoundedRecoveryManager.can_recover(current_attempts=0) is True
    assert BoundedRecoveryManager.can_recover(current_attempts=1) is False
    assert BoundedRecoveryManager.can_recover(current_attempts=2) is False


def test_format_syntax_error_diagnostic():
    diag = BoundedRecoveryManager.format_syntax_error_diagnostic(["Hunk mismatch line 10", "File not found"])
    assert "Hunk mismatch line 10" in diag
    assert "File not found" in diag
    assert "hunk line numbers" in diag


def test_format_regression_diagnostic():
    diag = BoundedRecoveryManager.format_regression_diagnostic(
        target_test="tests/test_tax.py::test_exemption",
        regression_stdout="FAILED tests/test_tax.py::test_vat - AssertionError: expected 120 got 100",
    )
    assert "tests/test_tax.py::test_exemption" in diag
    assert "AssertionError" in diag
    assert "WITHOUT breaking other functionality" in diag
