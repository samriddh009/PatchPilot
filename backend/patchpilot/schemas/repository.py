"""Repository schemas matching the approved REST API contract."""

from typing import List, Optional
from pydantic import BaseModel, Field

from patchpilot.schemas.enums import Language, TestFramework


class RepositoryResponse(BaseModel):
    """Repository metadata response (absolute host paths strictly omitted)."""
    id: str = Field(..., description="Unique repository identifier")
    name: str = Field(..., description="Human-readable repository name")
    language: Language = Field(..., description="Detected primary programming language")
    test_framework: TestFramework = Field(..., description="Detected testing framework")
    file_count: Optional[int] = Field(None, description="Total project source files scanned")
    test_targets: Optional[List[str]] = Field(None, description="Discovered target test identifiers")
    is_fixture: bool = Field(False, description="Whether this is a bundled demonstration fixture")
    execution_allowed: bool = Field(True, description="Whether test execution is permitted under current container feasibility")
    execution_warning: Optional[str] = Field(None, description="Warning if execution is restricted or refused")
    layout_status: Optional[str] = Field("supported", description="Status of project layout (supported, unsupported, missing_test_tooling)")
    created_at: str = Field(..., description="ISO 8601 UTC creation timestamp")


class RepositoryListResponse(BaseModel):
    items: List[RepositoryResponse] = Field(..., description="List of registered repositories")
    total: int = Field(..., description="Total repository count")


class RepositoryFilesResponse(BaseModel):
    repository_id: str = Field(..., description="Repository identifier")
    files: List[str] = Field(..., description="Safe relative file paths within the repository")


class OpenLocalRepositoryRequest(BaseModel):
    path: str = Field(..., description="Absolute path to local repository directory on the host")
    name: Optional[str] = Field(None, description="Optional custom display name")


class BrowseFolderResponse(BaseModel):
    path: Optional[str] = Field(None, description="Selected folder path on the host")
    cancelled: bool = Field(False, description="Whether user cancelled the dialog")
    supported: bool = Field(True, description="Whether host dialog is supported in this environment")
    message: Optional[str] = Field(None, description="Diagnostic message")


class RepositoryFileContentResponse(BaseModel):
    """File content response for in-app source browsing."""
    repository_id: str = Field(..., description="Repository identifier")
    file_path: str = Field(..., description="Relative file path within repository")
    content: str = Field(..., description="File text content")
    total_lines: int = Field(..., description="Total line count in the file")
    offset_line: int = Field(1, description="1-indexed line offset")
    limit_lines: int = Field(500, description="Line count limit")
    language: str = Field("plaintext", description="Detected language for syntax display")


class ProposeTestRequest(BaseModel):
    """Request payload to propose a focused test for source-only or existing repos."""
    bug_report: str = Field(..., min_length=10, description="Bug description or expected behavior")
    target_file: Optional[str] = Field(None, description="Optional target source file path")


class ProposedTestResponse(BaseModel):
    """Proposed focused test response generated without executing untrusted code."""
    repository_id: str = Field(..., description="Repository identifier")
    test_file_path: str = Field(..., description="Proposed test file path relative to workspace")
    test_code: str = Field(..., description="Generated test source code")
    test_target: str = Field(..., description="Target identifier to execute the test")
    explanation: str = Field(..., description="Explanation of what this proposed test verifies")
    status: str = Field("proposed", description="Status marking that this test is proposed, not executed")


class IngestProjectFile(BaseModel):
    """Individual file payload for browser-based project ingestion."""
    path: str = Field(..., min_length=1, max_length=500, description="Relative file path within project")
    content: str = Field(..., max_length=2_000_000, description="UTF-8 text content of the file")


class IngestProjectRequest(BaseModel):
    """Request payload for browser-native project ingestion."""
    name: str = Field(..., min_length=1, max_length=100, description="Display name for the uploaded/ingested project")
    files: List[IngestProjectFile] = Field(..., min_length=1, max_length=1000, description="List of project files to ingest")

