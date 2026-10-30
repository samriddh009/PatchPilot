"""Pytest shared test fixtures and configuration."""

import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from patchpilot.config import WORKSPACE_ROOT
from patchpilot.main import app
from patchpilot.schemas.enums import Language, TestFramework
from patchpilot.storage.database import Database, db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Provide an isolated SQLite database for each test."""
    test_db_path = tmp_path / "test_patchpilot.db"
    db.db_path = test_db_path
    db._init_db()

    # Register standard test fixtures
    fixtures_dir = WORKSPACE_ROOT / "fixtures"
    if fixtures_dir.exists():
        calc_bug = fixtures_dir / "python_calc_bug"
        if calc_bug.exists():
            db.register_repository(
                repo_id="repo_py_calc_01",
                name="python_calc_bug",
                root_path=str(calc_bug),
                language=Language.PYTHON,
                test_framework=TestFramework.PYTEST,
            )
        parser_bug = fixtures_dir / "python_parser_bug"
        if parser_bug.exists():
            db.register_repository(
                repo_id="repo_py_parser_01",
                name="python_parser_bug",
                root_path=str(parser_bug),
                language=Language.PYTHON,
                test_framework=TestFramework.PYTEST,
            )
        regr_bug = fixtures_dir / "python_regression_fixture"
        if regr_bug.exists():
            db.register_repository(
                repo_id="repo_py_regr_01",
                name="python_regression_fixture",
                root_path=str(regr_bug),
                language=Language.PYTHON,
                test_framework=TestFramework.PYTEST,
            )

    yield test_db_path


@pytest.fixture
def client():
    """FastAPI TestClient with loopback host."""
    return TestClient(app, base_url="http://127.0.0.1:8000")
