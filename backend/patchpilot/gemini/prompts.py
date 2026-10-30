"""Structured system instructions and prompt templates for model interaction."""

from typing import Any, Dict, List


SYSTEM_INSTRUCTION = """You are PatchPilot, an expert automated software repair agent.
Your mission is to produce a focused, minimal unified diff that repairs the reported bug without introducing regressions.

RULES:
1. Output MUST be valid JSON matching the following schema:
{
  "explanation": "Brief technical explanation of root cause and fix",
  "target_files": ["relative/path/to/file.py"],
  "unified_diff": "--- a/file.py\\n+++ b/file.py\\n@@ -line,count +line,count @@\\n..."
}
2. The unified_diff MUST be syntactically valid and use standard headers (--- a/..., +++ b/..., @@ ... @@).
3. Do NOT include markdown blocks, prose outside JSON, or conversational filler.
4. Keep edits surgical and minimal. Do not rewrite unaffected code or tests.
"""


def format_patch_prompt(
    bug_report: str,
    file_contexts: List[Dict[str, Any]],
    failure_logs: str,
) -> str:
    files_str = "\n\n".join(
        f"--- FILE: {fc['file_path']} ---\n{fc['content']}"
        for fc in file_contexts
    )
    return f"""BUG REPORT:
{bug_report}

BASELINE FAILURE EVIDENCE:
{failure_logs}

REPOSITORY FILES:
{files_str}

Please analyze the failure and generate the minimal JSON repair proposal:"""


def format_recovery_prompt(
    bug_report: str,
    previous_diff: str,
    recovery_diagnostic: str,
    file_contexts: List[Dict[str, Any]],
) -> str:
    files_str = "\n\n".join(
        f"--- FILE: {fc['file_path']} ---\n{fc['content']}"
        for fc in file_contexts
    )
    return f"""BUG REPORT:
{bug_report}

PREVIOUS REPAIR ATTEMPT:
{previous_diff}

DIAGNOSTIC FAILURE FEEDBACK:
{recovery_diagnostic}

REPOSITORY FILES:
{files_str}

Your previous patch was rejected or caused a regression. Please analyze the feedback and propose a revised minimal JSON repair:"""
