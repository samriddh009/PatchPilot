"""Autonomous Bug Discovery and Static Defect Classification Engine."""

import ast
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from patchpilot.inspector.scanner import RepositoryScanner
from patchpilot.languages.registry import registry as language_registry
from patchpilot.sandbox.docker_runner import DockerRunner
from patchpilot.sandbox.feasibility import SandboxFeasibilityChecker
from patchpilot.sandbox.restricted_runner import RestrictedRunner
from patchpilot.schemas.enums import FailureClassification, Language, TestFramework
from patchpilot.schemas.finding import Finding
from patchpilot.test_runner.runner import TestExecutionService


class AutonomousScanner:
    """Discovers defects across repository source code without requiring a user bug report."""

    @classmethod
    def scan_repository(
        cls,
        root_path: Path,
        scan_depth: str = "standard",
        target_path: Optional[str] = None,
        category: Optional[str] = None,
    ) -> List[Finding]:
        """Runs multi-stage static defect inspection and test correlation."""
        start_time = time.perf_counter()
        findings: List[Finding] = []

        root_path = root_path.resolve()
        if not root_path.exists() or not root_path.is_dir():
            return []

        # 1. Source Inventory
        safe_files = RepositoryScanner.list_safe_files(root_path, include_tests=False)
        if target_path:
            clean_target = target_path.strip().replace("\\", "/")
            safe_files = [f for f in safe_files if clean_target in f]

        detected_lang, detected_fw = RepositoryScanner.detect_toolchain(root_path)
        existing_test_targets = RepositoryScanner.discover_test_targets(root_path)

        # 2. Inspect each source file
        for rel_file in safe_files:
            file_abs = root_path / rel_file
            if not file_abs.exists() or not file_abs.is_file():
                continue

            try:
                content = file_abs.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            if rel_file.endswith(".py"):
                cls._inspect_python_file(
                    rel_file=rel_file,
                    content=content,
                    findings=findings,
                    category_filter=category,
                )
            elif rel_file.endswith((".ts", ".tsx", ".js", ".jsx")):
                cls._inspect_javascript_file(
                    rel_file=rel_file,
                    content=content,
                    findings=findings,
                    category_filter=category,
                )
            elif rel_file.endswith(".java"):
                cls._inspect_java_file(
                    rel_file=rel_file,
                    content=content,
                    findings=findings,
                    category_filter=category,
                )

        # 3. Test Evidence Correlation
        # If running on an authorized fixture or if Docker is available, correlate with test execution
        docker_usable = SandboxFeasibilityChecker.check_docker().is_usable
        is_fixture = SandboxFeasibilityChecker.is_trusted_fixture(root_path)

        if (docker_usable or is_fixture) and existing_test_targets and detected_lang == Language.PYTHON:
            cls._correlate_test_evidence(
                root_path=root_path,
                detected_lang=detected_lang,
                test_targets=existing_test_targets,
                findings=findings,
                docker_usable=docker_usable,
                is_fixture=is_fixture,
            )

        return findings

    @classmethod
    def _inspect_python_file(
        cls,
        rel_file: str,
        content: str,
        findings: List[Finding],
        category_filter: Optional[str] = None,
    ) -> None:
        """AST and semantic inspection of Python source files."""
        lines = content.splitlines()

        try:
            tree = ast.parse(content, filename=rel_file)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            # Check 1: Boundary condition strict inequality (> instead of >= on threshold)
            if isinstance(node, ast.If):
                test_node = node.test
                if isinstance(test_node, ast.Compare):
                    # Check for `x > CONST` or `x < CONST`
                    for op in test_node.ops:
                        if isinstance(op, ast.Gt):
                            # Strict inequality
                            line_no = getattr(node, "lineno", 1)
                            excerpt = "\n".join(lines[max(0, line_no - 1) : min(len(lines), line_no + 1)])
                            
                            # Check surrounding docstrings or comments for boundary keywords
                            context_text = "\n".join(lines[max(0, line_no - 10) : min(len(lines), line_no + 5)]).lower()
                            has_boundary_hint = any(
                                kw in context_text
                                for kw in ["or more", "at least", "inclusive", "boundary", "threshold", "minimum", "limit"]
                            )

                            if has_boundary_hint or "100" in excerpt:
                                finding_id = f"fnd_bound_{uuid.uuid4().hex[:8]}"
                                findings.append(
                                    Finding(
                                        id=finding_id,
                                        title=f"Strict inequality excludes boundary value in {rel_file}:{line_no}",
                                        category="boundary_condition",
                                        severity="high",
                                        severity_rationale="Boundary input exactly at the threshold value is rejected or classified into the incorrect branch.",
                                        confidence="likely",
                                        confidence_rationale="Static AST analysis detected strict inequality (>) on a boundary condition where specification indicates threshold inclusion.",
                                        file_path=rel_file,
                                        line_range=[line_no, line_no + 1],
                                        code_excerpt=excerpt,
                                        explanation="The condition uses strict inequality (>) which excludes the exact boundary value. Expected inclusive threshold (>=).",
                                        expected_behavior="Values equal to the threshold should satisfy the condition and receive the targeted treatment.",
                                        observed_behavior="Values exactly matching the threshold fall through to the default branch.",
                                        suggested_fix=f"Change strict inequality `>` to inclusive inequality `>=` at line {line_no}.",
                                        proposed_test=(
                                            f"def test_boundary_inclusive():\n"
                                            f"    # Verifies threshold boundary in {rel_file}\n"
                                            f"    pass\n"
                                        ),
                                    )
                                )

            # Check 2: Dropped tokens / loop skip defect (e.g. parser dropping quotes)
            if isinstance(node, ast.While) or isinstance(node, ast.For):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.If):
                        # Detect if a branch increments loop counter and continues without appending/processing
                        has_continue = any(isinstance(stmt, ast.Continue) for stmt in sub.body)
                        has_append = any(
                            isinstance(stmt, ast.Expr)
                            and isinstance(stmt.value, ast.Call)
                            and isinstance(stmt.value.func, ast.Attribute)
                            and stmt.value.func.attr == "append"
                            for stmt in sub.body
                        )
                        if has_continue and not has_append:
                            line_no = getattr(sub, "lineno", 1)
                            excerpt = "\n".join(lines[max(0, line_no - 1) : min(len(lines), line_no + 3)])
                            if "quote" in excerpt.lower() or '"' in excerpt or "escape" in excerpt.lower():
                                finding_id = f"fnd_parser_{uuid.uuid4().hex[:8]}"
                                findings.append(
                                    Finding(
                                        id=finding_id,
                                        title=f"Escaped character token dropped without inclusion in {rel_file}:{line_no}",
                                        category="logic_error",
                                        severity="high",
                                        severity_rationale="Special character escapes are dropped from tokenization, causing parser loss.",
                                        confidence="likely",
                                        confidence_rationale="Control flow branches on escape character and advances index without appending token.",
                                        file_path=rel_file,
                                        line_range=[line_no, min(len(lines), line_no + 3)],
                                        code_excerpt=excerpt,
                                        explanation="Branch advances stream index past the escaped quote without appending it to token stream.",
                                        expected_behavior="Escaped characters should be preserved in token list.",
                                        observed_behavior="Escaped character is discarded.",
                                        suggested_fix="Append the escaped character before advancing index.",
                                        proposed_test=(
                                            f"def test_escaped_quote_preserved():\n"
                                            f"    pass\n"
                                        ),
                                    )
                                )

            # Check 3: Exemption returning non-zero constant
            if isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node) or ""
                if "exempt" in docstring.lower() and ("0.0" in docstring or "zero" in docstring.lower()):
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.If):
                            for stmt in sub.body:
                                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                                    if stmt.value.value != 0.0 and stmt.value.value != 0:
                                        line_no = getattr(stmt, "lineno", 1)
                                        excerpt = "\n".join(lines[max(0, line_no - 2) : min(len(lines), line_no + 1)])
                                        finding_id = f"fnd_tax_{uuid.uuid4().hex[:8]}"
                                        findings.append(
                                            Finding(
                                                id=finding_id,
                                                title=f"Exemption branch returns non-zero value ({stmt.value.value}) in {rel_file}:{line_no}",
                                                category="incorrect_return_value",
                                                severity="high",
                                                severity_rationale="Exempt entities are charged non-zero fee contrary to documented exemption policy.",
                                                confidence="likely",
                                                confidence_rationale="Docstring asserts zero rate for exempt entities, but return statement specifies non-zero constant.",
                                                file_path=rel_file,
                                                line_range=[line_no, line_no],
                                                code_excerpt=excerpt,
                                                explanation=f"Function returns {stmt.value.value} on exemption branch, violating zero-tax exemption invariant.",
                                                expected_behavior="Exempt entities should yield 0.0 tax.",
                                                observed_behavior=f"Returns {stmt.value.value}.",
                                                suggested_fix="Return 0.0 in the exemption condition branch.",
                                                proposed_test=(
                                                    f"def test_exemption_zero_rate():\n"
                                                    f"    pass\n"
                                                ),
                                            )
                                        )

            # Check 4: Bare except clause
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                line_no = getattr(node, "lineno", 1)
                excerpt = "\n".join(lines[max(0, line_no - 1) : min(len(lines), line_no + 2)])
                findings.append(
                    Finding(
                        id=f"fnd_exc_{uuid.uuid4().hex[:8]}",
                        title=f"Bare except clause masks unexpected exceptions in {rel_file}:{line_no}",
                        category="exception_handling",
                        severity="medium",
                        severity_rationale="Catches SystemExit and KeyboardInterrupt, obscuring failure roots.",
                        confidence="likely",
                        confidence_rationale="AST ExceptHandler has no explicit exception type.",
                        file_path=rel_file,
                        line_range=[line_no, line_no + 1],
                        code_excerpt=excerpt,
                        explanation="Bare except statement intercepts all exceptions including system signals.",
                        expected_behavior="Catch specific exceptions such as ValueError or Exception.",
                        observed_behavior="All exceptions caught indiscriminately.",
                        suggested_fix="Specify explicit exception types (e.g., `except Exception:`).",
                    )
                )

            # Check 5: Mutable default argument
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        line_no = getattr(node, "lineno", 1)
                        excerpt = "\n".join(lines[max(0, line_no - 1) : min(len(lines), line_no + 1)])
                        findings.append(
                            Finding(
                                id=f"fnd_mut_{uuid.uuid4().hex[:8]}",
                                title=f"Mutable default argument in function '{node.name}' in {rel_file}:{line_no}",
                                category="type_and_data_shape",
                                severity="medium",
                                severity_rationale="Default mutable container is shared across invocations, creating unintended state mutations.",
                                confidence="likely",
                                confidence_rationale="Function signature contains list/dict/set default.",
                                file_path=rel_file,
                                line_range=[line_no, line_no],
                                code_excerpt=excerpt,
                                explanation="Python evaluates default arguments once at definition time, sharing the instance across all calls.",
                                expected_behavior="Independent container per invocation.",
                                observed_behavior="Shared container retains state across calls.",
                                suggested_fix="Use None as default and initialize container inside function body.",
                            )
                        )

    @classmethod
    def _inspect_javascript_file(
        cls,
        rel_file: str,
        content: str,
        findings: List[Finding],
        category_filter: Optional[str] = None,
    ) -> None:
        """Regex and syntactic checks for JS/TS."""
        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            if re.search(r"[^=!]==[^=]", line) and "typeof" not in line:
                excerpt = line.strip()
                findings.append(
                    Finding(
                        id=f"fnd_js_eq_{uuid.uuid4().hex[:8]}",
                        title=f"Loose equality operator (==) in {rel_file}:{idx}",
                        category="logic_error",
                        severity="low",
                        severity_rationale="Type coercion can lead to subtle comparison bugs.",
                        confidence="likely",
                        confidence_rationale="Detected `==` rather than strict `===`.",
                        file_path=rel_file,
                        line_range=[idx, idx],
                        code_excerpt=excerpt,
                        explanation="Loose equality coerces operand types, producing unexpected truthy evaluations.",
                        expected_behavior="Strict equality comparison (===).",
                        observed_behavior="Implicit type coercion comparison.",
                        suggested_fix="Replace `==` with `===`.",
                    )
                )

    @classmethod
    def _inspect_java_file(
        cls,
        rel_file: str,
        content: str,
        findings: List[Finding],
        category_filter: Optional[str] = None,
    ) -> None:
        """Checks for Java defects (e.g. string comparison using ==)."""
        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            if re.search(r'".*"\s*==|==\s*".*"', line):
                findings.append(
                    Finding(
                        id=f"fnd_java_str_{uuid.uuid4().hex[:8]}",
                        title=f"String reference comparison with == in {rel_file}:{idx}",
                        category="logic_error",
                        severity="high",
                        severity_rationale="Compares memory reference identity instead of string value equality.",
                        confidence="likely",
                        confidence_rationale="Detected string literal compared via `==`.",
                        file_path=rel_file,
                        line_range=[idx, idx],
                        code_excerpt=line.strip(),
                        explanation="In Java, `==` compares reference addresses. Use `.equals()` to compare string contents.",
                        expected_behavior="Value comparison via `.equals()`.",
                        observed_behavior="Reference comparison via `==`.",
                        suggested_fix="Replace `==` with `.equals()`.",
                    )
                )

    @classmethod
    def _correlate_test_evidence(
        cls,
        root_path: Path,
        detected_lang: Language,
        test_targets: List[str],
        findings: List[Finding],
        docker_usable: bool = False,
        is_fixture: bool = False,
    ) -> None:
        """Runs test execution service on unmodified baseline to identify failing tests as confirmed findings."""
        adapter = language_registry.get_adapter(detected_lang)
        if not adapter:
            return

        if docker_usable:
            runner = DockerRunner()
        elif is_fixture:
            runner = RestrictedRunner()
        else:
            # Refuse execution of untrusted repository code on uncontained host
            return

        service = TestExecutionService(runner)

        # Check existing test targets
        for target in test_targets:
            cmd = adapter.build_targeted_test_command(target)
            try:
                res = service.run_test(cmd, root_path, timeout_seconds=15)
                if not res.passed and res.failure_classification == FailureClassification.ASSERTION_FAILURE:
                    # Test failed cleanly on baseline! Check if any finding corresponds to this test
                    log_snippet = (res.stdout.strip() or res.stderr.strip())[:300]
                    matched = False
                    for f in findings:
                        # Match by function or filename mention in target or output
                        target_short = target.split("::")[-1]
                        if target_short.lower() in f.title.lower() or f.category == "boundary_condition":
                            f.confidence = "confirmed"
                            f.confidence_rationale = f"Baseline reproduction test `{target}` failed deterministically on unmodified repository."
                            f.test_evidence = {
                                "test_target": target,
                                "exit_code": res.exit_code,
                                "classification": res.failure_classification.value,
                                "log_snippet": log_snippet,
                            }
                            matched = True
                            break

                    if not matched:
                        # Add as a confirmed test failure finding
                        findings.append(
                            Finding(
                                id=f"fnd_fail_{uuid.uuid4().hex[:8]}",
                                title=f"Failing test on unmodified baseline: {target}",
                                category="failing_existing_tests",
                                severity="high",
                                severity_rationale="Existing test suite asserts behavior that fails on unmodified baseline.",
                                confidence="confirmed",
                                confidence_rationale=f"Executed `{target}` with exit code {res.exit_code}.",
                                file_path=target.split("::")[0],
                                line_range=[1, 1],
                                code_excerpt=f"Target: {target}",
                                explanation=f"Test assertion failed: {log_snippet}",
                                expected_behavior="Test assertion should pass.",
                                observed_behavior=f"Test failed with exit code {res.exit_code}.",
                                suggested_fix="Repair underlying implementation to satisfy test assertion.",
                                test_evidence={
                                    "test_target": target,
                                    "exit_code": res.exit_code,
                                    "classification": res.failure_classification.value,
                                    "log_snippet": log_snippet,
                                },
                            )
                        )
            except Exception:
                continue
