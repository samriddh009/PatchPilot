"""Workspace management with strict directory jailing and source immutability."""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from patchpilot import config


class PathTraversalSecurityException(Exception):
    """Raised when a path escapes the authorized workspace root."""


class SymlinkEscapeSecurityException(Exception):
    """Raised when a symlink points outside the authorized workspace root."""


class WorkspaceManager:
    """Manages ephemeral workspace provisioning, strict directory jailing, and cleanup."""

    # Patterns excluded from copying to ephemeral workspaces
    EXCLUDED_PATTERNS = {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".coverage",
        ".idea",
        ".vscode",
        ".env",
    }

    SECRET_FILENAMES = {
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

    @classmethod
    def is_secret_file(cls, filename: str) -> bool:
        """Determines if a filename represents an environment secret or credential."""
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
        return False

    @staticmethod
    def resolve_jailed_path(workspace_root: Path, requested_path: str) -> Path:
        """
        Canonicalize a path and strictly enforce directory jailing within workspace root.
        Raises PathTraversalSecurityException or SymlinkEscapeSecurityException on breach.
        """
        root_resolved = workspace_root.resolve()
        # Normalise separators and construct target
        cleaned_path = requested_path.strip().lstrip("/\\")
        target_path = (workspace_root / cleaned_path).resolve()

        # Enforce boundary confinement
        try:
            target_path.relative_to(root_resolved)
        except ValueError:
            raise PathTraversalSecurityException(
                f"Security violation: path '{requested_path}' escapes workspace jail '{root_resolved}'."
            )

        # Enforce symlink safety if link target exists
        if target_path.is_symlink():
            link_target = target_path.readlink()
            if not link_target.is_absolute():
                link_target = (target_path.parent / link_target).resolve()
            else:
                link_target = link_target.resolve()

            try:
                link_target.relative_to(root_resolved)
            except ValueError:
                raise SymlinkEscapeSecurityException(
                    f"Security violation: symlink '{requested_path}' points outside workspace jail."
                )

        return target_path

    @classmethod
    def compute_tree_hash(cls, root_path: Path) -> str:
        """Compute a deterministic SHA-256 tree hash over all project files."""
        hasher = hashlib.sha256()
        resolved_root = root_path.resolve()

        for dirpath, dirnames, filenames in os.walk(resolved_root):
            # Prune excluded directories in-place
            dirnames[:] = [d for d in dirnames if d not in cls.EXCLUDED_PATTERNS]
            dirnames.sort()

            for fname in sorted(filenames):
                if fname.endswith((".pyc", ".pyo", ".swp", ".tmp")) or cls.is_secret_file(fname):
                    continue
                file_path = Path(dirpath) / fname
                rel_path = file_path.relative_to(resolved_root).as_posix()
                hasher.update(rel_path.encode("utf-8"))

                try:
                    content = file_path.read_bytes()
                    hasher.update(content)
                except (OSError, PermissionError):
                    continue

        return hasher.hexdigest()

    @classmethod
    def create_ephemeral_workspace(cls, source_repo_path: Path, prefix: Optional[str] = None) -> Path:
        """
        Deep-copy authorized source repository into an ephemeral, disposable workspace directory.
        Preserves original project without touching it.
        """
        source_resolved = source_repo_path.resolve()
        if not source_resolved.exists() or not source_resolved.is_dir():
            raise ValueError(f"Source repository does not exist or is not a directory: {source_resolved}")

        pfx = prefix or config.WORKSPACE_TMP_PREFIX
        temp_dir = Path(tempfile.mkdtemp(prefix=pfx))

        def ignore_filter(dir_name: str, contents: list[str]) -> set[str]:
            ignored = set()
            for item in contents:
                if item in cls.EXCLUDED_PATTERNS or cls.is_secret_file(item) or item.endswith((".pyc", ".pyo", ".tmp")):
                    ignored.add(item)
            return ignored

        # Perform deep copy
        for item in source_resolved.iterdir():
            if item.name in cls.EXCLUDED_PATTERNS or cls.is_secret_file(item.name):
                continue
            dest = temp_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=ignore_filter, symlinks=False)
            else:
                shutil.copy2(item, dest)

        return temp_dir

    @classmethod
    def cleanup_workspace(cls, workspace_path: Optional[Path]) -> None:
        """Safely delete the ephemeral workspace and all temporary contents."""
        if workspace_path and workspace_path.exists() and workspace_path.is_dir():
            try:
                shutil.rmtree(workspace_path, ignore_errors=True)
            except Exception:
                pass

    # Aliases
    calculate_tree_hash = compute_tree_hash
    cleanup_ephemeral_workspace = cleanup_workspace
