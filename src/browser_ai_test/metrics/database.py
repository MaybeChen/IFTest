from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from browser_ai_test.models import CaseResult


class ResultsDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
          total_cases INTEGER NOT NULL DEFAULT 0, passed_cases INTEGER NOT NULL DEFAULT 0,
          failed_cases INTEGER NOT NULL DEFAULT 0, success_rate REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS case_results (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          case_id TEXT NOT NULL, case_name TEXT NOT NULL, started_at TEXT NOT NULL,
          finished_at TEXT NOT NULL, passed INTEGER NOT NULL, ui_ok INTEGER NOT NULL,
          network_ok INTEGER NOT NULL, answer_ok INTEGER NOT NULL, protocol TEXT,
          ttft_ms REAL, stream_total_ms REAL, workflow_total_seconds REAL,
          workflow_steps INTEGER NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
          error_type TEXT, error_detail TEXT, FOREIGN KEY(run_id) REFERENCES runs(id)
        );
        """)
        self._migrate_legacy_columns()
        self.connection.commit()

    def _migrate_legacy_columns(self) -> None:
        """Keep databases created by the former optional automation mode usable."""
        columns = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(case_results)").fetchall()
        }
        if "agent_ok" in columns and "ui_ok" not in columns:
            self.connection.execute(
                "ALTER TABLE case_results RENAME COLUMN agent_ok TO ui_ok"
            )
        if "agent_total_seconds" in columns and "workflow_total_seconds" not in columns:
            self.connection.execute(
                "ALTER TABLE case_results RENAME COLUMN agent_total_seconds TO workflow_total_seconds"
            )
        if "agent_steps" in columns and "workflow_steps" not in columns:
            self.connection.execute(
                "ALTER TABLE case_results RENAME COLUMN agent_steps TO workflow_steps"
            )

    def start_run(self, run_id: str, started_at: str) -> None:
        self.connection.execute("INSERT INTO runs(id, started_at) VALUES (?, ?)", (run_id, started_at))
        self.connection.commit()

    def save_case(self, result: CaseResult) -> None:
        self.connection.execute("""INSERT INTO case_results (
          run_id, case_id, case_name, started_at, finished_at, passed, ui_ok,
          network_ok, answer_ok, protocol, ttft_ms, stream_total_ms,
          workflow_total_seconds, workflow_steps, question, answer, error_type, error_detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            result.run_id, result.case_id, result.case_name, result.started_at.isoformat(),
            result.finished_at.isoformat(), result.passed, result.ui_ok, result.network_ok,
            result.answer_ok, result.protocol, result.ttft_ms, result.stream_total_ms,
            result.workflow_total_seconds, result.workflow_steps, result.question, result.answer,
            result.error_type.value if result.error_type else None, result.error_detail,
        ))
        self.connection.commit()

    def finish_run(self, run_id: str, finished_at: str, total: int, passed: int) -> None:
        rate = passed / total * 100 if total else 0.0
        self.connection.execute("""UPDATE runs SET finished_at=?, total_cases=?, passed_cases=?,
          failed_cases=?, success_rate=? WHERE id=?""", (finished_at, total, passed, total - passed, rate, run_id))
        self.connection.commit()

    def latest(self) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
        run = self.connection.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if run is None:
            return None
        cases = self.connection.execute("SELECT * FROM case_results WHERE run_id=? ORDER BY id", (run["id"],)).fetchall()
        return dict(run), [dict(item) for item in cases]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ResultsDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
