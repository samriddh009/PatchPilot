# PatchPilot — Acceptance Test Specifications & Verification Suites

**Document Version:** 1.0.0-freeze  
**Status:** Approved Architecture Baseline  
**Coverage Scope:** End-to-End Scenarios, Robustness Matrix, Security Attack Invariants  

---

## 1. Test Verification Philosophy

PatchPilot's acceptance criteria are rooted in **Deterministic Ground Truth**. An AI agent can make claims, but only the deterministic verification engine can validate reality.

```
                  +--------------------------------------------------------------+
                  |                 VERIFICATION MATRIX OF TRUTH                 |
                  +--------------------------------------------------------------+
                  | 1. Baseline Test (Unpatched)   == FAIL (Exit code 1)         |
                  |    - Classification            == "assertion_failure" ONLY   |
                  |    - Disallows: ImportError, SyntaxError, Timeout, Collector |
                  | 2. Targeted Test (Patched)     == PASS (Exit code 0)         |
                  | 3. Regression Suite (Patched)  == PASS (Exit code 0, 0 err)  |
                  | 4. Applied Unified Diff        >  0 Valid Lines              |
                  | 5. Source Repository Checksum  == UNCHANGED (0 bytes mutated)|
                  +--------------------------------------------------------------+
                                          │
                                          ▼
                         VERIFIED REPAIR (No Hallucinations)
```

> [!CRITICAL]
> **Evidence Verification Rule:** Verification requires actual, uncorrupted post-patch targeted and regression test results. Missing execution logs, truncated output lacking summary results, test timeouts, runner crashes, or ambiguous exit codes strictly count as verification failure. A non-zero baseline exit code alone does NOT permit patch generation unless proven to be a relevant, reproducible assertion failure.

---

## 2. Core End-to-End Acceptance Scenarios

### 2.1 Scenario A: Baseline Python Repair (Discount Boundary Off-by-One)

* **Goal:** Verify that PatchPilot can reproduce a real bug, generate a clean surgical patch, apply it in an isolated ephemeral workspace, run targeted and regression tests, and yield a verified report.
* **Target Repository:** `fixtures/python_calc_bug/`
* **Defect Description:** In `calculator/pricing.py`, the condition `if total > 100.0:` fails to award a 15% discount when the cart total equals exactly $100.00.
* **Target Test:** `tests/test_calculator.py::test_discount_boundary`

#### Setup:
1. Source directory contains valid `pyproject.toml`, `calculator/pricing.py`, and `tests/test_calculator.py`.
2. Compute baseline SHA-256 tree hash of `fixtures/python_calc_bug/`.
3. Virtual environment has `pytest` pre-installed.

#### Execution Sequence:
1. Client issues `POST /api/v1/repairs` with:
   ```json
   {
     "repository_id": "repo_py_calc_01",
     "bug_report": "Discount function does not apply 15% when total is exactly $100.00.",
     "test_target": "tests/test_calculator.py::test_discount_boundary"
   }
   ```
2. **State Transition:** `queued` -> `inspecting`. Ephemeral workspace cloned to temporary directory `patchpilot_ws_a1`.
3. **State Transition:** `inspecting` -> `reproducing`.
   - Tool `run_targeted_test` executes `pytest tests/test_calculator.py::test_discount_boundary`.
   - Result: Exit code `1`. Output confirms `AssertionError: 0.10 != 0.15`.
   - Baseline reproduction confirmed.
4. **State Transition:** `reproducing` -> `patching`.
   - Gemini provider is invoked with file context and failure logs.
   - Model emits tool call `propose_patch` containing unified diff:
     ```diff
     --- a/calculator/pricing.py
     +++ b/calculator/pricing.py
     @@ -14,3 +14,3 @@
     -    if total > 100.0:
     +    if total >= 100.0:
              return 0.15
     ```
   - Tool `validate_patch` confirms hunk offsets and file paths within workspace jail.
   - Tool `apply_patch` applies diff to `patchpilot_ws_a1/calculator/pricing.py`.
5. **State Transition:** `patching` -> `testing`.
   - Tool `run_targeted_test` executes `pytest tests/test_calculator.py::test_discount_boundary`.
   - Result: Exit code `0` (PASSED).
   - Tool `run_regression_tests` executes full suite `pytest`.
   - Result: Exit code `0` (6 passed, 0 failed).
6. **State Transition:** `testing` -> `verifying`.
   - Deterministic verification engine confirms all criteria met.
7. **State Transition:** `verifying` -> `verified`.
   - Report generated and stored in SQLite.
   - Ephemeral workspace `patchpilot_ws_a1` deleted.

#### Verification & Pass Criteria:
* Final status is `verified`.
* Baseline test exit code is `1`; patched targeted exit code is `0`; regression exit code is `0`.
* Original source repository tree hash is identical before and after repair (0 bytes mutated).
* Full report accessible via `GET /api/v1/repairs/{id}/report`.

---

### 2.2 Scenario B: Generalized Logic Repair (Token Stream String Escaping)

* **Goal:** Prove that PatchPilot is not hardcoded to a single calculation fixture and can repair string manipulation and parsing logic.
* **Target Repository:** `fixtures/python_parser_bug/`
* **Defect Description:** In `parser/tokenizer.py`, string tokenizer does not correctly unescape double backslashes (`\\\\`), dropping escaped quotes prematurely.
* **Target Test:** `tests/test_tokenizer.py::test_escaped_quote_handling`

#### Setup:
1. Source directory contains `fixtures/python_parser_bug/`.
2. Compute baseline SHA-256 tree hash.
3. Pre-run targeted test confirms failure: `AssertionError: Expected 'foo\"bar' got 'foobar'`.

#### Execution Sequence:
1. Client submits repair job targeting `tests/test_tokenizer.py::test_escaped_quote_handling`.
2. System transitions through `queued` -> `inspecting` -> `reproducing`.
3. Baseline failure is confirmed (exit code `1`).
4. In `patching` phase, model proposes replacement logic in `parser/tokenizer.py`.
5. `apply_patch` updates tokenizer logic in ephemeral workspace.
6. `testing` executes targeted test (PASS) and regression suite `tests/test_tokenizer.py` (PASS, 12 tests).
7. `verifying` confirms deterministic truth condition.
8. Status transitions to `verified`.

#### Verification & Pass Criteria:
* Demonstrates general reasoning over token parsing logic.
* Final status is `verified`.
* Source repo integrity checksum matches 100%.

---

### 2.3 Scenario C: Regression Detection & Bounded Recovery (Attempt $\le$ 1)

* **Goal:** Verify that if an initial patch breaks other tests (introduces a regression), PatchPilot initiates exactly one bounded recovery attempt, safely aborts if verification still fails, never creates an infinite loop, and reports `unresolved`.
* **Target Repository:** `fixtures/python_regression_fixture/`
* **Defect Description:** In `service/tax.py`, an aggressive refactor introduces a regression into the VAT calculation helper.

#### Execution Sequence:
1. Client submits repair job.
2. Baseline failure reproduced: `test_tax_exemption` fails with exit code `1`.
3. In `patching`, model proposes a naive fix that hardcodes an exemption return value.
4. In `testing`:
   - Targeted test `test_tax_exemption` passes (exit code `0`).
   - Regression suite executes: `test_standard_vat_rate` fails with exit code `1`!
5. **State Transition:** `testing` -> `recovering`.
   - Recovery attempt counter increments: `recovery_attempts = 1`.
   - Bounded recovery manager extracts regression failure traceback.
   - Recovery diagnostic prompt generated: *"Your proposed patch resolved the target test but introduced a regression in test_standard_vat_rate. Traceback: ... Please propose a revised patch."*
6. **State Transition:** `recovering` -> `patching` (Attempt 1).
   - Model receives feedback and attempts a second patch.
7. **Branch 1 (Recovery Success):** If second patch passes both targeted and regression suites, transitions to `verified`.
8. **Branch 2 (Recovery Failure / Budget Depleted):** If second patch fails or introduces another error:
   - Recovery manager checks: `recovery_attempts >= 1`.
   - State transitions: `testing` -> `unresolved`.
   - System terminates safely without looping further.

#### Verification & Pass Criteria:
* Exactly one recovery cycle is permitted (`recovery_attempts == 1`).
* If verification fails post-recovery, status transitions to `unresolved` (never false `verified`).
* Ephemeral workspace is cleaned up; source directory is completely untouched.

---

### 2.4 Scenario D: Source-Only Project Workflow (No Tests Detected)

* **Goal:** Verify that a developer can register and inspect a real supported source repository (Python, TypeScript, JavaScript, Java) that contains no test suite, browse its files safely, generate a focused reproduction test proposal via Gemini/stub without host execution, and receive safe execution refusal when Docker is absent.
* **Target Repository:** Ephemeral source-only repository containing `src/auth.py` and `service.py` (no `pytest`, `package.json`, or test files).

#### Setup:
1. Create a source-only directory with clean implementation files.
2. Compute baseline SHA-256 tree hash.

#### Execution Sequence:
1. Client issues `POST /api/v1/repositories/open-local` pointing to the directory.
   - Result: HTTP 200 OK.
   - Metadata confirms: `layout_status == "no_tests"`, `test_framework == "unknown"`, `execution_allowed == false`.
   - Execution warning returned: *"No existing tests detected. PatchPilot can inspect source and propose focused tests. Execution blocked: Docker sandbox unavailable."*
2. Client requests `GET /api/v1/repositories/{id}/file?path=src/auth.py`.
   - Result: HTTP 200 OK.
   - Content returned with line count and language highlighting metadata without reading secret files.
3. Client requests `POST /api/v1/repositories/{id}/propose-test` with:
   - `bug_report`: *"Password reset token expiration check fails for zero timestamp"*.
   - Result: HTTP 200 OK.
   - Response contains proposed test code and `status == "proposed"` (marking it as proposed, not executed).
   - Zero untrusted code was executed during test authoring.
4. Client attempts to dispatch repair execution via `POST /api/v1/repairs`.
   - Result: HTTP 403 Forbidden with `error.code == "SANDBOX_UNAVAILABLE"`.
   - Host machine is protected from arbitrary execution.
5. Verification confirms source directory SHA-256 hash is unchanged (0 bytes mutated).

---

### 2.5 Scenario E: Adaptive Execution Across Sandbox Modes

* **Goal:** Verify that PatchPilot adapts intelligently based on container availability without weakening security boundaries.
* **Execution Sequence:**
  1. **Mode A (Static Inspection):** Operates with zero Docker dependency. Registers local projects, browses source files, discovers tests, proposes tests, generates patches, and displays diffs.
  2. **Mode B (Restricted Local Execution):** Audited restricted process runner exclusively authorized for bundled demo fixtures (`fixtures/**`).
  3. **Mode C (Isolated Docker Execution):** When Docker is operational, untrusted user code executes inside unprivileged container sandbox (`patchpilot-sandbox:python-3.12`) with `--network none`, `--read-only`, non-root user (`1000:1000`), dropped capabilities, and memory/CPU limits.
  4. When Docker is unavailable, PatchPilot refuses untrusted host execution (`SANDBOX_UNAVAILABLE`) while keeping Mode A fully operational.

---

### 2.6 Scenario F: Security Invariants and Path Confinement

* **Goal:** Verify that the security jail, secret filtering, and diff validation protect host integrity under attack.
* **Execution Sequence:**
  1. Path traversal attacks (`../../`, `C:/Windows`) via file-read endpoints are rejected with HTTP 403 / 404.
  2. Symlink escape attempts pointing outside repository root are detected and blocked.
  3. Sensitive files (`.env`, `.env.local`, `id_rsa`, `*.pem`, `*.key`) are completely excluded from file lists and refused on read.
  4. Binary files (`image.png`, compiled binaries) are rejected with HTTP 422.
  5. Malformed diffs and hunks attempting path traversal (`--- a/../../escape.py`) are rejected by `PatchValidator`.

---

### 2.7 Scenario G: Full Application Integration

* **Goal:** Verify the complete, cohesive user journey through the live API.
* **Execution Sequence:**
  1. Register local repository via `POST /api/v1/repositories/open-local`.
  2. Query file tree via `GET /api/v1/repositories/{id}/files`.
  3. Read source file with syntax metadata via `GET /api/v1/repositories/{id}/file?path=...`.
  4. Propose focused reproduction test via `POST /api/v1/repositories/{id}/propose-test`.
  5. Create and coordinate repair job via `POST /api/v1/repairs`.
  6. Inspect state machine progress to `verified`.
  7. Retrieve chronological audit events via `GET /api/v1/repairs/{id}/events`.
  8. Retrieve unified diff via `GET /api/v1/repairs/{id}/diff`.
  9. Retrieve full audit report via `GET /api/v1/repairs/{id}/report`.
  10. Dispatch cancellation request via `POST /api/v1/repairs/{id}/cancel` on in-flight repair and verify cancellation.

---

### 2.8 Scenario H: Original Project Preservation

* **Goal:** Verify that user repositories and bundled fixtures remain 100% immutable across all repair and testing operations.
* **Execution Sequence:**
  1. Compute SHA-256 tree hashes for `C:\smart-reverse-auction` and bundled fixtures before any operations.
  2. Run the entire test and verification suite.
  3. Recompute SHA-256 tree hashes and compare byte-for-byte.
  4. Verify exact match (0 bytes altered).

---

## 3. Specialized Robustness & Security Acceptance Test Suite

The following automated tests must pass before the backend is considered production-ready.

```
+-----------------------------------------------------------------------------------+
|                        ROBUSTNESS & SECURITY TEST MATRIX                          |
+----+------------------------------+-----------------------------------------------+
| ID | Test Scenario                | Expected Behavior & Safety Invariant          |
+----+------------------------------+-----------------------------------------------+
| T1 | Path Traversal Attack        | Blocks paths containing '../'; raises 403.    |
| T2 | Symlink Escape Attack        | Blocks reading/writing through external links.|
| T3 | Malformed Model Output       | Rejects non-JSON or invalid unified diffs.    |
| T4 | Out-of-Bounds Diff Hunks     | Rejects patches where line context mismatches.|
| T5 | Provider Auth, Model & Quotas| Handles 401, 404, 429, 503 without leaking keys. |
| T6 | Test Execution Timeout       | Kills hung process at timeout limit; fails.  |
| T7 | Unsupported Language/Layout  | Detects missing toolchain; halts safely.      |
| T8 | User Cancellation Mid-Flight | Kills sandbox processes; cleans workspace.    |
| T9 | Excessive Command Output     | Truncates test logs at 64KB; prevents OOM.   |
| T10| Secret Leakage Prevention    | Redacts API keys from all logs and responses. |
| T11| Source Repo Immutability     | 0 bytes altered on host repository.           |
| T12| Prevention of Fake Success   | Model saying "I fixed it" cannot force pass.  |
| T13| Baseline Infrastructure Error| Missing import / runner error halts as failed.|
| T14| Untrusted Repo Sandbox Check | Refuses execution if Docker/image is missing. |
+----+------------------------------+-----------------------------------------------+
```

---

### Detailed Test Specifications:

#### T1: Path Traversal Attack
* **Input:** Model or API requests `read_file(file_path="../../etc/passwd")` or `file_path="C:/Windows/System32/drivers/etc/hosts"`.
* **Expectation:** `WorkspaceManager` canonicalizes path using `resolve()`; detects target lies outside ephemeral workspace root; raises `PathTraversalSecurityException`; emits audit event `error_encountered`; returns HTTP 403.

#### T2: Symlink Escape Attack
* **Input:** Repository contains a pre-existing symbolic link pointing to an external host directory (`/etc` or `C:/Users`).
* **Expectation:** `WorkspaceManager` during clone ignores or sanitizes symlinks; file readers reject traversing symlinks that resolve outside the workspace jail.

#### T3: Malformed Model Output
* **Input:** Gemini model returns conversational prose instead of structured JSON, or returns truncated diff with unclosed hunks.
* **Expectation:** `PatchValidator` catches syntax parsing error; transitions to `recovering` (or `failed` if prompt schema validation fails); never passes garbage strings to patch utilities.

#### T4: Out-of-Bounds Diff Hunks
* **Input:** Model proposes a patch where `@@ -50,5 +50,5 @@` targets a file with only 10 lines, or where context lines do not match file content.
* **Expectation:** `PatchValidator` detects hunk mismatch; application rejected cleanly without altering target file; `.bak` files preserved for rollback.

#### T5: Provider Key, Auth, Model, and Quota Errors
* **Input:** 
  1. API key is invalid (HTTP 401).
  2. Provider returns HTTP 429 (Resource / Rate Limit Exhausted).
  3. Configured model candidate (`GEMINI_MODEL`) is deprecated or unavailable (HTTP 404).
  4. Provider service times out or is down (HTTP 502/503/504).
* **Expectation:** `GeminiProviderAdapter` catches HTTP error; logs sanitized diagnostic message (zero API keys in logs or traces); transitions repair status to `failed` with code `PROVIDER_AUTH_FAILED`, `PROVIDER_QUOTA_EXHAUSTED`, `PROVIDER_MODEL_UNAVAILABLE`, or `PROVIDER_ERROR`. Free-tier quota exhaustion is handled gracefully.

#### T6: Execution Timeout
* **Input:** Test suite enters an infinite `while True:` loop.
* **Expectation:** `SandboxTestRunner` enforces 30s wall-clock timeout; sends `SIGKILL` to subprocess / Docker container; records `timed_out: true`; verification classifies outcome as failed.

#### T7: Unsupported Language / Missing Toolchain
* **Input:** Repository contains unknown layout (e.g. Haskell, or Python repo missing `pytest`).
* **Expectation:** `RepositoryInspector` detects `unknown` language or framework; orchestrator marks job as `failed` with message `"Unsupported project layout: pytest not detected in repository"`.

#### T8: User Cancellation Mid-Flight
* **Input:** User sends `POST /api/v1/repairs/{id}/cancel` while job is in `testing` phase.
* **Expectation:** Orchestrator cancels background asyncio task; kills active subprocess; transitions state to `cancelled`; cleans up ephemeral workspace immediately.

#### T9: Excessive Command Output
* **Input:** Bug causes test runner to print 100MB of infinite spam to stdout.
* **Expectation:** `SandboxTestRunner` caps buffered output at 64KB (65,536 bytes); appends `"... [TRUNCATED: Output exceeded 64KB limit]"`; prevents memory overflow.

#### T10: Secret Leakage Prevention
* **Input:** User passes `X-Session-Gemini-Key: YOUR_GEMINI_API_KEY`.
* **Expectation:** Grepping entire SQLite database, audit logs, and API responses reveals zero instances of `YOUR_GEMINI_API_KEY`. Subprocess environments stripped of `GEMINI_API_KEY`.

#### T11: Source Repository Immutability
* **Input:** Complete lifecycle run (Scenarios A, B, C, or malicious attacks).
* **Expectation:** Pre-repair SHA-256 file manifest of authorized source directory matches post-repair manifest identically.

#### T12: Prevention of Fake Success
* **Input:** Model generates a patch that changes nothing or leaves tests failing, but Gemini emits text: *"I have verified the repair and all tests pass."*
* **Expectation:** Deterministic verification engine ignores model prose; checks real exit code (`exit_code != 0`); marks status as `unresolved` or `failed`.

#### T13: Baseline Infrastructure & Import Error Detection
* **Input:** Baseline targeted test fails not due to an assertion failure, but due to `ModuleNotFoundError: No module named 'missing_pkg'`, a syntax error in the test file, or `pytest` exit code 5 (no tests collected).
* **Expectation:** Test runner classifies outcome as `import_error` or `collection_error`. The orchestrator terminates the repair immediately as `failed` with diagnostic error `MISSING_DEPENDENCY` or `INVALID_TEST_TARGET`. Patch generation is **prohibited**, preventing the agent from synthesizing hallucinations on broken environments.

#### T14: Untrusted Repository Sandbox Feasibility Enforcement
* **Input:** User submits an arbitrary / non-fixture repository for repair when Docker daemon is stopped, Docker CLI is missing, or the language sandbox container image is missing.
* **Expectation:** The backend performs the 3-way check; detects sandbox unavailability; **strictly refuses execution** with HTTP 412 / error code `SANDBOX_UNAVAILABLE`. The backend does **not** fall back to host execution for untrusted code. Restricted Demonstration Mode is permitted only for pre-registered, trusted test fixtures.
