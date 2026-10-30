"""Audit event schemas matching the approved REST API contract."""

from typing import Any, Dict, List
from pydantic import BaseModel, Field

from patchpilot.schemas.enums import AuditEventType


class AuditEventResponse(BaseModel):
    id: str = Field(..., description="Unique event identifier")
    sequence_id: int = Field(..., description="Monotonically increasing sequence number")
    event_type: AuditEventType = Field(..., description="Type of audit event")
    payload: Dict[str, Any] = Field(..., description="Structured event payload")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp")


class AuditEventListResponse(BaseModel):
    repair_id: str = Field(..., description="Repair job identifier")
    events: List[AuditEventResponse] = Field(..., description="Ordered sequential audit events")
    has_more: bool = Field(False, description="Whether additional events exist")
    latest_seq: int = Field(0, description="Highest sequence number returned")
