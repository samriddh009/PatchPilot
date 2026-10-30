"""Model provider protocol and domain data structures."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ProviderPatchProposal:
    patch_id: str
    explanation: str
    raw_diff: str
    target_files: List[str]


@runtime_checkable
class ModelProvider(Protocol):
    """Protocol for AI model providers."""

    is_stub: bool

    async def validate_connection(self, api_key: str) -> bool:
        """Conduct an active probe verifying key validity and model accessibility."""
        ...

    async def generate_patch(
        self,
        bug_report: str,
        file_contexts: List[Dict[str, Any]],
        failure_logs: str,
        api_key: Optional[str] = None,
    ) -> ProviderPatchProposal:
        """Generate candidate unified diff patch based on bug report and failure logs."""
        ...

    async def generate_recovery_patch(
        self,
        bug_report: str,
        previous_diff: str,
        recovery_diagnostic: str,
        file_contexts: List[Dict[str, Any]],
        api_key: Optional[str] = None,
    ) -> ProviderPatchProposal:
        """Generate revised patch after regression or validation failure."""
        ...
