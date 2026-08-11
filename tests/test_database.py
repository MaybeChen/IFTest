from datetime import datetime, timezone
import sqlite3

from browser_ai_test.metrics.database import ResultsDatabase
from browser_ai_test.models import CaseResult


def test_database_roundtrip(tmp_path):
    db = ResultsDatabase(tmp_path / "result.db")
    db.start_run("run", datetime.now(timezone.utc).isoformat())
    result = CaseResult(run_id="run", case_id="c", case_name="case", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc), passed=True, ui_ok=True, network_ok=True, answer_ok=True, question="q", answer="a")
    db.save_case(result); db.finish_run("run", datetime.now(timezone.utc).isoformat(), 1, 1)
    run, cases = db.latest()
    assert run["passed_cases"] == 1 and cases[0]["answer"] == "a"
    db.close()


def test_database_migrates_legacy_result_columns(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.execute("""CREATE TABLE case_results (
      id INTEGER PRIMARY KEY, agent_ok INTEGER, agent_total_seconds REAL,
      agent_steps INTEGER
    )""")
    connection.commit(); connection.close()

    database = ResultsDatabase(path)
    columns = {
        row[1]
        for row in database.connection.execute("PRAGMA table_info(case_results)")
    }
    database.close()

    assert {"ui_ok", "workflow_total_seconds", "workflow_steps"} <= columns
    assert "agent_ok" not in columns
