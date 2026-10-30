"""SQLite storage layer for PatchPilot metadata, repairs, and audit events."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from patchpilot import config
from patchpilot.schemas.enums import (
    AuditEventType,
    FailureClassification,
    Language,
    RepairStatus,
    TestFramework,
    VerificationOutcome,
)
from patchpilot.schemas.common import utc_now_iso


class Database:
    """Thread-safe SQLite database manager for local metadata persistence."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.DATABASE_PATH
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection with row factories and foreign keys."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _init_db(self) -> None:
        """Initialize database tables according to the approved architecture schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.get_connection() as conn:
            conn.executescript(
                """
                -- Repositories registered for local repair inspection
                CREATE TABLE IF NOT EXISTS repositories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    root_path TEXT NOT NULL UNIQUE,
                    language TEXT NOT NULL,
                    test_framework TEXT NOT NULL,
                    is_fixture INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                -- Repair jobs execution state
                CREATE TABLE IF NOT EXISTS repairs (
                    id TEXT PRIMARY KEY,
                    repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                    bug_report TEXT NOT NULL,
                    test_target TEXT,
                    status TEXT NOT NULL,
                    recovery_attempts INTEGER NOT NULL DEFAULT 0,
                    baseline_passed INTEGER,
                    baseline_failure_classification TEXT,
                    targeted_passed INTEGER,
                    regression_passed INTEGER,
                    diff_text TEXT,
                    error_message TEXT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );

                -- Append-only audit events for live polling and historical replay
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    repair_id TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
                    sequence_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(repair_id, sequence_id)
                );

                -- Formal verification records for evidence auditability
                CREATE TABLE IF NOT EXISTS verification_records (
                    id TEXT PRIMARY KEY,
                    repair_id TEXT NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
                    outcome TEXT NOT NULL,
                    baseline_exit_code INTEGER NOT NULL,
                    targeted_exit_code INTEGER NOT NULL,
                    regression_exit_code INTEGER NOT NULL,
                    execution_duration_ms INTEGER NOT NULL,
                    evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_repairs_repo ON repairs(repository_id);
                CREATE INDEX IF NOT EXISTS idx_audit_events_repair ON audit_events(repair_id, sequence_id);
                """
            )
            conn.commit()
            # Migration check: add is_fixture column if existing database lacked it
            try:
                conn.execute("ALTER TABLE repositories ADD COLUMN is_fixture INTEGER NOT NULL DEFAULT 0;")
                conn.commit()
            except sqlite3.OperationalError:
                pass
            conn.execute("UPDATE repositories SET is_fixture = 1 WHERE root_path LIKE '%fixtures%' OR id LIKE 'repo_py_%' OR id LIKE 'repo_ts_%' OR id LIKE 'repo_java_%';")
            conn.commit()

    # --- Repository Operations ---

    def register_repository(
        self,
        repo_id: str,
        name: str,
        root_path: str,
        language: Language,
        test_framework: TestFramework,
        is_fixture: bool = False,
    ) -> Dict[str, Any]:
        """Register or update a local repository."""
        now = utc_now_iso()
        lang_val = language.value if hasattr(language, "value") else str(language)
        fw_val = test_framework.value if hasattr(test_framework, "value") else str(test_framework)
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO repositories (id, name, root_path, language, test_framework, is_fixture, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    root_path=excluded.root_path,
                    language=excluded.language,
                    test_framework=excluded.test_framework,
                    is_fixture=excluded.is_fixture;
                """,
                (repo_id, name, str(root_path), lang_val, fw_val, int(is_fixture), now),
            )
            conn.commit()
        return self.get_repository(repo_id)  # type: ignore

    def get_repository(self, repo_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve repository metadata by ID or name (returns internal root_path)."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM repositories WHERE id = ? OR name = ?", (repo_id, repo_id))
            row = cur.fetchone()
            if row:
                return dict(row)
            return None

    def list_repositories(self) -> List[Dict[str, Any]]:
        """List all registered repositories."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM repositories ORDER BY created_at ASC")
            return [dict(row) for row in cur.fetchall()]

    # --- Repair Operations ---

    def create_repair(
        self,
        repair_id: str,
        repository_id: str,
        bug_report: str,
        test_target: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert a newly queued repair job."""
        now = utc_now_iso()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO repairs (
                    id, repository_id, bug_report, test_target, status,
                    recovery_attempts, started_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (repair_id, repository_id, bug_report, test_target, RepairStatus.QUEUED.value, now),
            )
            conn.commit()
        return self.get_repair(repair_id)  # type: ignore

    def get_repair(self, repair_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve repair metadata by ID."""
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM repairs WHERE id = ?", (repair_id,))
            row = cur.fetchone()
            if row:
                d = dict(row)
                d["baseline_passed"] = bool(d["baseline_passed"]) if d["baseline_passed"] is not None else None
                d["targeted_passed"] = bool(d["targeted_passed"]) if d["targeted_passed"] is not None else None
                d["regression_passed"] = bool(d["regression_passed"]) if d["regression_passed"] is not None else None
                d["has_diff"] = bool(d.get("diff_text"))
                return d
            return None

    def get_active_repair_for_repo(self, repository_id: str) -> Optional[Dict[str, Any]]:
        """Find an in-flight (non-terminal) repair job for a repository."""
        terminal_statuses = (
            RepairStatus.VERIFIED.value,
            RepairStatus.UNRESOLVED.value,
            RepairStatus.FAILED.value,
            RepairStatus.CANCELLED.value,
        )
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM repairs
                WHERE repository_id = ? AND status NOT IN (?, ?, ?, ?)
                ORDER BY started_at DESC LIMIT 1
                """,
                (repository_id, *terminal_statuses),
            )
            row = cur.fetchone()
            if row:
                d = dict(row)
                d["baseline_passed"] = bool(d["baseline_passed"]) if d["baseline_passed"] is not None else None
                d["targeted_passed"] = bool(d["targeted_passed"]) if d["targeted_passed"] is not None else None
                d["regression_passed"] = bool(d["regression_passed"]) if d["regression_passed"] is not None else None
                d["has_diff"] = bool(d.get("diff_text"))
                return d
            return None

    def update_repair(
        self,
        repair_id: str,
        status: Optional[RepairStatus] = None,
        recovery_attempts: Optional[int] = None,
        baseline_passed: Optional[bool] = None,
        baseline_failure_classification: Optional[FailureClassification] = None,
        targeted_passed: Optional[bool] = None,
        regression_passed: Optional[bool] = None,
        diff_text: Optional[str] = None,
        test_target: Optional[str] = None,
        error_message: Optional[str] = None,
        completed: bool = False,
    ) -> None:
        """Update active repair job state."""
        updates = []
        params = []

        if status is not None:
            updates.append("status = ?")
            params.append(status.value)
        if recovery_attempts is not None:
            updates.append("recovery_attempts = ?")
            params.append(recovery_attempts)
        if baseline_passed is not None:
            updates.append("baseline_passed = ?")
            params.append(1 if baseline_passed else 0)
        if baseline_failure_classification is not None:
            updates.append("baseline_failure_classification = ?")
            params.append(baseline_failure_classification.value)
        if targeted_passed is not None:
            updates.append("targeted_passed = ?")
            params.append(1 if targeted_passed else 0)
        if regression_passed is not None:
            updates.append("regression_passed = ?")
            params.append(1 if regression_passed else 0)
        if diff_text is not None:
            updates.append("diff_text = ?")
            params.append(diff_text)
        if test_target is not None:
            updates.append("test_target = ?")
            params.append(test_target)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)
        if completed:
            updates.append("completed_at = ?")
            params.append(utc_now_iso())

        if not updates:
            return

        params.append(repair_id)
        query = f"UPDATE repairs SET {', '.join(updates)} WHERE id = ?"

        with self.get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    # --- Audit Event Operations ---

    def record_audit_event(
        self,
        event_id: str,
        repair_id: str,
        event_type: AuditEventType,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Atomically record an audit event with sequential ordering."""
        now = utc_now_iso()
        with self.get_connection() as conn:
            # Determine next sequence_id atomically
            cur = conn.execute(
                "SELECT COALESCE(MAX(sequence_id), 0) + 1 FROM audit_events WHERE repair_id = ?",
                (repair_id,),
            )
            next_seq = cur.fetchone()[0]

            conn.execute(
                """
                INSERT INTO audit_events (id, repair_id, sequence_id, event_type, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (event_id, repair_id, next_seq, event_type.value, json.dumps(payload), now),
            )
            conn.commit()

        return {
            "id": event_id,
            "sequence_id": next_seq,
            "event_type": event_type.value,
            "payload": payload,
            "created_at": now,
        }

    def get_audit_events(
        self,
        repair_id: str,
        since_seq: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Retrieve sequential audit events for a repair."""
        with self.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT id, sequence_id, event_type, payload, created_at
                FROM audit_events
                WHERE repair_id = ? AND sequence_id > ?
                ORDER BY sequence_id ASC
                LIMIT ?
                """,
                (repair_id, since_seq, limit),
            )
            results = []
            for row in cur.fetchall():
                results.append(
                    {
                        "id": row["id"],
                        "sequence_id": row["sequence_id"],
                        "event_type": row["event_type"],
                        "payload": json.loads(row["payload"]),
                        "created_at": row["created_at"],
                    }
                )
            return results

    # --- Verification Record Operations ---

    def record_verification(
        self,
        record_id: str,
        repair_id: str,
        outcome: VerificationOutcome,
        baseline_exit_code: int,
        targeted_exit_code: int,
        regression_exit_code: int,
        execution_duration_ms: int,
        evidence: Dict[str, Any],
    ) -> None:
        """Store immutable verification evidence."""
        now = utc_now_iso()
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO verification_records (
                    id, repair_id, outcome, baseline_exit_code, targeted_exit_code,
                    regression_exit_code, execution_duration_ms, evidence_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    repair_id,
                    outcome.value,
                    baseline_exit_code,
                    targeted_exit_code,
                    regression_exit_code,
                    execution_duration_ms,
                    json.dumps(evidence),
                    now,
                ),
            )
            conn.commit()

    def get_verification_record(self, repair_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve verification record by repair ID."""
        with self.get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM verification_records WHERE repair_id = ? ORDER BY created_at DESC LIMIT 1",
                (repair_id,),
            )
            row = cur.fetchone()
            if row:
                d = dict(row)
                d["evidence"] = json.loads(d["evidence_json"])
                return d
            return None

    def reconcile_stale_repairs(self) -> int:
        """
        Reconcile in-flight repairs that were interrupted by a crash or restart.
        Ensures jobs are not permanently stuck in non-terminal states.
        """
        terminal_statuses = (
            RepairStatus.VERIFIED.value,
            RepairStatus.UNRESOLVED.value,
            RepairStatus.FAILED.value,
            RepairStatus.CANCELLED.value,
            RepairStatus.AWAITING_APPROVAL.value,
        )
        placeholders = ",".join("?" for _ in terminal_statuses)
        now = utc_now_iso()
        with self.get_connection() as conn:
            cur = conn.execute(
                f"""
                UPDATE repairs
                SET status = ?, error_message = ?, completed_at = ?
                WHERE status NOT IN ({placeholders})
                """,
                (
                    RepairStatus.FAILED.value,
                    "Execution interrupted by application restart or process shutdown.",
                    now,
                    *terminal_statuses,
                ),
            )
            reconciled = cur.rowcount
            conn.commit()
            return reconciled


# Global singleton instance for backend
db = Database()
