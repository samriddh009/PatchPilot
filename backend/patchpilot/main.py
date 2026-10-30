"""FastAPI entrypoint for PatchPilot modular monolith."""

from contextlib import asynccontextmanager
from typing import Any, Dict
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from patchpilot import config
from patchpilot.api.router_health import router as health_router
from patchpilot.api.router_provider import router as provider_router
from patchpilot.api.router_repairs import router as repairs_router
from patchpilot.api.router_repositories import router as repositories_router
from patchpilot.gemini.session_store import SessionKeyStore
from patchpilot.schemas.common import utc_now_iso
from patchpilot.schemas.enums import Language, TestFramework
from patchpilot.storage.database import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: reconcile interrupted repairs and seed default fixtures."""
    # 1. Reconcile stale in-flight repairs from previous session / crash
    db.reconcile_stale_repairs()

    # 2. Register fixtures if present on disk
    fixtures_dir = config.WORKSPACE_ROOT / "fixtures"
    if fixtures_dir.exists():
        calc_bug = fixtures_dir / "python_calc_bug"
        if calc_bug.exists():
            db.register_repository(
                repo_id="repo_py_calc_01",
                name="python_calc_bug",
                root_path=str(calc_bug),
                language=Language.PYTHON,
                test_framework=TestFramework.PYTEST,
                is_fixture=True,
            )
        parser_bug = fixtures_dir / "python_parser_bug"
        if parser_bug.exists():
            db.register_repository(
                repo_id="repo_py_parser_01",
                name="python_parser_bug",
                root_path=str(parser_bug),
                language=Language.PYTHON,
                test_framework=TestFramework.PYTEST,
                is_fixture=True,
            )
        regr_bug = fixtures_dir / "python_regression_fixture"
        if regr_bug.exists():
            db.register_repository(
                repo_id="repo_py_regr_01",
                name="python_regression_fixture",
                root_path=str(regr_bug),
                language=Language.PYTHON,
                test_framework=TestFramework.PYTEST,
                is_fixture=True,
            )
    yield


app = FastAPI(
    title="PatchPilot API",
    description="AI Software Delivery Agent REST API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 1. Enforce narrow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# 2. Loopback Host Header Validation Middleware
@app.middleware("http")
async def validate_host_and_sanitize(request: Request, call_next):
    host_header = request.headers.get("host", "").lower()
    # Permit local test client / loopback
    if host_header and not any(allowed in host_header for allowed in ["127.0.0.1", "localhost", "testserver"]):
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "FORBIDDEN_ORIGIN",
                    "message": f"Host '{host_header}' is unauthorized. Loopback binding strictly enforced.",
                    "details": {},
                    "timestamp": utc_now_iso(),
                }
            },
        )

    response = await call_next(request)
    return response


# 3. Standard Custom API Error Format Handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Format HTTPException into PatchPilot standard error envelope."""
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", "ERROR")
        message = exc.detail.get("message", "An error occurred.")
        raw_details = exc.detail.get("details")
        details = dict(raw_details) if isinstance(raw_details, dict) else {}
        # Preserve all extra top-level keys like available_models in details
        for k, v in exc.detail.items():
            if k not in ("code", "message", "details"):
                details[k] = v
    else:
        code = "HTTP_ERROR"
        message = str(exc.detail)
        details = {}

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": SessionKeyStore.redact_secrets(message),
                "details": details,
                "timestamp": utc_now_iso(),
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Format Pydantic schema validation errors into standard error envelope with actionable field-level messages."""
    errors = exc.errors()
    field_messages = []
    sanitized_errors = []
    for err in errors:
        loc = err.get("loc", [])
        field = ".".join(str(part) for part in loc if part != "body") or "payload"
        msg = err.get("msg", "Invalid value")
        field_messages.append(f"{field}: {msg}")
        sanitized_errors.append({
            "field": field,
            "message": SessionKeyStore.redact_secrets(msg),
            "type": err.get("type", "value_error"),
        })

    summary = f"Validation failed: {', '.join(field_messages)}" if field_messages else "Request payload failed schema validation."
    sanitized_summary = SessionKeyStore.redact_secrets(summary)

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": sanitized_summary,
                "details": {"errors": sanitized_errors},
                "timestamp": utc_now_iso(),
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all unhandled exception handler with secret redaction."""
    sanitized = SessionKeyStore.redact_secrets(str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {sanitized}",
                "details": {},
                "timestamp": utc_now_iso(),
            }
        },
    )


# Include Routers under /api/v1
API_V1_PREFIX = "/api/v1"
app.include_router(health_router, prefix=API_V1_PREFIX)
app.include_router(provider_router, prefix=API_V1_PREFIX)
app.include_router(repositories_router, prefix=API_V1_PREFIX)
app.include_router(repairs_router, prefix=API_V1_PREFIX)


@app.get("/health", tags=["Health"])
async def root_health():
    """Root health check for desktop readiness polling."""
    return {"status": "healthy", "service": "patchpilot"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("patchpilot.main:app", host=config.HOST, port=config.PORT, reload=True)
