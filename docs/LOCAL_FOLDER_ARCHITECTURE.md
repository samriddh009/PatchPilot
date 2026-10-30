# PatchPilot — User-Selected Local Repositories Design Specification

## 1. Architectural Overview & Browser Security Limitations

### 1.1 The Browser Sandbox Limitation
Standard W3C browser security specifications (HTML5 File API, WebKit Directory, File System Access API) strictly prohibit web pages from learning the absolute filesystem paths on the user's host machine:
- `<input type="file" webkitdirectory>` gives the browser read-access to file contents within the folder, but `file.path` is intentionally blank/suppressed by all modern browsers (Chrome, Edge, Firefox, Safari) to prevent local user directory disclosure.
- The W3C `window.showDirectoryPicker()` returns an in-memory `FileSystemDirectoryHandle` scoped to the web origin; it never exposes the host OS path (`C:\...` or `/home/...`).

### 1.2 Desktop Architecture, Web Progressive Enhancement, & Ingestion Strategy
To resolve this fundamental operating system security boundary without duplicating business logic, PatchPilot implements a **Unified Project Access Architecture** (`ProjectAccessService`):
1. **Desktop Shell Integration (`DesktopProjectAdapter`)**:
   - When launched as a desktop app via `npm run desktop` (Electron shell), the application uses `contextIsolation: true`, `nodeIntegration: false`, and `sandbox: true`.
   - The preload script (`frontend/electron/preload.cjs`) exposes a strictly scoped `window.desktopApi.openDirectory()`.
   - IPC handler in `main.cjs` validates the IPC sender (`event.senderFrame === mainWindow.webContents.mainFrame` and origin matches localhost/file), then calls the native Windows `dialog.showOpenDialog(mainWindow, { properties: ['openDirectory', 'dontAddToRecent'] })`.
   - The user selects any local directory visually using the standard Windows Explorer dialog.
   - The path is automatically registered via `POST /api/v1/repositories/open-local` with canonicalization and boundary verification.
2. **Web Progressive Enhancement & Ingestion (`WebProjectAdapter`)**:
   - When accessed directly in a web browser at `http://localhost:5173`, the UI uses progressive enhancement:
     - Uses `window.showDirectoryPicker()` when supported and permitted.
     - Automatically falls back to standard HTML `<input type="file" webkitdirectory>` where directory picker is unavailable.
     - Picker is triggered directly from a user click event (preserving the browser user activation token).
   - Reads relative paths and contents client-side, sanitizing paths and filtering binary files, dependency directories (`.git`, `node_modules`, `.venv`, etc.), and secret patterns (`.env*`, `*.pem`, `id_rsa`, `credentials.json`, etc.).
   - Displays selected folder name, file count, and detected language badges.
   - **Data Flow & Privacy Disclosure**: Explicitly discloses that selected source files are transferred to the local PatchPilot service, and if Gemini is enabled, relevant context will be sent to Google's Gemini API. Ingestion requires explicit user confirmation.
   - Transfers files to the backend via `POST /api/v1/repositories/ingest` with Pydantic payload constraints (max 1000 files, 2MB per file, 10MB total).
   - Backend normalizes paths, checks directory jailing in `tmp/web_ingested/repo_web_<hash>`, excludes secrets on server side as well, runs toolchain detector, and registers repository in DB.
3. **Manual Path Registration (Secondary Fallback)**:
   - For headless or CLI environments, a collapsible manual path entry input is available.
   - The backend canonicalizes the path, verifies safety, performs static toolchain detection, and registers the repository.

---

## 2. Security Boundaries & Safe Refusal Policy

### 2.1 Path Validation & Symlink Confinement
1. **Directory Existence**: Path must exist and be an actual directory (`p.is_dir()`).
2. **System Root & Sensitive Path Rejection**:
   - Windows: Rejects drive roots (`C:\`, `D:\`), `C:\Windows`, `C:\Program Files`, `C:\System Volume Information`.
   - POSIX: Rejects `/`, `/etc`, `/usr`, `/bin`, `/sbin`, `/var`, `/dev`, `/sys`, `/proc`.
3. **Symlink Escape Prevention**: If a path or subpath contains symlinks, their targets are canonicalized. Links pointing outside the designated repository root or into forbidden system directories are rejected.

### 2.2 Sensitive Files & Secret Exclusions
Both client-side `projectAccess.ts` and server-side `WorkspaceManager.is_secret_file` strictly exclude sensitive files:
- Environment configs: `.env`, `.env.*` (e.g., `.env.local`, `.env.production`)
- Private keys: `id_rsa`, `id_ed25519`, `id_ecdsa`, `*.pem`, `*.key`, `*.pkcs12`, `*.pfx`
- Credentials: `credentials.json`, `client_secret*.json`, `service-account*.json`, `token.json`, `auth.json`
- Keystores: `*.keystore`, `*.jks`
- Dependency & cache directories: `.git`, `.venv`, `venv`, `node_modules`, `target`, `build`, `dist`, `.gradle`, `__pycache__`
These files are never read, never copied to ephemeral workspaces, never transmitted over HTTP, and never passed to LLM context.

### 2.3 Adaptive Execution Policy & Docker Sandboxing
- Docker Desktop is supported and integrated for isolated user project execution.
- When Docker is available and the sandbox image (`patchpilot-sandbox:python-3.12`) is built:
  - User projects execute tests inside an unprivileged container with `--network none`, `--read-only`, non-root user (`1000:1000`), dropped capabilities, and memory/CPU limits.
- When Docker is unavailable or daemon is stopped:
  - PatchPilot keeps Mode A (Static Inspection, Source Explorer, AI Test Proposals, diff reviews) fully available.
  - PatchPilot refuses host execution of untrusted user code with HTTP 403 Forbidden (`SANDBOX_UNAVAILABLE`), protecting the developer's machine from arbitrary execution.
- The Restricted Process Runner remains authorized exclusively for bundled demonstration fixtures (`fixtures/**`).

### 2.4 Dependency Installation Policy
PatchPilot **never** executes `npm install`, `pip install`, `mvn dependency:resolve`, or any dependency managers. Repairs only execute pre-installed tools already available in the environment.

### 2.5 Source Code Immutability
All repair activities (patching, testing, verification) occur strictly inside ephemeral workspaces created in temporary directories. The user's original directory is strictly read-only.

---

## 3. Toolchain & Layout Detection Matrix

| Language | Recognized Markers / Source Evidence | Testing Frameworks Detected | Layout Status |
| :--- | :--- | :--- | :--- |
| **Python** | `pyproject.toml`, `requirements.txt`, `setup.py`, or `.py` source files | `pytest` (if config/tests exist) or `unknown` | `valid` (with tests) or `no_tests` |
| **TypeScript** | `tsconfig.json`, `package.json`, or `.ts`/`.tsx` source files | `vitest`, `jest` or `unknown` | `valid` (with tests) or `no_tests` |
| **JavaScript** | `package.json` or `.js`/`.mjs`/`.jsx` source files | `vitest`, `jest` or `unknown` | `valid` (with tests) or `no_tests` |
| **Java** | `pom.xml`, `build.gradle`, or `.java` source files | `maven_junit`, `gradle_junit` or `unknown` | `valid` (with tests) or `no_tests` |
| **Unknown** | Empty directory or no recognizable source files | `unknown` | `UNSUPPORTED_PROJECT_LAYOUT` error raised |

> [!NOTE]
> **No Tests Required for Registration:** A valid Python, JavaScript, TypeScript, or Java project is registered and inspectable even when no tests are present. It is assigned `layout_status: "no_tests"` and PatchPilot offers AI test proposal rather than rejecting the folder.

---

## 4. API Contract Extensions

### 4.1 `POST /api/v1/repositories/open-local`
- **Request**:
  ```json
  {
    "path": "C:\\path\\to\\project",
    "name": "optional-custom-name"
  }
  ```
- **Response (200 OK - Source-Only Project)**:
  ```json
  {
    "id": "repo_local_a1b2c3d4",
    "name": "project-name",
    "language": "python",
    "test_framework": "unknown",
    "layout_status": "no_tests",
    "file_count": 12,
    "test_targets": [],
    "is_fixture": false,
    "execution_allowed": false,
    "execution_warning": "No existing tests detected. PatchPilot can inspect source and propose focused tests. Execution blocked: Docker sandbox unavailable.",
    "created_at": "2026-10-13T02:00:00.000Z"
  }
  ```

### 4.2 `POST /api/v1/repositories/ingest`
- **Request**:
  ```json
  {
    "name": "my-project",
    "files": [
      { "path": "src/main.py", "content": "print('hello')" }
    ]
  }
  ```
- **Response (200 OK)**:
  ```json
  {
    "id": "repo_web_1ad38a92",
    "name": "my-project",
    "language": "python",
    "test_framework": "unknown",
    "layout_status": "no_tests",
    "file_count": 1,
    "test_targets": [],
    "is_fixture": false,
    "execution_allowed": false,
    "created_at": "2026-10-15T19:00:00.000Z"
  }
  ```

### 4.3 `GET /api/v1/repositories/{id}/file`
- Safely reads a jailed source file with line offset, limit, and syntax highlighting metadata.
- Excludes `.env*`, `.git`, `*.pem`, `*.key`, and blocks binary/oversized files.

### 4.4 `POST /api/v1/repositories/{id}/propose-test`
- Proposes a focused reproduction test based on the user's bug report without host code execution.
- Returns proposed test file path, code, and explanation with status `proposed`.

