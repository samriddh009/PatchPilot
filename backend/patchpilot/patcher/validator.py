"""Unified diff parser and strict syntax/path validator."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from patchpilot.workspace.manager import (
    PathTraversalSecurityException,
    WorkspaceManager,
)


@dataclass
class PatchValidationResult:
    is_valid: bool
    target_files: List[str]
    syntax_errors: List[str]


class PatchValidator:
    """Validates candidate unified diffs for syntax correctness, bounds, and path safety."""

    HUNK_HEADER_PATTERN = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    @classmethod
    def validate_diff(cls, workspace_root: Path, raw_diff: str) -> PatchValidationResult:
        if not raw_diff or not raw_diff.strip():
            return PatchValidationResult(
                is_valid=False,
                target_files=[],
                syntax_errors=["Diff content is empty."],
            )

        lines = raw_diff.splitlines()
        target_files: List[str] = []
        syntax_errors: List[str] = []

        i = 0
        current_file: str = ""

        while i < len(lines):
            line = lines[i]

            # Detect file header --- and +++
            if line.startswith("--- "):
                if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                    syntax_errors.append(f"Malformed file header at line {i+1}: missing '+++ ' line.")
                    i += 1
                    continue

                old_file_line = line[4:].strip()
                new_file_line = lines[i + 1][4:].strip()
                i += 2

                # Clean a/ and b/ prefixes
                target_rel = new_file_line
                if target_rel.startswith("b/") or target_rel.startswith("b\\"):
                    target_rel = target_rel[2:]
                elif target_rel == "/dev/null":
                    target_rel = old_file_line
                    if target_rel.startswith("a/") or target_rel.startswith("a\\"):
                        target_rel = target_rel[2:]

                # Check path traversal
                if ".." in target_rel:
                    syntax_errors.append(f"Path traversal detected in patch header: '{target_rel}'.")
                    continue

                try:
                    resolved_file = WorkspaceManager.resolve_jailed_path(workspace_root, target_rel)
                    if not resolved_file.exists() and old_file_line != "/dev/null":
                        syntax_errors.append(f"Target file does not exist in workspace: '{target_rel}'.")
                        continue
                except PathTraversalSecurityException as exc:
                    syntax_errors.append(str(exc))
                    continue

                current_file = target_rel
                if current_file not in target_files:
                    target_files.append(current_file)
                continue

            elif line.startswith("@@"):
                if not current_file:
                    syntax_errors.append(f"Hunk header without file header at line {i+1}.")
                    i += 1
                    continue

                match = cls.HUNK_HEADER_PATTERN.match(line)
                if not match:
                    syntax_errors.append(f"Malformed hunk header format at line {i+1}: '{line}'.")
                i += 1
                continue

            i += 1

        if not target_files and not syntax_errors:
            syntax_errors.append("No valid file patches found in diff.")

        return PatchValidationResult(
            is_valid=(len(syntax_errors) == 0),
            target_files=target_files,
            syntax_errors=syntax_errors,
        )
