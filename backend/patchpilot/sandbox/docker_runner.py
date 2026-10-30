"""Docker container sandbox runner for Tier 1 isolated execution."""

import time
import subprocess
from pathlib import Path
from typing import List

from patchpilot import config
from patchpilot.sandbox.base import ExecutionResult, SandboxRunner
from patchpilot.sandbox.feasibility import SandboxFeasibilityChecker


class DockerRunner(SandboxRunner):
    """
    Tier 1 production isolation runner using Docker.
    Enforces --network none, memory limits, read-only root, non-root user, and timeouts.
    """

    def __init__(self, image_tag: str = "patchpilot-sandbox:python-3.12"):
        self.image_tag = image_tag

    def execute(self, cmd: List[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        import uuid
        workspace_posix = str(cwd.resolve()).replace("\\", "/")
        docker_bin = SandboxFeasibilityChecker.get_docker_bin() or "docker"
        container_name = f"patchpilot-box-{uuid.uuid4().hex[:12]}"

        # If executing pytest, store cache in tmpfs /tmp to keep workspace pure
        run_cmd = list(cmd)
        if run_cmd and run_cmd[0] == "pytest" and "-o" not in run_cmd:
            run_cmd.extend(["-o", "cache_dir=/tmp/.pytest_cache"])

        docker_cmd = [
            docker_bin, "run", "--rm",
            "--name", container_name,
            "--network", "none",
            "--cpus", "1.5",
            "--memory", "1024m",
            "--pids-limit", "100",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{workspace_posix}:/workspace:rw",
            "-w", "/workspace",
            "--user", "1000:1000",
            "--cap-drop", "ALL",
            self.image_tag,
        ] + run_cmd

        start_time = time.perf_counter()
        timed_out = False
        truncated = False

        try:
            res = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            raw_stdout = res.stdout
            raw_stderr = res.stderr
            exit_code = res.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            # Force-remove container immediately so no background process lingers
            try:
                subprocess.run(
                    [docker_bin, "rm", "-f", container_name],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except Exception:
                pass
            raw_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            raw_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            raw_stderr += f"\n[Process killed: Container timed out after {timeout_seconds} seconds]"
            exit_code = 124
        except FileNotFoundError as exc:
            raw_stdout = ""
            raw_stderr = f"[Runner Error: Docker executable not found]: {exc}"
            exit_code = -1
        except OSError as exc:
            raw_stdout = ""
            raw_stderr = f"[Runner Error: Failed to execute Docker command]: {exc}"
            exit_code = -1

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        max_bytes = config.OUTPUT_MAX_BYTES
        if len(raw_stdout) > max_bytes:
            raw_stdout = raw_stdout[:max_bytes] + "\n... [TRUNCATED: Output exceeded 64KB limit]"
            truncated = True
        if len(raw_stderr) > max_bytes:
            raw_stderr = raw_stderr[:max_bytes] + "\n... [TRUNCATED: Output exceeded 64KB limit]"
            truncated = True

        return ExecutionResult(
            exit_code=exit_code,
            stdout=raw_stdout,
            stderr=raw_stderr,
            duration_ms=duration_ms,
            timed_out=timed_out,
            output_truncated=truncated,
        )
