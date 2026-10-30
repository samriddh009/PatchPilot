"""Core enumeration types for PatchPilot domain."""

from enum import Enum


class RepairStatus(str, Enum):
    QUEUED = "queued"
    INSPECTING = "inspecting"
    REPRODUCING = "reproducing"
    PATCHING = "patching"
    TESTING = "testing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    AWAITING_APPROVAL = "awaiting_approval"
    EXPORTING = "exporting"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    UNKNOWN = "unknown"


class TestFramework(str, Enum):
    __test__ = False
    PYTEST = "pytest"
    VITEST = "vitest"
    JEST = "jest"
    MAVEN_JUNIT = "maven_junit"
    GRADLE_JUNIT = "gradle_junit"
    UNKNOWN = "unknown"


class AuditEventType(str, Enum):
    STATE_TRANSITION = "state_transition"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    DIFF_GENERATED = "diff_generated"
    TEST_EXECUTION_STARTED = "test_execution_started"
    TEST_EXECUTION_COMPLETED = "test_execution_completed"
    RECOVERY_TRIGGERED = "recovery_triggered"
    VERIFICATION_VERDICT = "verification_verdict"
    APPROVAL_REQUESTED = "approval_requested"
    PATCH_APPROVED = "patch_approved"
    PATCH_REJECTED = "patch_rejected"
    EXPORT_COMPLETED = "export_completed"
    EXPORT_FAILED = "export_failed"
    ERROR_ENCOUNTERED = "error_encountered"


class VerificationOutcome(str, Enum):
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class FailureClassification(str, Enum):
    NONE = "none"
    ASSERTION_FAILURE = "assertion_failure"
    IMPORT_ERROR = "import_error"
    COLLECTION_ERROR = "collection_error"
    SYNTAX_ERROR = "syntax_error"
    TIMEOUT = "timeout"
    RUNNER_CRASH = "runner_crash"
