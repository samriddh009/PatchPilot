"""JavaScript and TypeScript language adapters."""

from pathlib import Path
from typing import List

from patchpilot.languages.base import LanguageAdapter
from patchpilot.schemas.enums import Language, TestFramework


class JavaScriptAdapter(LanguageAdapter):
    """Adapter for JavaScript test projects."""

    language = Language.JAVASCRIPT

    def detect_framework(self, root_path: Path) -> TestFramework:
        pkg = root_path / "package.json"
        if pkg.exists():
            text = pkg.read_text(encoding="utf-8", errors="ignore").lower()
            if "vitest" in text:
                return TestFramework.VITEST
            if "jest" in text:
                return TestFramework.JEST
        return TestFramework.UNKNOWN

    def build_targeted_test_command(self, test_target: str) -> List[str]:
        return ["npm", "test", "--", test_target]

    def build_regression_test_command(self) -> List[str]:
        return ["npm", "test"]


class TypeScriptAdapter(LanguageAdapter):
    """Adapter for TypeScript test projects."""

    language = Language.TYPESCRIPT

    def detect_framework(self, root_path: Path) -> TestFramework:
        pkg = root_path / "package.json"
        if pkg.exists():
            text = pkg.read_text(encoding="utf-8", errors="ignore").lower()
            if "vitest" in text:
                return TestFramework.VITEST
            if "jest" in text:
                return TestFramework.JEST
        return TestFramework.UNKNOWN

    def build_targeted_test_command(self, test_target: str) -> List[str]:
        return ["npm", "test", "--", test_target]

    def build_regression_test_command(self) -> List[str]:
        return ["npm", "test"]
