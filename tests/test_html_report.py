from datetime import datetime, timezone

from browser_ai_test.metrics.statistics import calculate_statistics
from browser_ai_test.models import CaseResult
from browser_ai_test.report.html import write_html_report


def test_html_report_contains_summary_and_escapes_page_content(tmp_path):
    result = CaseResult(
        run_id="run", case_id="C1", case_name="文件问答", started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc), passed=True, agent_ok=True, network_ok=True,
        answer_ok=True, question="q", answer="<script>alert(1)</script>", ttft_ms=10,
        stream_total_ms=20,
    )
    path = write_html_report("run", [result], calculate_statistics([result]), tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "Browser AI Test" in content and "C1" in content and "PASS" in content
    assert "&lt;script&gt;" in content and "<script>alert" not in content
