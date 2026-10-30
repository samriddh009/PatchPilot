from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from patchpilot import config
from patchpilot.api.deps import get_session_key
from patchpilot.gemini.session_store import SessionKeyStore, session_store
from patchpilot.schemas.provider import (
    DiscoverModelsRequest,
    ModelsListResponse,
    ProviderStatusResponse,
    SessionKeyRequest,
    SessionKeyResponse,
    SetModelRequest,
    SetModelResponse,
)

router = APIRouter(prefix="/provider", tags=["Provider"])

PRIVACY_NOTICE = (
    "Code snippets and bug descriptions are transmitted over TLS to Google Gemini API. "
    "Repository contents are subject to provider data policies."
)


@router.get("/status", response_model=ProviderStatusResponse)
async def get_provider_status(session_key: Optional[str] = Depends(get_session_key)):
    """Validates whether a Gemini API key is configured and returns connection status."""
    resolved_key, source = session_store.resolve_key(session_key)
    active_model = session_store.resolve_model()

    if not resolved_key:
        return ProviderStatusResponse(
            configured=False,
            source=source,
            model=active_model,
            connection_valid=False,
            available_models=[],
            error_message="No API key found in session or GEMINI_API_KEY environment variable.",
            privacy_notice=PRIVACY_NOTICE,
        )

    valid, err, models, is_live = await SessionKeyStore.validate_key_live(resolved_key, model_candidate=active_model)
    return ProviderStatusResponse(
        configured=True,
        source=source,
        model=active_model,
        connection_valid=valid,
        available_models=models,
        error_message=err,
        privacy_notice=PRIVACY_NOTICE,
    )


@router.get("/models", response_model=ModelsListResponse)
async def get_models(session_key: Optional[str] = Depends(get_session_key)):
    """Returns the list of supported and live available Gemini models."""
    resolved_key, _ = session_store.resolve_key(session_key)
    active_model = session_store.resolve_model()

    if resolved_key:
        models, err_msg, is_live = await SessionKeyStore.fetch_available_models(resolved_key)
        return ModelsListResponse(
            active_model=active_model,
            supported_models=config.SUPPORTED_GEMINI_MODELS,
            available_models=models,
            is_live_discovered=is_live,
            error_detail=err_msg,
        )

    return ModelsListResponse(
        active_model=active_model,
        supported_models=config.SUPPORTED_GEMINI_MODELS,
        available_models=[],
        is_live_discovered=False,
        error_detail="No API key provided. Supply a key to discover available models.",
    )


@router.post("/models", response_model=ModelsListResponse)
async def discover_models(
    payload: DiscoverModelsRequest,
    session_key: Optional[str] = Depends(get_session_key),
):
    """Probes Google Gemini API to discover live models available for the provided key."""
    key_to_use = payload.api_key.strip() if payload.api_key and payload.api_key.strip() else None
    if not key_to_use:
        key_to_use, _ = session_store.resolve_key(session_key)

    active_model = session_store.resolve_model()

    if not key_to_use:
        return ModelsListResponse(
            active_model=active_model,
            supported_models=config.SUPPORTED_GEMINI_MODELS,
            available_models=[],
            is_live_discovered=False,
            error_detail="No API key supplied to probe.",
        )

    models, err_msg, is_live = await SessionKeyStore.fetch_available_models(key_to_use)
    return ModelsListResponse(
        active_model=active_model,
        supported_models=config.SUPPORTED_GEMINI_MODELS,
        available_models=models,
        is_live_discovered=is_live,
        error_detail=err_msg,
    )


@router.post("/model", response_model=SetModelResponse)
async def set_active_model(payload: SetModelRequest):
    """Sets the active Gemini model for the current session."""
    clean_model = payload.model.strip().removeprefix("models/")
    session_store.set_session_model(clean_model)
    return SetModelResponse(
        active_model=clean_model,
        message=f"Active Gemini model set to '{clean_model}'.",
    )


@router.post("/session-key", response_model=SessionKeyResponse)
async def set_session_key(payload: SessionKeyRequest):
    """
    Actively validates user-supplied session key with Gemini API.
    Does not persist key to disk or database.
    """
    target_model = payload.model.strip().removeprefix("models/") if payload.model else session_store.resolve_model()
    valid, err_msg, discovered_models, is_live = await SessionKeyStore.validate_key_live(
        payload.api_key, model_candidate=target_model
    )

    if not valid:
        err_lower = (err_msg or "").lower()
        if is_live:
            # Key is authenticated by Google, but target_model was not in the returned models list
            code = "PROVIDER_MODEL_UNAVAILABLE"
            status_code = 400
        elif "quota" in err_lower or "rate limit" in err_lower:
            code = "PROVIDER_QUOTA_EXHAUSTED"
            status_code = 429
        elif "timed out" in err_lower:
            code = "PROVIDER_TIMEOUT"
            status_code = 504
        else:
            code = "PROVIDER_AUTH_FAILED"
            status_code = 401

        raise HTTPException(
            status_code=status_code,
            detail={
                "code": code,
                "message": err_msg or "Gemini API validation failed.",
                "details": {
                    "available_models": discovered_models,
                },
                "available_models": discovered_models,
            },
        )

    # Store in memory only
    session_store.set_session_key(payload.api_key)
    if payload.model:
        session_store.set_session_model(target_model)

    return SessionKeyResponse(
        valid=True,
        model_available=target_model,
        available_models=discovered_models,
        message="Connection established successfully.",
    )


