"""Docker 3-way feasibility check and untrusted repository refusal policy."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class SandboxUnavailableException(Exception):
    """Raised when container sandbox is unavailable and target is not a trusted fixture."""


@dataclass
class DockerFeasibility:
    cli_available: bool
    daemon_responsive: bool
    image_available: bool
    is_usable: bool


class SandboxFeasibilityChecker:
    """Verifies Docker readiness and enforces execution boundaries."""

    @classmethod
    def get_docker_bin(cls) -> Optional[str]:
        """Resolves docker CLI executable, checking system PATH and Windows Docker Desktop location."""
        import os, sys
        cli = None
        if sys.platform.startswith("win"):
            cli = shutil.which("docker.exe")
            if not cli:
                known = os.path.expandvars(r"%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe")
                if os.path.exists(known):
                    cli = known
        if not cli:
            cli = shutil.which("docker")
        return cli

    @classmethod
    def check_docker(cls, required_image: Optional[str] = None) -> DockerFeasibility:
        """Perform the 3-way check: CLI exists, daemon responds, image exists."""
        # 1. CLI Check
        docker_cli = cls.get_docker_bin()
        if not docker_cli:
            return DockerFeasibility(
                cli_available=False,
                daemon_responsive=False,
                image_available=False,
                is_usable=False,
            )

        # 2. Daemon Check
        try:
            res = subprocess.run(
                [docker_cli, "info"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            daemon_ok = res.returncode == 0
        except Exception:
            daemon_ok = False

        if not daemon_ok:
            return DockerFeasibility(
                cli_available=True,
                daemon_responsive=False,
                image_available=False,
                is_usable=False,
            )

        # 3. Image Check
        image_name = required_image or "patchpilot-sandbox:python-3.12"
        try:
            res_img = subprocess.run(
                [docker_cli, "image", "inspect", image_name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            image_ok = res_img.returncode == 0
        except Exception:
            image_ok = False

        return DockerFeasibility(
            cli_available=True,
            daemon_responsive=True,
            image_available=image_ok,
            is_usable=image_ok,
        )

    @staticmethod
    def is_trusted_fixture(repo_path: Path) -> bool:
        """Determine if a repository path belongs to authorized preconfigured demonstration fixtures."""
        posix = "/" + str(repo_path.resolve()).replace("\\", "/").lower().strip("/") + "/"
        return "/fixtures/" in posix

