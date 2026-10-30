"""Python language adapter using pytest."""

from pathlib import Path
from typing import List

from patchpilot.languages.base import LanguageAdapter
from patchpilot.schemas.enums import Language, TestFramework


class PythonAdapter(LanguageAdapter):
    """Reference implementation adapter for Python using pytest."""

    language = Language.PYTHON

    def detect_framework(self, root_path: Path) -> TestFramework:
        return TestFramework.PYTEST

    def build_targeted_test_command(self, test_target: str) -> List[str]:
        # Builds clean structured pytest arguments without shell injection
        return ["pytest", "-q", test_target]

    def build_regression_test_command(self) -> List[str]:
        return ["pytest", "-q"]
