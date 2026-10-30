"""In-memory BYOK session key management and credential sanitization."""

import re
from typing import List, Optional, Tuple

import httpx

from patchpilot import config


class SessionKeyStore:
    """Stores user-supplied Gemini API key and active model strictly in memory for the active session."""

    def __init__(self):
        self._session_key: Optional[str] = None
        self._session_model: Optional[str] = None

    def set_session_key(self, api_key: str) -> None:
        """Store key in memory only."""
        self._session_key = api_key.strip()

    def get_session_key(self) -> Optional[str]:
        return self._session_key

    def set_session_model(self, model_name: str) -> None:
        """Store active model choice in session memory."""
        cleaned = model_name.strip().removeprefix("models/")
        self._session_model = cleaned

    def get_session_model(self) -> Optional[str]:
        return self._session_model

    def resolve_model(self, model_override: Optional[str] = None) -> str:
        """Resolve model in order: explicit argument -> session model -> config.GEMINI_MODEL."""
        if model_override and model_override.strip():
            return model_override.strip().removeprefix("models/")
        if self._session_model:
            return self._session_model
        return config.GEMINI_MODEL.removeprefix("models/")

    def clear(self) -> None:
        self._session_key = None
        self._session_model = None

    def resolve_key(self, header_key: Optional[str] = None) -> Tuple[Optional[str], str]:
        """
        Resolve active API key and source ('session_header', 'environment_variable', 'none').
        """
        if header_key and header_key.strip():
            return header_key.strip(), "session_header"
        if self._session_key:
            return self._session_key, "session_header"
        if config.GEMINI_API_KEY and config.GEMINI_API_KEY.strip():
            return config.GEMINI_API_KEY.strip(), "environment_variable"
        return None, "none"

    @classmethod
    def redact_secrets(cls, text: str) -> str:
        """Mask potential API keys and secrets from output and logs."""
        if not text:
            return text
        # Redact Google API key pattern
        text = re.sub(r"AIza[0-9A-Za-z\-_]{20,60}", "AIzaSyD...[REDACTED]", text)
        return text

    @classmethod
    async def fetch_available_models(cls, api_key: str) -> Tuple[List[str], Optional[str], bool]:
        """Query Gemini API v1beta /models endpoint to discover live available models for key.
        
        Returns:
            Tuple[List[str], Optional[str], bool]: (models_list, error_message, is_live_discovered)
        """
        if not api_key or len(api_key.strip()) < 10:
            return [], "No API key supplied or key is too short.", False

        clean_key = api_key.strip()
        url = f"{config.GEMINI_API_BASE_URL}/v1beta/models?key={clean_key}"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    models = []
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        if not methods or "generateContent" in methods:
                            clean_name = m.get("name", "").removeprefix("models/")
                            if clean_name:
                                models.append(clean_name)
                    return models, None, True

                # Non-200 status code: extract upstream error message safely
                try:
                    err_payload = res.json().get("error", {})
                    msg = err_payload.get("message") or res.text
                    status = err_payload.get("status") or f"HTTP_{res.status_code}"
                except Exception:
                    msg = res.text
                    status = f"HTTP_{res.status_code}"

                sanitized = cls.redact_secrets(msg)
                return [], f"Gemini API error ({status} {res.status_code}): {sanitized}", False

        except httpx.TimeoutException:
            return [], "Connection to Google Gemini API timed out.", False
        except Exception as exc:
            return [], f"Failed to connect to Gemini API: {cls.redact_secrets(str(exc))}", False

    @classmethod
    async def validate_key_live(
        cls, api_key: str, model_candidate: Optional[str] = None
    ) -> Tuple[bool, Optional[str], List[str], bool]:
        """Conduct an active probe validating the Gemini API key against Google AI Studio.
        
        Returns:
            Tuple[bool, Optional[str], List[str], bool]: (valid, error_message, available_models, is_live_discovered)
        """
        if not api_key or len(api_key.strip()) < 20:
            return False, "API key is too short or malformed.", [], False

        clean_key = api_key.strip()
        models, err_msg, is_live = await cls.fetch_available_models(clean_key)

        if not is_live:
            return False, err_msg, [], False

        target_model = (model_candidate or session_store.resolve_model()).removeprefix("models/")

        if not models:
            return False, "Gemini API authenticated successfully, but returned 0 models supporting content generation.", [], True

        if target_model not in models:
            sample = ", ".join(models[:6])
            return (
                False,
                f"Configured model '{target_model}' was not found in available models for this API key. Available models: {sample}.",
                models,
                True,
            )

        return True, None, models, True


session_store = SessionKeyStore()
