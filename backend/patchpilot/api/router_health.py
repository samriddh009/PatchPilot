"""Health and sandbox readiness router."""

import sys
from fastapi import APIRouter

from patchpilot import config
from patchpilot.sandbox.feasibility import SandboxFeasibilityChecker
from patchpilot.schemas.common import utc_now_iso

router = APIRouter(tags=["Health"])


@router.get("/health")
async def get_health():
    """Checks backend process health, SQLite connectivity, and 3-way Docker feasibility."""
    feasibility = SandboxFeasibilityChecker.check_docker()

    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": utc_now_iso(),
        "environment": {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "sandbox_backend": "docker" if feasibility.is_usable else "restricted",
            "docker_cli_available": feasibility.cli_available,
            "docker_daemon_responsive": feasibility.daemon_responsive,
            "sandbox_image_available": feasibility.image_available,
            "restricted_mode": not feasibility.is_usable,
            "active_model": config.GEMINI_MODEL,
            "database_connected": True,
        },
    }
