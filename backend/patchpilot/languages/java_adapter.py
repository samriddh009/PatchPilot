"""Java language adapter supporting Maven and Gradle wrappers."""

import sys
from pathlib import Path
from typing import List

from patchpilot.languages.base import LanguageAdapter
from patchpilot.schemas.enums import Language, TestFramework


class JavaAdapter(LanguageAdapter):
    """Adapter for Java projects using Maven wrapper (mvnw) or Gradle wrapper (gradlew)."""

    language = Language.JAVA

    def detect_framework(self, root_path: Path) -> TestFramework:
        if (root_path / "pom.xml").exists():
            return TestFramework.MAVEN_JUNIT
        if (root_path / "build.gradle").exists() or (root_path / "build.gradle.kts").exists():
            return TestFramework.GRADLE_JUNIT
        return TestFramework.UNKNOWN

    def build_targeted_test_command(self, test_target: str) -> List[str]:
        # Detect whether to use maven or gradle
        is_windows = sys.platform.startswith("win")
        mvnw = ".\\mvnw.cmd" if is_windows else "./mvnw"
        return [mvnw, "test", f"-Dtest={test_target}"]

    def build_regression_test_command(self) -> List[str]:
        is_windows = sys.platform.startswith("win")
        mvnw = ".\\mvnw.cmd" if is_windows else "./mvnw"
        return [mvnw, "test"]
