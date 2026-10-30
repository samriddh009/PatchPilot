"""Repair schemas matching the approved REST API contract."""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

from patchpilot.schemas.enums import FailureClassification, RepairStatus


class RepairCreate(BaseModel):
    repository_id: str = Field(..., min_length=1, description="Repository identifier")
    bug_report: str = Field(..., min_length=10, max_length=4000, description="Bug report text")
    test_target: Optional[str] = Field(None, max_length=500, description="Optional targeted test path/node")
    model: Optional[str] = Field(None, description="Optional Gemini model selection for this repair")

    @field_validator("repository_id", mode="before")
    @classmethod
    def clean_repository_id(cls, v):
        if isinstance(v, str):
            cleaned = v.strip().strip("'\"")
            return cleaned
        return v

    @field_validator("bug_report", mode="before")
    @classmethod
    def clean_bug_report(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("test_target", mode="before")
    @classmethod
    def clean_test_target(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v or v.lower() in ("[object object]", "undefined", "null"):
                return None
            return v
        if isinstance(v, dict):
            # Safely extract test target string from object if provided
            target_str = v.get("test_target") or v.get("target") or v.get("id")
            if isinstance(target_str, str) and target_str.strip():
                clean_target = target_str.strip()
                if clean_target.lower() not in ("[object object]", "undefined", "null"):
                    return clean_target
            return None
        return v

    @field_validator("model", mode="before")
    @classmethod
    def clean_model(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v



class RepairResponse(BaseModel):
    id: str = Field(..., description="Unique repair identifier")
    repository_id: str = Field(..., description="Repository identifier")
    bug_report: str = Field(..., description="User bug report description")
    test_target: Optional[str] = Field(None, description="Targeted test file or node ID")
    status: RepairStatus = Field(..., description="Current repair lifecycle status")
    recovery_attempts: int = Field(0, description="Count of recovery attempts executed (max 1)")
    baseline_passed: Optional[bool] = Field(None, description="Whether baseline test unexpectedly passed")
    baseline_failure_classification: Optional[FailureClassification] = Field(
        None, description="Classification of baseline test failure"
    )
    targeted_passed: Optional[bool] = Field(None, description="Whether targeted test passed after patch")
    regression_passed: Optional[bool] = Field(None, description="Whether full regression suite passed")
    has_diff: bool = Field(False, description="Whether a valid patch diff has been generated")
    restricted_mode: bool = Field(False, description="Whether execution runs under restricted demonstration mode")
    error_message: Optional[str] = Field(None, description="Diagnostic error explanation if failed/unresolved")
    started_at: str = Field(..., description="ISO 8601 UTC start timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 UTC completion timestamp")


class FileChangeSummary(BaseModel):
    path: str = Field(..., description="Relative path of modified file")
    insertions: int = Field(..., description="Count of added lines")
    deletions: int = Field(..., description="Count of removed lines")


class DiffResponse(BaseModel):
    repair_id: str = Field(..., description="Repair job identifier")
    has_diff: bool = Field(..., description="Whether diff content exists")
    raw_diff: str = Field(..., description="Unified diff text")
    files_changed: List[FileChangeSummary] = Field(default_factory=list, description="List of altered files")
    total_insertions: int = Field(0, description="Total inserted lines")
    total_deletions: int = Field(0, description="Total deleted lines")


class CancelResponse(BaseModel):
    id: str = Field(..., description="Repair job identifier")
    status: RepairStatus = Field(..., description="Resulting cancelled status")
    message: str = Field(..., description="Cancellation confirmation message")


class ExportResponse(BaseModel):
    repair_id: str = Field(..., description="Repair job identifier")
    status: RepairStatus = Field(..., description="Resulting status (verified)")
    files_exported: List[str] = Field(default_factory=list, description="List of files written to original repository")
    message: str = Field(..., description="Export confirmation message")


class RejectResponse(BaseModel):
    repair_id: str = Field(..., description="Repair job identifier")
    status: RepairStatus = Field(..., description="Resulting status (unresolved)")
    message: str = Field(..., description="Rejection confirmation message")

