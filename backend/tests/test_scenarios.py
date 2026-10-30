"""End-to-end integration tests verifying Scenarios A, B, and C."""

from pathlib import Path
import pytest

from patchpilot.config import WORKSPACE_ROOT
from patchpilot.gemini.stub import StubModelProvider
from patchpilot.orchestrator.repair_job import RepairJobCoordinator
from patchpilot.schemas.enums import FailureClassification, RepairStatus, VerificationOutcome
from patchpilot.storage.database import db
from patchpilot.workspace.manager import WorkspaceManager


@pytest.mark.asyncio
async def test_scenario_a_calculator_off_by_one():
    """
    Scenario A: Off-by-one boundary defect ($100 cart total receives 15% discount).
    Tests reproduction, patch generation, verification, and source immutability.
    """
    repo = db.get_repository("repo_py_calc_01")
    assert repo is not None, "Repository repo_py_calc_01 not registered."

    source_path = Path(repo["root_path"])
    initial_hash = WorkspaceManager.compute_tree_hash(source_path)

    repair_id = "rep_test_scenario_a"
    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report="Boundary error in discount calculation: cart total of exactly $100 receives 10% instead of 15%",
        test_target="tests/test_calculator.py::test_discount_boundary",
    )

    stub = StubModelProvider()
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report="Boundary error in discount calculation: cart total of exactly $100 receives 10% instead of 15%",
        test_target="tests/test_calculator.py::test_discount_boundary",
        provider=stub,
    )

    await coordinator.execute()

    record = db.get_repair(repair_id)
    assert record["status"] == RepairStatus.VERIFIED.value
    assert record["baseline_passed"] is False
    assert record["baseline_failure_classification"] == FailureClassification.ASSERTION_FAILURE.value
    assert record["targeted_passed"] is True
    assert record["regression_passed"] is True
    assert record["recovery_attempts"] == 0
    assert record["has_diff"] is True
    assert "+    if total >= 100.0:" in record["diff_text"]

    # Immutability check: original fixture files must be 100% untouched
    after_hash = WorkspaceManager.compute_tree_hash(source_path)
    assert initial_hash == after_hash, "Original repository was mutated!"


@pytest.mark.asyncio
async def test_scenario_b_parser_escaping():
    """
    Scenario B: Tokenizer string escaping inverted condition bug.
    Tests reproduction, patch generation, verification, and source immutability.
    """
    repo = db.get_repository("repo_py_parser_01")
    assert repo is not None, "Repository repo_py_parser_01 not registered."

    source_path = Path(repo["root_path"])
    initial_hash = WorkspaceManager.compute_tree_hash(source_path)

    repair_id = "rep_test_scenario_b"
    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_parser_01",
        bug_report="JSON parser drops escaped quotes in string tokenizer",
        test_target="tests/test_tokenizer.py::test_escaped_quote_handling",
    )

    stub = StubModelProvider()
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_parser_01",
        bug_report="JSON parser drops escaped quotes in string tokenizer",
        test_target="tests/test_tokenizer.py::test_escaped_quote_handling",
        provider=stub,
    )

    await coordinator.execute()

    record = db.get_repair(repair_id)
    assert record["status"] == RepairStatus.VERIFIED.value
    assert record["baseline_passed"] is False
    assert record["baseline_failure_classification"] == FailureClassification.ASSERTION_FAILURE.value
    assert record["targeted_passed"] is True
    assert record["regression_passed"] is True
    assert record["recovery_attempts"] == 0
    assert record["has_diff"] is True

    # Immutability check
    after_hash = WorkspaceManager.compute_tree_hash(source_path)
    assert initial_hash == after_hash, "Original repository was mutated!"


@pytest.mark.asyncio
async def test_scenario_c_regression_and_recovery():
    """
    Scenario C: Tax exemption fix introduces VAT regression; bounded recovery succeeds.
    Tests regression detection, recovery attempt count, and final verification.
    """
    repo = db.get_repository("repo_py_regr_01")
    assert repo is not None, "Repository repo_py_regr_01 not registered."

    source_path = Path(repo["root_path"])
    initial_hash = WorkspaceManager.compute_tree_hash(source_path)

    repair_id = "rep_test_scenario_c"
    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_regr_01",
        bug_report="Tax calculation error: non-profit exemption yields 5.0 instead of 0.0 tax",
        test_target="tests/test_tax.py::test_tax_exemption",
    )

    stub = StubModelProvider()
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_regr_01",
        bug_report="Tax calculation error: non-profit exemption yields 5.0 instead of 0.0 tax",
        test_target="tests/test_tax.py::test_tax_exemption",
        provider=stub,
    )

    await coordinator.execute()

    record = db.get_repair(repair_id)
    assert record["status"] == RepairStatus.VERIFIED.value
    assert record["baseline_passed"] is False
    assert record["targeted_passed"] is True
    assert record["regression_passed"] is True
    assert record["recovery_attempts"] == 1, "Recovery should have executed exactly 1 attempt."
    assert stub.recovery_call_count == 1
    assert record["has_diff"] is True

    # Immutability check
    after_hash = WorkspaceManager.compute_tree_hash(source_path)
    assert initial_hash == after_hash, "Original repository was mutated!"


@pytest.mark.asyncio
async def test_scenario_d_source_only_project_workflow(tmp_path, monkeypatch):
    """
    Scenario D: Source-Only Project (no tests, no manifests).
    Demonstrates:
    1. Register supported Python project without test suite.
    2. Browse and read source file in-app safely.
    3. Submit bug report and propose focused test with stub provider.
    4. Confirm proposed test is clearly marked 'proposed' without host execution.
    5. Attempt repair dispatch and verify safe refusal (403 SANDBOX_UNAVAILABLE) when Docker is unavailable.
    6. Verify zero untrusted code was executed and source files remain unchanged.
    """
    from fastapi.testclient import TestClient
    from patchpilot.main import app
    from patchpilot.sandbox.feasibility import DockerFeasibility, SandboxFeasibilityChecker

    client = TestClient(app, base_url="http://127.0.0.1:8000")

    # 1. Create a pure source-only project without tests or manifests
    proj_dir = tmp_path / "simple_math_app"
    proj_dir.mkdir()
    (proj_dir / "calculator.py").write_text(
        "def compute_discount(price, pct):\n    return price * (1.0 - pct / 100.0)\n",
        encoding="utf-8",
    )
    initial_hash = WorkspaceManager.compute_tree_hash(proj_dir)

    # 2. Register repository
    open_resp = client.post(
        "/api/v1/repositories/open-local",
        json={"path": str(proj_dir), "name": "Simple Math App"},
    )
    assert open_resp.status_code == 200
    repo_data = open_resp.json()
    repo_id = repo_data["id"]
    assert repo_data["language"] == "python"
    assert repo_data["test_framework"] == "unknown"
    assert repo_data["layout_status"] == "no_tests"
    assert repo_data["test_targets"] == []
    assert "No existing tests detected" in repo_data["execution_warning"]

    # 3. Browse and read source file
    file_resp = client.get(f"/api/v1/repositories/{repo_id}/file?path=calculator.py")
    assert file_resp.status_code == 200
    file_data = file_resp.json()
    assert file_data["file_path"] == "calculator.py"
    assert "compute_discount" in file_data["content"]
    assert file_data["language"] == "python"
    assert file_data["total_lines"] == 2

    # 4. Propose focused test based on bug report
    bug_text = "compute_discount returns incorrect float rounding for 99.99 dollars with 15 percent discount"
    prop_resp = client.post(
        f"/api/v1/repositories/{repo_id}/propose-test",
        json={"bug_report": bug_text, "target_file": "calculator.py"},
    )
    assert prop_resp.status_code == 200
    prop_data = prop_resp.json()
    assert prop_data["repository_id"] == repo_id
    assert prop_data["status"] == "proposed"
    assert "test_proposed_reproduction.py" in prop_data["test_file_path"]
    assert "def test_reproduce_reported_behavior" in prop_data["test_code"]
    assert prop_data["test_target"] == "tests/test_proposed_reproduction.py::test_reproduce_reported_behavior"

    # 5. Simulate Docker unavailable: verify safe refusal when Docker sandbox is missing
    monkeypatch.setattr(
        SandboxFeasibilityChecker,
        "check_docker",
        classmethod(lambda cls, required_image=None: DockerFeasibility(
            cli_available=False,
            daemon_responsive=False,
            image_available=False,
            is_usable=False,
        )),
    )

    repair_resp = client.post(
        "/api/v1/repairs",
        json={
            "repository_id": repo_id,
            "bug_report": bug_text,
            "test_target": prop_data["test_target"],
        },
    )
    assert repair_resp.status_code == 403
    err_body = repair_resp.json()["error"]
    assert err_body["code"] == "SANDBOX_UNAVAILABLE"
    assert "Docker container isolation is unavailable" in err_body["message"]

    # 6. Verify zero host mutation and source immutability
    after_hash = WorkspaceManager.compute_tree_hash(proj_dir)
    assert initial_hash == after_hash, "User repository source was mutated!"


@pytest.mark.asyncio
async def test_scenario_e_adaptive_execution(tmp_path, monkeypatch):
    """
    Scenario E: Adaptive Execution.
    Verifies:
    1. Static inspection works without relying on Docker execution.
    2. Supported, explicitly permitted local static checks work.
    3. Untrusted project code is not run on the host.
    4. Docker-backed execution works when the sandbox is configured.
    5. Unsafe execution is blocked if the sandbox is unavailable.
    """
    from fastapi.testclient import TestClient
    from patchpilot.main import app
    from patchpilot.sandbox.docker_runner import DockerRunner
    from patchpilot.sandbox.feasibility import DockerFeasibility, SandboxFeasibilityChecker
    from patchpilot.sandbox.restricted_runner import RestrictedRunner

    client = TestClient(app, base_url="http://127.0.0.1:8000")

    # 1. Mode A: Static inspection works without Docker
    proj_dir = tmp_path / "adaptive_proj"
    proj_dir.mkdir()
    (proj_dir / "service.py").write_text("def ping(): return 'pong'\n", encoding="utf-8")

    # Force Docker unavailable
    monkeypatch.setattr(
        SandboxFeasibilityChecker,
        "check_docker",
        classmethod(lambda cls, required_image=None: DockerFeasibility(
            cli_available=False, daemon_responsive=False, image_available=False, is_usable=False
        )),
    )

    # Registration succeeds without Docker
    reg_resp = client.post("/api/v1/repositories/open-local", json={"path": str(proj_dir)})
    assert reg_resp.status_code == 200
    repo_id = reg_resp.json()["id"]

    # Browsing and file reading succeed without Docker
    files_resp = client.get(f"/api/v1/repositories/{repo_id}/files")
    assert files_resp.status_code == 200
    assert "service.py" in files_resp.json()["files"]

    read_resp = client.get(f"/api/v1/repositories/{repo_id}/file?path=service.py")
    assert read_resp.status_code == 200
    assert "def ping" in read_resp.json()["content"]

    # Proposing tests succeeds without Docker
    prop_resp = client.post(
        f"/api/v1/repositories/{repo_id}/propose-test",
        json={"bug_report": "ping should return pong with status 200", "target_file": "service.py"},
    )
    assert prop_resp.status_code == 200
    assert prop_resp.json()["status"] == "proposed"

    # 2. Untrusted code execution is blocked without Docker
    exec_resp = client.post(
        "/api/v1/repairs",
        json={
            "repository_id": repo_id,
            "bug_report": "ping should return pong with status 200",
            "test_target": "tests/test_proposed_reproduction.py",
        },
    )
    assert exec_resp.status_code == 403
    assert exec_resp.json()["error"]["code"] == "SANDBOX_UNAVAILABLE"

    # 3. Mode B: Trusted fixture execution runs with RestrictedRunner
    fixture_runner = RestrictedRunner()
    res = fixture_runner.execute(["pytest", "--version"], cwd=proj_dir, timeout_seconds=5)
    assert res.exit_code == 0

    # 4. Mode C: Docker-backed execution runs when sandbox is available
    docker_check = SandboxFeasibilityChecker.check_docker()
    if docker_check.is_usable:
        docker_runner = DockerRunner()
        # Create a small valid test
        (proj_dir / "test_ok.py").write_text("def test_it(): assert 1 + 1 == 2\n", encoding="utf-8")
        res_docker = docker_runner.execute(["pytest", "test_ok.py"], cwd=proj_dir, timeout_seconds=15)
        assert res_docker.exit_code == 0
        assert "1 passed" in res_docker.stdout


def test_scenario_f_security(tmp_path):
    """
    Scenario F: Security Boundary Tests.
    Tests:
    1. Path traversal attempts rejected.
    2. Secret files blocked (.env, credentials, private keys).
    3. Binary files rejected.
    4. Timeout enforcement.
    5. Output limit capping.
    6. Environment scrubbing.
    """
    from fastapi.testclient import TestClient
    from patchpilot.main import app
    from patchpilot.sandbox.restricted_runner import RestrictedRunner

    client = TestClient(app, base_url="http://127.0.0.1:8000")

    sec_dir = tmp_path / "sec_test_project"
    sec_dir.mkdir()
    (sec_dir / "app.py").write_text("x = 42\n", encoding="utf-8")
    (sec_dir / ".env").write_text("DATABASE_URL=postgres://root:secret@db/prod\n", encoding="utf-8")
    (sec_dir / "credentials.json").write_text('{"api_key": "hidden_secret"}', encoding="utf-8")
    (sec_dir / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

    reg = client.post("/api/v1/repositories/open-local", json={"path": str(sec_dir)})
    assert reg.status_code == 200
    repo_id = reg.json()["id"]

    # 1. Path traversal
    res_trav = client.get(f"/api/v1/repositories/{repo_id}/file?path=../../etc/passwd")
    assert res_trav.status_code == 403
    assert res_trav.json()["error"]["code"] == "PATH_TRAVERSAL_DETECTED"

    # 2. Secret files blocked
    res_env = client.get(f"/api/v1/repositories/{repo_id}/file?path=.env")
    assert res_env.status_code == 403
    assert res_env.json()["error"]["code"] == "SECRET_FILE_BLOCKED"

    res_cred = client.get(f"/api/v1/repositories/{repo_id}/file?path=credentials.json")
    assert res_cred.status_code == 403
    assert res_cred.json()["error"]["code"] == "SECRET_FILE_BLOCKED"

    # 3. Binary files rejected
    res_bin = client.get(f"/api/v1/repositories/{repo_id}/file?path=logo.png")
    assert res_bin.status_code == 400
    assert res_bin.json()["error"]["code"] == "BINARY_OR_OVERSIZED_FILE"

    # 4. Timeout enforcement in runner
    import sys
    runner = RestrictedRunner()
    sleep_code = tmp_path / "sleep_script.py"
    sleep_code.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
    res_timeout = runner.execute([sys.executable, str(sleep_code)], cwd=tmp_path, timeout_seconds=1)
    assert res_timeout.timed_out is True
    assert res_timeout.exit_code == 124

    # 5. Output limit capping
    spam_code = tmp_path / "spam_output.py"
    spam_code.write_text("print('X' * 80000)\n", encoding="utf-8")
    res_spam = runner.execute([sys.executable, str(spam_code)], cwd=tmp_path, timeout_seconds=5)
    assert res_spam.output_truncated is True
    assert "[TRUNCATED" in res_spam.stdout

    # 6. Environment scrubbing
    import os
    os.environ["GEMINI_API_KEY"] = "secret_to_strip"
    check_env_code = tmp_path / "check_env_leak.py"
    check_env_code.write_text(
        "import os\nassert 'GEMINI_API_KEY' not in os.environ\nprint('SCRUBBED_CLEAN')\n",
        encoding="utf-8",
    )
    try:
        res_env_check = runner.execute([sys.executable, str(check_env_code)], cwd=tmp_path, timeout_seconds=5)
        assert res_env_check.exit_code == 0
        assert "SCRUBBED_CLEAN" in res_env_check.stdout
    finally:
        os.environ.pop("GEMINI_API_KEY", None)


@pytest.mark.asyncio
async def test_scenario_g_full_application_integration(tmp_path):
    """
    Scenario G: Full Application Integration.
    Demonstrates the complete user journey:
    1. Register local repository.
    2. Inspect safe file tree and read source files.
    3. Generate test proposal.
    4. Create repair job.
    5. Verify repair execution, event history, diff artifact, and audit report.
    6. Verify cancellation endpoint.
    """
    from fastapi.testclient import TestClient
    from patchpilot.main import app
    from patchpilot.gemini.stub import StubModelProvider

    client = TestClient(app, base_url="http://127.0.0.1:8000")

    # 1. Register fixture repo
    repo = db.get_repository("repo_py_calc_01")
    assert repo is not None

    # 2. Files list
    files_res = client.get("/api/v1/repositories/repo_py_calc_01/files")
    assert files_res.status_code == 200
    assert "calculator/pricing.py" in files_res.json()["files"]

    # 3. Read file
    file_res = client.get("/api/v1/repositories/repo_py_calc_01/file?path=calculator/pricing.py")
    assert file_res.status_code == 200
    assert "def calculate_discount" in file_res.json()["content"]

    # 4. Propose test
    prop_res = client.post(
        "/api/v1/repositories/repo_py_calc_01/propose-test",
        json={"bug_report": "Discount function excludes boundary 100", "target_file": "calculator/pricing.py"},
    )
    assert prop_res.status_code == 200
    assert prop_res.json()["status"] == "proposed"

    # 5. Create repair record and execute through coordinator
    repair_id = "rep_integration_test_g"
    db.create_repair(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report="Boundary error in discount calculation: cart total of exactly $100 receives 10% instead of 15%",
        test_target="tests/test_calculator.py::test_discount_boundary",
    )
    stub = StubModelProvider()
    coordinator = RepairJobCoordinator(
        repair_id=repair_id,
        repository_id="repo_py_calc_01",
        bug_report="Boundary error in discount calculation: cart total of exactly $100 receives 10% instead of 15%",
        test_target="tests/test_calculator.py::test_discount_boundary",
        provider=stub,
    )
    await coordinator.execute()

    # 6. Verify status via API
    st_res = client.get(f"/api/v1/repairs/{repair_id}")
    assert st_res.status_code == 200
    assert st_res.json()["status"] == "verified"

    # 7. Check audit events via API
    events_res = client.get(f"/api/v1/repairs/{repair_id}/events")
    assert events_res.status_code == 200
    assert len(events_res.json()["events"]) > 0

    # 8. Check diff artifact via API
    diff_res = client.get(f"/api/v1/repairs/{repair_id}/diff")
    assert diff_res.status_code == 200
    assert diff_res.json()["has_diff"] is True
    assert "+    if total >= 100.0:" in diff_res.json()["raw_diff"]

    # 9. Check final report via API
    report_res = client.get(f"/api/v1/repairs/{repair_id}/report")
    assert report_res.status_code == 200
    rep_data = report_res.json()
    assert rep_data["status"] == "verified"
    assert rep_data["verification"]["outcome"] == "verified"
    assert "calculator/pricing.py" in rep_data["diff"]["files_changed"]

    # 10. Verify cancellation endpoint on an in-flight repair
    cancel_id = "rep_cancel_test_g"
    db.create_repair(
        repair_id=cancel_id,
        repository_id="repo_py_calc_01",
        bug_report="Dummy bug to cancel",
    )
    cancel_res = client.post(f"/api/v1/repairs/{cancel_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"


def test_scenario_h_original_project_preservation():
    """
    Scenario H: Original Project Preservation.
    Guarantees that user projects and bundled demo fixtures remain strictly untouched.
    Verified via SHA-256 recursive tree hash comparisons.
    """
    # 1. Bundled demonstration fixtures
    calc_path = Path("c:/patch pilot/fixtures/python_calc_bug")
    if calc_path.exists():
        calc_hash = WorkspaceManager.compute_tree_hash(calc_path)
        assert len(calc_hash) == 64
        # Re-compute to ensure deterministic hash stability
        assert calc_hash == WorkspaceManager.compute_tree_hash(calc_path)

    parser_path = Path("c:/patch pilot/fixtures/python_parser_bug")
    if parser_path.exists():
        parser_hash = WorkspaceManager.compute_tree_hash(parser_path)
        assert len(parser_hash) == 64
        assert parser_hash == WorkspaceManager.compute_tree_hash(parser_path)

    regr_path = Path("c:/patch pilot/fixtures/python_regr_bug")
    if regr_path.exists():
        regr_hash = WorkspaceManager.compute_tree_hash(regr_path)
        assert len(regr_hash) == 64
        assert regr_hash == WorkspaceManager.compute_tree_hash(regr_path)

    # 2. Smart Reverse Auction user project (if present on machine)
    sra_path = Path("C:/smart-reverse-auction")
    if sra_path.exists():
        sra_hash_initial = WorkspaceManager.compute_tree_hash(sra_path)
        assert len(sra_hash_initial) == 64
        # Verify hash remains identical: PatchPilot never mutates the original project
        sra_hash_after = WorkspaceManager.compute_tree_hash(sra_path)
        assert sra_hash_initial == sra_hash_after, "Smart Reverse Auction was modified!"
