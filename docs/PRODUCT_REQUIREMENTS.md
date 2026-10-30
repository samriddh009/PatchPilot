# PatchPilot — Product Requirements Document (PRD)

**Document Version:** 2.0.0-release  
**Status:** Approved Product Baseline  
**Product Category:** Standalone Local Desktop Software Engineering Agent  

---

## 1. Executive Summary & Product Vision

PatchPilot is a local desktop software engineering agent designed to bridge the gap between AI code generation and reliable, deterministic software maintenance. Unlike cloud-hosted code generators that hallucinate untested diffs directly into production codebases, PatchPilot operates strictly on the developer's local workstation under an immutable verification discipline:

1. **Autonomous Bug Discovery:** Discovers boundary defects, logic errors, loop drops, and exception handling faults directly from source code and AST analysis without requiring user prompts or prior knowledge of defects.
2. **Directed Investigation & Repair:** Investigates user-provided bug reports, error stack traces, and failing tests, generating focused reproduction suites before attempting repairs.
3. **Disposable Workspaces & Repository Immutability:** All candidate patches are generated, applied, and verified in isolated disposable clones. The developer's original project is strictly read-only until explicit approval.
4. **Desktop Native Operation:** Genuine Windows native directory selection dialogs, integrated source code explorer, and zero orphaned background processes.
5. **Strict Approval Gate:** Changes cannot be written to the developer's repository without explicit manual approval.

---

## 2. Core Functional Requirements

### 2.1 Repository Access & Project Management
- **FR-1.1 Native Directory Selection:** The desktop application MUST provide a genuine Windows native folder selection dialog (`dialog.showOpenDialog`). Manual path entry is preserved solely as an accessible secondary fallback.
- **FR-1.2 Path Canonicalization & Confinement:** All selected project paths must be canonicalized to their authoritative roots. Traversal attacks (`..`), alternate data streams, drive changes, and symlink escapes outside the project root must be rejected with HTTP 400.
- **FR-1.3 Supported Languages:** Detection and AST inspection for:
  1. Python (pytest, unittest)
  2. JavaScript (npm, vitest, jest)
  3. TypeScript (npm, vitest, jest)
  4. Java (Maven, Gradle, JUnit)
- **FR-1.4 Source-Only Projects:** Projects lacking configured test runners must still allow complete source inspection, static defect discovery, and test proposal without being falsely rejected.

### 2.2 Integrated Source Explorer
- **FR-2.1 Hierarchical File Tree:** Collapsible directory tree displaying project files matching canonicalized repository confinement.
- **FR-2.2 Safe Source Viewing:** Read-only viewing of source files with line numbers.
- **FR-2.3 Binary & Secret Protection:** Binary files, files exceeding preview limits (1 MB), and sensitive files (`.env`, `.pem`, `.key`, `id_rsa`) are blocked from rendering in the UI.

### 2.3 Autonomous Bug Discovery
- **FR-3.1 Zero-Input Defect Scanning:** Developers can click **Find Bugs** immediately after selecting a project without entering any bug description.
- **FR-3.2 Defect Categories:** Static and pattern rules scan for:
  - Boundary condition strict inequality errors (`>` vs `>=`).
  - Parser dropped token loops and infinite conditions.
  - Non-zero return value assumptions (e.g. exit codes).
  - Bare `except:` clauses swallowing unexpected runtime errors.
  - Mutable default arguments (`def func(x=[])`).
- **FR-3.3 Evidence-Driven Findings:** Every finding provides a unique ID, title, severity, confidence level, file path, line range, relevant code excerpt, explanation, suggested fix, and test evidence.
- **FR-3.4 Dual Action Paths:**
  - **Find Bugs:** Discovers and presents a structured findings report.
  - **Find Bugs & Prepare Fixes:** Discovers defects and immediately dispatches a repair job into a disposable workspace to produce reviewable diffs.

### 2.4 Directed Investigation & Repair
- **FR-4.1 User Report Ingestion:** Supports natural language descriptions, stack traces, expected vs. actual behavior, and failing test targets.
- **FR-4.2 Deterministic Verification Pipeline:**
  1. Pre-patch baseline reproduction (must reproduce failure before claiming repair).
  2. Structured patch generation via Gemini API.
  3. Patch validation and sandbox application in disposable clone.
  4. Targeted test verification (must pass).
  5. Regression test suite execution (must remain 100% passing).
  6. Source repository integrity verification (original repository tree hash must remain identical).

### 2.5 Approval Gate & Safe Export
- **FR-5.1 Original Repository Immutability:** Candidate diffs remain confined to the disposable workspace.
- **FR-5.2 Four Explicit User Actions:**
  1. **Approve and Export:** Applies the verified unified diff to the developer's original repository, verifies written files, and records audit trail.
  2. **Reject Changes:** Rejects candidate patch, marks repair unresolved, and leaves original repository 100% untouched.
  3. **Review Diff:** Navigates directly to unified diff visualization.
  4. **Keep Report Without Exporting:** Closes report without applying any changes.
- **FR-5.3 External Conflict Detection:** Validates that original repository files have not been modified externally since candidate patch generation.

---

## 3. Gemini API (BYOK) Integration

- **FR-6.1 Bring-Your-Own-Key:** Keys are held only in frontend memory for the active session and transmitted via loopback header `X-Session-Gemini-Key`. Keys are NEVER persisted to SQLite, localStorage, or logs.
- **FR-6.2 Model Discovery:** Queries `https://generativelanguage.googleapis.com/v1beta/models` to discover models dynamically supported by the user's key.
- **FR-6.3 Developer Instruction Compatibility:** Dynamically detects HTTP 400 `INVALID_ARGUMENT: Developer instruction is not enabled for this model` and automatically prepends system instructions to the user prompt parts.
- **FR-6.4 Bounded Retries:** Exponential backoff retry (maximum 2 retries) on HTTP 429 rate limits, HTTP 503 service unavailable, and network timeouts.
- **FR-6.5 Strict Schema Parsing:** Delimited JSON code fence extraction with Pydantic v2 schema validation. Unstructured text or malformed JSON is strictly rejected.

---

## 4. Desktop Lifecycle & Security Boundaries

- **FR-7.1 Desktop Shell:** Electron running on Node.js v24 securely bridges native Windows capabilities.
- **FR-7.2 Child Process Management:** Automatically starts the Python FastAPI backend, handles port collisions (detects if port 8000 is occupied and binds to an ephemeral free port), and enforces complete tree termination (`taskkill /pid <PID> /T /F`) upon application exit.
- **FR-7.3 Execution Boundaries:**
  - **Untrusted User Repositories:** Require isolated Docker Desktop containers with network disabled and resource limits. If Docker is unavailable, test execution is strictly refused (Mode A: Static Inspection).
  - **Trusted Bundled Fixtures:** Permitted to run on host under restricted subprocess runners with secret environment variable scrubbing and 30-second timeouts.
- **FR-7.4 Crash Recovery:** Stale or interrupted repairs from previous unclean shutdowns are automatically reconciled to terminal `failed` status upon backend startup.
