# PatchPilot

<div align="center">

**AI-Assisted Software Repair & Autonomous Defect Remediation Agent**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB.svg?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.5+-3178C6.svg?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![Electron](https://img.shields.io/badge/Electron-44+-47848F.svg?logo=electron&logoColor=white)](https://www.electronjs.org)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

</div>

---

PatchPilot is a local-first software delivery and bug-repair agent that automatically investigates, reproduces, patches, and verifies defects directly within your development workstation. 

Unlike general-purpose conversational coding assistants that edit files without verification, PatchPilot enforces a **closed-loop verification lifecycle**: every proposed patch is tested in an isolated, ephemeral workspace, verified against targeted reproduction tests, checked against existing regression test suites, and presented as an interactive diff for explicit human review before any code is modified in your source repository.

---

## Key Capabilities

### 1. Autonomous Bug Finding
- AST-driven structural analysis and static heuristic scanning (`POST /api/v1/repositories/{id}/discover-bugs`).
- Detects boundary condition bugs (e.g., strict inequality on discount thresholds), inverted escape handlers, unhandled exceptions, and dead code without executing arbitrary target code.
- Categorizes findings by severity (`critical`, `high`, `medium`, `low`) and confidence score with exact code excerpts and suggested remediation paths.

### 2. Directed Bug Investigation & Repair
- Guided remediation based on user bug descriptions and test failure logs.
- Finite state machine coordinates the repair lifecycle:
  ```
  [Queued] -> [Inspecting] -> [Reproducing] -> [Patching] -> [Verifying]
                                                                  |
                                       +--------------------------+--------------------------+
                                       |                          |                          |
                                  [Verified]                 [Unresolved]                 [Failed]
                                       |
                   +-------------------+-------------------+
                   |                                       |
              [Exported]                               [Rejected]
          (Human Approved)                         (Human Discarded)
  ```
- **Bounded Recovery**: If an initial patch fixes the target bug but introduces a regression elsewhere in the test suite, PatchPilot feeds the failure logs back into the model for a bounded single recovery attempt (`MAX_RECOVERY_ATTEMPTS = 1`).

### 3. AI-Assisted Test Generation
- When a bug report is provided without an existing reproduction test, PatchPilot generates a focused reproduction unit test (`POST /api/v1/repositories/{id}/propose-test`).
- Isolates test targets to ensure test cases can verify both bug reproduction (failure on baseline) and resolution (pass on patched workspace).

### 4. Controlled Patching & Human Approval Gate
- **Source Immutability**: Source repositories remain strictly read-only throughout exploration. All modifications occur in ephemeral, disposable workspaces (`patchpilot_ws_<id>`).
- **Interactive Diff Inspection**: Developers inspect unified diffs before exporting changes.
- **Export with Automatic Backups**: Applying a patch (`POST /api/v1/repairs/{id}/export`) writes changes to the source repository while generating timestamped `.bak` files for instant rollbacks.
- **Explicit Rejection**: Users can discard patches (`POST /api/v1/repairs/{id}/reject`), immediately cleaning up ephemeral workspaces.

---

## Supported Languages & Frameworks

| Language | Test Frameworks | Detection & AST Inspection | Test Execution Engine |
| :--- | :--- | :--- | :--- |
| **Python** | `pytest`, `unittest` | AST Parser & Pattern Matcher | Supported (Docker container & local restricted runner) |
| **TypeScript** | `vitest`, `jest` | Package manifest & Config Scanner | Supported (Command builder & Docker container runner) |
| **JavaScript** | `vitest`, `jest` | Package manifest & Config Scanner | Supported (Command builder & Docker container runner) |
| **Java** | `JUnit` (Maven `mvnw`, Gradle `gradlew`) | Build file parser (`pom.xml`, `build.gradle`) | Supported (Command builder & container runner) |

*Note: Bundled demonstration fixtures provide deterministic end-to-end verification for Python; arbitrary user projects require Docker daemon availability for execution isolation.*

---

## Architecture & System Design

PatchPilot is structured as a **Modular Monolith** backend paired with a reactive frontend and Electron desktop shell.

```
patchpilot/
├── backend/                        # FastAPI Modular Monolith Backend
│   ├── patchpilot/
│   │   ├── api/                    # REST API routers (/repairs, /repositories, /provider, /health)
│   │   ├── gemini/                 # Google Gemini BYOK provider client, prompts, and session store
│   │   ├── inspector/              # Static file scanner, AST analyzer, autonomous bug detector
│   │   ├── languages/              # Language adapters (Python, JS, TS, Java)
│   │   ├── orchestrator/           # Finite state machine and RepairJobCoordinator
│   │   ├── patcher/                # Unified diff parser, validator, and safe file applier
│   │   ├── recovery/               # Bounded regression recovery manager
│   │   ├── report/                 # Evidence markdown report builder
│   │   ├── sandbox/                # Docker container runner and host safety feasibility checker
│   │   ├── schemas/                # Pydantic v2 data models, enums, and API envelopes
│   │   ├── storage/                # SQLite metadata store and append-only audit event log
│   │   ├── test_runner/            # Process runner with timeouts and output truncation
│   │   ├── verifier/               # Deterministic verification engine (baseline, targeted, regression)
│   │   ├── workspace/              # Ephemeral workspace manager with SHA-256 tree hashing
│   │   ├── config.py               # Application configuration and environment defaults
│   │   └── main.py                 # FastAPI application factory, lifespan, and middleware
│   ├── tests/                      # Pytest test suite (125 tests)
│   ├── pyproject.toml              # Python project metadata and dependencies
│   └── requirements.txt            # Locked backend dependencies
├── frontend/                       # React 18 + Vite + TypeScript Single-Page Application
│   ├── electron/                   # Context-isolated Electron main and preload scripts
│   ├── src/
│   │   ├── api/                    # Typed API client and endpoint contracts
│   │   ├── components/             # UI components (DiffViewer, RepairTimeline, BugReportForm, etc.)
│   │   ├── context/                # In-memory React session key context
│   │   ├── hooks/                  # Polling and session key hooks
│   │   └── services/               # Local folder and IPC service layer
│   ├── package.json                # Frontend dependencies and npm scripts
│   └── vite.config.ts              # Vite build configuration
├── fixtures/                       # Bundled demonstration fixtures for reproduction testing
│   ├── python_calc_bug/            # Boundary condition inequality bug (15% vs 10% discount)
│   ├── python_parser_bug/          # Tokenizer string escape handling defect
│   └── python_regression_fixture/  # Tax calculation exemption defect with potential regression
├── docs/                           # Architecture, API specifications, and security runbooks
└── sandbox/                        # Docker sandbox environment definitions (Dockerfile.python)
```

---

## Security & Sandbox Model

PatchPilot is designed for secure, local-first execution on developer workstations:

1. **Loopback-Only Binding**: The backend binds exclusively to `127.0.0.1` and validates `Host` and `Origin` headers. Requests from unauthorized network origins are rejected with HTTP 403 `FORBIDDEN_ORIGIN`.
2. **Path Confinement & Jail**: All filesystem paths are canonicalized and resolved against the repository root. Directory traversal (`../`), symlink escapes, and Windows drive escapes are rejected with HTTP 403 `PATH_TRAVERSAL_DETECTED`.
3. **Secret Redaction & Confinement**:
   - Sensitive files (`.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`) are automatically filtered out during scanning, ingestion, and patch application.
   - All error envelopes, audit logs, and provider payloads pass through `SessionKeyStore.redact_secrets()`, automatically masking Google API keys and credentials.
4. **Bring Your Own Key (BYOK)**:
   - Users provide their own Google Gemini API key.
   - Keys entered via the UI are held exclusively in-memory in React state and transmitted per-request via the `X-Session-Gemini-Key` header.
   - Keys are **never** persisted to `localStorage`, cookies, SQLite databases, `.env` files, or log outputs.
5. **Sandbox Isolation & Docker Feasibility**:
   - The backend runs a 3-way check (`cli_available`, `daemon_responsive`, `image_available`).
   - Untrusted user repositories require Docker container execution to prevent unauthorized host code execution. If Docker is unavailable, PatchPilot refuses arbitrary code execution with HTTP 412 `SANDBOX_UNAVAILABLE`.
   - Bundled demo fixtures are verified via a restricted runner that scrubs environment variables.
6. **Execution Limits**: Process runners enforce strict execution limits: 30-second targeted test timeout, 60-second regression test timeout, and a 64KB capped output buffer to prevent hangs and denial-of-service from runaway tests.

---

## Prerequisites

- **Python**: Version 3.11 or 3.12
- **Node.js**: Version 18, 20, or 22
- **npm**: Version 9 or 10
- **Docker Desktop** *(Optional, recommended for arbitrary user repositories)*: Required for running tests on untrusted third-party code.
- **Google Gemini API Key** *(Optional for demo mode)*: Free or paid key from [Google AI Studio](https://aistudio.google.com/).

---

## Quickstart & Local Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/patchpilot.git
cd patchpilot
```

### 2. Set Up the Backend Environment

```bash
cd backend

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Set Up the Frontend Environment

```bash
cd ../frontend

# Install Node dependencies
npm install
```

---

## Running PatchPilot Locally

### Starting the Backend

From the `backend` directory (with virtual environment activated):

```bash
uvicorn patchpilot.main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at `http://127.0.0.1:8000`. You can explore the interactive OpenAPI documentation at `http://127.0.0.1:8000/docs`.

### Starting the Frontend Web App

From the `frontend` directory:

```bash
npm run dev
```

Open your browser at `http://localhost:5173`.

### Starting the Electron Desktop App

To run PatchPilot as a native desktop application with local directory picker integration:

From the `frontend` directory:

```bash
npm run desktop
```

---

## Configuration & Environment Variables

Copy `.env.example` to `.env` to configure optional server settings:

```bash
cp .env.example .env
```

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PATCHPILOT_HOST` | `127.0.0.1` | Loopback IP address for backend binding. |
| `PATCHPILOT_PORT` | `8000` | Port for the backend API. |
| `PATCHPILOT_DB_PATH` | `backend/patchpilot.db` | Path to the local SQLite database. |
| `GEMINI_API_KEY` | *(empty)* | Optional default API key. Can also be set in-memory via UI dialog. |
| `GEMINI_MODEL` | `gemini-1.5-flash` | Default Gemini model candidate (`gemini-1.5-flash`, `gemini-1.5-pro`, `gemini-2.0-flash`). |
| `GEMINI_API_BASE_URL` | `https://generativelanguage.googleapis.com` | Base URL for Google AI Gemini API. |
| `PATCHPILOT_TARGET_TIMEOUT` | `30` | Timeout in seconds for targeted reproduction test execution. |
| `PATCHPILOT_REGRESSION_TIMEOUT` | `60` | Timeout in seconds for regression test suite execution. |
| `PATCHPILOT_OUTPUT_MAX_BYTES` | `65536` | Maximum capture buffer (64KB) for test output logs. |

---

## Running the Verification Test Suites

### Backend Test Suite (Pytest)

The backend test suite includes 125 tests covering API contracts, repair orchestration, sandbox feasibility, path traversal guards, secret redaction, and end-to-end repair scenarios.

```bash
cd backend
python -m pytest -v
```

*All automated tests execute offline using deterministic test stubs and never consume live Gemini API credits.*

### Frontend Test Suite (Vitest)

The frontend test suite validates IPC handlers, API clients, session key state handling, model utilities, and directory validation:

```bash
cd frontend
npm test -- --run
```

### TypeScript Type Checking & Production Build

Verify strict TypeScript compilation and test the production bundle build:

```bash
cd frontend

# TypeScript type check
npm run typecheck

# Production Vite bundle build
npm run build
```

---

## Project Status & Roadmap

### Current Status: Phase 2.1 Complete
- [x] Modular Monolith API with loopback security and structured error envelopes.
- [x] Three bundled reproduction scenarios (Calculator boundary, Parser escaping, Tax regression).
- [x] Gemini 1.5/2.0 BYOK integration with in-memory key confinement.
- [x] Static AST scanner and autonomous bug discovery engine.
- [x] Bounded regression recovery engine.
- [x] Human approval gate with interactive diffs and automatic `.bak` backups.
- [x] Electron desktop wrapper with context-isolated IPC.

### Roadmap
- [ ] Language Server Protocol (LSP) integration for enhanced type-aware AST inspection.
- [ ] Multi-file patch orchestration for cross-module architectural refactoring.
- [ ] Support for additional model providers (Anthropic Claude, Ollama local models).
- [ ] Pre-configured devcontainer definitions for zero-install evaluation.

---

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork and branch**: Create a descriptive feature branch (`feature/your-feature-name` or `fix/issue-description`).
2. **Local testing**: Ensure all backend tests (`pytest`), frontend tests (`vitest`), and typechecks (`tsc --noEmit`) pass cleanly.
3. **Security first**: Never hardcode API keys, credentials, or private keys into test files or documentation.
4. **Pull request**: Open a Pull Request with a clear description of changes, test coverage, and rationale.

---

## Responsible Security Disclosure

If you discover a security vulnerability within PatchPilot, please review our [Security Policy](docs/SECURITY.md) and report it responsibly rather than opening a public issue.

---

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
