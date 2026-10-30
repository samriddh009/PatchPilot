"""Base protocol and interfaces for language adapters."""

from pathlib import Path
from typing import List, Protocol, runtime_checkable

from patchpilot.schemas.enums import Language, TestFramework


@runtime_checkable
class LanguageAdapter(Protocol):
    """Protocol for language-specific test execution command builders."""

    language: Language

    def detect_framework(self, root_path: Path) -> TestFramework:
        """Detect the project test framework."""
        ...

    def build_targeted_test_command(self, test_target: str) -> List[str]:
        """Construct structured CLI arguments for executing a targeted test."""
        ...

    def build_regression_test_command(self) -> List[str]:
        """Construct structured CLI arguments for executing the full regression suite."""
        ...
