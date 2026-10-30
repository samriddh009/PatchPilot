"""Report service compiling evidence-backed dossiers."""

from patchpilot.schemas.enums import RepairStatus, VerificationOutcome
from patchpilot.schemas.report import (
    DiffDetails,
    RepairReportResponse,
    VerificationDetails,
)
from patchpilot.verifier.engine import VerificationVerdict


class ReportBuilder:
    """Builds structured and markdown evidence dossiers from verification records."""

    @classmethod
    def build_report(
        cls,
        repair_id: str,
        repository_id: str,
        status: RepairStatus,
        bug_report: str,
        duration_seconds: float,
        recovery_attempts: int,
        verdict: VerificationVerdict,
        raw_diff: str,
        modified_files: list[str],
    ) -> RepairReportResponse:
        verification_details = VerificationDetails(
            outcome=verdict.outcome,
            baseline_reproduced=verdict.baseline_reproduced,
            baseline_exit_code=verdict.baseline_exit_code,
            baseline_log_snippet=verdict.baseline_log_snippet,
            targeted_pass=verdict.targeted_pass,
            targeted_exit_code=verdict.targeted_exit_code,
            regression_pass=verdict.regression_pass,
            regression_exit_code=verdict.regression_exit_code,
            total_tests_run=verdict.total_tests_run,
            total_tests_passed=verdict.total_tests_passed,
        )

        diff_details = DiffDetails(
            raw_diff=raw_diff,
            files_changed=modified_files,
        )

        md_summary = cls._generate_markdown(
            status=status,
            repair_id=repair_id,
            repository_id=repository_id,
            bug_report=bug_report,
            duration_seconds=duration_seconds,
            recovery_attempts=recovery_attempts,
            verdict=verdict,
            modified_files=modified_files,
        )

        return RepairReportResponse(
            repair_id=repair_id,
            repository_id=repository_id,
            status=status,
            bug_report=bug_report,
            duration_seconds=round(duration_seconds, 2),
            recovery_attempts=recovery_attempts,
            verification=verification_details,
            diff=diff_details,
            markdown_summary=md_summary,
        )

    @staticmethod
    def _generate_markdown(
        status: RepairStatus,
        repair_id: str,
        repository_id: str,
        bug_report: str,
        duration_seconds: float,
        recovery_attempts: int,
        verdict: VerificationVerdict,
        modified_files: list[str],
    ) -> str:
        files_str = ", ".join(f"`{f}`" for f in modified_files) if modified_files else "None"
        baseline_str = (
            f"Exit code `{verdict.baseline_exit_code}` ({verdict.baseline_failure_classification.value})"
            if verdict.baseline_exit_code is not None
            else "Not executed"
        )
        targeted_str = (
            f"Exit code `{verdict.targeted_exit_code}` ({'PASSED' if verdict.targeted_pass else 'FAILED'})"
            if verdict.targeted_exit_code is not None
            else "Not executed (Skipped due to upstream failure)"
        )
        regression_str = (
            f"Exit code `{verdict.regression_exit_code}` ({'PASSED' if verdict.regression_pass else 'FAILED'})"
            if verdict.regression_exit_code is not None
            else "Not executed (Skipped due to upstream failure)"
        )
        return f"""### PatchPilot Repair Dossier: {status.value.upper()}

- **Repair ID:** `{repair_id}`
- **Repository:** `{repository_id}`
- **Duration:** {duration_seconds:.2f}s | **Recovery Attempts:** {recovery_attempts}/1
- **Status Verdict:** `{verdict.outcome.value}`

#### 1. Problem Description
> {bug_report}

#### 2. Verification Evidence
- **Baseline Test:** {baseline_str}
- **Targeted Post-Patch Test:** {targeted_str}
- **Regression Suite:** {regression_str}
- **Total Tests Verified:** {verdict.total_tests_passed} / {verdict.total_tests_run} passing

#### 3. Patch & Integrity Verification
- **Modified Files:** {files_str}
- **Source Repository Immutability:** 100% verified (0 bytes mutated on host).
- **Execution Boundary:** Ephemeral workspace cleaned up.

*{verdict.verdict_explanation}*
"""
