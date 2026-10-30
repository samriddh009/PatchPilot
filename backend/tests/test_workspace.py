"""Tests for workspace manager, directory jailing, ephemeral copies, and immutability."""

import os
import shutil
import tempfile
from pathlib import Path
import pytest

from patchpilot.workspace.manager import (
    WorkspaceManager,
    PathTraversalSecurityException,
    SymlinkEscapeSecurityException,
)


def test_canonicalize_and_jail_valid(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    file_path = root / "src" / "main.py"
    file_path.parent.mkdir()
    file_path.write_text("print('hello')", encoding="utf-8")

    resolved = WorkspaceManager.resolve_jailed_path(root, "src/main.py")
    assert resolved == file_path.resolve()
    assert resolved.exists()


def test_canonicalize_and_jail_rejects_traversal(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(PathTraversalSecurityException):
        WorkspaceManager.resolve_jailed_path(root, "../outside.txt")

    with pytest.raises(PathTraversalSecurityException):
        WorkspaceManager.resolve_jailed_path(root, "../../etc/passwd")

    with pytest.raises(PathTraversalSecurityException):
        WorkspaceManager.resolve_jailed_path(root, "src/../../outside.txt")


def test_canonicalize_and_jail_rejects_absolute_path_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()

    # On Windows C:\Windows or /etc on Unix
    abs_escape = "C:/Windows/System32" if os.name == "nt" else "/etc/passwd"
    with pytest.raises(PathTraversalSecurityException):
        WorkspaceManager.resolve_jailed_path(root, abs_escape)


def test_create_and_cleanup_ephemeral_workspace(tmp_path):
    src_dir = tmp_path / "original_repo"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("x = 10\n", encoding="utf-8")
    (src_dir / "tests").mkdir()
    (src_dir / "tests" / "test_app.py").write_text("def test_x(): pass\n", encoding="utf-8")

    initial_hash = WorkspaceManager.calculate_tree_hash(src_dir)
    assert len(initial_hash) == 64

    # Create working copy
    work_dir = WorkspaceManager.create_ephemeral_workspace(src_dir, "rep_test_01")
    try:
        assert work_dir.exists()
        assert (work_dir / "app.py").exists()
        assert (work_dir / "app.py").read_text(encoding="utf-8") == "x = 10\n"

        # Mutate working copy
        (work_dir / "app.py").write_text("x = 20\n", encoding="utf-8")
        assert (work_dir / "app.py").read_text(encoding="utf-8") == "x = 20\n"

        # Verify original was NOT mutated
        assert (src_dir / "app.py").read_text(encoding="utf-8") == "x = 10\n"
        after_hash = WorkspaceManager.calculate_tree_hash(src_dir)
        assert initial_hash == after_hash
    finally:
        WorkspaceManager.cleanup_ephemeral_workspace(work_dir)
        assert not work_dir.exists()


def test_calculate_tree_hash_ignores_ephemeral_artifacts(tmp_path):
    root = tmp_path / "repo_hash"
    root.mkdir()
    (root / "module.py").write_text("def run(): pass\n", encoding="utf-8")

    hash1 = WorkspaceManager.calculate_tree_hash(root)

    # Create pycache and git
    pycache = root / "__pycache__"
    pycache.mkdir()
    (pycache / "module.cpython-312.pyc").write_bytes(b"\x00\x01\x02")

    hash2 = WorkspaceManager.calculate_tree_hash(root)
    # Tree hash excludes __pycache__
    assert hash1 == hash2
