"""FastAPI dependency injection utilities."""

from typing import Optional
from fastapi import Header


def get_session_key(
    x_session_gemini_key: Optional[str] = Header(None, alias="X-Session-Gemini-Key"),
) -> Optional[str]:
    """Extract optional session API key passed in request header."""
    if x_session_gemini_key and x_session_gemini_key.strip():
        return x_session_gemini_key.strip()
    return None
