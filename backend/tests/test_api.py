"""Tests for PatchPilot API endpoints, error envelopes, and host restrictions."""

import pytest
from fastapi.testclient import TestClient
from patchpilot.schemas.enums import RepairStatus
from patchpilot.storage.database import db


def test_health_endpoint(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "python_version" in data["environment"]
    assert "docker_cli_available" in data["environment"]
    assert "restricted_mode" in data["environment"]


def test_host_header_check(client: TestClient):
    # Host header not in loopback allowlist should return 403
    response = client.get("/api/v1/health", headers={"Host": "malicious-site.com"})
    assert response.status_code == 403
    err = response.json()
    assert err["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_provider_status_endpoint(client: TestClient):
    response = client.get("/api/v1/provider/status")
    assert response.status_code == 200
    data = response.json()
    assert "configured" in data
    assert "privacy_notice" in data
    assert "TLS" in data["privacy_notice"]


def test_provider_status_with_session_header(client: TestClient):
    # Verify X-Session-Gemini-Key header is accepted and recognized as session_header
    response = client.get(
        "/api/v1/provider/status",
        headers={"X-Session-Gemini-Key": "dummy_header_key_12345678901234567890"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "session_header"
    assert data["configured"] is True


def test_provider_session_key_invalid(client: TestClient):
    # Short key rejected by schema validator
    response_short = client.post("/api/v1/provider/session-key", json={"api_key": "short_key"})
    assert response_short.status_code == 422
    err_short = response_short.json()
    assert err_short["error"]["code"] == "INVALID_REQUEST"

    # Malformed key rejected by provider validator
    response_invalid = client.post(
        "/api/v1/provider/session-key",
        json={"api_key": "invalid_fake_key_12345678901234567890"},
    )
    assert response_invalid.status_code == 401
    err_invalid = response_invalid.json()
    assert err_invalid["error"]["code"] == "PROVIDER_AUTH_FAILED"


def test_provider_models_endpoints(client: TestClient):
    """Verify provider models list and model configuration endpoints."""
    # 1. Get models
    res_models = client.get("/api/v1/provider/models")
    assert res_models.status_code == 200
    data = res_models.json()
    assert "active_model" in data
    assert "supported_models" in data
    assert "gemini-1.5-flash" in data["supported_models"]

    # 2. Set active model
    res_set = client.post("/api/v1/provider/model", json={"model": "gemini-1.5-pro"})
    assert res_set.status_code == 200
    assert res_set.json()["active_model"] == "gemini-1.5-pro"

    # Verify active model is updated in status
    res_status = client.get("/api/v1/provider/status")
    assert res_status.status_code == 200
    assert res_status.json()["model"] == "gemini-1.5-pro"


def test_list_repositories(client: TestClient):
    response = client.get("/api/v1/repositories")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert data["total"] >= 1
    # Check that registered fixtures are listed
    ids = [item["id"] for item in data["items"]]
    assert "repo_py_calc_01" in ids


def test_get_repository_found_and_not_found(client: TestClient):
    # Found
    res_ok = client.get("/api/v1/repositories/repo_py_calc_01")
    assert res_ok.status_code == 200
    repo_data = res_ok.json()
    assert repo_data["id"] == "repo_py_calc_01"
    assert "test_targets" in repo_data
    assert repo_data["file_count"] >= 1

    # Not found
    res_404 = client.get("/api/v1/repositories/repo_nonexistent")
    assert res_404.status_code == 404
    err = res_404.json()
    assert err["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_get_repository_files(client: TestClient):
    res = client.get("/api/v1/repositories/repo_py_calc_01/files")
    assert res.status_code == 200
    data = res.json()
    assert data["repository_id"] == "repo_py_calc_01"
    assert "calculator/pricing.py" in data["files"]
    assert "tests/test_calculator.py" in data["files"]

    # Exclude tests
    res_no_tests = client.get("/api/v1/repositories/repo_py_calc_01/files?include_tests=false")
    assert res_no_tests.status_code == 200
    assert "tests/test_calculator.py" not in res_no_tests.json()["files"]

    # Not found
    res_404 = client.get("/api/v1/repositories/repo_nonexistent/files")
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_repair_lifecycle_and_cancel(client: TestClient):
    # 1. Dispatch repair
    payload = {
        "repository_id": "repo_py_calc_01",
        "bug_report": "Boundary error in discount calculation when subtotal is exactly $100",
    }
    create_res = client.post("/api/v1/repairs", json=payload)
    assert create_res.status_code == 201
    repair = create_res.json()
    repair_id = repair["id"]
    assert repair["repository_id"] == "repo_py_calc_01"

    # 2. Get repair status
    get_res = client.get(f"/api/v1/repairs/{repair_id}")
    assert get_res.status_code == 200

    # 3. Get events
    events_res = client.get(f"/api/v1/repairs/{repair_id}/events")
    assert events_res.status_code == 200
    assert "events" in events_res.json()

    # 4. Get diff
    diff_res = client.get(f"/api/v1/repairs/{repair_id}/diff")
    assert diff_res.status_code == 200

    # 5. Cancel repair
    # Note: If the background task finishes rapidly or is active, cancellation succeeds or is already completed
    cancel_res = client.post(f"/api/v1/repairs/{repair_id}/cancel")
    assert cancel_res.status_code in {200, 409}


def test_repair_report_not_found(client: TestClient):
    res = client.get("/api/v1/repairs/rep_nonexistent/report")
    assert res.status_code == 404
    err = res.json()
    assert err["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_discover_models_endpoint_with_mock(client: TestClient, monkeypatch):
    """Verify POST /api/v1/provider/models response schema and live discovery flag."""
    import httpx

    class MockResp:
        status_code = 200
        def json(self):
            return {
                "models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
                ]
            }

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())

    res = client.post("/api/v1/provider/models", json={"api_key": "AIza" + "SyMockKeyForDiscoveryTests12345"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_live_discovered"] is True
    assert "gemini-2.5-flash" in data["available_models"]
    assert "gemini-2.5-pro" in data["available_models"]
    # Non-generateContent model must be filtered out
    assert "text-embedding-004" not in data["available_models"]


def test_session_key_unavailable_model_preserves_discovered_models_in_error(client: TestClient, monkeypatch):
    """Verify that when requested model is unavailable, HTTP 400 preserves discovered models in error details."""
    import httpx

    class MockResp:
        status_code = 200
        def json(self):
            return {
                "models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
                ]
            }

    class MockClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())

    # User attempts to validate gemini-1.5-flash, but key only has 2.5 series
    res = client.post(
        "/api/v1/provider/session-key",
        json={"api_key": "AIza" + "SyMockKeyForDiscoveryTests12345", "model": "gemini-1.5-flash"},
    )
    assert res.status_code == 400
    err = res.json()["error"]
    assert err["code"] == "PROVIDER_MODEL_UNAVAILABLE"
    assert "gemini-1.5-flash" in err["message"]
    # Crucial: available_models must NOT be stripped by error handler
    assert "available_models" in err["details"]
    assert err["details"]["available_models"] == ["gemini-2.5-flash", "gemini-2.5-pro"]

