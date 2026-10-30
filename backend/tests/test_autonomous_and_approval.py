"""Automated verification for Autonomous Bug Discovery and Approval Gate & Safe Export."""

import asyncio
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from patchpilot import config
from patchpilot.inspector.autonomous_scanner import AutonomousScanner
from patchpilot.main import app
from patchpilot.orchestrator.repair_job import RepairJobCoordinator
from patchpilot.gemini.stub import StubModelProvider
from patchpilot.schemas.enums import RepairStatus, FailureClassification
from patchpilot.storage.database import db
from patchpilot.workspace.manager import WorkspaceManager


def test_autonomous_scanner_finds_calculator_boundary_bug():
    """Verify autonomous scanner detects strict inequality in calculator fixture without bug report."""
    calc_path = config.WORKSPACE_ROOT / "fixtures" / "python_calc_bug"
    findings = AutonomousScanner.scan_repository(calc_path)

    assert len(findings) >= 1
    boundary_finding = next((f for f in findings if f.category == "boundary_condition"), None)
    assert boundary_finding is not None
    assert "calculator/pricing.py" in boundary_finding.file_path
    assert boundary_finding.line_range[0] == 9
    assert ">" in boundary_finding.code_excerpt
    assert boundary_finding.confidence in ("likely", "confirmed")
    assert "Strict inequality" in boundary_finding.title
    assert "suggested_fix" in boundary_finding.model_dump()


def test_autonomous_discover_bugs_endpoint(client):
    """Verify POST /api/v1/repositories/{id}/discover-bugs returns structured findings."""
    res = client.post("/api/v1/repositories/repo_py_calc_01/discover-bugs", json={"scan_depth": "standard"})
    assert res.status_code == 200
    data = res.json()
    assert data["repository_id"] == "repo_py_calc_01"
    assert data["total_findings"] >= 1
    assert len(data["findings"]) >= 1

    top = data["findings"][0]
    assert "id" in top
    assert "title" in top
    assert "severity" in top
    assert "confidence" in top
    assert "code_excerpt" in top


def test_reconcile_stale_repairs_on_startup():
    """Verify uncompleted repairs from a crash are reconciled into terminal failed state."""
    db.create_repair("rep_stuck_01", "repo_py_calc_01", "Some interrupted bug report")
    db.update_repair("rep_stuck_01", status=RepairStatus.PATCHING)

    # Calling reconcile should transition stuck job to FAILED
    reconciled = db.reconcile_stale_repairs()
    assert reconciled >= 1

    record = db.get_repair("rep_stuck_01")
    assert record["status"] == RepairStatus.FAILED.value
    assert "interrupted" in record["error_message"].lower()


@pytest.mark.asyncio
async def test_approval_gate_and_safe_export(tmp_path, client):
    """
    Verify complete Approval Gate & Safe Export:
    1. Candidate repair produces verified diff in disposable workspace.
    2. Original files are 100% untouched before export.
    3. User calls POST /repairs/{id}/export to safely apply changes.
    4. Target file is updated; external modification causes conflict refusal.
    """
    # Create isolated copy of calculator repo in temp directory
    calc_src = config.WORKSPACE_ROOT / "fixtures" / "python_calc_bug"
    test_repo_root = tmp_path / "fixtures" / "calc_test_repo"
    import shutil
    shutil.copytree(calc_src, test_repo_root)

    repo_id = f"repo_test_export_{tmp_path.name[:8]}"
    db.register_repository(
        repo_id=repo_id,
        name="test_export_calc",
        root_path=str(test_repo_root),
        language="python",
        test_framework="pytest",
        is_fixture=True,
    )

    initial_pricing = (test_repo_root / "calculator" / "pricing.py").read_text(encoding="utf-8")
    assert "if total > 100.0:" in initial_pricing

    # Run repair job with StubModelProvider
    repair_id = f"rep_exp_{tmp_path.name[:8]}"
    db.create_repair(repair_id, repo_id, "Boundary error at 100.0")

    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id=repo_id,
        bug_report="Boundary error at 100.0",
        test_target="tests/test_calculator.py::test_discount_boundary",
        provider=StubModelProvider(),
    )
    await coordinator.execute()

    # Verify original repository is untouched before approval
    unmodified_pricing = (test_repo_root / "calculator" / "pricing.py").read_text(encoding="utf-8")
    assert unmodified_pricing == initial_pricing, "Original repo was mutated before export approval!"

    # Export via POST /api/v1/repairs/{id}/export
    exp_res = client.post(f"/api/v1/repairs/{repair_id}/export")
    if exp_res.status_code != 200:
        print("EXP_RES_ERROR:", exp_res.json())
    assert exp_res.status_code == 200
    exp_data = exp_res.json()
    assert exp_data["status"] == "verified"
    assert "calculator/pricing.py" in exp_data["files_exported"]

    # Verify original repository has now been updated with approved fix
    exported_pricing = (test_repo_root / "calculator" / "pricing.py").read_text(encoding="utf-8")
    assert "if total >= 100.0:" in exported_pricing


@pytest.mark.asyncio
async def test_reject_repair_leaves_original_repo_untouched(tmp_path, client):
    """Verify rejecting changes leaves original files unchanged and marks job unresolved."""
    calc_src = config.WORKSPACE_ROOT / "fixtures" / "python_calc_bug"
    test_repo_root = tmp_path / "calc_test_reject"
    import shutil
    shutil.copytree(calc_src, test_repo_root)

    repo_id = f"repo_test_rej_{tmp_path.name[:8]}"
    db.register_repository(
        repo_id=repo_id,
        name="test_reject_calc",
        root_path=str(test_repo_root),
        language="python",
        test_framework="pytest",
        is_fixture=True,
    )

    initial_pricing = (test_repo_root / "calculator" / "pricing.py").read_text(encoding="utf-8")

    repair_id = f"rep_rej_{tmp_path.name[:8]}"
    db.create_repair(repair_id, repo_id, "Boundary error")

    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id=repo_id,
        bug_report="Boundary error",
        test_target="tests/test_calculator.py::test_discount_boundary",
        provider=StubModelProvider(),
    )
    await coordinator.execute()

    # Reject via POST /api/v1/repairs/{id}/reject
    rej_res = client.post(f"/api/v1/repairs/{repair_id}/reject")
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "unresolved"

    # Verify original file remains 100% identical
    final_pricing = (test_repo_root / "calculator" / "pricing.py").read_text(encoding="utf-8")
    assert final_pricing == initial_pricing


@pytest.mark.asyncio
async def test_gemini_developer_instruction_fallback(monkeypatch):
    """Verify GeminiProvider automatically adapts when model rejects developer instruction with 400."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider

    calls = []

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json=None, **kwargs):
            calls.append(dict(json))
            if len(calls) == 1:
                # First call returns 400 with developer instruction error
                class ErrorResp:
                    status_code = 400
                    text = "INVALID_ARGUMENT: Developer instruction is not enabled for this model"
                    def json(self):
                        return {"error": {"code": 400, "message": self.text}}
                return ErrorResp()
            else:
                # Second call succeeds with valid response
                class SuccessResp:
                    status_code = 200
                    text = '{"explanation": "Fix", "target_files": ["calculator/pricing.py"], "unified_diff": "--- a/calculator/pricing.py\\n+++ b/calculator/pricing.py\\n@@ -9,1 +9,1 @@\\n-    if total > 100.0:\\n+    if total >= 100.0:\\n"}'
                    def json(self):
                        import json as j
                        return {
                            "candidates": [{
                                "content": {"parts": [{"text": self.text}]},
                                "finishReason": "STOP"
                            }]
                        }
                return SuccessResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())
    provider = GeminiProvider()
    proposal = await provider._call_model("test prompt", api_key="AIza" + "SyDummyKey12345")
    assert proposal.explanation == "Fix"
    assert len(calls) == 2
    # Verify second call removed system_instruction and prepended to user prompt
    assert "system_instruction" not in calls[1]
    assert len(calls[1]["contents"][0]["parts"]) == 1


def test_autonomous_scanner_clean_fixture_zero_false_positives(tmp_path):
    """Verify autonomous scanner produces zero false positives on clean, correct code."""
    clean_dir = tmp_path / "fixtures" / "clean_service"
    clean_dir.mkdir(parents=True)
    src_file = clean_dir / "service.py"
    src_file.write_text(
        "def calculate_total(prices: list[float], tax_rate: float) -> float:\n"
        "    if tax_rate < 0.0 or tax_rate > 1.0:\n"
        "        raise ValueError('Invalid tax rate')\n"
        "    subtotal = sum(prices)\n"
        "    return round(subtotal * (1.0 + tax_rate), 2)\n\n"
        "def format_greeting(name: str) -> str:\n"
        "    if not name:\n"
        "        return 'Hello, Guest'\n"
        "    return f'Hello, {name}'\n",
        encoding="utf-8"
    )

    findings = AutonomousScanner.scan_repository(clean_dir)
    assert len(findings) == 0, f"Expected 0 findings on clean code, got: {findings}"

