"""Real Google Gemini API client adapter."""

import asyncio
import json
import re
import uuid
from typing import Any, Dict, List, Optional

import httpx

from patchpilot import config
from patchpilot.gemini.base import ModelProvider, ProviderPatchProposal
from patchpilot.gemini.prompts import (
    SYSTEM_INSTRUCTION,
    format_patch_prompt,
    format_recovery_prompt,
)
from patchpilot.gemini.session_store import SessionKeyStore, session_store
from patchpilot.patcher.validator import PatchValidator


REPAIR_PROPOSAL_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "explanation": {
            "type": "STRING",
            "description": "Brief technical explanation of root cause and fix",
        },
        "target_files": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "Relative file paths modified by this patch",
        },
        "unified_diff": {
            "type": "STRING",
            "description": "Syntactically valid unified diff using standard headers",
        },
    },
    "required": ["explanation", "target_files", "unified_diff"],
}


class GeminiProviderError(Exception):
    """Raised on Gemini API errors."""
    def __init__(self, code: str, message: str, status_code: int = 500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class GeminiProvider(ModelProvider):
    """Production provider calling Google Gemini REST API."""

    is_stub = False

    def __init__(self, model_name: Optional[str] = None):
        self._explicit_model = model_name

    @property
    def model_name(self) -> str:
        return session_store.resolve_model(self._explicit_model)

    async def validate_connection(self, api_key: str) -> bool:
        valid, _, _, _ = await SessionKeyStore.validate_key_live(api_key, model_candidate=self.model_name)
        return valid

    async def generate_patch(
        self,
        bug_report: str,
        file_contexts: List[Dict[str, Any]],
        failure_logs: str,
        api_key: Optional[str] = None,
    ) -> ProviderPatchProposal:
        prompt_text = format_patch_prompt(bug_report, file_contexts, failure_logs)
        return await self._call_model(prompt_text, api_key)

    async def generate_recovery_patch(
        self,
        bug_report: str,
        previous_diff: str,
        recovery_diagnostic: str,
        file_contexts: List[Dict[str, Any]],
        api_key: Optional[str] = None,
    ) -> ProviderPatchProposal:
        prompt_text = format_recovery_prompt(bug_report, previous_diff, recovery_diagnostic, file_contexts)
        return await self._call_model(prompt_text, api_key)

    @classmethod
    def extract_and_parse_json(cls, candidate_text: str) -> Dict[str, Any]:
        """Safely extracts and parses JSON repair proposal from model text.
        
        Permits:
        1. A single valid JSON object ({...})
        2. A clearly delimited markdown code block (```json ... ``` or ``` ... ```)
        
        Rejects arbitrary execution, ordinary text without JSON, and malformed JSON payloads.
        """
        cleaned = candidate_text.strip()
        if not cleaned:
            raise GeminiProviderError(
                code="PROVIDER_EMPTY_RESPONSE",
                message="Gemini candidate contained no text content.",
                status_code=502,
            )

        json_str: Optional[str] = None

        # 1. Entire output enclosed in markdown code block
        if cleaned.startswith("```"):
            match = re.match(r"^```(?:json)?\s*\n?([\s\S]*?)\n?```$", cleaned, re.IGNORECASE)
            if match:
                json_str = match.group(1).strip()
            else:
                fenced_inner = re.sub(r"^```[a-zA-Z]*\s*\n?", "", cleaned)
                fenced_inner = re.sub(r"\n?```$", "", fenced_inner).strip()
                json_str = fenced_inner

        # 2. Text containing a clearly delimited ```json { ... } ``` code block
        if json_str is None:
            blocks = re.findall(r"```(?:json)?\s*\n?({[\s\S]*?})\n?```", cleaned, re.IGNORECASE)
            if len(blocks) == 1:
                json_str = blocks[0].strip()

        # 3. Direct JSON or JSON within text:
        if json_str is None:
            if "{" in cleaned:
                start_idx = cleaned.find("{")
                end_idx = cleaned.rfind("}")
                if end_idx != -1 and end_idx > start_idx:
                    json_str = cleaned[start_idx:end_idx + 1].strip()
                else:
                    json_str = cleaned[start_idx:].strip()

        # 4. If no '{' at all, it is ordinary text without JSON
        if json_str is None:
            snippet = (cleaned[:120] + "...") if len(cleaned) > 120 else cleaned
            sanitized = SessionKeyStore.redact_secrets(snippet)
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message=f"Model returned ordinary text instead of required JSON repair proposal: '{sanitized}'",
                status_code=502,
            )

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as exc:
            sanitized_err = SessionKeyStore.redact_secrets(str(exc))
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message=f"Model returned invalid JSON response: {sanitized_err}",
                status_code=502,
            )

        if not isinstance(parsed, dict):
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message=f"Model returned JSON type '{type(parsed).__name__}', expected JSON object (dict).",
                status_code=502,
            )

        return parsed

    @classmethod
    def validate_patch_proposal(cls, parsed: Dict[str, Any]) -> ProviderPatchProposal:
        """Validates parsed proposal against strict schema, path boundaries, diff syntax, and size limits."""
        # 1. Required fields
        required_fields = ["explanation", "target_files", "unified_diff"]
        missing = [f for f in required_fields if f not in parsed]
        if missing:
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message=f"Model JSON response missing required fields: {', '.join(missing)}.",
                status_code=502,
            )

        explanation = parsed.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message="Field 'explanation' must be a non-empty string.",
                status_code=502,
            )

        target_files = parsed.get("target_files")
        if not isinstance(target_files, list) or len(target_files) == 0:
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message="Field 'target_files' must be a non-empty list of file paths.",
                status_code=502,
            )

        sanitized_targets: List[str] = []
        for tf in target_files:
            if not isinstance(tf, str) or not tf.strip():
                raise GeminiProviderError(
                    code="PROVIDER_MALFORMED_RESPONSE",
                    message="All entries in 'target_files' must be non-empty strings.",
                    status_code=502,
                )
            clean_tf = tf.strip().replace("\\", "/")
            if (
                ".." in clean_tf
                or clean_tf.startswith("/")
                or bool(re.match(r"^[a-zA-Z]:", clean_tf))
            ):
                raise GeminiProviderError(
                    code="PROVIDER_MALFORMED_RESPONSE",
                    message=f"Field 'target_files' contains illegal or traversal path: '{tf}'.",
                    status_code=502,
                )
            sanitized_targets.append(clean_tf)

        raw_diff = parsed.get("unified_diff")
        if not isinstance(raw_diff, str) or not raw_diff.strip():
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message="Field 'unified_diff' must be a non-empty unified diff string.",
                status_code=502,
            )

        # Patch size limit (default 64KB)
        if len(raw_diff.encode("utf-8")) > config.OUTPUT_MAX_BYTES:
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message=f"Model proposed patch size exceeds limit ({config.OUTPUT_MAX_BYTES} bytes).",
                status_code=502,
            )

        # Diff syntax and structure validation
        diff_lines = raw_diff.splitlines()
        has_file_header = False
        has_hunk_header = False
        diff_files: List[str] = []

        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("--- ") and i + 1 < len(diff_lines) and diff_lines[i + 1].startswith("+++ "):
                has_file_header = True
                old_file = line[4:].strip()
                new_file = diff_lines[i + 1][4:].strip()
                i += 2

                target_rel = new_file
                if target_rel.startswith("b/") or target_rel.startswith("b\\"):
                    target_rel = target_rel[2:]
                elif target_rel == "/dev/null":
                    target_rel = old_file[2:] if (old_file.startswith("a/") or old_file.startswith("a\\")) else old_file

                clean_rel = target_rel.replace("\\", "/").strip()
                if (
                    ".." in clean_rel
                    or clean_rel.startswith("/")
                    or bool(re.match(r"^[a-zA-Z]:", clean_rel))
                ):
                    raise GeminiProviderError(
                        code="PROVIDER_MALFORMED_RESPONSE",
                        message=f"Diff header contains illegal or traversal path: '{target_rel}'.",
                        status_code=502,
                    )
                if clean_rel not in diff_files:
                    diff_files.append(clean_rel)
                continue

            if line.startswith("@@"):
                if PatchValidator.HUNK_HEADER_PATTERN.match(line):
                    has_hunk_header = True
                else:
                    raise GeminiProviderError(
                        code="PROVIDER_MALFORMED_RESPONSE",
                        message=f"Malformed unified diff hunk header: '{line}'.",
                        status_code=502,
                    )
            i += 1

        if not has_file_header or not has_hunk_header:
            raise GeminiProviderError(
                code="PROVIDER_MALFORMED_RESPONSE",
                message="Proposed unified_diff lacks standard diff file headers (--- / +++) or hunk headers (@@ ... @@).",
                status_code=502,
            )

        return ProviderPatchProposal(
            patch_id=f"patch_{uuid.uuid4().hex[:12]}",
            explanation=explanation.strip(),
            raw_diff=raw_diff,
            target_files=sanitized_targets,
        )

    async def _call_model(self, prompt: str, api_key: Optional[str] = None) -> ProviderPatchProposal:
        resolved_key, _ = session_store.resolve_key(api_key)
        if not resolved_key:
            raise GeminiProviderError(
                code="PROVIDER_KEY_MISSING",
                message="No Gemini API key supplied in session or environment.",
                status_code=401,
            )

        active_model = self.model_name.removeprefix("models/")
        url = f"{config.GEMINI_API_BASE_URL}/v1beta/models/{active_model}:generateContent?key={resolved_key}"

        # Prefer structured output mode matching explicit contract
        payload: Dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": REPAIR_PROPOSAL_SCHEMA,
                "temperature": 0.1,
            },
        }

        try:
            data = None
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        res = await client.post(url, json=payload)

                        # 1. Parameter compatibility adaptation on 400
                        if res.status_code == 400:
                            err_text = res.text.lower()
                            modified = False

                            # Handle "Developer instruction is not enabled for this model"
                            if (
                                "developer instruction" in err_text
                                or "system instruction" in err_text
                                or "system_instruction" in err_text
                            ):
                                if "system_instruction" in payload:
                                    payload.pop("system_instruction", None)
                                    combined_prompt = f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
                                    payload["contents"] = [{"role": "user", "parts": [{"text": combined_prompt}]}]
                                    modified = True

                            # Handle response_schema rejection
                            if "response_schema" in err_text or "schema" in err_text:
                                payload["generationConfig"] = {
                                    "response_mime_type": "application/json",
                                    "temperature": 0.1,
                                }
                                modified = True
                            elif "response_mime_type" in err_text:
                                payload["generationConfig"] = {"temperature": 0.1}
                                modified = True

                            if modified:
                                res = await client.post(url, json=payload)

                        # 2. Bounded retry for transient 503 / 429 rate limit
                        if res.status_code in (429, 503) and attempt < max_retries:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue

                        if res.status_code != 200:
                            try:
                                err_payload = res.json().get("error", {})
                                upstream_code = err_payload.get("code") or res.status_code
                                upstream_msg = err_payload.get("message") or res.text
                                upstream_status = err_payload.get("status") or f"HTTP_{res.status_code}"
                            except Exception:
                                upstream_code = res.status_code
                                upstream_msg = res.text
                                upstream_status = f"HTTP_{res.status_code}"

                            sanitized = SessionKeyStore.redact_secrets(upstream_msg)

                            if res.status_code in (400, 401):
                                if (
                                    "key not valid" in sanitized.lower()
                                    or "api_key_invalid" in sanitized.lower()
                                    or res.status_code == 401
                                ):
                                    raise GeminiProviderError(
                                        code="PROVIDER_AUTH_FAILED",
                                        message=f"Gemini API authentication rejected ({upstream_status} {upstream_code}): {sanitized}",
                                        status_code=401,
                                    )
                                else:
                                    raise GeminiProviderError(
                                        code="PROVIDER_ERROR",
                                        message=f"Gemini API invalid request ({upstream_status} {upstream_code}): {sanitized}",
                                        status_code=400,
                                    )
                            elif res.status_code == 404:
                                supported = ", ".join(config.SUPPORTED_GEMINI_MODELS)
                                raise GeminiProviderError(
                                    code="PROVIDER_MODEL_UNAVAILABLE",
                                    message=f"Google Gemini API returned 404 ({upstream_status}): {sanitized}. (Requested model: '{active_model}', known candidates: {supported})",
                                    status_code=404,
                                )
                            elif res.status_code == 429:
                                raise GeminiProviderError(
                                    code="PROVIDER_QUOTA_EXHAUSTED",
                                    message=f"Gemini API quota or rate limit exceeded ({upstream_status} {upstream_code}): {sanitized}",
                                    status_code=429,
                                )
                            elif res.status_code == 503:
                                raise GeminiProviderError(
                                    code="PROVIDER_UNAVAILABLE",
                                    message=f"Google Gemini service is temporarily unavailable (503 {upstream_status}): {sanitized}. Please retry deliberately after service recovery.",
                                    status_code=503,
                                )
                            else:
                                raise GeminiProviderError(
                                    code="PROVIDER_ERROR",
                                    message=f"Gemini API returned error status {res.status_code} ({upstream_status}): {sanitized}",
                                    status_code=502,
                                )

                        data = res.json()
                        break

                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as net_err:
                    if attempt < max_retries:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    raise GeminiProviderError(
                        code="PROVIDER_TIMEOUT" if isinstance(net_err, (httpx.ConnectTimeout, httpx.ReadTimeout)) else "PROVIDER_NETWORK_ERROR",
                        message=f"Network communication with Gemini API failed: {str(net_err)}",
                        status_code=504 if isinstance(net_err, (httpx.ConnectTimeout, httpx.ReadTimeout)) else 502,
                    )

            if data is None:
                raise GeminiProviderError(
                    code="PROVIDER_EMPTY_RESPONSE",
                    message="Gemini API returned an empty response.",
                    status_code=502,
                )

            # 1. Top-level safety / block feedback
            prompt_feedback = data.get("promptFeedback", {})
            block_reason = prompt_feedback.get("blockReason")
            if block_reason:
                if block_reason == "SAFETY":
                    raise GeminiProviderError(
                        code="PROVIDER_SAFETY_REFUSAL",
                        message="Gemini model blocked request due to safety filters.",
                        status_code=400,
                    )
                raise GeminiProviderError(
                    code="PROVIDER_REFUSAL",
                    message=f"Gemini model blocked request due to policy ({block_reason}).",
                    status_code=400,
                )

            # 2. Candidate presence check
            candidates = data.get("candidates", [])
            if not candidates:
                raise GeminiProviderError(
                    code="PROVIDER_EMPTY_RESPONSE",
                    message="Gemini API returned an empty response (no candidates).",
                    status_code=502,
                )

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason")

            if finish_reason == "SAFETY":
                raise GeminiProviderError(
                    code="PROVIDER_SAFETY_REFUSAL",
                    message="Gemini model refused generation due to safety filters.",
                    status_code=400,
                )
            if finish_reason in ("RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"):
                raise GeminiProviderError(
                    code="PROVIDER_REFUSAL",
                    message=f"Gemini model refused generation due to content policy ({finish_reason}).",
                    status_code=400,
                )
            if finish_reason == "MAX_TOKENS":
                raise GeminiProviderError(
                    code="PROVIDER_TRUNCATED_RESPONSE",
                    message="Gemini response was truncated due to maximum token limit (finishReason: MAX_TOKENS).",
                    status_code=502,
                )

            # 3. Content parts extraction
            parts = candidate.get("content", {}).get("parts", [])
            if not parts:
                raise GeminiProviderError(
                    code="PROVIDER_EMPTY_RESPONSE",
                    message="Gemini candidate contained no content parts.",
                    status_code=502,
                )

            # Extract text parts, excluding internal model thoughts if present
            text_parts = [
                p.get("text", "")
                for p in parts
                if isinstance(p, dict) and not p.get("thought") and "text" in p
            ]
            if not text_parts:
                text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]

            candidate_text = "".join(text_parts).strip()
            if not candidate_text:
                raise GeminiProviderError(
                    code="PROVIDER_EMPTY_RESPONSE",
                    message="Gemini candidate contained no text content.",
                    status_code=502,
                )

            # 4. Safe JSON extraction and strict schema validation
            parsed = self.extract_and_parse_json(candidate_text)
            return self.validate_patch_proposal(parsed)

        except httpx.TimeoutException:
            raise GeminiProviderError(
                code="PROVIDER_TIMEOUT",
                message="Google Gemini API request timed out.",
                status_code=504,
            )
        except httpx.NetworkError:
            raise GeminiProviderError(
                code="PROVIDER_NETWORK_ERROR",
                message="Network connection to Gemini API failed.",
                status_code=503,
            )
        except GeminiProviderError:
            raise
        except Exception as exc:
            sanitized = SessionKeyStore.redact_secrets(str(exc))
            raise GeminiProviderError(
                code="PROVIDER_ERROR",
                message=f"Unexpected provider error: {sanitized}",
                status_code=500,
            )

