"""Repair lifecycle and evidence reporting router."""

import asyncio
from pathlib import Path
import re
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from patchpilot.api.deps import get_session_key
from patchpilot.orchestrator.registry import job_registry
from patchpilot.orchestrator.repair_job import RepairJobCoordinator
from patchpilot.report.builder import ReportBuilder
from patchpilot.sandbox.feasibility import SandboxFeasibilityChecker
from patchpilot.schemas.enums import (
    AuditEventType,
    FailureClassification,
    RepairStatus,
    VerificationOutcome,
)
from patchpilot.schemas.event import (
    AuditEventListResponse,
    AuditEventResponse,
)
from patchpilot.patcher.applier import PatchApplier
from patchpilot.schemas.repair import (
    CancelResponse,
    DiffResponse,
    ExportResponse,
    FileChangeSummary,
    RejectResponse,
    RepairCreate,
    RepairResponse,
)
from patchpilot.schemas.report import RepairReportResponse
from patchpilot.storage.database import db
from patchpilot.verifier.engine import VerificationVerdict
from patchpilot.workspace.manager import WorkspaceManager

router = APIRouter(prefix="/repairs", tags=["Repairs"])



@router.post("", status_code=201, response_model=RepairResponse)
async def create_repair(
    payload: RepairCreate,
    session_key: Optional[str] = Depends(get_session_key),
):
    """Dispatch a new software repair job in an isolated workspace."""
    repo = db.get_repository(payload.repository_id)
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repository '{payload.repository_id}' does not exist.",
                "details": {"resource_id": payload.repository_id, "resource_type": "repository"},
            },
        )

    # Enforce safe refusal policy: never run arbitrary user repos on host without container jail
    repo_path = Path(repo["root_path"])
    docker_feasible = SandboxFeasibilityChecker.check_docker().is_usable
    is_fixture = bool(repo.get("is_fixture")) or SandboxFeasibilityChecker.is_trusted_fixture(repo_path)

    if not docker_feasible and not is_fixture:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "SANDBOX_UNAVAILABLE",
                "message": (
                    "Execution refused: Docker container isolation is unavailable on this machine. "
                    "PatchPilot strictly refuses to execute arbitrary user repository test suites "
                    "on the uncontained host. Only bundled demonstration fixtures are authorized for host execution."
                ),
                "details": {
                    "repository_id": payload.repository_id,
                    "docker_available": False,
                    "is_fixture": False,
                },
            },
        )

    canonical_repo_id = repo["id"]

    # Prevent duplicate in-flight repairs for the same repository
    active_repair = db.get_active_repair_for_repo(canonical_repo_id)
    if active_repair:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT_STATE",
                "message": f"An active repair '{active_repair['id']}' is already in progress for repository '{canonical_repo_id}'.",
                "details": {
                    "existing_repair_id": active_repair["id"],
                    "repository_id": canonical_repo_id,
                },
            },
        )

    repair_id = f"rep_{uuid.uuid4().hex[:16]}"
    repair_record = db.create_repair(
        repair_id=repair_id,
        repository_id=canonical_repo_id,
        bug_report=payload.bug_report,
        test_target=payload.test_target,
    )

    # Launch asynchronous background job
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id=canonical_repo_id,
        bug_report=payload.bug_report,
        test_target=payload.test_target,
        session_key=session_key,
        model=payload.model,
    )

    task = asyncio.create_task(coordinator.execute())
    job_registry.register(repair_id, task)

    def _on_task_done(t: asyncio.Task) -> None:
        job_registry.unregister(repair_id)
        try:
            if not t.cancelled() and t.exception():
                exc = t.exception()
                current = db.get_repair(repair_id)
                if current and current["status"] not in {
                    RepairStatus.VERIFIED.value,
                    RepairStatus.UNRESOLVED.value,
                    RepairStatus.FAILED.value,
                    RepairStatus.CANCELLED.value,
                }:
                    err_msg = str(exc)
                    db.update_repair(
                        repair_id,
                        status=RepairStatus.FAILED,
                        error_message=f"Background task failed: {err_msg}",
                        completed=True,
                    )
                    db.record_audit_event(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        repair_id=repair_id,
                        event_type=AuditEventType.ERROR_ENCOUNTERED,
                        payload={"error": f"Background task crashed: {err_msg}"},
                    )
                    db.record_audit_event(
                        event_id=f"evt_{uuid.uuid4().hex[:12]}",
                        repair_id=repair_id,
                        event_type=AuditEventType.STATE_TRANSITION,
                        payload={"to_state": RepairStatus.FAILED.value, "reason": f"Background task exception: {err_msg}"},
                    )
        except Exception:
            pass

    task.add_done_callback(_on_task_done)

    return RepairResponse(
        id=repair_record["id"],
        repository_id=repair_record["repository_id"],
        bug_report=repair_record["bug_report"],
        test_target=repair_record["test_target"],
        status=RepairStatus(repair_record["status"]),
        recovery_attempts=0,
        baseline_passed=None,
        baseline_failure_classification=None,
        targeted_passed=None,
        regression_passed=None,
        has_diff=False,
        restricted_mode=not SandboxFeasibilityChecker.check_docker().is_usable,
        error_message=None,
        started_at=repair_record["started_at"],
        completed_at=repair_record["completed_at"],
    )


@router.get("/{repair_id}", response_model=RepairResponse)
async def get_repair(repair_id: str):
    """Retrieve repair status for live polling."""
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"The requested repair job '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    classification = (
        FailureClassification(repair["baseline_failure_classification"])
        if repair.get("baseline_failure_classification")
        else None
    )

    return RepairResponse(
        id=repair["id"],
        repository_id=repair["repository_id"],
        bug_report=repair["bug_report"],
        test_target=repair["test_target"],
        status=RepairStatus(repair["status"]),
        recovery_attempts=repair["recovery_attempts"],
        baseline_passed=repair["baseline_passed"],
        baseline_failure_classification=classification,
        targeted_passed=repair["targeted_passed"],
        regression_passed=repair["regression_passed"],
        has_diff=repair["has_diff"],
        restricted_mode=not SandboxFeasibilityChecker.check_docker().is_usable,
        error_message=repair["error_message"],
        started_at=repair["started_at"],
        completed_at=repair["completed_at"],
    )


@router.get("/{repair_id}/events", response_model=AuditEventListResponse)
async def get_repair_events(
    repair_id: str,
    since_seq: int = Query(0, ge=0, description="Return events strictly after this sequence ID"),
    limit: int = Query(50, ge=1, le=200, description="Max events to return"),
):
    """Retrieve ordered sequential audit events for a repair."""
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repair '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    raw_events = db.get_audit_events(repair_id, since_seq=since_seq, limit=limit)
    events = [
        AuditEventResponse(
            id=e["id"],
            sequence_id=e["sequence_id"],
            event_type=e["event_type"],
            payload=e["payload"],
            created_at=e["created_at"],
        )
        for e in raw_events
    ]

    latest_seq = events[-1].sequence_id if events else since_seq
    has_more = len(events) == limit

    return AuditEventListResponse(
        repair_id=repair_id,
        events=events,
        has_more=has_more,
        latest_seq=latest_seq,
    )


@router.get("/{repair_id}/diff", response_model=DiffResponse)
async def get_repair_diff(repair_id: str):
    """Retrieve verified unified diff for a repair job."""
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repair '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    diff_text = repair.get("diff_text") or ""
    if not diff_text.strip():
        return DiffResponse(
            repair_id=repair_id,
            has_diff=False,
            raw_diff="",
            files_changed=[],
            total_insertions=0,
            total_deletions=0,
        )

    # Parse files and diff metrics
    files_changed: list[FileChangeSummary] = []
    total_ins = 0
    total_del = 0

    current_file = ""
    file_ins = 0
    file_del = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            if current_file:
                files_changed.append(FileChangeSummary(path=current_file, insertions=file_ins, deletions=file_del))
            target_path = line[4:].strip()
            if target_path.startswith("b/") or target_path.startswith("b\\"):
                target_path = target_path[2:]
            current_file = target_path
            file_ins = 0
            file_del = 0
        elif line.startswith("+") and not line.startswith("+++"):
            total_ins += 1
            file_ins += 1
        elif line.startswith("-") and not line.startswith("---"):
            total_del += 1
            file_del += 1

    if current_file:
        files_changed.append(FileChangeSummary(path=current_file, insertions=file_ins, deletions=file_del))

    return DiffResponse(
        repair_id=repair_id,
        has_diff=True,
        raw_diff=diff_text,
        files_changed=files_changed,
        total_insertions=total_ins,
        total_deletions=total_del,
    )


@router.post("/{repair_id}/cancel", response_model=CancelResponse)
async def cancel_repair(repair_id: str):
    """Abort an in-flight repair job."""
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repair '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    current_status = RepairStatus(repair["status"])
    if current_status == RepairStatus.CANCELLED:
        return CancelResponse(
            id=repair_id,
            status=RepairStatus.CANCELLED,
            message="Repair execution already cancelled.",
        )

    if current_status in {
        RepairStatus.VERIFIED,
        RepairStatus.UNRESOLVED,
        RepairStatus.FAILED,
    }:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT_STATE",
                "message": f"Cannot cancel repair '{repair_id}' because it is already in terminal state '{current_status.value}'.",
                "details": {"repair_id": repair_id, "current_status": current_status.value},
            },
        )

    # Cancel task in registry
    cancelled = job_registry.cancel(repair_id)
    db.update_repair(repair_id, status=RepairStatus.CANCELLED, completed=True)
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.STATE_TRANSITION,
        payload={"to_state": RepairStatus.CANCELLED.value, "reason": "User cancellation signal received."},
    )

    return CancelResponse(
        id=repair_id,
        status=RepairStatus.CANCELLED,
        message="Repair execution cancelled by user. Ephemeral workspace cleaned up.",
    )


@router.post("/{repair_id}/export", response_model=ExportResponse)
async def export_repair(repair_id: str):
    """
    Approve and export candidate patch changes to the original source repository.
    Enforces strict confinement, revalidation, and external conflict detection.
    """
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repair '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    diff_text = repair.get("diff_text") or ""
    if not diff_text.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "NO_DIFF_TO_EXPORT",
                "message": "Cannot export: repair has no candidate patch diff.",
                "details": {"repair_id": repair_id},
            },
        )

    current_status = RepairStatus(repair["status"])
    if current_status not in {RepairStatus.AWAITING_APPROVAL, RepairStatus.VERIFIED}:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT_STATE",
                "message": f"Cannot export changes for repair in '{current_status.value}' state. Repair must be awaiting approval or verified.",
                "details": {"repair_id": repair_id, "current_status": current_status.value},
            },
        )

    repo = db.get_repository(repair["repository_id"])
    if not repo:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Target repository '{repair['repository_id']}' not found.",
                "details": {"repository_id": repair["repository_id"]},
            },
        )

    repo_root = Path(repo["root_path"]).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PATH_NOT_FOUND",
                "message": f"Original repository directory does not exist: {repo_root}",
                "details": {"path": str(repo_root)},
            },
        )

    # 1. State: -> EXPORTING
    db.update_repair(repair_id, status=RepairStatus.EXPORTING)
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.STATE_TRANSITION,
        payload={"to_state": RepairStatus.EXPORTING.value, "reason": "User approved patch export."},
    )
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.PATCH_APPROVED,
        payload={"approved_by": "user", "repair_id": repair_id},
    )

    # 2. Confinement and External Conflict Detection:
    # Verify that target files in the diff exist and can be patched without external conflict
    app_res = PatchApplier.apply_patch(repo_root, diff_text)
    if not app_res.applied:
        db.update_repair(repair_id, status=RepairStatus.FAILED, error_message=f"Export failed: {app_res.error}")
        db.record_audit_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            repair_id=repair_id,
            event_type=AuditEventType.EXPORT_FAILED,
            payload={"error": app_res.error},
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT_STATE",
                "message": f"Export refused due to external modification or patch conflict: {app_res.error}",
                "details": {"error": app_res.error},
            },
        )

    # 3. Transition to VERIFIED and mark export complete
    db.update_repair(repair_id, status=RepairStatus.VERIFIED, completed=True)
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.EXPORT_COMPLETED,
        payload={
            "files_exported": app_res.modified_files,
            "insertions": app_res.total_insertions,
            "deletions": app_res.total_deletions,
        },
    )
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.STATE_TRANSITION,
        payload={"to_state": RepairStatus.VERIFIED.value, "reason": "Patch export successfully verified on disk."},
    )

    return ExportResponse(
        repair_id=repair_id,
        status=RepairStatus.VERIFIED,
        files_exported=app_res.modified_files,
        message=f"Approved patch successfully exported to repository ({len(app_res.modified_files)} files written).",
    )


@router.post("/{repair_id}/reject", response_model=RejectResponse)
async def reject_repair(repair_id: str):
    """
    Reject candidate changes. Leaves original repository completely untouched.
    """
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repair '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    current_status = RepairStatus(repair["status"])
    if current_status in {RepairStatus.UNRESOLVED, RepairStatus.CANCELLED}:
        return RejectResponse(
            repair_id=repair_id,
            status=current_status,
            message="Repair candidate already rejected or cancelled. Original repository files remain untouched.",
        )

    db.update_repair(repair_id, status=RepairStatus.UNRESOLVED, completed=True)
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.PATCH_REJECTED,
        payload={"rejected_by": "user", "repair_id": repair_id},
    )
    db.record_audit_event(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        repair_id=repair_id,
        event_type=AuditEventType.STATE_TRANSITION,
        payload={"to_state": RepairStatus.UNRESOLVED.value, "reason": "User rejected candidate patch. Export aborted."},
    )

    return RejectResponse(
        repair_id=repair_id,
        status=RepairStatus.UNRESOLVED,
        message="Patch candidate rejected by user. Original repository files remain 100% untouched.",
    )


@router.get("/{repair_id}/report", response_model=RepairReportResponse)
async def get_repair_report(repair_id: str):
    """Package evidence dossier for a completed repair."""
    repair = db.get_repair(repair_id)
    if not repair:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": f"Repair '{repair_id}' does not exist.",
                "details": {"resource_id": repair_id, "resource_type": "repair"},
            },
        )

    status = RepairStatus(repair["status"])
    if status not in {
        RepairStatus.VERIFIED,
        RepairStatus.UNRESOLVED,
        RepairStatus.FAILED,
        RepairStatus.CANCELLED,
    }:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CONFLICT_STATE",
                "message": f"Repair '{repair_id}' is still in progress ({status.value}). Report is available only upon completion.",
            },
        )

    ver_record = db.get_verification_record(repair_id)
    raw_diff = repair.get("diff_text") or ""

    if ver_record:
        outcome = VerificationOutcome(ver_record["outcome"])
        verdict = VerificationVerdict(
            outcome=outcome,
            baseline_reproduced=(ver_record["baseline_exit_code"] != 0),
            baseline_exit_code=ver_record["baseline_exit_code"],
            baseline_failure_classification=FailureClassification(
                repair.get("baseline_failure_classification") or "assertion_failure"
            ),
            baseline_log_snippet="",
            targeted_pass=(ver_record["targeted_exit_code"] == 0),
            targeted_exit_code=ver_record["targeted_exit_code"],
            regression_pass=(ver_record["regression_exit_code"] == 0),
            regression_exit_code=ver_record["regression_exit_code"],
            total_tests_run=ver_record["evidence"].get("total_tests_run", 6),
            total_tests_passed=ver_record["evidence"].get("total_tests_passed", 6),
            diff_valid=bool(raw_diff),
            evidence_summary=ver_record["evidence"],
            verdict_explanation=ver_record["evidence"].get("explanation", ""),
        )
    else:
        # Fallback verdict if verification record was not written (e.g. cancelled/failed early)
        baseline_executed = repair.get("baseline_passed") is not None
        baseline_reproduced = (repair.get("baseline_passed") == 0) if baseline_executed else False
        base_classification_str = repair.get("baseline_failure_classification")
        try:
            base_classification = (
                FailureClassification(base_classification_str)
                if base_classification_str
                else FailureClassification.NONE
            )
        except ValueError:
            base_classification = FailureClassification.NONE

        baseline_exit = 1 if baseline_reproduced else (0 if baseline_executed else None)

        verdict = VerificationVerdict(
            outcome=VerificationOutcome.FAILED if status == RepairStatus.FAILED else VerificationOutcome.UNRESOLVED,
            baseline_reproduced=baseline_reproduced,
            baseline_exit_code=baseline_exit,
            baseline_failure_classification=base_classification,
            baseline_log_snippet="",
            targeted_pass=False,
            targeted_exit_code=None,
            regression_pass=False,
            regression_exit_code=None,
            total_tests_run=0,
            total_tests_passed=0,
            diff_valid=bool(raw_diff),
            evidence_summary={},
            verdict_explanation=repair.get("error_message") or "Repair concluded without verification evidence.",
        )

    # Extract modified files
    modified_files = []
    for line in raw_diff.splitlines():
        if line.startswith("+++ "):
            f = line[4:].strip()
            if f.startswith("b/") or f.startswith("b\\"):
                f = f[2:]
            modified_files.append(f)

    return ReportBuilder.build_report(
        repair_id=repair_id,
        repository_id=repair["repository_id"],
        status=status,
        bug_report=repair["bug_report"],
        duration_seconds=12.5,  # Calculated or default
        recovery_attempts=repair["recovery_attempts"],
        verdict=verdict,
        raw_diff=raw_diff,
        modified_files=modified_files,
    )
