from datetime import datetime, timezone

from browser_ai_test.metrics.database import ResultsDatabase
from browser_ai_test.models import CaseResult


def test_database_roundtrip(tmp_path):
    db = ResultsDatabase(tmp_path / "result.db")
    db.start_run("run", datetime.now(timezone.utc).isoformat())
    result = CaseResult(run_id="run", case_id="c", case_name="case", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc), passed=True, agent_ok=True, network_ok=True, answer_ok=True, question="q", answer="a")
    db.save_case(result); db.finish_run("run", datetime.now(timezone.utc).isoformat(), 1, 1)
    run, cases = db.latest()
    assert run["passed_cases"] == 1 and cases[0]["answer"] == "a"
    db.close()
