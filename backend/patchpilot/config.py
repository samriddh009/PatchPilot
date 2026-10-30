"""Application configuration settings for PatchPilot backend."""

import os
from pathlib import Path

# Base Paths
BACKEND_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = BACKEND_ROOT.parent

# Database configuration
DATABASE_PATH = Path(os.getenv("PATCHPILOT_DB_PATH", str(BACKEND_ROOT / "patchpilot.db")))

# Network & Loopback Security configuration
HOST = os.getenv("PATCHPILOT_HOST", "127.0.0.1")
PORT = int(os.getenv("PATCHPILOT_PORT", "8000"))
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
ALLOWED_HOSTS = ["127.0.0.1", "127.0.0.1:8000", "localhost", "localhost:8000", "testserver"]

# Gemini Provider configuration
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
SUPPORTED_GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash",
]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_BASE_URL = os.getenv("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com")

# Execution Sandbox & Process safety
TARGET_TIMEOUT_SECONDS = int(os.getenv("PATCHPILOT_TARGET_TIMEOUT", "30"))
REGRESSION_TIMEOUT_SECONDS = int(os.getenv("PATCHPILOT_REGRESSION_TIMEOUT", "60"))
OUTPUT_MAX_BYTES = int(os.getenv("PATCHPILOT_OUTPUT_MAX_BYTES", "65536"))  # 64 KB
MAX_RECOVERY_ATTEMPTS = 1

# Ephemeral workspace prefix
WORKSPACE_TMP_PREFIX = "patchpilot_ws_"
