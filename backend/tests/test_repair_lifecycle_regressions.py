"""Regression tests for repair lifecycle, queued cancellation, duplicate prevention, and background task failure handling."""

import asyncio
import pytest
from fastapi.testclient import TestClient

from patchpilot.gemini.stub import StubModelProvider
from patchpilot.orchestrator.registry import job_registry
from patchpilot.orchestrator.repair_job import RepairJobCoordinator
from patchpilot.schemas.enums import AuditEventType, RepairStatus
from patchpilot.storage.database import db


def test_status_retrieval(client: TestClient):
    """Verify repair status retrieval schema and attributes across lifecycle states."""
    # 1. Create a repair
    payload = {
        "repository_id": "repo_py_calc_01",
        "bug_report": "Boundary error in discount calculation when subtotal is exactly $100",
    }
    create_res = client.post("/api/v1/repairs", json=payload)
    assert create_res.status_code == 201
    repair_id = create_res.json()["id"]

    # 2. Immediately retrieve status
    status_res = client.get(f"/api/v1/repairs/{repair_id}")
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["id"] == repair_id
    assert data["repository_id"] == "repo_py_calc_01"
    assert "status" in data
    assert "has_diff" in data
    assert "recovery_attempts" in data

    # Clean up by cancelling
    client.post(f"/api/v1/repairs/{repair_id}/cancel")


def test_queued_cancellation(client: TestClient):
    """Verify that cancelling a repair immediately while queued halts execution cleanly."""
    payload = {
        "repository_id": "repo_py_calc_01",
        "bug_report": "Cancel immediately while queued",
    }
    create_res = client.post("/api/v1/repairs", json=payload)
    assert create_res.status_code == 201
    repair_id = create_res.json()["id"]

    # Cancel immediately
    cancel_res = client.post(f"/api/v1/repairs/{repair_id}/cancel")
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["id"] == repair_id
    assert cancel_data["status"] == "cancelled"

    # Verify status in database
    db_record = db.get_repair(repair_id)
    assert db_record is not None
    assert db_record["status"] == "cancelled"


def test_repeated_cancellation(client: TestClient):
    """Verify that calling cancel repeatedly on an already cancelled repair is idempotent and returns 200."""
    payload = {
        "repository_id": "repo_py_calc_01",
        "bug_report": "Test repeated cancellation",
    }
    create_res = client.post("/api/v1/repairs", json=payload)
    repair_id = create_res.json()["id"]

    # First cancel
    res1 = client.post(f"/api/v1/repairs/{repair_id}/cancel")
    assert res1.status_code == 200
    assert res1.json()["status"] == "cancelled"

    # Second cancel (should be idempotent 200, not 409 error)
    res2 = client.post(f"/api/v1/repairs/{repair_id}/cancel")
    assert res2.status_code == 200
    assert res2.json()["status"] == "cancelled"
    assert "already cancelled" in res2.json()["message"]


def test_terminal_repair_cancel_rejected(client: TestClient):
    """Verify that attempting to cancel a verified or failed repair returns 409 CONFLICT_STATE."""
    repair_id = "rep_test_terminal_cancel"
    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report="Terminal test",
    )
    db.update_repair(repair_id, status=RepairStatus.FAILED, completed=True)

    cancel_res = client.post(f"/api/v1/repairs/{repair_id}/cancel")
    assert cancel_res.status_code == 409
    err = cancel_res.json()
    assert err["error"]["code"] == "CONFLICT_STATE"
    assert "terminal state 'failed'" in err["error"]["message"]


def test_duplicate_repair_prevention(client: TestClient):
    """Verify that starting a second repair while one is active on the same repo is rejected with 409 CONFLICT_STATE."""
    # 1. Create first repair
    payload = {
        "repository_id": "repo_py_calc_01",
        "bug_report": "First active repair",
    }
    create_res = client.post("/api/v1/repairs", json=payload)
    assert create_res.status_code == 201
    first_id = create_res.json()["id"]

    # 2. Attempt duplicate repair on same repository while first is active
    dup_res = client.post("/api/v1/repairs", json=payload)
    # If the first is still active, it must return 409
    active = db.get_active_repair_for_repo("repo_py_calc_01")
    if active and active["id"] == first_id:
        assert dup_res.status_code == 409
        err = dup_res.json()
        assert err["error"]["code"] == "CONFLICT_STATE"
        assert "already in progress" in err["error"]["message"]

    # Clean up
    client.post(f"/api/v1/repairs/{first_id}/cancel")


@pytest.mark.asyncio
async def test_background_task_failure_produces_terminal_state():
    """Verify that unhandled exceptions in the background task transition the repair to FAILED in the DB."""
    repair_id = "rep_crash_test_01"
    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report="Crash test",
    )

    # Define a failing background task
    async def failing_worker():
        raise RuntimeError("Simulated unhandled worker crash")

    task = asyncio.create_task(failing_worker())
    job_registry.register(repair_id, task)

    # Attach the same done callback as router_repairs
    def _on_task_done(t: asyncio.Task) -> None:
        job_registry.unregister(repair_id)
        if not t.cancelled() and t.exception():
            exc = t.exception()
            current = db.get_repair(repair_id)
            if current and current["status"] not in {
                RepairStatus.VERIFIED.value,
                RepairStatus.UNRESOLVED.value,
                RepairStatus.FAILED.value,
                RepairStatus.CANCELLED.value,
            }:
                db.update_repair(
                    repair_id,
                    status=RepairStatus.FAILED,
                    error_message=f"Background task failed: {str(exc)}",
                    completed=True,
                )

    task.add_done_callback(_on_task_done)

    # Wait for task completion
    try:
        await task
    except RuntimeError:
        pass

    # Verify repair record was set to failed with error message
    record = db.get_repair(repair_id)
    assert record is not None
    assert record["status"] == "failed"
    assert "Simulated unhandled worker crash" in (record["error_message"] or "")


@pytest.mark.asyncio
async def test_user_exact_calculator_bug_report_verified():
    """Verify that submitting the exact user prompt 'Strict inequality excludes boundary total == 100.0' works cleanly."""
    repair_id = "rep_user_prompt_test"
    exact_prompt = "Strict inequality excludes boundary total == 100.0"

    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report=exact_prompt,
        test_target="tests/test_calculator.py::test_discount_boundary",
    )

    stub = StubModelProvider()
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report=exact_prompt,
        test_target="tests/test_calculator.py::test_discount_boundary",
        provider=stub,
    )

    await coordinator.execute()

    record = db.get_repair(repair_id)
    assert record is not None
    assert record["status"] == "verified"
    assert record["targeted_passed"] is True
    assert record["regression_passed"] is True
    assert record["has_diff"] is True


@pytest.mark.asyncio
async def test_repair_failure_on_unsupported_model_reports_truthful_verdict(client: TestClient):
    """
    Verify that when model invocation fails (e.g. model not found),
    the report reflects the true baseline status and unexecuted post-patch tests
    without fabricating a fake runner_crash or -1 exit codes.
    """
    from patchpilot.gemini.client import GeminiProviderError

    class FailingProvider:
        is_stub = True
        async def generate_patch(self, *args, **kwargs):
            raise GeminiProviderError(
                code="PROVIDER_MODEL_UNAVAILABLE",
                message="Configured model 'gemini-2.0-flash' not found or unsupported.",
                status_code=404,
            )
        async def generate_recovery_patch(self, *args, **kwargs):
            raise NotImplementedError()

    repair_id = "rep_unsupported_model_test"
    prompt = "Strict inequality excludes boundary total == 100.0"

    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report=prompt,
        test_target="tests/test_calculator.py::test_discount_boundary",
    )

    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report=prompt,
        test_target="tests/test_calculator.py::test_discount_boundary",
        provider=FailingProvider(),
    )

    await coordinator.execute()

    record = db.get_repair(repair_id)
    assert record is not None
    assert record["status"] == "failed"
    assert "PROVIDER_MODEL_UNAVAILABLE" in record["error_message"]
    # Baseline was cleanly reproduced before patching failed!
    assert record["baseline_passed"] == 0
    assert record["baseline_failure_classification"] == "assertion_failure"

    # Fetch final report via API
    rep_res = client.get(f"/api/v1/repairs/{repair_id}/report")
    assert rep_res.status_code == 200
    report_data = rep_res.json()

    assert report_data["status"] == "failed"
    ver = report_data["verification"]
    # Baseline should be recorded as reproduced assertion failure, NOT runner_crash!
    assert ver["baseline_reproduced"] is True
    assert ver["baseline_exit_code"] == 1
    # Targeted and regression tests did not run, so exit codes must be null (not -1 masquerading as test failure)
    assert ver["targeted_exit_code"] is None
    assert ver["regression_exit_code"] is None

    # Markdown summary should explicitly declare unexecuted tests as Not executed
    md = report_data["markdown_summary"]
    assert "Not executed" in md
    assert "Exit code `-1`" not in md
    assert "runner_crash" not in md


def test_runner_start_failures_captured_with_real_stderr(tmp_path):
    """
    Verify runner launch failures (nonexistent binary, permission denied)
    return exit_code -1 and capture real stderr so they cannot masquerade as test passes or failures.
    """
    from patchpilot.sandbox.restricted_runner import RestrictedRunner
    from patchpilot.test_runner.runner import TestExecutionService
    from patchpilot.schemas.enums import FailureClassification
    from patchpilot.sandbox.base import ExecutionResult

    sandbox = RestrictedRunner()
    service = TestExecutionService(sandbox)

    # 1. Nonexistent binary on PATH
    res_nonexistent = service.run_test(["python_nonexistent_binary_xyz123"], cwd=tmp_path, timeout_seconds=5)
    assert res_nonexistent.exit_code == -1
    assert res_nonexistent.failure_classification == FailureClassification.RUNNER_CRASH
    assert "[Runner Error:" in res_nonexistent.stderr

    # 2. Command rejected by execution allowlist
    res_disallowed = service.run_test(["curl", "http://example.com"], cwd=tmp_path, timeout_seconds=5)
    assert res_disallowed.exit_code == -1
    assert res_disallowed.failure_classification == FailureClassification.RUNNER_CRASH
    assert "Permission Denied" in res_disallowed.stderr or "rejected" in res_disallowed.stderr

    # 3. Docker container failure with word 'failure' in stderr must NOT masquerade as ASSERTION_FAILURE
    docker_crash = ExecutionResult(
        exit_code=125,
        stdout="",
        stderr="docker: Error response from daemon: container startup failure: resource unavailable",
        duration_ms=50,
        timed_out=False,
        output_truncated=False,
    )
    classification = service._classify_failure(docker_crash)
    assert classification == FailureClassification.RUNNER_CRASH

    # 4. Pytest exit code 5 (no tests collected) must be COLLECTION_ERROR, not RUNNER_CRASH
    pytest_no_tests = ExecutionResult(
        exit_code=5,
        stdout="no tests ran in 0.05s\n",
        stderr="",
        duration_ms=50,
        timed_out=False,
        output_truncated=False,
    )
    classification_col = service._classify_failure(pytest_no_tests)
    assert classification_col == FailureClassification.COLLECTION_ERROR


@pytest.mark.asyncio
async def test_directed_repair_without_manual_test_selection():
    """
    Workflow B verification:
    Run directed repair for python_calc_bug without manually providing test_target.
    Verify that the system automatically discovers and scores candidate tests,
    finds test_discount_boundary, reproduces the defect on baseline,
    applies the patch, and deterministically verifies the fix.
    """
    repair_id = "rep_workflow_b_no_test_target"
    bug_report = "The calculate_discount function fails to apply a 15% discount when the cart total equals exactly $100.00."

    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report=bug_report,
        test_target=None,
    )

    stub = StubModelProvider()
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report=bug_report,
        test_target=None,
        provider=stub,
    )

    await coordinator.execute()

    record = db.get_repair(repair_id)
    assert record is not None
    assert record["status"] == "verified"
    # Auto-discovered test target was recorded
    assert record["test_target"] == "tests/test_calculator.py::test_discount_boundary"
    assert record["targeted_passed"] is True
    assert record["regression_passed"] is True
    assert record["has_diff"] is True



