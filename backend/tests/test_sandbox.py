"""Tests for sandbox feasibility, command allowlists, environment scrubbing, and timeouts."""

import os
import sys
from pathlib import Path
import pytest

from patchpilot.sandbox.feasibility import SandboxFeasibilityChecker, DockerFeasibility
from patchpilot.sandbox.restricted_runner import RestrictedRunner


def test_feasibility_check():
    feasibility = SandboxFeasibilityChecker.check_docker()
    assert isinstance(feasibility, DockerFeasibility)
    # On this Windows host, docker may or may not be installed; ensure fields are boolean
    assert isinstance(feasibility.cli_available, bool)
    assert isinstance(feasibility.daemon_responsive, bool)
    assert isinstance(feasibility.is_usable, bool)


def test_is_trusted_fixture():
    assert SandboxFeasibilityChecker.is_trusted_fixture(Path("C:/patch pilot/fixtures/python_calc_bug"))
    assert SandboxFeasibilityChecker.is_trusted_fixture(Path("/workspaces/fixtures/js_bug"))
    assert not SandboxFeasibilityChecker.is_trusted_fixture(Path("C:/arbitrary_repo/my_code"))


def test_restricted_runner_rejects_unauthorized_command(tmp_path):
    runner = RestrictedRunner()
    with pytest.raises(PermissionError):
        runner.execute(["curl", "http://evil.com"], cwd=tmp_path, timeout_seconds=5)

    with pytest.raises(PermissionError):
        runner.execute(["bash", "-c", "echo 1"], cwd=tmp_path, timeout_seconds=5)

    with pytest.raises(PermissionError):
        runner.execute(["cmd.exe", "/c", "dir"], cwd=tmp_path, timeout_seconds=5)


def test_restricted_runner_scrubs_secrets_from_env(tmp_path):
    runner = RestrictedRunner()
    # Inject sensitive env var
    os.environ["GEMINI_API_KEY"] = "super_secret_token_12345"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "aws_secret_key_67890"

    try:
        # Run python script that checks os.environ
        check_script = tmp_path / "check_env.py"
        check_script.write_text(
            "import os, sys\n"
            "assert 'GEMINI_API_KEY' not in os.environ, 'Leaked GEMINI_API_KEY'\n"
            "assert 'AWS_SECRET_ACCESS_KEY' not in os.environ, 'Leaked AWS key'\n"
            "print('ENV_CLEAN')\n",
            encoding="utf-8"
        )

        res = runner.execute([sys.executable, str(check_script)], cwd=tmp_path, timeout_seconds=5)
        assert res.exit_code == 0
        assert "ENV_CLEAN" in res.stdout
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)


def test_restricted_runner_enforces_timeout(tmp_path):
    runner = RestrictedRunner()
    sleep_script = tmp_path / "sleep_forever.py"
    sleep_script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")

    res = runner.execute([sys.executable, str(sleep_script)], cwd=tmp_path, timeout_seconds=1)
    assert res.timed_out is True
    assert res.exit_code == 124
    assert "timed out" in res.stderr.lower()


def test_restricted_runner_truncates_large_output(tmp_path):
    runner = RestrictedRunner()
    spam_script = tmp_path / "spam.py"
    # Generate 100,000 characters (> 64KB)
    spam_script.write_text("print('A' * 100000)\n", encoding="utf-8")

    res = runner.execute([sys.executable, str(spam_script)], cwd=tmp_path, timeout_seconds=5)
    assert res.output_truncated is True
    assert "[TRUNCATED" in res.stdout


def test_docker_runner_security_boundaries(tmp_path):
    """Verify live Docker sandbox enforces network isolation, read-only root, non-root user, and limits."""
    from patchpilot.sandbox.docker_runner import DockerRunner
    feasibility = SandboxFeasibilityChecker.check_docker()
    if not feasibility.is_usable:
        pytest.skip("Docker daemon not usable in this environment")

    runner = DockerRunner()

    # 1. Non-root user check
    res_user = runner.execute(["python", "-c", "import os; print('UID:', os.getuid())"], cwd=tmp_path, timeout_seconds=10)
    assert res_user.exit_code == 0
    assert "UID: 1000" in res_user.stdout

    # 2. Read-only root filesystem check
    res_ro = runner.execute(["python", "-c", "open('/etc/malicious', 'w').write('bad')"], cwd=tmp_path, timeout_seconds=10)
    assert res_ro.exit_code != 0
    assert "Read-only file system" in res_ro.stderr

    # 3. Network isolation check (--network none)
    res_net = runner.execute(
        ["python", "-c", "import urllib.request; urllib.request.urlopen('http://8.8.8.8', timeout=2)"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert res_net.exit_code != 0
    assert ("Network is unreachable" in res_net.stderr or "URLError" in res_net.stderr or "timed out" in res_net.stderr)

    # 4. Output limit capping in Docker
    res_trunc = runner.execute(
        ["python", "-c", "print('DOCKER_SPAM_' * 10000)"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert res_trunc.output_truncated is True
    assert "[TRUNCATED" in res_trunc.stdout


def test_docker_runner_workspace_isolation(tmp_path):
    """Verify live Docker sandbox only exposes mounted workspace and blocks external writes."""
    from patchpilot.sandbox.docker_runner import DockerRunner
    feasibility = SandboxFeasibilityChecker.check_docker()
    if not feasibility.is_usable:
        pytest.skip("Docker daemon not usable in this environment")

    runner = DockerRunner()

    # 1. Host workspace file readable inside container
    in_file = tmp_path / "hello_host.txt"
    in_file.write_text("HELLO_FROM_HOST_WORKSPACE", encoding="utf-8")

    res_read = runner.execute(
        ["python", "-c", "print('READ:', open('/workspace/hello_host.txt').read().strip())"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert res_read.exit_code == 0
    assert "READ: HELLO_FROM_HOST_WORKSPACE" in res_read.stdout

    # 2. Container can write inside /workspace and changes reflect on host
    res_write = runner.execute(
        ["python", "-c", "open('/workspace/out_from_container.txt', 'w').write('WRITTEN_IN_CONTAINER')"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert res_write.exit_code == 0
    out_file = tmp_path / "out_from_container.txt"
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == "WRITTEN_IN_CONTAINER"

    # 3. Container cannot write to root or external system paths
    res_ext = runner.execute(
        ["python", "-c", "open('/var/unauthorized_leak.txt', 'w').write('leak')"],
        cwd=tmp_path,
        timeout_seconds=10,
    )
    assert res_ext.exit_code != 0
    assert "Read-only file system" in res_ext.stderr


def test_docker_runner_timeout_and_container_cleanup(tmp_path):
    """Verify live Docker container is terminated and forcefully removed upon timeout."""
    from patchpilot.sandbox.docker_runner import DockerRunner
    import subprocess
    feasibility = SandboxFeasibilityChecker.check_docker()
    if not feasibility.is_usable:
        pytest.skip("Docker daemon not usable in this environment")

    runner = DockerRunner()
    res = runner.execute(
        ["python", "-c", "import time; time.sleep(15)"],
        cwd=tmp_path,
        timeout_seconds=2,
    )
    assert res.timed_out is True
    assert res.exit_code == 124
    assert "timed out after 2 seconds" in res.stderr

    # Confirm container was removed and is not lingering in docker ps
    docker_bin = SandboxFeasibilityChecker.get_docker_bin() or "docker"
    ps_res = subprocess.run([docker_bin, "ps", "--filter", "name=patchpilot-box-", "-q"], capture_output=True, text=True)
    assert ps_res.returncode == 0
    # Output should be empty (no lingering patchpilot-box containers)
    assert ps_res.stdout.strip() == ""


def test_docker_runner_failure_when_unavailable(tmp_path, monkeypatch):
    """Verify DockerRunner returns clean failure ExecutionResult when Docker executable is not found."""
    from patchpilot.sandbox.docker_runner import DockerRunner
    import subprocess

    def mock_run_fnf(*args, **kwargs):
        raise FileNotFoundError("docker not found in PATH")

    monkeypatch.setattr(subprocess, "run", mock_run_fnf)
    runner = DockerRunner()
    res = runner.execute(["python", "-c", "print(1)"], cwd=tmp_path, timeout_seconds=5)
    assert res.exit_code == -1
    assert res.timed_out is False
    assert "Docker executable not found" in res.stderr


def test_docker_runner_command_construction(tmp_path, monkeypatch):
    """Verify DockerRunner constructs strict isolation arguments without requiring live daemon."""
    from patchpilot.sandbox.docker_runner import DockerRunner
    import subprocess

    captured_args = []
    def mock_run(cmd, **kwargs):
        captured_args.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="mock_out", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)

    runner = DockerRunner("test-image:tag")
    res = runner.execute(["pytest", "tests/test_calc.py"], cwd=tmp_path, timeout_seconds=15)

    assert res.exit_code == 0
    assert len(captured_args) == 1
    args = captured_args[0]
    assert "--name" in args
    assert "--network" in args and args[args.index("--network") + 1] == "none"
    assert "--read-only" in args
    assert "--user" in args and args[args.index("--user") + 1] == "1000:1000"
    assert "--cap-drop" in args and args[args.index("--cap-drop") + 1] == "ALL"
    assert "--tmpfs" in args
    assert "/workspace" in str(args)
    assert "test-image:tag" in args


