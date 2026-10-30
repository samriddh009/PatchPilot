"""Tests for user-selected local repositories: path validation, secret exclusion, layout discovery, and safe refusal."""

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from patchpilot.inspector.scanner import RepositoryScanner
from patchpilot.main import app
from patchpilot.schemas.enums import Language, TestFramework
from patchpilot.storage.database import db

client = TestClient(app, base_url="http://127.0.0.1:8000")


def test_open_local_nonexistent_path():
    """Verify opening a nonexistent path returns 404 PATH_NOT_FOUND."""
    resp = client.post(
        "/api/v1/repositories/open-local",
        json={"path": "C:/nonexistent/path/for/patchpilot_test_12345"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "PATH_NOT_FOUND"


def test_open_local_file_not_directory(tmp_path):
    """Verify opening a file path returns 422 INVALID_DIRECTORY."""
    test_file = tmp_path / "some_file.txt"
    test_file.write_text("Hello world", encoding="utf-8")

    resp = client.post(
        "/api/v1/repositories/open-local",
        json={"path": str(test_file)},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "INVALID_DIRECTORY"


def test_open_local_system_root_rejected():
    """Verify root drives and protected OS folders are rejected with 403 RESTRICTED_SYSTEM_PATH."""
    # Windows drive root
    resp_root = client.post(
        "/api/v1/repositories/open-local",
        json={"path": "C:\\"},
    )
    assert resp_root.status_code == 403
    assert resp_root.json()["error"]["code"] == "RESTRICTED_SYSTEM_PATH"

    # Protected Windows folder
    resp_win = client.post(
        "/api/v1/repositories/open-local",
        json={"path": "C:\\Windows"},
    )
    assert resp_win.status_code == 403
    assert resp_win.json()["error"]["code"] == "RESTRICTED_SYSTEM_PATH"


def test_open_local_unsupported_project_layout(tmp_path):
    """Verify an empty directory or folder without recognized project files returns 422 UNSUPPORTED_PROJECT_LAYOUT."""
    empty_dir = tmp_path / "empty_project"
    empty_dir.mkdir()
    (empty_dir / "random_notes.txt").write_text("just notes", encoding="utf-8")

    resp = client.post(
        "/api/v1/repositories/open-local",
        json={"path": str(empty_dir)},
    )
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "UNSUPPORTED_PROJECT_LAYOUT"


def test_open_local_python_project(tmp_path):
    """Verify opening a valid Python pytest project registers successfully."""
    py_dir = tmp_path / "my_py_app"
    py_dir.mkdir()
    (py_dir / "pyproject.toml").write_text("[project]\nname = 'my_py_app'\n", encoding="utf-8")
    (py_dir / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    tests_dir = py_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_ok(): assert True\n", encoding="utf-8")

    resp = client.post(
        "/api/v1/repositories/open-local",
        json={"path": str(py_dir), "name": "my-python-app"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my-python-app"
    assert data["language"] == "python"
    assert data["test_framework"] == "pytest"
    assert data["is_fixture"] is False
    assert data["layout_status"] == "supported"
    assert any("test_main.py" in t for t in data["test_targets"])


def test_open_local_typescript_and_javascript_projects(tmp_path):
    """Verify opening TypeScript and JavaScript projects detects language and testing tools."""
    # 1. TypeScript project
    ts_dir = tmp_path / "ts_service"
    ts_dir.mkdir()
    (ts_dir / "tsconfig.json").write_text("{}", encoding="utf-8")
    (ts_dir / "package.json").write_text('{"name": "ts-svc", "devDependencies": {"vitest": "^1.0"}}', encoding="utf-8")
    (ts_dir / "service.test.ts").write_text("test('ok', () => {});", encoding="utf-8")

    resp_ts = client.post("/api/v1/repositories/open-local", json={"path": str(ts_dir)})
    assert resp_ts.status_code == 200
    ts_data = resp_ts.json()
    assert ts_data["language"] == "typescript"
    assert ts_data["test_framework"] == "vitest"

    # 2. JavaScript project
    js_dir = tmp_path / "js_app"
    js_dir.mkdir()
    (js_dir / "package.json").write_text('{"name": "js-app", "devDependencies": {"jest": "^29.0"}}', encoding="utf-8")

    resp_js = client.post("/api/v1/repositories/open-local", json={"path": str(js_dir)})
    assert resp_js.status_code == 200
    js_data = resp_js.json()
    assert js_data["language"] == "javascript"
    assert js_data["test_framework"] == "jest"


def test_open_local_java_project(tmp_path):
    """Verify opening Maven and Gradle Java projects registers properly."""
    java_dir = tmp_path / "java_service"
    java_dir.mkdir()
    (java_dir / "pom.xml").write_text("<project></project>", encoding="utf-8")

    resp = client.post("/api/v1/repositories/open-local", json={"path": str(java_dir)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["language"] == "java"
    assert data["test_framework"] == "maven_junit"


def test_secret_files_exclusion(tmp_path):
    """Verify sensitive files such as .env and credentials are excluded from inspection."""
    proj = tmp_path / "secret_project"
    proj.mkdir()
    (proj / "pyproject.toml").write_text("[project]\nname='secret_project'\n", encoding="utf-8")
    (proj / "main.py").write_text("print('hello')\n", encoding="utf-8")
    # Sensitive files
    (proj / ".env").write_text("SECRET_KEY=12345\n", encoding="utf-8")
    (proj / ".env.local").write_text("DB_PASS=secret\n", encoding="utf-8")
    (proj / "id_rsa").write_text("-----" + "BEGIN RSA PRIVATE KEY" + "-----\n", encoding="utf-8")
    (proj / "credentials.json").write_text('{"private_key": "xxx"}', encoding="utf-8")

    # 1. list_safe_files must NOT include secret files
    safe_files = RepositoryScanner.list_safe_files(proj)
    assert "main.py" in safe_files
    assert "pyproject.toml" in safe_files
    assert ".env" not in safe_files
    assert ".env.local" not in safe_files
    assert "id_rsa" not in safe_files
    assert "credentials.json" not in safe_files

    # 2. inspect_file must raise PermissionError if secret file access is attempted
    with pytest.raises(PermissionError):
        RepositoryScanner.inspect_file(proj, ".env")

    with pytest.raises(PermissionError):
        RepositoryScanner.inspect_file(proj, "credentials.json")


def test_safe_refusal_when_docker_unavailable(tmp_path, monkeypatch):
    """Verify arbitrary user repositories are refused test execution when Docker is unavailable."""
    from patchpilot.sandbox.feasibility import DockerFeasibility, SandboxFeasibilityChecker
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

    # Register a user project
    proj = tmp_path / "user_calc"
    proj.mkdir()
    (proj / "pyproject.toml").write_text("[project]\nname='user_calc'\n", encoding="utf-8")
    (proj / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (proj / "tests").mkdir()
    (proj / "tests" / "test_calc.py").write_text("def test_dummy(): pass\n", encoding="utf-8")

    open_resp = client.post("/api/v1/repositories/open-local", json={"path": str(proj)})
    assert open_resp.status_code == 200
    repo_id = open_resp.json()["id"]

    # Attempt to start a repair on user repository
    # On this machine Docker is unavailable, so execution must be refused with 403 SANDBOX_UNAVAILABLE
    repair_resp = client.post(
        "/api/v1/repairs",
        json={
            "repository_id": repo_id,
            "bug_report": "Fix calculation defect in user project",
            "test_target": "tests/test_calc.py::test_dummy",
        },
    )
    assert repair_resp.status_code == 403
    err = repair_resp.json()["error"]
    assert err["code"] == "SANDBOX_UNAVAILABLE"
    assert "refuses to execute arbitrary user repository" in err["message"]


def test_demo_fixture_continues_working():
    """Verify bundled demo fixtures continue to be accepted for host execution."""
    # List repositories
    list_resp = client.get("/api/v1/repositories")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    demo_item = next((r for r in items if r["id"] == "repo_py_calc_01"), None)
    assert demo_item is not None
    assert demo_item["is_fixture"] is True
    assert demo_item["execution_allowed"] is True


def test_open_local_source_only_python_project_without_tests(tmp_path):
    """Verify a Python project with source files but NO tests or manifests registers successfully with layout_status='no_tests'."""
    src_dir = tmp_path / "py_source_only"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def run(): print('app running')\n", encoding="utf-8")
    (src_dir / "calculator.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")

    resp = client.post("/api/v1/repositories/open-local", json={"path": str(src_dir)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["language"] == "python"
    assert data["test_framework"] == "unknown"
    assert data["layout_status"] == "no_tests"
    assert "No existing tests detected" in data["execution_warning"]
    assert data["test_targets"] == []


def test_open_local_source_only_javascript_and_typescript_without_tests(tmp_path):
    """Verify JS and TS source-only projects without tests register successfully."""
    # TS
    ts_dir = tmp_path / "ts_source_only"
    ts_dir.mkdir()
    (ts_dir / "index.ts").write_text("export const greeting = 'hello';\n", encoding="utf-8")

    resp_ts = client.post("/api/v1/repositories/open-local", json={"path": str(ts_dir)})
    assert resp_ts.status_code == 200
    assert resp_ts.json()["language"] == "typescript"
    assert resp_ts.json()["layout_status"] == "no_tests"

    # JS
    js_dir = tmp_path / "js_source_only"
    js_dir.mkdir()
    (js_dir / "server.js").write_text("console.log('server started');\n", encoding="utf-8")

    resp_js = client.post("/api/v1/repositories/open-local", json={"path": str(js_dir)})
    assert resp_js.status_code == 200
    assert resp_js.json()["language"] == "javascript"
    assert resp_js.json()["layout_status"] == "no_tests"


def test_open_local_source_only_java_without_tests(tmp_path):
    """Verify Java project with .java files but no build tool registers successfully."""
    java_dir = tmp_path / "java_source_only"
    java_dir.mkdir()
    (java_dir / "Main.java").write_text("public class Main { public static void main(String[] args) {} }\n", encoding="utf-8")

    resp = client.post("/api/v1/repositories/open-local", json={"path": str(java_dir)})
    assert resp.status_code == 200
    assert resp.json()["language"] == "java"
    assert resp.json()["layout_status"] == "no_tests"


def test_get_repository_file_content_valid(tmp_path):
    """Verify reading a safe file content returns lines, content, and language."""
    proj = tmp_path / "sample_repo"
    proj.mkdir()
    (proj / "main.py").write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    open_resp = client.post("/api/v1/repositories/open-local", json={"path": str(proj)})
    repo_id = open_resp.json()["id"]

    resp = client.get(f"/api/v1/repositories/{repo_id}/file?path=main.py")
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_path"] == "main.py"
    assert "line 1" in data["content"]
    assert data["total_lines"] == 3
    assert data["language"] == "python"


def test_get_repository_file_missing_and_traversal(tmp_path):
    """Verify file endpoint rejects missing files and traversal attempts."""
    proj = tmp_path / "sample_repo_2"
    proj.mkdir()
    (proj / "main.py").write_text("print('hi')", encoding="utf-8")

    open_resp = client.post("/api/v1/repositories/open-local", json={"path": str(proj)})
    repo_id = open_resp.json()["id"]

    # 1. Missing file
    resp_missing = client.get(f"/api/v1/repositories/{repo_id}/file?path=nonexistent.py")
    assert resp_missing.status_code == 404
    assert resp_missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    # 2. Path traversal
    resp_traversal = client.get(f"/api/v1/repositories/{repo_id}/file?path=../../etc/passwd")
    assert resp_traversal.status_code == 403
    assert resp_traversal.json()["error"]["code"] == "PATH_TRAVERSAL_DETECTED"


def test_get_repository_file_blocks_secrets_and_binaries(tmp_path):
    """Verify file reader blocks sensitive config files and binary files."""
    proj = tmp_path / "sample_repo_3"
    proj.mkdir()
    (proj / "main.py").write_text("x = 1\n", encoding="utf-8")
    (proj / ".env").write_text("DB_PASSWORD=secret123\n", encoding="utf-8")
    (proj / "app.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    open_resp = client.post("/api/v1/repositories/open-local", json={"path": str(proj)})
    repo_id = open_resp.json()["id"]

    # 1. Secret file blocked
    resp_secret = client.get(f"/api/v1/repositories/{repo_id}/file?path=.env")
    assert resp_secret.status_code == 403
    assert resp_secret.json()["error"]["code"] == "SECRET_FILE_BLOCKED"

    # 2. Binary file blocked
    resp_bin = client.get(f"/api/v1/repositories/{repo_id}/file?path=app.png")
    assert resp_bin.status_code == 400
    assert resp_bin.json()["error"]["code"] == "BINARY_OR_OVERSIZED_FILE"


def test_propose_test_endpoint(tmp_path):
    """Verify propose-test endpoint generates a focused test template without running untrusted code."""
    proj = tmp_path / "py_untested"
    proj.mkdir()
    (proj / "pricing.py").write_text("def calc(a): return a * 2\n", encoding="utf-8")

    open_resp = client.post("/api/v1/repositories/open-local", json={"path": str(proj)})
    repo_id = open_resp.json()["id"]

    resp = client.post(
        f"/api/v1/repositories/{repo_id}/propose-test",
        json={
            "bug_report": "The calculate function returns 0 when input is negative numbers",
            "target_file": "pricing.py",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["repository_id"] == repo_id
    assert "test_proposed_reproduction.py" in data["test_file_path"]
    assert "def test_reproduce_reported_behavior" in data["test_code"]
    assert data["status"] == "proposed"
    assert "Focused pytest" in data["explanation"]


def test_browse_folder_selection(tmp_path, monkeypatch):
    """Verify browse-folder endpoint returns selected valid directory path."""
    from patchpilot.api import router_repositories

    chosen_dir = tmp_path / "my_project"
    chosen_dir.mkdir()
    monkeypatch.setattr(router_repositories, "_show_native_dialog", lambda: (str(chosen_dir), False))

    resp = client.post("/api/v1/repositories/browse-folder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == str(chosen_dir)
    assert data["cancelled"] is False
    assert data["supported"] is True


def test_browse_folder_cancellation(monkeypatch):
    """Verify browse-folder endpoint handles dialog cancellation without error."""
    from patchpilot.api import router_repositories

    monkeypatch.setattr(router_repositories, "_show_native_dialog", lambda: (None, True))

    resp = client.post("/api/v1/repositories/browse-folder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] is None
    assert data["cancelled"] is True
    assert data["supported"] is True
    assert "cancelled" in data["message"].lower()


def test_browse_folder_unavailable_on_non_windows(monkeypatch):
    """Verify non-Windows platforms report supported=False gracefully."""
    import sys
    monkeypatch.setattr(sys, "platform", "linux")

    resp = client.post("/api/v1/repositories/browse-folder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] is None
    assert data["cancelled"] is False
    assert data["supported"] is False
    assert "Windows desktop" in data["message"]


def test_browse_folder_exception_handling(monkeypatch):
    """Verify dialog invocation failure reports supported=False with diagnostic."""
    from patchpilot.api import router_repositories

    def _failing_dialog():
        raise RuntimeError("PowerShell process failed to start")

    monkeypatch.setattr(router_repositories, "_show_native_dialog", _failing_dialog)

    resp = client.post("/api/v1/repositories/browse-folder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] is None
    assert data["supported"] is False
    assert "unavailable" in data["message"].lower()


def test_browse_folder_invalid_or_file_path(tmp_path, monkeypatch):
    """Verify that selecting a file instead of a folder returns error message."""
    from patchpilot.api import router_repositories

    a_file = tmp_path / "not_a_dir.txt"
    a_file.write_text("I am a file", encoding="utf-8")
    monkeypatch.setattr(router_repositories, "_show_native_dialog", lambda: (str(a_file), False))

    resp = client.post("/api/v1/repositories/browse-folder")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] is None
    assert "not a valid directory" in data["message"]


def test_browse_folder_path_with_spaces_and_registration(tmp_path, monkeypatch):
    """Verify folder picker correctly handles Windows paths with spaces, followed by registration."""
    from patchpilot.api import router_repositories

    proj_spaces = tmp_path / "My Cool Project Space"
    proj_spaces.mkdir()
    (proj_spaces / "app.py").write_text("print('hello spaces')\n", encoding="utf-8")

    monkeypatch.setattr(router_repositories, "_show_native_dialog", lambda: (str(proj_spaces), False))

    # 1. Browse returns path with spaces
    browse_resp = client.post("/api/v1/repositories/browse-folder")
    assert browse_resp.status_code == 200
    chosen_path = browse_resp.json()["path"]
    assert chosen_path == str(proj_spaces)
    assert "My Cool Project Space" in chosen_path

    # 2. Registration succeeds with that path
    reg_resp = client.post("/api/v1/repositories/open-local", json={"path": chosen_path})
    assert reg_resp.status_code == 200
    assert reg_resp.json()["language"] == "python"
    assert reg_resp.json()["layout_status"] == "no_tests"


def test_browse_folder_security_forbidden_origin():
    """Verify picker endpoint rejects unauthorized cross-origin requests."""
    resp = client.post(
        "/api/v1/repositories/browse-folder",
        headers={"Origin": "http://evil-attacker.example.com"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_browse_folder_security_cross_site():
    """Verify picker endpoint rejects cross-site Sec-Fetch-Site requests."""
    resp = client.post(
        "/api/v1/repositories/browse-folder",
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_browse_folder_security_invalid_host():
    """Verify loopback middleware rejects arbitrary external Host headers."""
    resp = client.post(
        "/api/v1/repositories/browse-folder",
        headers={"Host": "malicious.internal.network"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_ingest_project_valid():
    """Verify browser-ingested project files create an isolated workspace and valid repo."""
    payload = {
        "name": "browser_calc_project",
        "files": [
            {
                "path": "calculator/math_ops.py",
                "content": "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n",
            },
            {
                "path": "tests/test_math_ops.py",
                "content": "from calculator.math_ops import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
            },
        ],
    }

    resp = client.post("/api/v1/repositories/ingest", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "browser_calc_project"
    assert data["language"] == "python"
    assert data["test_framework"] == "pytest"
    assert data["file_count"] == 2
    repo_id = data["id"]

    # Verify files can be listed
    files_resp = client.get(f"/api/v1/repositories/{repo_id}/files")
    assert files_resp.status_code == 200
    assert "calculator/math_ops.py" in files_resp.json()["files"]
    assert "tests/test_math_ops.py" in files_resp.json()["files"]

    # Verify file content can be read
    content_resp = client.get(f"/api/v1/repositories/{repo_id}/file?path=calculator/math_ops.py")
    assert content_resp.status_code == 200
    assert "def add(a, b):" in content_resp.json()["content"]


def test_ingest_project_secret_files_filtered():
    """Verify secrets (.env, id_rsa) are automatically filtered during ingestion."""
    payload = {
        "name": "project_with_secrets",
        "files": [
            {"path": "main.py", "content": "print('hello world')\n"},
            {"path": ".env", "content": "SECRET_KEY=super_secret\n"},
            {"path": "keys/id_rsa", "content": "-----" + "BEGIN RSA PRIVATE KEY" + "-----\nMIIE...\n"},
        ],
    }

    resp = client.post("/api/v1/repositories/ingest", json=payload)
    assert resp.status_code == 200
    repo_id = resp.json()["id"]

    # Only main.py should be saved; .env and id_rsa must be discarded
    files_resp = client.get(f"/api/v1/repositories/{repo_id}/files")
    assert files_resp.status_code == 200
    assert files_resp.json()["files"] == ["main.py"]


def test_ingest_project_empty_rejected():
    """Verify empty project or all-excluded files produce 422 validation error."""
    payload = {
        "name": "empty_project",
        "files": [
            {"path": ".env", "content": "KEY=val\n"},
        ],
    }

    resp = client.post("/api/v1/repositories/ingest", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "EMPTY_REPOSITORY"


def test_ingest_project_path_traversal_rejected():
    """Verify relative path traversal attempts inside ingested files are rejected with 422."""
    payload = {
        "name": "malicious_project",
        "files": [
            {"path": "safe/path.py", "content": "print('ok')\n"},
            {"path": "../escape.py", "content": "print('bad')\n"},
        ],
    }

    resp = client.post("/api/v1/repositories/ingest", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PATH_TRAVERSAL_DETECTED"


def test_ingest_project_multi_language_detection():
    """Verify TypeScript and Java projects are correctly detected after web ingestion."""
    # 1. TypeScript project
    ts_payload = {
        "name": "web_ts_service",
        "files": [
            {"path": "tsconfig.json", "content": "{\n  \"compilerOptions\": {}\n}\n"},
            {"path": "src/index.ts", "content": "export function hello(): string { return 'world'; }\n"},
        ],
    }
    ts_resp = client.post("/api/v1/repositories/ingest", json=ts_payload)
    assert ts_resp.status_code == 200
    ts_data = ts_resp.json()
    assert ts_data["language"] == "typescript"

    # 2. Java project
    java_payload = {
        "name": "web_java_service",
        "files": [
            {"path": "pom.xml", "content": "<project><modelVersion>4.0.0</modelVersion></project>\n"},
            {"path": "src/main/java/App.java", "content": "public class App { public static void main(String[] args) {} }\n"},
        ],
    }
    java_resp = client.post("/api/v1/repositories/ingest", json=java_payload)
    assert java_resp.status_code == 200
    java_data = java_resp.json()
    assert java_data["language"] == "java"
    assert java_data["test_framework"] == "maven_junit"


