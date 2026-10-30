"""Tests for SessionKeyStore, credential redaction, and StubModelProvider behavior."""

import pytest
from patchpilot.gemini.session_store import SessionKeyStore
from patchpilot.gemini.stub import StubModelProvider

DUMMY_GEMINI_KEY = "AIza" + "SyDummyKeyForMockingTesting12345"
DUMMY_BAD_KEY = "AIza" + "SyBadKey123456789012345"
DUMMY_REDACT_SAMPLE = "AIza" + "SyD1234567890123456789012345678901"


def test_session_key_store_memory_lifecycle():
    store = SessionKeyStore()
    assert store.get_session_key() is None

    store.set_session_key("test_api_key_12345678901234567890")
    assert store.get_session_key() == "test_api_key_12345678901234567890"

    store.clear()
    assert store.get_session_key() is None


def test_session_key_resolution_precedence():
    store = SessionKeyStore()
    store.set_session_key("session_key_abc")

    # Header overrides session key
    key, src = store.resolve_key(header_key="header_key_xyz")
    assert key == "header_key_xyz"
    assert src == "session_header"

    # In absence of header, session key is used
    key, src = store.resolve_key()
    assert key == "session_key_abc"
    assert src == "session_header"

    store.clear()
    key, src = store.resolve_key()
    assert key is None
    assert src == "none"


def test_redact_secrets():
    raw_log = f"Error from https://generativelanguage.googleapis.com?key={DUMMY_REDACT_SAMPLE} in request"
    redacted = SessionKeyStore.redact_secrets(raw_log)
    assert DUMMY_REDACT_SAMPLE[:16] not in redacted
    assert "[REDACTED]" in redacted


@pytest.mark.asyncio
async def test_stub_model_provider_behavior():
    stub = StubModelProvider()
    assert stub.is_stub is True

    # Scenario A proposal
    prop_a = await stub.generate_patch(
        bug_report="Discount calculation boundary error at $100",
        file_contexts=[],
        failure_logs="FAILED tests/test_calculator.py::test_boundary_discount",
    )
    assert prop_a.target_files == ["calculator/pricing.py"]
    assert "total > 100.0" in prop_a.raw_diff

    # Scenario B proposal
    prop_b = await stub.generate_patch(
        bug_report="JSON parser fails on escaped quotes in string tokens",
        file_contexts=[],
        failure_logs="FAILED tests/test_tokenizer.py",
    )
    assert prop_b.target_files == ["parser/tokenizer.py"]

    # Simulating quota error
    stub.should_fail_quota = True
    with pytest.raises(RuntimeError) as exc:
        await stub.generate_patch("any bug", [], "")
    assert "429" in str(exc.value)

    # Simulating auth failure
    stub.should_fail_quota = False
    stub.should_fail_auth = True
    with pytest.raises(PermissionError):
        await stub.generate_patch("any bug", [], "")


@pytest.mark.asyncio
async def test_gemini_provider_unsupported_model_raises_404_distinctly(monkeypatch):
    """Verify GeminiProvider raises PROVIDER_MODEL_UNAVAILABLE on 404 without guessing."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError
    from patchpilot.gemini.session_store import session_store

    session_store.set_session_key(DUMMY_GEMINI_KEY)

    class MockResponse:
        status_code = 404
        text = "Model not found"
        def json(self):
            return {"error": {"message": "models/gemini-unsupported-model is not found"}}

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())

    provider = GeminiProvider(model_name="gemini-unsupported-model")
    with pytest.raises(GeminiProviderError) as exc_info:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)

    err = exc_info.value
    assert err.code == "PROVIDER_MODEL_UNAVAILABLE"
    assert err.status_code == 404
    assert "gemini-unsupported-model" in err.message
    assert "gemini-unsupported-model is not found" in err.message


@pytest.mark.asyncio
async def test_gemini_provider_quota_and_auth_distinct_errors(monkeypatch):
    """Verify quota and auth errors are cleanly differentiated."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    class MockClient401:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            class Resp:
                status_code = 401
                text = "API key not valid"
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient401())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_401:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_401.value.code == "PROVIDER_AUTH_FAILED"
    assert exc_401.value.status_code == 401

    class MockClient429:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            class Resp:
                status_code = 429
                text = "Resource exhausted"
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient429())
    with pytest.raises(GeminiProviderError) as exc_429:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_429.value.code == "PROVIDER_QUOTA_EXHAUSTED"
    assert exc_429.value.status_code == 429


def test_session_store_model_resolution():
    """Verify session model configuration, resolution precedence, and prefix cleaning."""
    from patchpilot.gemini.session_store import SessionKeyStore
    store = SessionKeyStore()

    # Default resolution
    assert "gemini" in store.resolve_model()

    # Session override
    store.set_session_model("models/gemini-1.5-pro")
    assert store.get_session_model() == "gemini-1.5-pro"
    assert store.resolve_model() == "gemini-1.5-pro"

    # Explicit argument override
    assert store.resolve_model("models/gemini-2.0-flash-exp") == "gemini-2.0-flash-exp"


@pytest.mark.asyncio
async def test_gemini_provider_timeout_and_network_errors(monkeypatch):
    """Verify timeout and network errors raise distinct provider error codes."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    class TimeoutClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            raise httpx.TimeoutException("Timeout after 30s")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: TimeoutClient())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_to:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_to.value.code == "PROVIDER_TIMEOUT"
    assert exc_to.value.status_code == 504

    class NetworkErrorClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            raise httpx.NetworkError("Failed to connect")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: NetworkErrorClient())
    with pytest.raises(GeminiProviderError) as exc_net:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_net.value.code == "PROVIDER_NETWORK_ERROR"
    assert exc_net.value.status_code == 503


@pytest.mark.asyncio
async def test_gemini_provider_safety_refusal_and_malformed(monkeypatch):
    """Verify safety refusals and malformed responses are cleanly classified."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    # 1. Safety refusal
    class SafetyResp:
        status_code = 200
        def json(self):
            return {
                "candidates": [{
                    "finishReason": "SAFETY",
                    "content": {"parts": []}
                }]
            }

    class MockClientSafety:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return SafetyResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClientSafety())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_safe:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_safe.value.code == "PROVIDER_SAFETY_REFUSAL"
    assert exc_safe.value.status_code == 400

    # 2. Malformed JSON candidate
    class MalformedResp:
        status_code = 200
        def json(self):
            return {
                "candidates": [{
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "this is not valid json {"}]}
                }]
            }

    class MockClientMalformed:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return MalformedResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClientMalformed())
    with pytest.raises(GeminiProviderError) as exc_mal:
        await provider._call_model("test prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_mal.value.code == "PROVIDER_MALFORMED_RESPONSE"
    assert exc_mal.value.status_code == 502


@pytest.mark.asyncio
async def test_fetch_available_models_mocked(monkeypatch):
    """Verify live model discovery filters, normalizes, and sets is_live flag."""
    import httpx
    from patchpilot.gemini.session_store import SessionKeyStore

    class MockModelsResp:
        status_code = 200
        def json(self):
            return {
                "models": [
                    {
                        "name": "models/gemini-1.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-1.5-pro",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/text-embedding-004",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            }

    class MockClientModels:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            return MockModelsResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClientModels())
    models, err, is_live = await SessionKeyStore.fetch_available_models(DUMMY_GEMINI_KEY)
    assert is_live is True
    assert err is None
    assert "gemini-1.5-flash" in models
    assert "gemini-1.5-pro" in models
    assert "text-embedding-004" not in models  # Filtered out because it does not support generateContent


@pytest.mark.asyncio
async def test_fetch_available_models_failure_does_not_return_fake_models(monkeypatch):
    """Verify discovery failure returns empty list and does NOT pretend models exist."""
    import httpx
    from patchpilot.gemini.session_store import SessionKeyStore

    class MockFailResp:
        status_code = 401
        text = "API key not valid."
        def json(self):
            return {"error": {"code": 401, "message": "API key not valid. Please pass a valid API key.", "status": "UNAUTHENTICATED"}}

    class MockClientFail:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            return MockFailResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClientFail())
    models, err, is_live = await SessionKeyStore.fetch_available_models(DUMMY_BAD_KEY)
    assert is_live is False
    assert models == []
    assert "UNAUTHENTICATED" in err
    assert "API key not valid" in err


@pytest.mark.asyncio
async def test_validate_key_live_invalid_model_selection(monkeypatch):
    """Verify selecting a model not in the key's available list is rejected with available alternatives."""
    import httpx
    from patchpilot.gemini.session_store import SessionKeyStore

    class MockModelsResp:
        status_code = 200
        def json(self):
            return {
                "models": [
                    {"name": "models/gemini-2.0-flash-exp", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
                ]
            }

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            return MockModelsResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())

    # User configured gemini-1.5-flash, but key only has 2.0-flash-exp and 1.5-pro
    valid, err_msg, available_models, is_live = await SessionKeyStore.validate_key_live(
        DUMMY_GEMINI_KEY, model_candidate="gemini-1.5-flash"
    )
    assert valid is False
    assert is_live is True
    assert "gemini-1.5-flash" in err_msg
    assert "gemini-2.0-flash-exp" in err_msg
    assert "gemini-2.0-flash-exp" in available_models
    assert "gemini-1.5-pro" in available_models


@pytest.mark.asyncio
async def test_selected_model_propagation_to_repair_coordinator(monkeypatch):
    """Verify that explicitly selected model is passed to GeminiProvider and used in endpoint URL."""
    import httpx
    from patchpilot.orchestrator.repair_job import RepairJobCoordinator
    from patchpilot.gemini.client import GeminiProvider

    captured_url = None

    class CaptureClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            nonlocal captured_url
            captured_url = str(url)
            class Resp:
                status_code = 200
                def json(self):
                    return {
                        "candidates": [{
                            "finishReason": "STOP",
                            "content": {
                                "parts": [{"text": '{"explanation": "Fix", "unified_diff": "--- a/x\\n+++ b/x\\n@@ -1,1 +1,1 @@\\n-old\\n+new\\n", "target_files": ["x"]}'}]
                            }
                        }]
                    }
            return Resp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: CaptureClient())

    coordinator = RepairJobCoordinator(
        repair_id="rep_test_model_prop",
        repository_id="repo_py_calc_01",
        bug_report="Dummy bug",
        session_key=DUMMY_GEMINI_KEY,
        model="models/gemini-1.5-pro",
    )
    assert isinstance(coordinator.provider, GeminiProvider)
    assert coordinator.provider.model_name == "gemini-1.5-pro"

    # Call generate_patch to verify URL construction
    proposal = await coordinator.provider.generate_patch(
        bug_report="Dummy bug",
        file_contexts=[],
        failure_logs="",
        api_key=DUMMY_GEMINI_KEY,
    )
    assert proposal is not None
    assert captured_url is not None
    assert "/v1beta/models/gemini-1.5-pro:generateContent" in captured_url
    assert "/models/models/" not in captured_url


# ==============================================================================
# Mocked Regression Tests for Gemini Provider Response Parsing & Validation
# (Zero Gemini Credits Consumed)
# ==============================================================================

VALID_DIFF_PAYLOAD = (
    "--- a/calculator/pricing.py\n"
    "+++ b/calculator/pricing.py\n"
    "@@ -10,3 +10,3 @@\n"
    "-def discount(total):\n"
    "+def discount(total, rate=0.1):\n"
)


def _make_mock_client_for_text(text: str, finish_reason: str = "STOP", candidates_override=None, block_reason=None):
    import httpx

    class MockResp:
        status_code = 200

        def json(self):
            data = {}
            if block_reason:
                data["promptFeedback"] = {"blockReason": block_reason}
            if candidates_override is not None:
                data["candidates"] = candidates_override
            else:
                data["candidates"] = [{
                    "finishReason": finish_reason,
                    "content": {"parts": [{"text": text}]},
                }]
            return data

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, **kwargs):
            return MockResp()

    return MockClient


@pytest.mark.asyncio
async def test_mock_gemini_valid_raw_json(monkeypatch):
    """1. Valid pure JSON response parses into ProviderPatchProposal."""
    import json
    import httpx
    from patchpilot.gemini.client import GeminiProvider

    valid_json = json.dumps({
        "explanation": "Add default rate parameter",
        "target_files": ["calculator/pricing.py"],
        "unified_diff": VALID_DIFF_PAYLOAD,
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(valid_json)())
    provider = GeminiProvider()
    proposal = await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert proposal.explanation == "Add default rate parameter"
    assert proposal.target_files == ["calculator/pricing.py"]
    assert proposal.raw_diff == VALID_DIFF_PAYLOAD


@pytest.mark.asyncio
async def test_mock_gemini_code_fenced_json(monkeypatch):
    """2. Valid JSON inside markdown code fence (```json ... ``` and ``` ... ```) parses cleanly."""
    import json
    import httpx
    from patchpilot.gemini.client import GeminiProvider

    payload_dict = {
        "explanation": "Code fenced JSON proposal",
        "target_files": ["calculator/pricing.py"],
        "unified_diff": VALID_DIFF_PAYLOAD,
    }
    fenced_json = f"```json\n{json.dumps(payload_dict, indent=2)}\n```"
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(fenced_json)())
    provider = GeminiProvider()
    proposal = await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert proposal.explanation == "Code fenced JSON proposal"
    assert proposal.target_files == ["calculator/pricing.py"]

    # Also test generic ``` fence without json tag
    payload_dict["explanation"] = "Generic fence proposal"
    generic_fenced = f"```\n{json.dumps(payload_dict, indent=2)}\n```"
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(generic_fenced)())
    proposal2 = await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert proposal2.explanation == "Generic fence proposal"


@pytest.mark.asyncio
async def test_mock_gemini_ordinary_text_rejected(monkeypatch):
    """3. Ordinary text responses without JSON are safely rejected with PROVIDER_MALFORMED_RESPONSE."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    plain_text = "I apologize, but I cannot repair this code because the bug report is ambiguous."
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(plain_text)())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_info:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_info.value.code == "PROVIDER_MALFORMED_RESPONSE"
    assert "ordinary text" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_mock_gemini_malformed_json_rejected(monkeypatch):
    """4. Syntactically invalid JSON raises PROVIDER_MALFORMED_RESPONSE with sanitized diagnostic."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    broken_json = '{"explanation": "Fix", "target_files": ["a.py"], "unified_diff": '
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(broken_json)())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_info:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_info.value.code == "PROVIDER_MALFORMED_RESPONSE"
    assert "invalid json" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_mock_gemini_missing_fields_rejected(monkeypatch):
    """5. Valid JSON missing required contract fields raises PROVIDER_MALFORMED_RESPONSE."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    missing_fields_json = '{"explanation": "Only explanation provided"}'
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(missing_fields_json)())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_info:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_info.value.code == "PROVIDER_MALFORMED_RESPONSE"
    assert "missing required fields" in exc_info.value.message.lower()
    assert "target_files" in exc_info.value.message
    assert "unified_diff" in exc_info.value.message


@pytest.mark.asyncio
async def test_mock_gemini_invalid_patch_rejected(monkeypatch):
    """6. Invalid patch (missing diff headers, traversal in paths, or oversized) raises PROVIDER_MALFORMED_RESPONSE."""
    import json
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    # 6a. Non-diff text in unified_diff
    invalid_diff_json = json.dumps({
        "explanation": "Fix",
        "target_files": ["foo.py"],
        "unified_diff": "Just change line 5 to return true",
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(invalid_diff_json)())
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_1:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_1.value.code == "PROVIDER_MALFORMED_RESPONSE"
    assert "lacks standard diff" in exc_1.value.message.lower()

    # 6b. Path traversal in target_files
    traversal_json = json.dumps({
        "explanation": "Escape attempt",
        "target_files": ["../../etc/passwd"],
        "unified_diff": VALID_DIFF_PAYLOAD,
    })
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text(traversal_json)())
    with pytest.raises(GeminiProviderError) as exc_2:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_2.value.code == "PROVIDER_MALFORMED_RESPONSE"
    assert "traversal" in exc_2.value.message.lower()


@pytest.mark.asyncio
async def test_mock_gemini_empty_response(monkeypatch):
    """7. Empty response candidates or empty parts raise PROVIDER_EMPTY_RESPONSE."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    # 7a. No candidates
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: _make_mock_client_for_text("", candidates_override=[])()
    )
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_empty:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_empty.value.code == "PROVIDER_EMPTY_RESPONSE"
    assert exc_empty.value.status_code == 502

    # 7b. Empty text parts
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _make_mock_client_for_text(
            "",
            candidates_override=[{"finishReason": "STOP", "content": {"parts": [{"text": "   "}]}}],
        )(),
    )
    with pytest.raises(GeminiProviderError) as exc_parts:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_parts.value.code == "PROVIDER_EMPTY_RESPONSE"


@pytest.mark.asyncio
async def test_mock_gemini_truncated_response(monkeypatch):
    """8. Truncated output (finishReason: MAX_TOKENS) raises distinct PROVIDER_TRUNCATED_RESPONSE."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    partial_text = '{"explanation": "Fix", "target_files": ["a.py"], "unified_diff": "--- a/a.py\\n'
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _make_mock_client_for_text(partial_text, finish_reason="MAX_TOKENS")(),
    )
    provider = GeminiProvider()
    with pytest.raises(GeminiProviderError) as exc_info:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_info.value.code == "PROVIDER_TRUNCATED_RESPONSE"
    assert exc_info.value.status_code == 502
    assert "max_tokens" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_mock_gemini_provider_refusal(monkeypatch):
    """9. Provider safety and policy refusals raise PROVIDER_SAFETY_REFUSAL or PROVIDER_REFUSAL."""
    import httpx
    from patchpilot.gemini.client import GeminiProvider, GeminiProviderError

    provider = GeminiProvider()

    # 9a. Candidate finishReason: SAFETY
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _make_mock_client_for_text("", finish_reason="SAFETY")(),
    )
    with pytest.raises(GeminiProviderError) as exc_safe:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_safe.value.code == "PROVIDER_SAFETY_REFUSAL"
    assert exc_safe.value.status_code == 400

    # 9b. PromptFeedback blockReason: SAFETY
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _make_mock_client_for_text("", candidates_override=[], block_reason="SAFETY")(),
    )
    with pytest.raises(GeminiProviderError) as exc_fb:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_fb.value.code == "PROVIDER_SAFETY_REFUSAL"

    # 9c. Candidate finishReason: RECITATION
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _make_mock_client_for_text("", finish_reason="RECITATION")(),
    )
    with pytest.raises(GeminiProviderError) as exc_rec:
        await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert exc_rec.value.code == "PROVIDER_REFUSAL"
    assert "recitation" in exc_rec.value.message.lower()


@pytest.mark.asyncio
async def test_mock_gemini_multipart_and_thought_filtering(monkeypatch):
    """Candidate with thinking parts filters thoughts and parses final JSON part."""
    import json
    import httpx
    from patchpilot.gemini.client import GeminiProvider

    valid_json = json.dumps({
        "explanation": "Fix thinking model",
        "target_files": ["calculator/pricing.py"],
        "unified_diff": VALID_DIFF_PAYLOAD,
    })
    candidates = [{
        "finishReason": "STOP",
        "content": {
            "parts": [
                {"thought": True, "text": "Analyzing the code to find the root cause..."},
                {"text": valid_json},
            ]
        },
    }]

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: _make_mock_client_for_text("", candidates_override=candidates)(),
    )
    provider = GeminiProvider()
    proposal = await provider._call_model("prompt", api_key=DUMMY_GEMINI_KEY)
    assert proposal.explanation == "Fix thinking model"




