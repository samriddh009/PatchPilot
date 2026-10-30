"""Schemas for Autonomous Bug Discovery and Defect Classification."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Finding(BaseModel):
    id: str = Field(..., description="Unique finding identifier (e.g., fnd_12345678)")
    title: str = Field(..., description="Concise summary of the discovered defect")
    category: str = Field(..., description="Defect category (boundary_condition, logic_error, etc.)")
    severity: str = Field(..., description="Severity level: critical, high, medium, low")
    severity_rationale: str = Field(..., description="Explanation for assigned severity")
    confidence: str = Field(..., description="Confidence: confirmed, likely, inconclusive")
    confidence_rationale: str = Field(..., description="Explanation for assigned confidence")
    file_path: str = Field(..., description="Relative path of file containing the defect")
    line_range: List[int] = Field(..., description="[start_line, end_line] 1-indexed range")
    code_excerpt: str = Field(..., description="Actual source lines from the file")
    explanation: str = Field(..., description="Technical diagnosis of the defect mechanism")
    expected_behavior: str = Field(..., description="Expected program behavior")
    observed_behavior: str = Field(..., description="Observed or predicted anomalous behavior")
    suggested_fix: str = Field(..., description="Recommended correction")
    proposed_test: Optional[str] = Field(None, description="Generated reproduction test code")
    test_evidence: Optional[Dict[str, Any]] = Field(None, description="Execution test evidence if reproduced")
    status: str = Field("open", description="Finding status: open, verified, repaired, dismissed")


class DiscoverBugsRequest(BaseModel):
    scan_depth: Optional[str] = Field("standard", description="Scan depth: shallow, standard, deep")
    target_path: Optional[str] = Field(None, description="Optional subfolder or specific file to scope scan")
    category: Optional[str] = Field(None, description="Optional defect category filter")
    auto_prepare_fix: bool = Field(False, description="Whether to immediately prepare candidate patch in disposable workspace")
    model: Optional[str] = Field(None, description="Optional Gemini model to use for patch preparation")


class DiscoverBugsResponse(BaseModel):
    repository_id: str = Field(..., description="Repository identifier")
    findings: List[Finding] = Field(default_factory=list, description="Discovered defect findings")
    total_findings: int = Field(0, description="Total count of findings")
    scan_duration_ms: int = Field(0, description="Scan duration in milliseconds")
    tests_discovered: List[str] = Field(default_factory=list, description="Existing test targets found")
    repair_id: Optional[str] = Field(None, description="Repair job ID if auto_prepare_fix was dispatched")
