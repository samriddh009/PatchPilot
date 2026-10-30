"""Deterministic test stub provider for offline, repeatable testing."""

import uuid
from typing import Any, Dict, List, Optional

from patchpilot.gemini.base import ModelProvider, ProviderPatchProposal


class StubModelProvider(ModelProvider):
    """
    Deterministic test stub implementing ModelProvider for repeatable offline testing.
    Clearly identified as a test stub (is_stub = True).
    """

    is_stub = True

    def __init__(self):
        self.should_fail_quota: bool = False
        self.should_fail_auth: bool = False
        self.should_emit_malformed_json: bool = False
        self.should_emit_out_of_bounds: bool = False
        self.recovery_call_count: int = 0

    async def validate_connection(self, api_key: str) -> bool:
        if self.should_fail_auth:
            return False
        return bool(api_key and len(api_key) >= 20)

    async def generate_patch(
        self,
        bug_report: str,
        file_contexts: List[Dict[str, Any]],
        failure_logs: str,
        api_key: Optional[str] = None,
    ) -> ProviderPatchProposal:
        if self.should_fail_auth:
            raise PermissionError("Stub Auth Failed: Invalid API key.")
        if self.should_fail_quota:
            raise RuntimeError("Stub Quota Exhausted: 429 Resource Exhausted.")

        if self.should_emit_out_of_bounds:
            return ProviderPatchProposal(
                patch_id=f"patch_{uuid.uuid4().hex[:12]}",
                explanation="Out of bounds test patch",
                raw_diff=(
                    "--- a/calculator/pricing.py\n"
                    "+++ b/calculator/pricing.py\n"
                    "@@ -999,3 +999,3 @@\n"
                    "-    nonexistent line\n"
                    "+    replacement line\n"
                ),
                target_files=["calculator/pricing.py"],
            )

        report_lower = bug_report.lower()
        is_calc = (
            any(k in report_lower for k in ["discount", "calculator", "boundary", "inequality", "100", "pricing"])
            or any("calculator" in str(fc.get("path", "")).lower() or "pricing" in str(fc.get("path", "")).lower() for fc in file_contexts)
        )
        is_parser = (
            any(k in report_lower for k in ["tokenizer", "escape", "parser", "quote", "token"])
            or any("tokenizer" in str(fc.get("path", "")).lower() or "parser" in str(fc.get("path", "")).lower() for fc in file_contexts)
        )
        is_tax = (
            any(k in report_lower for k in ["tax", "vat", "exempt"])
            or any("tax" in str(fc.get("path", "")).lower() for fc in file_contexts)
        )

        # Scenario A: Calculator boundary off-by-one
        if is_calc:
            diff = (
                "--- a/calculator/pricing.py\n"
                "+++ b/calculator/pricing.py\n"
                "@@ -9,3 +9,3 @@\n"
                "-    if total > 100.0:  # DEFECT: Strict inequality excludes boundary total == 100.0\n"
                "+    if total >= 100.0:\n"
                "         return 0.15\n"
            )
            return ProviderPatchProposal(
                patch_id=f"patch_{uuid.uuid4().hex[:12]}",
                explanation="Fix off-by-one discount boundary condition from > to >=",
                raw_diff=diff,
                target_files=["calculator/pricing.py"],
            )

        # Scenario B: Tokenizer parser escaping
        elif is_parser:
            diff = (
                "--- a/parser/tokenizer.py\n"
                "+++ b/parser/tokenizer.py\n"
                "@@ -15,4 +15,5 @@\n"
                "-            # DEFECT: drops escaped quotes\n"
                "             if next_char == '\"':\n"
                "+                tokens.append(next_char)\n"
                "                 i += 2\n"
                "                 continue\n"
            )
            return ProviderPatchProposal(
                patch_id=f"patch_{uuid.uuid4().hex[:12]}",
                explanation="Preserve escaped quotes when preceded by backslash",
                raw_diff=diff,
                target_files=["parser/tokenizer.py"],
            )

        # Scenario C: Tax exemption initial naive patch (triggers regression in VAT calculation)
        elif is_tax:
            diff = (
                "--- a/service/tax.py\n"
                "+++ b/service/tax.py\n"
                "@@ -10,3 +10,3 @@\n"
                "-    if is_exempt:\n"
                "-        return 5.0  # DEFECT: Non-profit exemption returns $5.0 instead of $0.0\n"
                "-    return amount * 0.20\n"
                "+    # Naive fix breaking VAT standard rate\n"
                "+    return 0.0\n"
            )
            return ProviderPatchProposal(
                patch_id=f"patch_{uuid.uuid4().hex[:12]}",
                explanation="Naive tax fix that inadvertently zeroes out all VAT calculations",
                raw_diff=diff,
                target_files=["service/tax.py"],
            )

        # Generic fallback
        return ProviderPatchProposal(
            patch_id=f"patch_{uuid.uuid4().hex[:12]}",
            explanation="Generic fallback patch from test stub.",
            raw_diff=(
                "--- a/dummy.py\n"
                "+++ b/dummy.py\n"
                "@@ -1,1 +1,1 @@\n"
                "-x = 1\n"
                "+x = 2\n"
            ),
            target_files=["dummy.py"],
        )

    async def generate_recovery_patch(
        self,
        bug_report: str,
        previous_diff: str,
        recovery_diagnostic: str,
        file_contexts: List[Dict[str, Any]],
        api_key: Optional[str] = None,
    ) -> ProviderPatchProposal:
        self.recovery_call_count += 1

        # If Scenario C recovery prompt
        if "tax" in bug_report.lower() or "vat" in bug_report.lower():
            # Revised surgical patch that fixes exemption without breaking standard VAT
            diff = (
                "--- a/service/tax.py\n"
                "+++ b/service/tax.py\n"
                "@@ -10,2 +10,3 @@\n"
                "-    # Naive fix breaking VAT standard rate\n"
                "-    return 0.0\n"
                "+    if is_exempt:\n"
                "+        return 0.0\n"
                "+    return amount * 0.20\n"
            )
            return ProviderPatchProposal(
                patch_id=f"patch_{uuid.uuid4().hex[:12]}",
                explanation="Surgical recovery patch restoring standard VAT while keeping non-profit exemption",
                raw_diff=diff,
                target_files=["service/tax.py"],
            )

        return await self.generate_patch(bug_report, file_contexts, recovery_diagnostic, api_key)
