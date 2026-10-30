"""Workspace package exports for PatchPilot."""

from patchpilot.workspace.manager import (
    WorkspaceManager,
    PathTraversalSecurityException,
    SymlinkEscapeSecurityException,
)

__all__ = [
    "WorkspaceManager",
    "PathTraversalSecurityException",
    "SymlinkEscapeSecurityException",
]
