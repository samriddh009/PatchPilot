"""Common shared models and standard error envelopes."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return the current UTC timestamp formatted as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error identifier")
    message: str = Field(..., description="Human-readable error description")
    details: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic contextual metadata")
    timestamp: str = Field(default_factory=utc_now_iso, description="ISO 8601 UTC timestamp")


class APIError(BaseModel):
    """PatchPilot standard structured JSON error envelope."""
    error: ErrorDetail
