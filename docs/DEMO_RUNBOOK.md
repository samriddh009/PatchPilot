# PatchPilot — Demo Runbook & Developer Evaluation Guide

**Document Version:** 1.0.0-release  
**Status:** Implemented & Verified Baseline  
**Evaluation Scope:** Local Setup, Verification Scenarios, and Troubleshooting  

---

## 1. Prerequisites & Environment Matrix

To run and evaluate PatchPilot locally, the host system must meet the following baseline requirements:

| Component | Minimum Version | Recommended Version | Verification Command |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10/11, macOS 13+, or Ubuntu 22.04 LTS | Windows 11 / Ubuntu 22.04 | `systeminfo` / `uname -a` |
| **Python** | Python 3.12.0+ | Python 3.12.4 | `python --version` |
| **Node.js** | Node.js 20.x LTS | Node.js 20.12+ | `node --version` |
| **Package Manager** | npm 10.x | npm 10.5+ | `npm --version` |
| **Docker Engine** *(Optional for Untrusted Repos)* | Docker 24.0+ CLI & active daemon | Docker Desktop 4.28+ | `docker --version` & `docker info` |
| **Sandbox Container Image** *(Tier 1)* | Built locally | `patchpilot-sandbox:python-3.12` | `docker image inspect patchpilot-sandbox:python-3.12` |
| **AI Provider Key** | Google Gemini API Key | Valid Gemini 1.5 Flash / Pro Key | BYOK Key from Google AI Studio |

---

## 2. Configuration & Secrets Setup

PatchPilot uses a Bring-Your-Own-Key (BYOK) architecture. Users configure their Gemini API key via either an environment variable or the frontend in-memory session modal.

### Option A: Environment Variables (Recommended for Automated Runs)
Set configuration variables in your terminal before launching the backend:

**PowerShell (Windows):**
```powershell
$env:GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
$env:GEMINI_MODEL = "gemini-1.5-flash"  # Default candidate; configurable
```

**Bash / Zsh (Linux / macOS):**
```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
export GEMINI_MODEL="gemini-1.5-flash"  # Default candidate; configurable
```

*Notice on Model Availability & Quotas:*
- Default model candidate is `gemini-1.5-flash`.
- Supported options: `gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash-exp`, `gemini-2.0-flash`.
- Model identifiers are automatically normalized to remove any leading `models/` prefix.
- Free-tier keys are subject to Google AI Studio rate limits (15 RPM).
- Automated tests mock provider responses and never consume live Gemini credits.

### Option B: Frontend Session Key (In-Memory Only)
If the environment variable is omitted, the frontend UI provides an in-memory key setup dialog:
1. Open `http://localhost:5173`.
2. Click **"Configure"** or **"Gemini API Key"** in the navigation header.
3. Select your desired model from the dropdown (default: `gemini-1.5-flash`).
4. Enter your Gemini API key in the masked input field.
5. Click **"Test Connection"**. The backend performs an active validation probe (`POST /api/v1/provider/session-key`). Keys are never assumed valid upon entry.
6. The key is kept strictly in React component memory for the active browser session and passed via the `X-Session-Gemini-Key` header over local loopback (`http://127.0.0.1:8000`). It is never stored in browser `localStorage`, `sessionStorage`, cookies, `.env`, or backend SQLite.
7. Alternatively, click **"Continue in Demo Mode"** to test bundled fixtures without providing a key.

---

## 3. Local Startup Sequence

PatchPilot supports two execution modes: **Desktop Mode (Native Application)** and **Browser Development Mode**.

### Mode 1: Desktop Application Mode (Recommended for Full Native Capabilities)
The desktop application uses Electron with context isolation and secure IPC to offer the native Windows folder-selection dialog:
```powershell
cd "c:\patch pilot\frontend"
npm run desktop
```
*Desktop Lifecycle Features:*
- Automatically detects an existing backend on port 8000 or spawns the local Python backend service (`backend/.venv/Scripts/python.exe`).
- Validates health on `http://127.0.0.1:8000/api/v1/health`.
- Opens a dedicated desktop window titled **"PatchPilot — Desktop Engineering Agent"**.
- Enables the real native Windows folder-selection dialog (`window.desktopApi.openDirectory()`) with zero manual path typing.
- Terminates child backend processes cleanly upon application quit.
- To execute a non-interactive automated smoke test of the desktop shell:
  ```powershell
  npm run desktop -- --smoke-test
  ```

### Mode 2: Browser Development Mode
If running during UI development or without the desktop shell:
```powershell
# Terminal 1: Backend service
cd "c:\patch pilot\backend"
.\.venv\Scripts\Activate.ps1
python -m uvicorn patchpilot.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Vite development server
cd "c:\patch pilot\frontend"
npm run dev -- --host 127.0.0.1 --port 5173
```
Navigate to `http://127.0.0.1:5173`.
*Browser Sandbox Notice:* Modern web browsers intentionally hide local OS directory paths from web pages (`file.path` is suppressed for security). In browser mode, PatchPilot clearly displays a `Browser Mode` badge and provides a deliberate manual path entry input, automatically sanitizing quotes and resolving relative workspace paths.

Verify backend health:
```powershell
curl http://127.0.0.1:8000/api/v1/health
```

Expected Health Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": {
    "python_version": "3.12.0",
    "sandbox_backend": "docker",
    "docker_cli_available": true,
    "docker_daemon_responsive": false,
    "sandbox_image_available": false,
    "restricted_mode": true,
    "active_model": "gemini-1.5-flash",
    "database_connected": true
  }
}
```

Verify available models:
```powershell
curl http://127.0.0.1:8000/api/v1/provider/models
```

---

## 4. Scenario Walkthroughs & Expected Results

---

### Scenario A: Baseline Python Repair (Discount Boundary Off-by-One)

* **Repository Fixture:** `c:/patch pilot/fixtures/python_calc_bug/`
* **Defect Location:** `calculator/pricing.py` (`total > 100.0` instead of `>= 100.0`)
* **Failing Test:** `tests/test_calculator.py::test_discount_boundary`

#### Execution Steps:
1. In the PatchPilot Web UI, select repository **"python_calc_bug"**.
2. In the Bug Report field, enter:
   ```text
   The calculate_discount function fails to apply a 15% discount when the cart total equals exactly $100.00.
   ```
3. In the Test Target field, enter:
   ```text
   tests/test_calculator.py::test_discount_boundary
   ```
4. Click **"Start Controlled Repair"**.

#### Observed Lifecycle & Expected Evidence:
1. **Queued -> Inspecting:** Progress indicator shows ephemeral workspace created at temporary directory `patchpilot_ws_*`. Detected language: `python`, test runner: `pytest`.
2. **Reproducing:** Test runner executes `pytest tests/test_calculator.py::test_discount_boundary`.
   * Real baseline failure captured:
     ```text
     FAILED tests/test_calculator.py::test_discount_boundary - AssertionError: 0.10 != 0.15
     1 failed, 0 passed in 0.04s
     ```
   * Baseline passed indicator shows red badge (`FAIL - Expected for reproduction`).
3. **Patching:** Synthesizes unified diff:
   ```diff
   --- a/calculator/pricing.py
   +++ b/calculator/pricing.py
   @@ -14,3 +14,3 @@
   -    if total > 100.0:
   +    if total >= 100.0:
            return 0.15
   ```
   * Patch validator checks bounds and applies patch to disposable workspace.
4. **Testing:**
   * Targeted test executes: `pytest tests/test_calculator.py::test_discount_boundary` -> **PASSED** (Exit code 0).
   * Regression test executes: `pytest` -> **6 passed, 0 failed** (Exit code 0).
5. **Verifying:** Deterministic verification engine validates all checks.
6. **Final State:** **`verified`** (Green banner displayed).
7. **Integrity Check:** Original `fixtures/python_calc_bug/` directory remains completely untouched (SHA-256 tree hash unchanged).

---

### Scenario B: Different Logic Repair (Token Stream String Escaping)

* **Repository Fixture:** `c:/patch pilot/fixtures/python_parser_bug/`
* **Defect Location:** `parser/tokenizer.py` (Double backslash escaping logic)
* **Failing Test:** `tests/test_tokenizer.py::test_escaped_quote_handling`

#### Execution Steps:
1. Select repository **"python_parser_bug"**.
2. Enter Bug Report:
   ```text
   String tokenizer improperly drops escaped quote characters when preceded by double backslashes.
   ```
3. Enter Test Target:
   ```text
   tests/test_tokenizer.py::test_escaped_quote_handling
   ```
4. Click **"Start Controlled Repair"**.

#### Expected Evidence:
* Baseline failure confirmed: `AssertionError: Expected 'foo\"bar' got 'foobar'`.
* Agent synthesizes patch correcting string escape index tracking.
* Ephemeral test runner validates targeted fix and full test suite.
* Status reaches **`verified`**, proving agent operates on complex string parsing logic, not just numeric comparisons.

---

### Scenario C: Regression Detection & Bounded Recovery (Attempt $\le$ 1)

* **Repository Fixture:** `c:/patch pilot/fixtures/python_regression_fixture/`
* **Defect Location:** `service/tax.py`
* **Target Test:** `tests/test_tax.py::test_tax_exemption`

#### Execution Steps:
1. Select repository **"python_regression_fixture"**.
2. Enter Bug Report:
   ```text
   Tax exemption helper returns incorrect rate for non-profit entities.
   ```
3. Click **"Start Controlled Repair"**.

#### Observed Lifecycle & Expected Evidence:
1. Baseline reproduced: `test_tax_exemption` fails.
2. In `patching`, model proposes a naive fix that hardcodes an exemption return value.
3. In `testing`:
   * Targeted test `test_tax_exemption` passes.
   * Regression test suite runs: `test_standard_vat_rate` **FAILS**!
4. State transitions to **`recovering`**:
   * UI displays: *"Regression detected in test_standard_vat_rate. Initiating bounded recovery attempt (1/1)..."*
   * Recovery manager extracts failure logs and sends diagnostic feedback prompt.
5. In `patching (recovery)`:
   * Model attempts second patch.
6. If the second patch resolves the regression:
   * State transitions to **`verified`**.
7. If the second patch still fails or introduces another regression:
   * Recovery budget is exhausted (`recovery_attempts == 1`).
   * State transitions to **`unresolved`**.
   * UI displays: *"Repair Unresolved: Bounded recovery attempt exhausted. Original repository preserved unchanged."*

---

### Scenario D: Local Source-Only Project Inspection & Test Proposal

#### Goal:
Demonstrate opening a local project without tests, browsing its source code safely in-app, generating a focused reproduction test proposal via Gemini/stub, and receiving safe execution refusal when Docker is absent.

#### Execution Steps:
1. In the repository selector, click **"Open Local Folder"**.
2. Select your folder via the Windows dialog or type the directory path (e.g., a folder containing `calculator.py`).
3. Click **"Register & Open Project"**.
4. Observe the repository card:
   - Displays detected language (e.g. `python`, `typescript`, `javascript`, `java`).
   - Displays layout badge: **"No Tests Detected"**.
   - Displays security warning if Docker is unavailable.
5. Click **"Browse Source"** (or use the **"Explore Source Code"** header button).
   - In-app Source Explorer opens.
   - Inspect source code with line numbers and syntax highlighting.
   - Sensitive files (`.env*`, `.git`, credentials) are omitted or blocked.
6. Click **"Continue with Selected Repository"**.
7. In the Bug Report step, enter a bug description.
8. Click **"Generate Proposed Test with AI"**:
   - PatchPilot inspects the source files and generates a focused test.
   - Preview card shows proposed test file, code, and verification explanation marked with status **"PROPOSED (NOT EXECUTED)"**.
9. Confirm 0 bytes altered in the user's project directory.

---

### Scenario E: AI Provider Failures & Honest Error Reporting

* **Goal:** Verify that invalid keys, unsupported models, quota exhaustion, timeouts, and network errors are reported with distinct error codes and never fabricate patches.
* **Handled Error Codes:**
  - `PROVIDER_AUTH_FAILED` (401): Invalid or expired API key.
  - `PROVIDER_MODEL_UNAVAILABLE` (404): Configured model not found or unsupported for key tier.
  - `PROVIDER_QUOTA_EXHAUSTED` (429): Rate limit (15 RPM) or quota exhausted.
  - `PROVIDER_TIMEOUT` (504): API request timed out.
  - `PROVIDER_NETWORK_ERROR` (503): Network connection failed.
  - `PROVIDER_SAFETY_REFUSAL` (400): Content blocked by safety filters.
  - `PROVIDER_MALFORMED_RESPONSE` (502): Malformed JSON candidate response.

---

### Scenario F: Cancellation & Status Polling Recovery

* **Goal:** Verify immediate cancellation of queued jobs, running jobs, repeated cancellation idempotency, and graceful background failure recovery.
* **Execution:**
  - Clicking **"Cancel Repair"** while Queued cancels execution before workspace allocation.
  - In-flight cancellation kills running test processes and halts subsequent stages.
  - Repetitive cancellation returns safe 200 responses without race conditions.
  - Terminal repairs reject cancellation with clear feedback.

---

### Scenario G: Tier 1 Sandbox Isolation & Security Boundaries

* **Isolation Guarantees (Verified by live Docker tests):**
  - **Network Isolation:** `--network none` blocks all inbound/outbound socket operations.
  - **Read-Only Root Filesystem:** `--read-only` prevents host or container root alterations.
  - **Non-Root Execution:** Container runs with `--user 1000:1000` (non-root UID: 1000).
  - **Capabilities Dropped:** `--cap-drop ALL` strips all Linux kernel capabilities.
  - **Resource Capping:** 1.5 CPUs, 1024MB RAM, 100 PID limit.
  - **Output Capping:** Stdout and stderr capped to 64KB with `[TRUNCATED]` indicator.
  - **Timeout Enforcement:** Process killed after timeout seconds with exit code 124.

---

### Scenario H: End-to-End API Integration & Fixture Integrity

* Full user journey tested via FastAPI TestClient and live HTTP:
  - Repository registration -> File browsing -> Test proposal -> Repair dispatch -> Event polling -> Diff retrieval -> Final report generation -> Cancellation.
  - SHA-256 recursive tree hash verified: original repository fixtures and `C:\smart-reverse-auction` remain strictly unchanged.

---

## 5. Live BYOK Manual Verification Procedure

When you are ready to perform a single manual live Gemini API test with your own API key:

1. Launch backend and frontend servers:
   ```powershell
   # Terminal 1: Backend
   cd "c:\patch pilot\backend"
   .\.venv\Scripts\python.exe -m uvicorn patchpilot.main:app --host 127.0.0.1 --port 8000

   # Terminal 2: Frontend
   cd "c:\patch pilot\frontend"
   npm run dev -- --host 127.0.0.1 --port 5173
   ```
2. Open `http://localhost:5173` in your browser.
3. Click **"Configure"** or **"Gemini API Key"** in the navigation bar.
4. Select model **"gemini-1.5-flash"** (or another model enabled on your Google AI Studio account).
5. Paste your Gemini API key from [Google AI Studio](https://aistudio.google.com/).
6. Click **"Test Connection"**. Confirm green success checkmark.
7. Click **"Save Settings"** (key resides in-memory only).
8. Select the **"python_calc_bug"** repository.
9. Enter bug report: `Strict inequality excludes boundary total == 100.0`.
10. Target test: `tests/test_calculator.py::test_discount_boundary`.
11. Click **"Start Controlled Repair"**.
12. Verify:
    - Baseline reproduction captured (`AssertionError: 0.10 != 0.15`).
    - Diff generated by Gemini (`total >= 100.0`).
    - Targeted test passes (`exit_code = 0`).
    - Regression test passes (`6 passed`).
    - Final report displays `verified`.
    - Original fixture remains 100% untouched.

---

## 6. Standalone Desktop Launch & Autonomous / Directed Workflows

### 6.1 Launching the Desktop Application
PatchPilot is packaged as a standalone desktop application combining the React frontend in Electron with the Python backend process lifecycle:

```powershell
# 1. Open PowerShell at project root
cd "C:\patch pilot\frontend"

# 2. Build production assets and launch desktop shell:
npm run build
npm run desktop
```

*What happens automatically during launch:*
1. Electron main process checks if port 8000 is free (or dynamically assigns a free port to avoid collisions).
2. Spawns the local Python backend (`uvicorn patchpilot.main:app`).
3. Polls the backend health check endpoint (`/health`) until 200 OK.
4. Opens the PatchPilot desktop window with native Windows decorations.
5. Injects `window.desktopApi` via secure preload IPC.
6. When the user closes the window, Electron cleanly executes `taskkill /pid <Python_PID> /T /F`, guaranteeing zero orphaned background processes.

---

### 6.2 Autonomous Bug Discovery Workflow
1. In the desktop application, click **"Open Local Folder"** (or select a bundled demo fixture).
2. The real Windows native directory picker opens (`dialog.showOpenDialog`). Select your repository folder.
3. Click **"Find Bugs"** in the repository actions footer.
4. (Optional) Choose scan depth, defect categories, or target files.
5. Click **"Find Bugs"** (or **"Find Bugs & Prepare Fixes"**).
6. PatchPilot's AST scanner inspects all source files and runs baseline tests:
   - Identifies boundary inequalities, parser infinite loops, non-zero return assumptions, and bare except clauses.
   - Correlates with baseline tests to present confirmed defect evidence.
7. Click **"Prepare Fix"** on any finding to dispatch a repair job in a disposable workspace.

---

### 6.3 Patch Approval Gate & Safe Export
1. Once a candidate repair passes targeted tests and full regression verification, the **Repair Report** displays the **Patch Application Approval Gate**.
2. Notice the indicator: **"Original Repo Unchanged"**. All changes remain confined to the disposable workspace.
3. Review the unified diff and verification results.
4. Choose from four explicit actions:
   - **Approve and Export:** Pre-export conflict validation verifies that original repository files were not modified externally. Applies the verified unified diff to the developer's original repository and reports written files.
   - **Reject Changes:** Rejects the patch, marks repair unresolved, and preserves the original repository 100% untouched.
   - **Review Diff:** Scrolls to the unified diff viewer.
   - **Keep Report Without Exporting:** Closes the report without altering repository files.

---

## 7. Troubleshooting & Recovery

### 7.1 Provider API Errors & Quota Limits
* **Symptom:** UI displays error `PROVIDER_AUTH_FAILED` or `PROVIDER_QUOTA_EXHAUSTED`.
* **Remedy:**
  1. Verify your Gemini API key in [Google AI Studio](https://aistudio.google.com/).
  2. If using a free-tier key, ensure rate limits (15 RPM) have not been exceeded.
  3. Select an alternate model (e.g. `gemini-1.5-pro` or `gemini-2.0-flash-exp`) from the Model dropdown.

### 7.2 Docker Sandbox Unavailable
* **Symptom:** Health endpoint indicates Docker CLI or daemon unresponsive.
* **Behavior:**
  - Trusted local fixtures: run via RestrictedRunner.
  - Untrusted user repositories: safely refused with `403 SANDBOX_UNAVAILABLE`.
* **Remedy:** Start Docker Desktop from the Start Menu or PowerShell:
  ```powershell
  Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  ```

### 7.3 Port Collisions
* **Symptom:** Port 8000 is occupied by another local service.
* **Electron Auto-Resolution:** The desktop shell automatically detects the port collision and selects a free port (e.g. 8001+), passing the base URL to the frontend via `desktopApi.getApiBaseUrl()`.

