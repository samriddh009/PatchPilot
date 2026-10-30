"""Static repository inspection and heuristic language / test framework discovery."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from patchpilot.schemas.enums import Language, TestFramework
from patchpilot.workspace.manager import WorkspaceManager


class RepositoryScanner:
    """Non-destructive static scanner for languages, test frameworks, and file hierarchies."""

    SECRET_FILENAMES = {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
        ".env.staging",
        "id_rsa",
        "id_dsa",
        "id_ed25519",
        "id_ecdsa",
        "credentials.json",
        "client_secret.json",
        "token.json",
        "auth.json",
        "secrets.json",
    }

    SECRET_EXTENSIONS = {
        ".pem",
        ".key",
        ".pkcs12",
        ".pfx",
        ".p12",
        ".keystore",
        ".jks",
    }

    BINARY_EXTENSIONS = {
        ".pyc", ".pyo", ".pyd", ".so", ".dll", ".exe", ".bin",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip",
        ".tar", ".gz", ".jar", ".war", ".class",
    }

    MAX_INSPECTION_FILE_SIZE = 256 * 1024  # 256 KB

    @classmethod
    def is_secret_or_credential(cls, filename: str, rel_path: str = "") -> bool:
        """Determines if a filename or path represents an environment secret or credential."""
        fname = filename.lower()
        if fname == ".env" or fname.startswith(".env."):
            return True
        if fname in cls.SECRET_FILENAMES:
            return True
        if any(fname.endswith(ext) for ext in cls.SECRET_EXTENSIONS):
            return True
        if fname.startswith("client_secret") and fname.endswith(".json"):
            return True
        if fname.startswith("service-account") and fname.endswith(".json"):
            return True
        rel_lower = rel_path.lower()
        if any(p in rel_lower for p in [".aws", ".gcp", ".azure"]) and fname in {"credentials", "config"}:
            return True
        return False

    @classmethod
    def list_safe_files(cls, root_path: Path, include_tests: bool = True) -> List[str]:
        """
        Scan and return relative paths of all safe, non-secret text files.
        Prunes dependency caches and secret files.
        """
        resolved_root = root_path.resolve()
        safe_files: List[str] = []

        for dirpath, dirnames, filenames in os.walk(resolved_root):
            dirnames[:] = [d for d in dirnames if d not in WorkspaceManager.EXCLUDED_PATTERNS]
            dirnames.sort()

            for fname in sorted(filenames):
                rel_dir = Path(dirpath).relative_to(resolved_root).as_posix()
                rel_file = f"{rel_dir}/{fname}" if rel_dir != "." else fname
                if cls.is_secret_or_credential(fname, rel_file):
                    continue
                if any(fname.endswith(ext) for ext in cls.BINARY_EXTENSIONS):
                    continue

                full_path = Path(dirpath) / fname
                try:
                    if full_path.stat().st_size > cls.MAX_INSPECTION_FILE_SIZE:
                        continue
                except (OSError, PermissionError):
                    continue

                rel_path = full_path.relative_to(resolved_root).as_posix()
                if not include_tests and (rel_path.startswith("test") or "/test" in rel_path):
                    continue

                safe_files.append(rel_path)

        return safe_files

    @classmethod
    def detect_toolchain(cls, root_path: Path) -> Tuple[Language, TestFramework]:
        """
        Detect project language and primary testing framework through static inspection.
        Supports both manifest-configured projects and source-only layouts without tests.
        Does not execute any arbitrary project code.
        """
        resolved_root = root_path.resolve()

        # 1. Manifest / Config based checks
        # Python manifests
        if (
            (resolved_root / "pyproject.toml").exists()
            or (resolved_root / "requirements.txt").exists()
            or (resolved_root / "setup.py").exists()
            or (resolved_root / "setup.cfg").exists()
            or (resolved_root / "Pipfile").exists()
            or (resolved_root / "pytest.ini").exists()
        ):
            framework = TestFramework.UNKNOWN
            if (
                (resolved_root / "pytest.ini").exists()
                or (resolved_root / "tests").exists()
                or cls._file_contains(resolved_root / "pyproject.toml", "pytest")
                or cls._file_contains(resolved_root / "requirements.txt", "pytest")
            ):
                framework = TestFramework.PYTEST
            return Language.PYTHON, framework

        # TypeScript manifests
        if (resolved_root / "tsconfig.json").exists():
            pkg_json = resolved_root / "package.json"
            framework = TestFramework.UNKNOWN
            if pkg_json.exists():
                if cls._file_contains(pkg_json, "vitest"):
                    framework = TestFramework.VITEST
                elif cls._file_contains(pkg_json, "jest"):
                    framework = TestFramework.JEST
            return Language.TYPESCRIPT, framework

        # JavaScript manifests
        if (resolved_root / "package.json").exists():
            pkg_json = resolved_root / "package.json"
            framework = TestFramework.UNKNOWN
            if cls._file_contains(pkg_json, "vitest"):
                framework = TestFramework.VITEST
            elif cls._file_contains(pkg_json, "jest"):
                framework = TestFramework.JEST
            # If package.json has typescript dependency, treat as TypeScript
            if cls._file_contains(pkg_json, "typescript"):
                return Language.TYPESCRIPT, framework
            return Language.JAVASCRIPT, framework

        # Java manifests
        if (resolved_root / "pom.xml").exists():
            return Language.JAVA, TestFramework.MAVEN_JUNIT
        if (resolved_root / "build.gradle").exists() or (resolved_root / "build.gradle.kts").exists():
            return Language.JAVA, TestFramework.GRADLE_JUNIT

        # 2. Source-file based fallback (for projects without manifests or tests)
        safe_files = cls.list_safe_files(resolved_root, include_tests=True)
        has_py = any(f.endswith(".py") for f in safe_files)
        has_ts = any(f.endswith(".ts") or f.endswith(".tsx") for f in safe_files)
        has_js = any(f.endswith(".js") or f.endswith(".jsx") or f.endswith(".mjs") for f in safe_files)
        has_java = any(f.endswith(".java") for f in safe_files)

        if has_py:
            has_tests = any("test" in f.lower() for f in safe_files)
            return Language.PYTHON, TestFramework.PYTEST if has_tests else TestFramework.UNKNOWN
        if has_ts:
            has_vitest = any("vitest" in f.lower() for f in safe_files)
            has_jest = any("jest" in f.lower() for f in safe_files)
            fw = TestFramework.VITEST if has_vitest else (TestFramework.JEST if has_jest else TestFramework.UNKNOWN)
            return Language.TYPESCRIPT, fw
        if has_js:
            has_vitest = any("vitest" in f.lower() for f in safe_files)
            has_jest = any("jest" in f.lower() for f in safe_files)
            fw = TestFramework.VITEST if has_vitest else (TestFramework.JEST if has_jest else TestFramework.UNKNOWN)
            return Language.JAVASCRIPT, fw
        if has_java:
            return Language.JAVA, TestFramework.UNKNOWN

        return Language.UNKNOWN, TestFramework.UNKNOWN

    @classmethod
    def is_test_file(cls, rel_path: str) -> bool:
        """Determines if a relative path represents a test file across Python, TS/JS, and Java."""
        posix = rel_path.replace("\\", "/").lower()
        parts = posix.split("/")
        fname = parts[-1]

        # In a test directory
        in_test_dir = any(p in ("tests", "test", "__tests__") for p in parts[:-1])

        # Python test files
        if fname.endswith(".py"):
            if fname.startswith("test_") or fname.endswith("_test.py") or (in_test_dir and fname != "__init__.py" and fname != "conftest.py"):
                return True

        # TypeScript / JavaScript test files
        if any(fname.endswith(ext) for ext in (
            ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
            ".test.js", ".test.jsx", ".spec.js", ".spec.jsx",
            ".test.mjs", ".spec.mjs",
        )):
            return True
        if in_test_dir and any(fname.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs")):
            return True

        # Java test files
        if fname.endswith(".java"):
            base = fname[:-5]
            if base.endswith("test") or base.endswith("tests") or base.startswith("test") or in_test_dir:
                return True

        return False

    @classmethod
    def discover_test_targets(cls, root_path: Path) -> List[str]:
        """Discover runnable test file targets within the repository."""
        safe_files = cls.list_safe_files(root_path, include_tests=True)
        return [f for f in safe_files if cls.is_test_file(f)]

    @classmethod
    def detect_file_language(cls, file_path: str) -> str:
        """Map file extension to syntax language identifier for UI rendering."""
        p = file_path.lower()
        if p.endswith(".py"):
            return "python"
        if p.endswith(".ts") or p.endswith(".tsx"):
            return "typescript"
        if p.endswith(".js") or p.endswith(".jsx") or p.endswith(".mjs"):
            return "javascript"
        if p.endswith(".java"):
            return "java"
        if p.endswith(".json"):
            return "json"
        if p.endswith(".toml"):
            return "toml"
        if p.endswith(".yaml") or p.endswith(".yml"):
            return "yaml"
        if p.endswith(".xml") or p.endswith(".html"):
            return "xml"
        if p.endswith(".md"):
            return "markdown"
        if p.endswith(".css"):
            return "css"
        if p.endswith(".sh") or p.endswith(".bash"):
            return "bash"
        if p.endswith(".sql"):
            return "sql"
        return "plaintext"

    @classmethod
    def inspect_file(cls, root_path: Path, relative_path: str, offset_line: int = 1, limit_lines: int = 500) -> Dict[str, Any]:
        """
        Safely read a file with strict path jailing, binary detection, and line limits.
        """
        target = WorkspaceManager.resolve_jailed_path(root_path, relative_path)
        if not target.is_file():
            raise FileNotFoundError(f"Target file not found: {relative_path}")

        if cls.is_secret_or_credential(target.name, relative_path):
            raise PermissionError("Access to secret configuration files is strictly forbidden.")

        if any(target.name.lower().endswith(ext) for ext in cls.BINARY_EXTENSIONS):
            raise ValueError(f"Cannot display binary file as text: {target.name}")

        try:
            size = target.stat().st_size
            if size > cls.MAX_INSPECTION_FILE_SIZE:
                raise ValueError(f"File size ({size // 1024} KB) exceeds maximum safe inspection limit ({cls.MAX_INSPECTION_FILE_SIZE // 1024} KB).")
        except (OSError, PermissionError):
            pass

        content = target.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        start = max(1, offset_line) - 1
        end = start + max(1, limit_lines)
        sliced_content = "".join(lines[start:end])

        return {
            "file_path": relative_path,
            "total_lines": total_lines,
            "offset_line": start + 1,
            "limit_lines": limit_lines,
            "content": sliced_content,
            "language": cls.detect_file_language(relative_path),
        }

    @staticmethod
    def _file_contains(file_path: Path, needle: str) -> bool:
        if not file_path.exists() or not file_path.is_file():
            return False
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return needle.lower() in content.lower()
        except Exception:
            return False
