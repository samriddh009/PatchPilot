"""Sandbox runner protocol and execution result."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Protocol, runtime_checkable


@dataclass
class ExecutionResult:
    """Captured process execution result."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool
    output_truncated: bool


@runtime_checkable
class SandboxRunner(Protocol):
    """Protocol for isolated execution runners."""

    def execute(self, cmd: List[str], cwd: Path, timeout_seconds: int) -> ExecutionResult:
        """Execute command in sandbox."""
        ...
