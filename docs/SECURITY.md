# PatchPilot — Security Architecture & Threat Model

**Document Version:** 1.0.0-freeze  
**Status:** Approved Architecture Baseline  
**Classification:** Defense-in-Depth Security Specification  

---

## 1. Threat Model & Trust Boundaries

PatchPilot executes in developer workstations where untrusted or buggy code, third-party libraries, and external AI model providers intersect. To protect the developer's machine and proprietary IP, the system defines four concentric trust zones.

```
+-----------------------------------------------------------------------------------------+
|                                    TRUST ZONES & BOUNDARIES                             |
+-----------------------------------------------------------------------------------------+
| ZONE 0: Developer Workstation & Host OS                                                 |
|   - Host Environment, User Files, SSH Keys, AWS Credentials, Source Repositories       |
|   - Policy: MAXIMUM PROTECTION. Never exposed to arbitrary child execution.            |
+-----------------------------------------------------------------------------------------+
                                          │
                                 [ Jailed Isolation ]
                                          ▼
+-----------------------------------------------------------------------------------------+
| ZONE 1: PatchPilot Backend Process (FastAPI / Modular Monolith)                         |
|   - Trusted application logic. Manages state machine, enforces tool allowlists.         |
|   - Holds in-memory session API key. Sanitizes environment variables.                   |
|   - Binds strictly to 127.0.0.1. Rejects untrusted origins via strict CORS.             |
|   - Note: Local loopback HTTP is not TLS; local host process isolation is required.    |
+-----------------------------------------------------------------------------------------+
                                          │
                            [ Sandbox Execution Boundary ]
                                          ▼
+-----------------------------------------------------------------------------------------+
| ZONE 2: Ephemeral Workspace & Execution Sandbox (Docker / Restricted Runner)            |
|   - Ephemeral clone of repository. Modified files, test runners, compiler cache.        |
|   - Policy: ZERO NETWORK ACCESS. ZERO INHERITED SECRETS. BOUNDED TIMEOUTS.              |
|   - Tier 1: Isolated Docker container. Tier 2: Restricted runner (TRUSTED FIXTURES ONLY).|
+-----------------------------------------------------------------------------------------+
                                          │
                                  [ TLS HTTPS / BYOK ]
                                          ▼
+-----------------------------------------------------------------------------------------+
| ZONE 3: External AI Model Provider (Google Gemini API)                                  |
|   - Processes prompt text and diffs. External infrastructure.                           |
|   - Configurable model (GEMINI_MODEL, default candidate: gemini-2.0-flash).             |
|   - Policy: EXPLICIT USER PRIVACY DISCLOSURE. ZERO REPOSITORY EXPOSURE OUTSIDE PROMPTS. |
+-----------------------------------------------------------------------------------------+
```

### 1.1 Key Threat Vectors Analyzed:
1. **Malicious / Buggy Code Execution:** A repository or test suite contains harmful logic (e.g. `os.system("rm -rf ~")`, cryptominers, reverse shells).
2. **Path Traversal / Escape:** An AI model or API request attempts to read or write files outside the repository boundary (e.g. `../../.ssh/id_rsa`).
3. **Secret Leakage:** Gemini API keys or local host credentials leaked to logs, database records, frontend browser responses, or sandbox processes.
4. **Denial of Service (DoS):** Infinite test loops, disk exhaustion via runaway logs, or memory exhaustion.
5. **Cross-Origin / Loopback Hijacking:** A malicious web page visited in the developer's browser attempts to interact with the local backend on `http://127.0.0.1:8000`.
6. **Prompt Injection / Jailbreak:** Bug reports or repository comments craft instructions designed to bypass tool constraints or trick the model into executing dangerous payloads.

### 1.2 Local Loopback Security Architecture
Because local loopback traffic (`http://127.0.0.1`) does not use TLS:
* **Strict Loopback Binding:** The FastAPI backend binds exclusively to `127.0.0.1:8000` and refuses to bind to `0.0.0.0`.
* **Narrow CORS Policy:** Access is restricted strictly to authorized local frontend origins (`http://localhost:5173`, `http://127.0.0.1:5173`). Requests from unauthorized web origins receive HTTP 403 / CORS rejection.
* **Host Header Validation:** Incoming requests must have valid `Host: 127.0.0.1:8000` or `Host: localhost:8000` headers, preventing DNS rebinding attacks.

---

## 2. Secrets Management (BYOK Architecture)

PatchPilot strictly implements a **Bring-Your-Own-Key (BYOK)** pattern.

### 2.1 Storage & Session Lifecycle
* **Session-Only Frontend Memory:** When a user enters their Gemini API key in the UI modal, it is stored **strictly in React state memory** for the active browser session. It is never persisted to `localStorage`, `sessionStorage`, cookies, or browser caches.
* **Zero Disk Persistence:** Gemini API keys are **never** stored in SQLite, flat files, `.env` files written by the application, or temporary files.
* **Active Validation Requirement:** A submitted key is never silently trusted upon entry. `POST /api/v1/provider/session-key` executes an active validation ping against the Gemini API. Only keys that pass live validation are accepted for repair sessions.
* **Transmission Protocol:** The key is passed to the backend per-request via the `X-Session-Gemini-Key` header over local loopback (`http://127.0.0.1:8000`), or read directly from the host environment variable `GEMINI_API_KEY`.

### 2.2 Redaction & Log Scrubbing
* **Filter Rule:** An application-wide logging filter inspects every log message, error report, tracing span, and audit event payload. Any string matching Google API key patterns (`AIza[0-9A-Za-z-_]{35}`) or generic secret formats is masked:
  `YOUR_GEMINI_API_KEY` -> `AIzaSyD...[REDACTED]`
* **Database Invariant:** SQLite tables (`repositories`, `repairs`, `audit_events`, `verification_records`) have no column or JSON field capable of accepting or storing API keys.

---

## 3. Sandbox Isolation & Process Execution Feasibility

Testing requires running real code. PatchPilot deploys a tiered sandbox architecture governed by strict feasibility checks.

```
                      +---------------------------------------+
                      |     3-WAY DOCKER FEASIBILITY CHECK    |
                      +---------------------------------------+
                      | 1. Docker CLI binary exists in PATH?  |
                      | 2. Docker daemon responsive to ping?  |
                      | 3. Required sandbox image installed?  |
                      +---------------------------------------+
                                          │
                        All 3 Checks Pass?
                         ├── YES ──> TIER 1: Docker Container Sandbox (Required for Arbitrary Repos)
                         └── NO  ──> Is Target an Authorized Preconfigured Fixture?
                                      ├── YES ──> TIER 2: Restricted Demonstration Mode (With Warning)
                                      └── NO  ──> STRICT EXECUTION REFUSAL (SANDBOX_UNAVAILABLE)
```

> [!CRITICAL]
> **Refusal Policy for Arbitrary Code:** The system does **not** treat command allowlisting as sufficient protection for arbitrary, untrusted repositories. If Docker, the daemon, or the required sandbox image is unavailable, PatchPilot **strictly refuses execution** with HTTP 412 (`SANDBOX_UNAVAILABLE`) rather than silently falling back to host execution. Restricted Demonstration Mode is permitted **strictly and exclusively** for authorized, preconfigured demonstration fixtures.

### 3.1 Docker Sandbox Provisioning & Toolchains
Merely having the `docker` executable installed on the host does not guarantee Docker is usable. Before dispatching repairs, PatchPilot independently verifies:
1. `docker --version` exits with code 0.
2. `docker info` exits with code 0 (confirming daemon socket connectivity).
3. `docker image inspect patchpilot-sandbox:<language>-<version>` exits with code 0.

#### Required Sandbox Image Definition:
Sandbox images are provisioned using locked minimal base images without network tools:

```dockerfile
# File: PatchPilot/sandbox/Dockerfile.python
FROM python:3.12-slim
RUN useradd -m -u 1000 -s /bin/bash sandboxuser && \
    pip install --no-cache-dir pytest
WORKDIR /workspace
USER sandboxuser
```

*Build Command:*
```bash
docker build -t patchpilot-sandbox:python-3.12 -f sandbox/Dockerfile.python .
```

#### Runtime Execution Policy:
When executing in Tier 1 Docker Sandbox:
```bash
docker run --rm \
  --network none \
  --cpus 1.5 \
  --memory 1024m \
  --pids-limit 100 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v "C:/Temp/patchpilot_ws_abc123:/workspace:rw" \
  --user 1000:1000 \
  --cap-drop ALL \
  patchpilot-sandbox:python-3.12 \
  pytest tests/test_calculator.py
```

* **Network Disabled:** `--network none` guarantees that malicious code or dependency hooks cannot phone home, exfiltrate files, or download payloads.
* **Resource Quotas:** Memory capped at 1024MB; CPUs capped at 1.5 cores; PID limit capped at 100 to prevent fork bombs.
* **Privilege Dropped:** `--user 1000:1000` and `--cap-drop ALL` prevents root escalation or container breakout.
* **Filesystem Isolation:** Container root is strictly `--read-only`. Only `/workspace` (ephemeral clone) and a small bounded tmpfs are writable.

### 3.2 Tier 2: Restricted Demonstration Mode (Authorized Fixtures Only)
If Docker or a required container image is unavailable, PatchPilot activates Restricted Demonstration Mode **strictly for pre-registered, trusted test fixtures** (e.g. fixtures under `PatchPilot/fixtures/`).

> [!WARNING]
> **Persistent Warning Banner:** The frontend UI displays a high-visibility warning banner: *"Restricted Demonstration Mode Active — Process running on host without container jail. Execution restricted to trusted local fixtures only."* API responses include `"restricted_mode": true`.

#### Hardened Host Process Guarantees:
1. **Target Restriction:** Rejects any repository path not present on the internal trusted fixture whitelist.
2. **Command Allowlist:** Arbitrary commands are completely rejected. Only pre-registered executable binaries matching specific arguments may run:
   * Python: `["pytest", ...]`
   * JavaScript / TypeScript: `["npm", "test", "--", ...]`, `["vitest", "run", ...]`
   * Java: `["./mvnw", "test", ...]`, `["./gradlew", "test", ...]`
3. **Environment Stripping:** The child process receives a scrubbed environment dictionary containing only `PATH`, `SYSTEMROOT`, and Python virtual environment paths. All host secrets (`GEMINI_API_KEY`, `AWS_*`, `GITHUB_*`, `SSH_*`) are explicitly deleted from `os.environ` copies.
4. **Execution Timeouts:** Hard kill (`SIGTERM` followed by `SIGKILL` after 2 seconds) enforced at 30 seconds for targeted tests and 60 seconds for regression suites.
5. **Output Buffering Cap:** Stdout and stderr streams are capped at 64 KB (65,536 bytes) to eliminate memory exhaustion attacks.

---

## 4. Workspace Security & Path Jail Enforcement

### 4.1 Ephemeral Cloning
* The user's primary repository is **never** used as the execution directory.
* Source files are cloned into a unique temporary directory (e.g. `C:/Users/parid/AppData/Local/Temp/patchpilot_ws_9b1deb4d/`).
* Upon job conclusion (or unexpected crash), `shutil.rmtree` cleans up all temporary files.

### 4.2 Canonical Path Jail Implementation
Before reading, writing, or validating any file path, the system enforces directory confinement:

```python
def resolve_jailed_path(workspace_root: Path, requested_path: str) -> Path:
    # 1. Normalize and resolve canonical path
    resolved_path = (workspace_root / requested_path).resolve()
    
    # 2. Check if resolved path is strictly within the workspace root
    try:
        resolved_path.relative_to(workspace_root.resolve())
    except ValueError:
        raise PathTraversalSecurityException(
            f"Security violation: path '{requested_path}' escapes workspace jail."
        )
        
    # 3. Check for symlink targets escaping the jail
    if resolved_path.is_symlink():
        target = resolved_path.readlink().resolve()
        try:
            target.relative_to(workspace_root.resolve())
        except ValueError:
            raise SymlinkEscapeSecurityException(
                f"Security violation: symlink '{requested_path}' points outside workspace."
            )
            
    return resolved_path
```

---

## 5. Model Provider Privacy & Data Disclosure

### 5.1 Privacy Disclosure Policy
Before a user triggers their first repair job, PatchPilot presents an explicit privacy notice:

> **Data Transmission Notice:**  
> PatchPilot transmits relevant code snippets, file context, and bug report text directly to Google Gemini API over an encrypted TLS connection. Repository data processed by the model is subject to Google's API Terms of Service and data-handling policies. Do not use PatchPilot with repositories containing classified, export-controlled, or highly confidential information unless your Gemini API tier provides explicit privacy guarantees.

### 5.2 Content Minimization
* PatchPilot does **not** upload entire repositories to Gemini.
* Only files directly identified by the static inspector as relevant to the bug report and failing test target are read and included in model prompts.
* `.env`, `.git/config`, `id_rsa`, and secret credential patterns are explicitly omitted from repository scanning and file reading tools.

### 5.3 Model Candidate Configuration & Provider Quota Limits
* **Configurable Model Candidate:** The Gemini model is configured via the backend environment variable `GEMINI_MODEL` (default candidate: `gemini-2.0-flash` or `gemini-1.5-flash`). Model names in examples and documentation represent candidate defaults, not a permanent guarantee of availability or performance across regions.
* **Quota & Rate Limit Disclosures:** Free tier Gemini API keys are subject to strict provider quotas (e.g. 15 requests per minute, daily limits). The system does not claim or assume unlimited access.
* **Provider Error Translation:** The backend translates provider responses into sanitized domain errors without leaking secrets:
  * HTTP 400 / 401: `PROVIDER_AUTH_FAILED` (Invalid or missing key).
  * HTTP 404: `PROVIDER_MODEL_UNAVAILABLE` (Configured model not found or deprecated).
  * HTTP 429: `PROVIDER_QUOTA_EXHAUSTED` (Rate limit reached; user prompted to wait or supply a paid-tier key).
  * HTTP 502 / 503 / 504: `PROVIDER_ERROR` (Transient provider downtime or timeout).

---

## 6. In-App Source Explorer & File Access Security

When a user opens and navigates source files in PatchPilot:
1. **Jail Enforcement:** `canonicalize_and_jail_path` verifies that every requested path resolves strictly beneath the registered repository root. Traversal tokens (`../`) and relative escapes are rejected with `PATH_TRAVERSAL_DETECTED`.
2. **Secret File Exclusion:** Sensitive files matching `.env*`, `.git`, `*.pem`, `*.key`, `id_rsa`, `*credential*`, and `*token*` are strictly blocked (`SECRET_FILE_BLOCKED`). They are omitted from file tree listings and refused by the file-reading endpoint.
3. **Binary & Size Protection:** Files are scanned for null bytes (`\x00`) to detect binaries, and file sizes are capped at 1MB to prevent memory exhaustion (`BINARY_OR_OVERSIZED_FILE`).
4. **Context Minimization:** Only requested line slices (default: 500 lines) are returned to the frontend. Whole repositories are never loaded into process memory or transmitted to the LLM.

---

## 7. Native OS Dialog & Process Execution Isolation

1. **Native Electron Dialog:** The desktop application invokes the native Windows folder picker via Electron's `dialog.showOpenDialog({ properties: ['openDirectory', 'dontAddToRecent'] })` directly interfacing with Windows Shell API. User-controlled strings are never executed in a shell, eliminating command injection risks.
2. **Loopback Fallback Helper:** When running headless or in development, loopback helper runs via parameterized PowerShell with a strict 15-second timeout and sanitization.
3. **Manual Fallback Invariant:** If the dialog is cancelled or unavailable, the system safely preserves existing path state without discarding user inputs.

---

## 8. Patch Approval Gate & Repository Immutability Security

1. **Original Repository Immutability:** The developer's original project is strictly read-only during the entire bug discovery, AST analysis, test proposal, baseline reproduction, patch synthesis, sandbox test execution, and recovery workflow.
2. **Disposable Workspace Jail:** All candidate changes, file writes, and test runner executions occur exclusively in disposable workspaces located in system temporary directories (`tempfile.mkdtemp(prefix="patchpilot_ws_")`).
3. **Explicit User Approval Gate:** Patches cannot be exported to the developer's original repository without explicit manual approval via `POST /api/v1/repairs/{id}/export`. Merely viewing the unified diff or opening the final report does not trigger export.
4. **Pre-Export Conflict Detection:** Before modifying any file in the original repository, the backend verifies that the target files have not been modified externally since the candidate patch snapshot was created. If external modifications are detected, export is aborted with HTTP 409 Conflict to prevent overwriting developer changes.
5. **Rejection Guarantee:** If the user clicks **Reject Changes** (`POST /api/v1/repairs/{id}/reject`), the repair transitions to `unresolved`, candidate files in the ephemeral workspace are wiped, and the original repository remains 100% untouched.

---

## 9. Desktop Shell & Electron Process Boundary

1. **IPC Context Isolation:** The Electron desktop shell enforces `contextIsolation: true` and `nodeIntegration: false`. The renderer process running the React UI has zero direct access to Node.js APIs (`fs`, `child_process`).
2. **Minimal Bridge Surface:** The preload script (`preload.cjs`) exposes only explicit methods (`openDirectory`, `getApiBaseUrl`, `isDesktop`) via `window.desktopApi`.
3. **Guaranteed Child Process Termination:** When the desktop application window is closed or receives a termination signal (`SIGINT`, `SIGTERM`), the main Electron process executes `taskkill /pid <Python_PID> /T /F` on Windows to cleanly terminate the entire child process tree, preventing orphaned background uvicorn servers.


