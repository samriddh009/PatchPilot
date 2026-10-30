"""Restricted Demonstration Runner with environment scrubbing and command allowlists."""

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import Dict, List

from patchpilot import config
from patchpilot.sandbox.base import ExecutionResult, SandboxRunner


class RestrictedRunner(SandboxRunner):
    """
    Tier 2 process runner strictly for authorized demonstration fixtures.
    Enforces strict command allowlists, secret environment stripping, timeouts, and output limits.
    """

    ALLOWED_BINARIES = {
        "pytest",
        "python",
        "python.exe",
        "npm",
        "npx",
        "vitest",
        "node",
        "node.exe",
        "./mvnw",
        ".\\mvnw.cmd",
        "./gradlew",
        ".\\gradlew.bat",
    }

    SAFE_ENV_VARS = {
        "PATH",
        "SYSTEMROOT",
        "COMSPEC",
        "TEMP",
        "TMP",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERPROFILE",
    }

    def execute(self, cmd: List[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        if not cmd:
            raise ValueError("Command list cannot be empty.")

        binary = cmd[0]
        binary_base = Path(binary).name.lower()

        # Check binary allowlist
        if not any(
            binary_base == allowed or binary == allowed or binary_base.startswith("pytest")
            for allowed in self.ALLOWED_BINARIES
        ):
            raise PermissionError(f"Command '{binary}' rejected by execution allowlist.")

        # Scrub environment: strip GEMINI_API_KEY and other sensitive variables
        scrubbed_env: Dict[str, str] = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if (
                k in self.SAFE_ENV_VARS
                or k_upper.startswith("PYTHON")
                or k_upper.startswith("PATH")
            ) and not any(secret in k_upper for secret in ["GEMINI", "KEY", "TOKEN", "SECRET", "AUTH", "PASS"]):
                scrubbed_env[k] = v

        # If pytest is requested, make sure we use the current venv's python if available
        final_cmd = list(cmd)
        if final_cmd[0] == "pytest":
            venv_pytest = Path(sys.prefix) / ("Scripts/pytest.exe" if sys.platform.startswith("win") else "bin/pytest")
            if venv_pytest.exists():
                final_cmd[0] = str(venv_pytest)
            else:
                final_cmd = [sys.executable, "-m", "pytest"] + final_cmd[1:]

        start_time = time.perf_counter()
        timed_out = False
        truncated = False

        try:
            res = subprocess.run(
                final_cmd,
                cwd=str(cwd),
                env=scrubbed_env,
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
            raw_stdout = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout.decode("utf-8", "replace") if exc.stdout else "")
            raw_stderr = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr.decode("utf-8", "replace") if exc.stderr else "")
            raw_stderr += f"\n[Process killed: Execution timed out after {timeout_seconds} seconds]"
            exit_code = 124
        except FileNotFoundError as exc:
            raw_stdout = ""
            raw_stderr = f"[Runner Error: Executable not found '{final_cmd[0]}']: {exc}"
            exit_code = -1
        except OSError as exc:
            raw_stdout = ""
            raw_stderr = f"[Runner Error: Failed to execute process '{final_cmd[0]}']: {exc}"
            exit_code = -1

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Enforce 64 KB output buffer truncation
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
