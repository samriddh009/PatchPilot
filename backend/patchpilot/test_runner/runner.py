"""Test runner with failure classification and metrics extraction."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from patchpilot.sandbox.base import ExecutionResult, SandboxRunner
from patchpilot.schemas.enums import FailureClassification


@dataclass
class TestRunResult:
    __test__ = False
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    duration_ms: int
    timed_out: bool
    failure_classification: FailureClassification
    tests_run: int
    tests_passed: int
    tests_failed: int


class TestExecutionService:
    __test__ = False
    """Dispatches test execution through the active sandbox and parses structured evidence."""

    def __init__(self, sandbox: SandboxRunner):
        self.sandbox = sandbox

    def run_test(
        self,
        cmd: List[str],
        cwd: Path,
        timeout_seconds: int,
    ) -> TestRunResult:
        try:
            result: ExecutionResult = self.sandbox.execute(cmd, cwd, timeout_seconds)
        except PermissionError as exc:
            result = ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"[Runner Error: Permission Denied]: {exc}",
                duration_ms=0,
                timed_out=False,
                output_truncated=False,
            )
        except FileNotFoundError as exc:
            result = ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"[Runner Error: Command not found '{cmd[0] if cmd else ''}']: {exc}",
                duration_ms=0,
                timed_out=False,
                output_truncated=False,
            )
        except Exception as exc:
            result = ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=f"[Runner Error: Process launch failed]: {exc}",
                duration_ms=0,
                timed_out=False,
                output_truncated=False,
            )

        passed = (result.exit_code == 0 and not result.timed_out)

        classification = self._classify_failure(result)
        tests_run, tests_passed, tests_failed = self._parse_counts(result.stdout, passed)

        return TestRunResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            passed=passed,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            failure_classification=classification,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
        )

    @staticmethod
    def _classify_failure(res: ExecutionResult) -> FailureClassification:
        if res.timed_out:
            return FailureClassification.TIMEOUT
        if res.exit_code == 0:
            return FailureClassification.NONE

        output = f"{res.stdout}\n{res.stderr}".lower()

        # Check for process launch failure / runner crash first so it never masquerades as assertion failure
        if (
            res.exit_code in (-1, 125, 126, 127)
            or "[runner error" in output
            or "docker: error response" in output
            or "failed to start" in output
        ):
            return FailureClassification.RUNNER_CRASH

        # Check for dependency / import errors
        if "modulenotfounderror" in output or "importerror" in output or "no module named" in output:
            return FailureClassification.IMPORT_ERROR

        # Check for test collection failures
        if (
            "error collecting" in output
            or "no tests collected" in output
            or "collected 0 items" in output
            or "no tests ran" in output
            or "pytest: error:" in output
        ):
            return FailureClassification.COLLECTION_ERROR

        # Check for syntax errors
        if "syntaxerror:" in output or "indentationerror:" in output:
            return FailureClassification.SYNTAX_ERROR

        # Check for genuine assertion failures
        if (
            "assertionerror" in output
            or "assert " in output
            or "=== failures ===" in output
            or "=== failed ===" in output
            or (res.exit_code == 1 and ("failed" in output or "failure" in output))
        ):
            return FailureClassification.ASSERTION_FAILURE

        return FailureClassification.RUNNER_CRASH

    @staticmethod
    def _parse_counts(stdout: str, passed: bool) -> tuple[int, int, int]:
        """Extract test counts from pytest or standard runner summaries."""
        # Check pytest summary format: e.g. "1 failed, 5 passed in 0.05s" or "6 passed in 0.04s"
        passed_match = re.search(r"(\d+)\s+passed", stdout)
        failed_match = re.search(r"(\d+)\s+failed", stdout)

        p_count = int(passed_match.group(1)) if passed_match else (1 if passed else 0)
        f_count = int(failed_match.group(1)) if failed_match else (0 if passed else 1)
        total = p_count + f_count
        return max(total, 1), p_count, f_count
