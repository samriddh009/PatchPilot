"""Tests for Pydantic domain schemas and enum values."""

import pytest
from pydantic import ValidationError

from patchpilot.schemas.enums import (
    AuditEventType,
    FailureClassification,
    Language,
    RepairStatus,
    TestFramework,
    VerificationOutcome,
)
from patchpilot.schemas.common import APIError, ErrorDetail
from patchpilot.schemas.repair import RepairCreate, RepairResponse


def test_repair_status_values():
    expected = {
        "queued", "inspecting", "reproducing", "patching", "testing",
        "verifying", "recovering", "awaiting_approval", "exporting",
        "verified", "unresolved", "failed", "cancelled"
    }
    actual = {s.value for s in RepairStatus}
    assert actual == expected


def test_language_and_framework_values():
    assert {l.value for l in Language} == {"python", "javascript", "typescript", "java", "unknown"}
    assert {f.value for f in TestFramework} == {
        "pytest", "vitest", "jest", "maven_junit", "gradle_junit", "unknown"
    }


def test_repair_create_validation():
    # Valid minimal
    rc = RepairCreate(repository_id="repo1", bug_report="This is a bug that fails at boundary")
    assert rc.repository_id == "repo1"
    assert rc.bug_report == "This is a bug that fails at boundary"
    assert rc.test_target is None
    assert rc.model is None

    # Valid with optional test_target and model
    rc_full = RepairCreate(
        repository_id="  'repo1'  ",
        bug_report="  Valid bug report text here  ",
        test_target="  tests/test_calc.py::test_boundary  ",
        model="  gemini-1.5-flash  ",
    )
    assert rc_full.repository_id == "repo1"
    assert rc_full.bug_report == "Valid bug report text here"
    assert rc_full.test_target == "tests/test_calc.py::test_boundary"
    assert rc_full.model == "gemini-1.5-flash"

    # Empty string test_target and model converted to None
    rc_empty_opt = RepairCreate(
        repository_id="repo1",
        bug_report="Valid bug report text here",
        test_target="   ",
        model="",
    )
    assert rc_empty_opt.test_target is None
    assert rc_empty_opt.model is None

    # Object / dict test_target safely extracts test_target string
    rc_dict = RepairCreate(
        repository_id="repo1",
        bug_report="Valid bug report text here",
        test_target={"test_target": "tests/test_calc.py::test_boundary", "exit_code": 1},  # type: ignore
    )
    assert rc_dict.test_target == "tests/test_calc.py::test_boundary"

    # [object Object], undefined, and null literals are converted to None
    for literal in ("[object Object]", "undefined", "null", "UNDEFINED", "NULL"):
        rc_lit = RepairCreate(
            repository_id="repo1",
            bug_report="Valid bug report text here",
            test_target=literal,
        )
        assert rc_lit.test_target is None

    # Genuinely invalid types (e.g. int, bool, list) are rejected by strict validation
    with pytest.raises(ValidationError):
        RepairCreate(repository_id="repo1", bug_report="Valid bug report text here", test_target=12345)  # type: ignore
    with pytest.raises(ValidationError):
        RepairCreate(repository_id="repo1", bug_report="Valid bug report text here", test_target=True)  # type: ignore


    # Too short bug_report (< 10 chars)
    with pytest.raises(ValidationError) as exc_info:
        RepairCreate(repository_id="repo1", bug_report="123456789")
    assert "bug_report" in str(exc_info.value)

    # Exact boundary length 10 chars succeeds
    rc_min = RepairCreate(repository_id="repo1", bug_report="0123456789")
    assert len(rc_min.bug_report) == 10

    # Exact boundary length 4000 chars succeeds
    rc_max = RepairCreate(repository_id="repo1", bug_report="a" * 4000)
    assert len(rc_max.bug_report) == 4000

    # Boundary length 4001 chars fails
    with pytest.raises(ValidationError):
        RepairCreate(repository_id="repo1", bug_report="a" * 4001)

    # Empty repo_id
    with pytest.raises(ValidationError):
        RepairCreate(repository_id="", bug_report="Valid bug report text here")

    # Extra/unknown fields are ignored safely without raising
    rc_extra = RepairCreate(
        repository_id="repo1",
        bug_report="Valid bug report text here",
        unknown_field="extra_value",  # type: ignore
        ui_only_property="should_be_ignored",  # type: ignore
    )
    assert rc_extra.repository_id == "repo1"
    assert not hasattr(rc_extra, "unknown_field")


def test_api_validation_error_handler(client):
    """Verify that FastAPI validation error handler formats actionable field-level errors and redacts secrets."""
    # 1. Missing required fields
    res = client.post("/api/v1/repairs", json={})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "INVALID_REQUEST"
    assert "Validation failed:" in err["message"]
    assert "repository_id" in err["message"]
    assert "bug_report" in err["message"]
    assert isinstance(err["details"]["errors"], list)
    assert len(err["details"]["errors"]) >= 2

    # 2. Short bug_report
    res_short = client.post("/api/v1/repairs", json={"repository_id": "repo1", "bug_report": "short"})
    assert res_short.status_code == 422
    err_short = res_short.json()["error"]
    assert "bug_report" in err_short["message"]

    secret_token = "AIza" + "SyD12345678901234567890123456789012"
    res_secret = client.post(
        "/api/v1/repairs",
        json={"repository_id": "repo1", "bug_report": secret_token},
    )
    # Even if accepted or rejected, secrets are never exposed in error envelope
    if res_secret.status_code != 201:
        assert secret_token[:16] not in res_secret.text


def test_api_error_envelope():
    err = APIError(
        error=ErrorDetail(
            code="RESOURCE_NOT_FOUND",
            message="Item not found",
            details={"id": "abc"},
        )
    )
    assert err.error.code == "RESOURCE_NOT_FOUND"
    assert err.error.message == "Item not found"
    assert err.error.details == {"id": "abc"}
    assert "T" in err.error.timestamp

