from typing import List, Optional
from pydantic import BaseModel, Field


class ProviderStatusResponse(BaseModel):
    configured: bool = Field(..., description="Whether a Gemini API key is currently configured")
    source: str = Field(..., description="Source of API key ('session_header', 'environment_variable', 'none')")
    model: str = Field(..., description="Candidate or configured Gemini model identifier")
    connection_valid: bool = Field(..., description="Whether the key passes active validation")
    available_models: List[str] = Field(default_factory=list, description="Available models detected or supported")
    error_message: Optional[str] = Field(None, description="Diagnostic error if invalid or unreachable")
    privacy_notice: str = Field(..., description="Mandatory provider privacy disclosure notice")


class SessionKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=20, max_length=128, description="User-supplied Gemini API key")
    model: Optional[str] = Field(None, description="Optional Gemini model to use for this session")


class SessionKeyResponse(BaseModel):
    valid: bool = Field(..., description="Whether key was verified successfully against Gemini API")
    model_available: str = Field(..., description="Active candidate Gemini model name")
    available_models: List[str] = Field(default_factory=list, description="Models discovered live from Google API")
    message: str = Field(..., description="Status description")


class DiscoverModelsRequest(BaseModel):
    api_key: Optional[str] = Field(None, description="Optional API key to probe for models")


class ModelsListResponse(BaseModel):
    active_model: str = Field(..., description="Current active Gemini model")
    supported_models: List[str] = Field(..., description="Known configured candidate model identifiers")
    available_models: List[str] = Field(default_factory=list, description="Live available models discovered from API key if accessible")
    is_live_discovered: bool = Field(False, description="True if available_models were returned directly by Google's API for the active key")
    error_detail: Optional[str] = Field(None, description="Sanitized upstream error message if live discovery failed")


class SetModelRequest(BaseModel):
    model: str = Field(..., min_length=3, max_length=128, description="Model identifier to set as active")


class SetModelResponse(BaseModel):
    active_model: str = Field(..., description="New active model identifier")
    message: str = Field(..., description="Status message")


