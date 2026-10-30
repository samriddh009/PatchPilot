"""Repair report schemas matching the approved REST API contract."""

from typing import List, Optional
from pydantic import BaseModel, Field

from patchpilot.schemas.enums import RepairStatus, VerificationOutcome


class VerificationDetails(BaseModel):
    outcome: VerificationOutcome = Field(..., description="Deterministic outcome verdict")
    baseline_reproduced: bool = Field(..., description="Whether baseline test failure was reproduced")
    baseline_exit_code: Optional[int] = Field(None, description="Baseline test runner exit code")
    baseline_log_snippet: Optional[str] = Field(None, description="Relevant excerpt from baseline failure")
    targeted_pass: bool = Field(..., description="Whether post-patch targeted test passed")
    targeted_exit_code: Optional[int] = Field(None, description="Post-patch targeted test runner exit code")
    regression_pass: bool = Field(..., description="Whether post-patch regression suite passed")
    regression_exit_code: Optional[int] = Field(None, description="Post-patch regression test runner exit code")
    total_tests_run: int = Field(0, description="Total tests run across test suites")
    total_tests_passed: int = Field(0, description="Total tests passed across test suites")


class DiffDetails(BaseModel):
    raw_diff: str = Field(..., description="Unified diff string")
    files_changed: List[str] = Field(default_factory=list, description="Relative paths of modified files")


class RepairReportResponse(BaseModel):
    repair_id: str = Field(..., description="Unique repair identifier")
    repository_id: str = Field(..., description="Repository identifier")
    status: RepairStatus = Field(..., description="Final terminal repair status")
    bug_report: str = Field(..., description="User bug report description")
    duration_seconds: float = Field(..., description="Total wall-clock execution duration in seconds")
    recovery_attempts: int = Field(0, description="Count of recovery attempts executed")
    verification: VerificationDetails = Field(..., description="Deterministic verification evidence")
    diff: DiffDetails = Field(..., description="Applied patch diff details")
    markdown_summary: str = Field(..., description="Evidence-backed human readable report summary")
