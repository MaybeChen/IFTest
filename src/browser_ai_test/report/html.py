from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from browser_ai_test.models import CaseResult


def write_html_report(
    run_id: str,
    results: list[CaseResult],
    statistics: dict[str, Any],
    directory: Path,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.html"
    rows = "".join(
        "<tr>"
        f"<td>{escape(item.case_id)}</td><td>{escape(item.case_name)}</td>"
        f"<td class='{_status(item.passed)}'>{_label(item.passed)}</td>"
        f"<td>{_label(item.ui_ok)}</td><td>{_label(item.network_ok)}</td>"
        f"<td>{_label(item.answer_ok)}</td><td>{_number(item.ttft_ms)}</td>"
        f"<td>{_number(item.stream_total_ms)}</td>"
        f"<td>{escape(item.answer)}</td>"
        f"<td>{escape(item.error_type.value if item.error_type else '')}</td>"
        f"<td>{escape(item.error_detail or '')}</td></tr>"
        for item in results
    )
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Browser AI Test {escape(run_id)}</title><style>
body{{font-family:Arial,sans-serif;margin:24px;color:#222}}.cards{{display:flex;gap:12px}}
.card{{padding:12px 18px;background:#f3f5f7;border-radius:8px}}table{{border-collapse:collapse;width:100%;margin-top:20px}}
th,td{{border:1px solid #ddd;padding:8px;vertical-align:top}}th{{background:#f3f5f7}}.pass{{color:#087f23;font-weight:bold}}.fail{{color:#c62828;font-weight:bold}}
</style></head><body><h1>Browser AI Test</h1><p>Run ID: {escape(run_id)}</p>
<div class="cards"><div class="card">Total: {statistics['total']}</div>
<div class="card pass">PASS: {statistics['passed']}</div><div class="card fail">FAIL: {statistics['failed']}</div>
<div class="card">Success: {statistics['success_rate']:.2f}%</div></div>
<p>UI: {statistics['ui_success_rate']:.2f}% · Network: {statistics['network_success_rate']:.2f}% · Answer: {statistics['answer_success_rate']:.2f}%</p>
<table><thead><tr><th>Case</th><th>Name</th><th>Result</th><th>UI</th><th>Network</th><th>Answer</th><th>TTFT ms</th><th>Stream ms</th><th>Page Answer</th><th>Error</th><th>Detail</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path


def _label(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _status(value: bool) -> str:
    return "pass" if value else "fail"


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"
