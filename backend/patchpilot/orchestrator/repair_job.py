"""Asynchronous coordinator for the multi-step software delivery repair lifecycle."""

from patchpilot.gemini.session_store import SessionKeyStore
import asyncio
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from patchpilot import config
from patchpilot.gemini.base import ModelProvider
from patchpilot.gemini.client import GeminiProvider, GeminiProviderError
from patchpilot.gemini.session_store import session_store
from patchpilot.gemini.stub import StubModelProvider
from patchpilot.inspector.scanner import RepositoryScanner
from patchpilot.languages.registry import registry as language_registry
from patchpilot.orchestrator.state_machine import RepairStateMachine
from patchpilot.patcher.applier import PatchApplier
from patchpilot.patcher.validator import PatchValidator
from patchpilot.recovery.manager import BoundedRecoveryManager
from patchpilot.report.builder import ReportBuilder
from patchpilot.sandbox.docker_runner import DockerRunner
from patchpilot.sandbox.feasibility import (
    SandboxFeasibilityChecker,
    SandboxUnavailableException,
)
from patchpilot.sandbox.restricted_runner import RestrictedRunner
from patchpilot.schemas.enums import (
    AuditEventType,
    FailureClassification,
    Language,
    RepairStatus,
    VerificationOutcome,
)
from patchpilot.storage.database import db
from patchpilot.test_runner.runner import TestExecutionService, TestRunResult
from patchpilot.verifier.engine import DeterministicVerifier, VerificationVerdict
from patchpilot.workspace.manager import WorkspaceManager


class RepairJobCoordinator:
    """Coordinates the deterministic repair execution lifecycle."""

    def __init__(
        self,
        repair_id: str,
        repository_id: str,
        bug_report: str,
        test_target: Optional[str] = None,
        provider: Optional[ModelProvider] = None,
        session_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.repair_id = repair_id
        self.repository_id = repository_id
        self.bug_report = bug_report
        self.test_target = test_target
        self.session_key = session_key
        self.selected_model = model

        # Resolve model provider (use stub if no live key and no explicit provider provided)
        if provider:
            self.provider = provider
        else:
            resolved_key, _ = session_store.resolve_key(session_key)
            if resolved_key:
                active_model = self.selected_model or session_store.resolve_model()
                self.provider = GeminiProvider(model_name=active_model)
            else:
                self.provider = StubModelProvider()

        self.workspace_path: Optional[Path] = None
        self.source_path: Optional[Path] = None
        self.initial_source_hash: str = ""
        self.start_time = time.perf_counter()
        self.recovery_attempts = 0
        self.current_status = RepairStatus.QUEUED
        self.restricted_mode = False

    def _transition(self, to_status: RepairStatus, reason: str = "") -> None:
        RepairStateMachine.validate_transition(self.current_status, to_status)
        from_status = self.current_status
        self.current_status = to_status

        db.update_repair(self.repair_id, status=to_status)
        db.record_audit_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            repair_id=self.repair_id,
            event_type=AuditEventType.STATE_TRANSITION,
            payload={
                "from_state": from_status.value,
                "to_state": to_status.value,
                "reason": reason,
            },
        )

    def _emit_event(self, event_type: AuditEventType, payload: Dict[str, Any]) -> None:
        db.record_audit_event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            repair_id=self.repair_id,
            event_type=event_type,
            payload=payload,
        )

    async def execute(self) -> None:
        """Run the end-to-end repair state machine workflow."""
        try:
            # Yield control to event loop so POST /repairs returns 201 Created immediately
            await asyncio.sleep(0.05)

            # Check if cancelled while queued
            current_repair = db.get_repair(self.repair_id)
            if current_repair and current_repair["status"] == RepairStatus.CANCELLED.value:
                self.current_status = RepairStatus.CANCELLED
                return

            # 1. State: QUEUED -> INSPECTING
            self._transition(RepairStatus.INSPECTING, "Initializing workspace and static inspection.")

            repo_meta = db.get_repository(self.repository_id)
            if not repo_meta:
                raise ValueError(f"Repository not found: {self.repository_id}")

            self.source_path = Path(repo_meta["root_path"])
            if not self.source_path.exists():
                raise FileNotFoundError(f"Source repository does not exist on disk: {self.source_path}")

            # Capture baseline SHA-256 tree hash
            self.initial_source_hash = WorkspaceManager.compute_tree_hash(self.source_path)

            # Check sandbox feasibility
            feasibility = SandboxFeasibilityChecker.check_docker()
            if feasibility.is_usable:
                sandbox_runner = DockerRunner()
                self.restricted_mode = False
            else:
                # Docker is unavailable; check if target is an authorized fixture
                if SandboxFeasibilityChecker.is_trusted_fixture(self.source_path):
                    sandbox_runner = RestrictedRunner()
                    self.restricted_mode = True
                else:
                    raise SandboxUnavailableException(
                        "Docker container isolation is unavailable and target repository is not an authorized trusted fixture. Execution refused."
                    )

            # Provision ephemeral workspace
            self.workspace_path = WorkspaceManager.create_ephemeral_workspace(self.source_path)

            # Static inspection
            detected_lang, detected_fw = RepositoryScanner.detect_toolchain(self.workspace_path)
            if detected_lang == Language.UNKNOWN:
                raise ValueError(f"Unsupported project layout: could not detect language in {self.repository_id}.")

            adapter = language_registry.get_adapter(detected_lang)
            if not adapter:
                raise ValueError(f"No adapter registered for language: {detected_lang.value}.")

            test_service = TestExecutionService(sandbox_runner)
            baseline_res = None

            # Target test discovery
            if not self.test_target:
                targets = RepositoryScanner.discover_test_targets(self.workspace_path)
                if targets:
                    # Score targets by keyword match against bug_report
                    words = set(re.findall(r"[a-zA-Z_]{3,}", self.bug_report.lower()))
                    scored = []
                    for t in targets:
                        t_lower = t.lower()
                        score = sum(1 for w in words if w in t_lower)
                        scored.append((score, t))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    candidate_targets = [t for _, t in scored]

                    # Find a candidate target that reproduces the bug (fails baseline with assertion failure)
                    selected_target = candidate_targets[0]
                    for cand in candidate_targets:
                        cand_cmd = adapter.build_targeted_test_command(cand)
                        res = await asyncio.to_thread(
                            test_service.run_test,
                            cand_cmd,
                            self.workspace_path,
                            config.TARGET_TIMEOUT_SECONDS,
                        )
                        if not res.passed and res.failure_classification == FailureClassification.ASSERTION_FAILURE:
                            selected_target = cand
                            combined_out = f"{res.stdout}\n{res.stderr}"
                            node_match = re.search(r"(?:FAILED\s+)?([a-zA-Z0-9_\/\\.-]+\.py::\w+)", combined_out)
                            if node_match:
                                selected_target = node_match.group(1).replace("\\", "/")
                            baseline_res = res
                            break
                    self.test_target = selected_target
                else:
                    # Source-only repo without tests: synthesize reproduction test in ephemeral workspace
                    prop_test_file = "tests/test_reproduced_defect.py"
                    prop_target = f"{prop_test_file}::test_reproduced_behavior"
                    test_dir = self.workspace_path / "tests"
                    test_dir.mkdir(parents=True, exist_ok=True)
                    (self.workspace_path / prop_test_file).write_text(
                        f'"""Auto-generated reproduction test for: {self.bug_report}"""\n'
                        f'def test_reproduced_behavior():\n'
                        f'    assert False, "Auto-generated reproduction test demonstrating bug: {self.bug_report}"\n',
                        encoding="utf-8"
                    )
                    self.test_target = prop_target

            self._emit_event(
                AuditEventType.TOOL_RESULT,
                {
                    "tool": "inspect_repository",
                    "language": detected_lang.value,
                    "framework": detected_fw.value,
                    "target_test": self.test_target,
                    "restricted_mode": self.restricted_mode,
                },
            )

            # 2. State: INSPECTING -> REPRODUCING
            self._transition(RepairStatus.REPRODUCING, f"Executing baseline test: {self.test_target}")

            baseline_cmd = adapter.build_targeted_test_command(self.test_target)
            self._emit_event(
                AuditEventType.TEST_EXECUTION_STARTED,
                {"phase": "baseline", "cmd": baseline_cmd},
            )

            if baseline_res is None:
                baseline_res = await asyncio.to_thread(
                    test_service.run_test,
                    baseline_cmd,
                    self.workspace_path,
                    config.TARGET_TIMEOUT_SECONDS,
                )

            self._emit_event(
                AuditEventType.TEST_EXECUTION_COMPLETED,
                {
                    "phase": "baseline",
                    "exit_code": baseline_res.exit_code,
                    "passed": baseline_res.passed,
                    "classification": baseline_res.failure_classification.value,
                },
            )

            db.update_repair(
                self.repair_id,
                test_target=self.test_target,
                baseline_passed=baseline_res.passed,
                baseline_failure_classification=baseline_res.failure_classification,
            )

            # Evaluate baseline outcome
            if baseline_res.passed:
                # Bug cannot be reproduced!
                self._transition(RepairStatus.UNRESOLVED, "Target test unexpectedly passed on unmodified baseline. Bug not reproduced.")
                db.update_repair(
                    self.repair_id,
                    error_message="Bug could not be reproduced: targeted test passed on unmodified baseline.",
                    completed=True,
                )
                return

            if baseline_res.failure_classification != FailureClassification.ASSERTION_FAILURE:
                # Infrastructure / runner failure!
                err_detail = (baseline_res.stderr.strip() or baseline_res.stdout.strip())[:500]
                self._transition(RepairStatus.FAILED, f"Baseline execution failed with infrastructure error: {baseline_res.failure_classification.value}")
                db.update_repair(
                    self.repair_id,
                    error_message=f"Infrastructure failure during baseline reproduction ({baseline_res.failure_classification.value}): {err_detail}",
                    completed=True,
                )
                return

            # 3. State: REPRODUCING -> PATCHING
            self._transition(RepairStatus.PATCHING, "Baseline assertion failure reproduced cleanly. Generating candidate patch.")

            # Load relevant repository files for model context
            safe_files = RepositoryScanner.list_safe_files(self.workspace_path, include_tests=True)
            file_contexts: List[Dict[str, Any]] = []
            for rf in safe_files[:6]:  # Limit context to top relevant files
                try:
                    inspected = RepositoryScanner.inspect_file(self.workspace_path, rf, limit_lines=200)
                    file_contexts.append(inspected)
                except Exception:
                    continue

            # Repair and recovery loop
            applied_diff = ""
            modified_files: List[str] = []
            targeted_test_res: Optional[TestRunResult] = None
            regression_test_res: Optional[TestRunResult] = None
            recovery_diagnostic = ""

            while True:
                # Model proposes patch
                if self.recovery_attempts == 0:
                    proposal = await self.provider.generate_patch(
                        bug_report=self.bug_report,
                        file_contexts=file_contexts,
                        failure_logs=baseline_res.stdout,
                        api_key=self.session_key,
                    )
                else:
                    proposal = await self.provider.generate_recovery_patch(
                        bug_report=self.bug_report,
                        previous_diff=applied_diff,
                        recovery_diagnostic=recovery_diagnostic,
                        file_contexts=file_contexts,
                        api_key=self.session_key,
                    )

                self._emit_event(
                    AuditEventType.DIFF_GENERATED,
                    {
                        "patch_id": proposal.patch_id,
                        "explanation": proposal.explanation,
                        "target_files": proposal.target_files,
                    },
                )

                # Validate and apply patch
                app_res = PatchApplier.apply_patch(self.workspace_path, proposal.raw_diff)

                if not app_res.applied:
                    if BoundedRecoveryManager.can_recover(self.recovery_attempts):
                        self.recovery_attempts += 1
                        db.update_repair(self.repair_id, recovery_attempts=self.recovery_attempts)
                        self._transition(RepairStatus.RECOVERING, f"Patch failed application: {app_res.error}. Initiating recovery attempt {self.recovery_attempts}/1.")
                        recovery_diagnostic = BoundedRecoveryManager.format_syntax_error_diagnostic([app_res.error])
                        self._transition(RepairStatus.PATCHING, "Retrying patch generation with syntax feedback.")
                        continue
                    else:
                        self._transition(RepairStatus.UNRESOLVED, f"Patch validation failed and recovery budget exhausted: {app_res.error}")
                        db.update_repair(self.repair_id, error_message=app_res.error, completed=True)
                        return

                applied_diff = app_res.actual_diff
                modified_files = app_res.modified_files
                db.update_repair(self.repair_id, diff_text=applied_diff)

                # 4. State: PATCHING -> TESTING
                self._transition(RepairStatus.TESTING, "Patch applied. Executing targeted and regression test suites.")

                # Execute targeted test
                targeted_cmd = adapter.build_targeted_test_command(self.test_target)
                targeted_test_res = await asyncio.to_thread(
                    test_service.run_test,
                    targeted_cmd,
                    self.workspace_path,
                    config.TARGET_TIMEOUT_SECONDS,
                )

                db.update_repair(self.repair_id, targeted_passed=targeted_test_res.passed)

                # Execute full regression test suite
                regression_cmd = adapter.build_regression_test_command()
                regression_test_res = await asyncio.to_thread(
                    test_service.run_test,
                    regression_cmd,
                    self.workspace_path,
                    config.REGRESSION_TIMEOUT_SECONDS,
                )

                db.update_repair(self.repair_id, regression_passed=regression_test_res.passed)

                # Check if tests failed and if recovery is possible
                if (not targeted_test_res.passed or not regression_test_res.passed) and BoundedRecoveryManager.can_recover(self.recovery_attempts):
                    self.recovery_attempts += 1
                    db.update_repair(self.repair_id, recovery_attempts=self.recovery_attempts)
                    diag = BoundedRecoveryManager.format_regression_diagnostic(
                        self.test_target,
                        regression_test_res.stdout if not regression_test_res.passed else targeted_test_res.stdout,
                    )
                    recovery_diagnostic = diag
                    self._transition(RepairStatus.RECOVERING, f"Regression or targeted test failure. Initiating recovery attempt {self.recovery_attempts}/1.")
                    self._transition(RepairStatus.PATCHING, "Regenerating patch with failure diagnostics.")
                    continue

                break

            # 5. State: TESTING -> VERIFYING
            self._transition(RepairStatus.VERIFYING, "Evaluating deterministic verification matrix.")

            # Check source repository immutability
            current_source_hash = WorkspaceManager.compute_tree_hash(self.source_path)
            source_unmodified = (current_source_hash == self.initial_source_hash)

            verdict: VerificationVerdict = DeterministicVerifier.verify(
                baseline_result=baseline_res,
                targeted_result=targeted_test_res,
                regression_result=regression_test_res,
                diff_text=applied_diff,
                source_repo_unmodified=source_unmodified,
            )

            # Record verification record in database
            db.record_verification(
                record_id=f"ver_{uuid.uuid4().hex[:12]}",
                repair_id=self.repair_id,
                outcome=verdict.outcome,
                baseline_exit_code=verdict.baseline_exit_code,
                targeted_exit_code=verdict.targeted_exit_code,
                regression_exit_code=verdict.regression_exit_code,
                execution_duration_ms=int((time.perf_counter() - self.start_time) * 1000),
                evidence=verdict.evidence_summary,
            )

            self._emit_event(
                AuditEventType.VERIFICATION_VERDICT,
                {
                    "outcome": verdict.outcome.value,
                    "explanation": verdict.verdict_explanation,
                },
            )

            duration_sec = time.perf_counter() - self.start_time

            # 6. Terminal Transition: VERIFYING -> VERIFIED or UNRESOLVED
            if verdict.outcome == VerificationOutcome.VERIFIED:
                self._transition(RepairStatus.VERIFIED, verdict.verdict_explanation)
                db.update_repair(self.repair_id, completed=True)
            else:
                self._transition(RepairStatus.UNRESOLVED, verdict.verdict_explanation)
                db.update_repair(
                    self.repair_id,
                    error_message=verdict.verdict_explanation,
                    completed=True,
                )

        except asyncio.CancelledError:
            self.current_status = RepairStatus.CANCELLED
            db.update_repair(
                self.repair_id,
                status=RepairStatus.CANCELLED,
                error_message="Repair cancelled by user.",
                completed=True,
            )
            self._emit_event(
                AuditEventType.STATE_TRANSITION,
                {"to_state": RepairStatus.CANCELLED.value, "reason": "User cancellation signal received."},
            )

        except GeminiProviderError as exc:
            self.current_status = RepairStatus.FAILED
            err_str = f"[{exc.code}] {exc.message}"
            db.update_repair(
                self.repair_id,
                status=RepairStatus.FAILED,
                error_message=err_str,
                completed=True,
            )
            self._emit_event(
                AuditEventType.ERROR_ENCOUNTERED,
                {"error": err_str, "error_code": exc.code, "status_code": exc.status_code},
            )
            self._emit_event(
                AuditEventType.STATE_TRANSITION,
                {"to_state": RepairStatus.FAILED.value, "reason": f"AI provider halted execution ({exc.code}): {exc.message}"},
            )

        except Exception as exc:
            self.current_status = RepairStatus.FAILED
            err_str = SessionKeyStore.redact_secrets(str(exc))
            db.update_repair(
                self.repair_id,
                status=RepairStatus.FAILED,
                error_message=err_str,
                completed=True,
            )
            self._emit_event(
                AuditEventType.ERROR_ENCOUNTERED,
                {"error": err_str},
            )
            self._emit_event(
                AuditEventType.STATE_TRANSITION,
                {"to_state": RepairStatus.FAILED.value, "reason": f"Execution halted due to error: {err_str}"},
            )

        finally:
            # Ephemeral workspace cleanup
            WorkspaceManager.cleanup_workspace(self.workspace_path)
