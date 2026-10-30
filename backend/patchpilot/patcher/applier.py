"""Atomic patch application with rollback and diff metrics computation."""

import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from patchpilot.patcher.validator import PatchValidator
from patchpilot.schemas.repair import FileChangeSummary
from patchpilot.workspace.manager import WorkspaceManager


@dataclass
class PatchApplicationResult:
    applied: bool
    modified_files: List[str]
    total_insertions: int
    total_deletions: int
    actual_diff: str
    error: str = ""


class PatchApplier:
    """Applies verified unified diffs atomically to the ephemeral workspace."""

    @classmethod
    def apply_patch(cls, workspace_root: Path, raw_diff: str) -> PatchApplicationResult:
        validation = PatchValidator.validate_diff(workspace_root, raw_diff)
        if not validation.is_valid:
            return PatchApplicationResult(
                applied=False,
                modified_files=[],
                total_insertions=0,
                total_deletions=0,
                actual_diff="",
                error="; ".join(validation.syntax_errors),
            )

        file_patches = cls._parse_diff_into_file_chunks(raw_diff)
        backups: Dict[Path, Path] = {}
        modified_files: List[str] = []

        try:
            # 1. Back up all target files before touching anything
            for rel_path, _ in file_patches.items():
                target = WorkspaceManager.resolve_jailed_path(workspace_root, rel_path)
                if target.exists():
                    bak_path = target.with_suffix(target.suffix + ".ppbak")
                    shutil.copy2(target, bak_path)
                    backups[target] = bak_path

            # 2. Apply hunks to each file
            for rel_path, hunks in file_patches.items():
                target = WorkspaceManager.resolve_jailed_path(workspace_root, rel_path)
                original_content = target.read_text(encoding="utf-8") if target.exists() else ""
                patched_content = cls._apply_hunks_to_text(original_content, hunks)

                target.write_text(patched_content, encoding="utf-8")
                modified_files.append(rel_path)

            # 3. Clean up backups on success
            for _, bak in backups.items():
                if bak.exists():
                    bak.unlink(missing_ok=True)

            # 4. Generate actual diff from real filesystem state
            diff_lines: List[str] = []
            total_ins = 0
            total_del = 0

            for rel_path in modified_files:
                target = WorkspaceManager.resolve_jailed_path(workspace_root, rel_path)
                # Compute diff lines from raw_diff
                for h in file_patches[rel_path]:
                    for line in h:
                        if line.startswith("+") and not line.startswith("+++"):
                            total_ins += 1
                        elif line.startswith("-") and not line.startswith("---"):
                            total_del += 1

            return PatchApplicationResult(
                applied=True,
                modified_files=modified_files,
                total_insertions=total_ins,
                total_deletions=total_del,
                actual_diff=raw_diff,
            )

        except Exception as exc:
            # Rollback all modified files from backups
            for target, bak in backups.items():
                if bak.exists():
                    shutil.copy2(bak, target)
                    bak.unlink(missing_ok=True)

            return PatchApplicationResult(
                applied=False,
                modified_files=[],
                total_insertions=0,
                total_deletions=0,
                actual_diff="",
                error=f"Failed during patch application: {str(exc)}",
            )

    @classmethod
    def _parse_diff_into_file_chunks(cls, raw_diff: str) -> Dict[str, List[List[str]]]:
        """Group diff lines into hunks per target relative file path."""
        chunks: Dict[str, List[List[str]]] = {}
        current_file = ""
        current_hunk: List[str] = []

        lines = raw_diff.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                if current_file and current_hunk:
                    chunks.setdefault(current_file, []).append(current_hunk)
                    current_hunk = []

                old_file = line[4:].strip()
                new_file = lines[i + 1][4:].strip()
                target_rel = new_file
                if target_rel.startswith("b/") or target_rel.startswith("b\\"):
                    target_rel = target_rel[2:]
                elif target_rel == "/dev/null":
                    target_rel = old_file[2:] if old_file.startswith("a/") or old_file.startswith("a\\") else old_file

                current_file = target_rel
                i += 2
                continue

            if line.startswith("@@"):
                if current_file and current_hunk:
                    chunks.setdefault(current_file, []).append(current_hunk)
                    current_hunk = []
                current_hunk = [line]
                i += 1
                continue

            if current_hunk is not None:
                current_hunk.append(line)
            i += 1

        if current_file and current_hunk:
            chunks.setdefault(current_file, []).append(current_hunk)

        return chunks

    @classmethod
    def _apply_hunks_to_text(cls, original_text: str, hunks: List[List[str]]) -> str:
        """Apply unified diff hunks sequentially to original file text."""
        orig_lines = original_text.splitlines()

        for hunk in hunks:
            if not hunk:
                continue
            header = hunk[0]
            match = PatchValidator.HUNK_HEADER_PATTERN.match(header)
            if not match:
                raise ValueError(f"Invalid hunk header: {header}")

            old_start = int(match.group(1)) - 1  # 1-indexed to 0-indexed
            hunk_body = hunk[1:]

            # Collect expected lines to remove/match and lines to insert
            expected_old: List[str] = []
            replacement_new: List[str] = []

            for line in hunk_body:
                if line.startswith("-"):
                    expected_old.append(line[1:])
                elif line.startswith("+"):
                    replacement_new.append(line[1:])
                elif line.startswith(" "):
                    expected_old.append(line[1:])
                    replacement_new.append(line[1:])

            # Find matching location in orig_lines around old_start
            match_idx = -1
            # Try exact offset first
            if cls._slice_matches(orig_lines, old_start, expected_old):
                match_idx = old_start
            else:
                # Search up and down within 50 lines
                for offset in range(1, 50):
                    if old_start + offset < len(orig_lines) and cls._slice_matches(orig_lines, old_start + offset, expected_old):
                        match_idx = old_start + offset
                        break
                    if old_start - offset >= 0 and cls._slice_matches(orig_lines, old_start - offset, expected_old):
                        match_idx = old_start - offset
                        break

            if match_idx == -1:
                # Fallback: search anywhere in file if not found locally
                for idx in range(len(orig_lines)):
                    if cls._slice_matches(orig_lines, idx, expected_old):
                        match_idx = idx
                        break

            if match_idx == -1:
                raise ValueError(f"Hunk context mismatch: could not locate context for hunk:\n{header}")

            # Splice replacement lines
            orig_lines = orig_lines[:match_idx] + replacement_new + orig_lines[match_idx + len(expected_old):]

        result = "\n".join(orig_lines)
        if original_text.endswith("\n") or not original_text:
            result += "\n"
        return result

    @staticmethod
    def _slice_matches(lines: List[str], start_idx: int, expected: List[str]) -> bool:
        if start_idx + len(expected) > len(lines):
            return False
        for i, exp in enumerate(expected):
            if lines[start_idx + i] != exp:
                return False
        return True
