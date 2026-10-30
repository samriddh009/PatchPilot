"""Tests for unified diff validator and atomic patch application."""

from pathlib import Path
import pytest

from patchpilot.patcher.validator import PatchValidator
from patchpilot.patcher.applier import PatchApplier


def test_validate_empty_diff(tmp_path):
    res = PatchValidator.validate_diff(tmp_path, "")
    assert not res.is_valid
    assert "empty" in res.syntax_errors[0].lower()


def test_validate_malformed_diff_header(tmp_path):
    diff = "--- a/src/main.py\n@@ -1,1 +1,1 @@\n-old\n+new"
    res = PatchValidator.validate_diff(tmp_path, diff)
    assert not res.is_valid
    assert any("missing '+++ '" in err for err in res.syntax_errors)


def test_validate_rejects_path_traversal_in_diff(tmp_path):
    diff = """--- a/../../outside.py
+++ b/../../outside.py
@@ -1,1 +1,1 @@
-old
+new
"""
    res = PatchValidator.validate_diff(tmp_path, diff)
    assert not res.is_valid
    assert any("traversal" in err.lower() or "outside" in err.lower() for err in res.syntax_errors)


def test_apply_patch_valid(tmp_path):
    workspace = tmp_path / "work"
    workspace.mkdir()
    file_path = workspace / "math.py"
    file_path.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

    diff = """--- a/math.py
+++ b/math.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""
    res = PatchApplier.apply_patch(workspace, diff)
    assert res.applied is True
    assert "math.py" in res.modified_files
    assert res.total_insertions == 1
    assert res.total_deletions == 1

    content = file_path.read_text(encoding="utf-8")
    assert "return a + b" in content
    # Ensure backup file is cleaned up after successful application
    assert not (workspace / "math.py.ppbak").exists()


def test_apply_patch_rollback_on_mismatch(tmp_path):
    workspace = tmp_path / "work"
    workspace.mkdir()
    file_path = workspace / "test.py"
    original_text = "def hello():\n    return 'hello'\n"
    file_path.write_text(original_text, encoding="utf-8")

    # Diff has context that does not match original file
    diff = """--- a/test.py
+++ b/test.py
@@ -1,2 +1,2 @@
 def completely_different():
-    return 'mismatch'
+    return 'new'
"""
    res = PatchApplier.apply_patch(workspace, diff)
    assert res.applied is False
    assert "Hunk context mismatch" in res.error

    # Ensure file was rolled back to exact original content
    assert file_path.read_text(encoding="utf-8") == original_text
    assert not (workspace / "test.py.ppbak").exists()
