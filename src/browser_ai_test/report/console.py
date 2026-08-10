from __future__ import annotations

from typing import Any
from rich.console import Console
from rich.table import Table

from browser_ai_test.models import CaseResult

console = Console()


def render_case(result: CaseResult, index: int, total: int) -> None:
    status = lambda value: "[green]PASS[/]" if value else "[red]FAIL[/]"
    table = Table(title=f"[{index}/{total}] {result.case_id} — {result.case_name}")
    table.add_column("Agent"); table.add_column("Network"); table.add_column("Answer")
    table.add_column("TTFT"); table.add_column("Stream"); table.add_column("Result")
    table.add_row(status(result.agent_ok), status(result.network_ok), status(result.answer_ok),
                  f"{result.ttft_ms:.0f} ms" if result.ttft_ms is not None else "-",
                  f"{result.stream_total_ms:.0f} ms" if result.stream_total_ms is not None else "-",
                  status(result.passed))
    console.print(table)
    if result.error_type:
        console.print(f"[red]Error: {result.error_type.value}[/]\nDetail: {result.error_detail or '-'}")


def render_summary(run_id: str, stats: dict[str, Any]) -> None:
    console.rule("Browser AI Test")
    console.print(f"Run ID: {run_id}\nCases: {stats['total']}  PASS: {stats['passed']}  FAIL: {stats['failed']}")
    console.print(f"Success Rate: {stats['success_rate']:.2f}%")
    console.print(f"Agent Success: {stats['agent_success_rate']:.2f}%  Network Success: {stats['network_success_rate']:.2f}%  Answer Success: {stats['answer_success_rate']:.2f}%")
    for title, key, divisor, unit in (("TTFT", "ttft", 1, "ms"), ("Stream Total", "stream", 1000, "s")):
        values = [f"AVG {stats[f'{key}_avg'] / divisor:.2f} {unit}" if stats[f"{key}_avg"] is not None else "AVG -"]
        values += [f"P{p} {stats[f'{key}_p{p}'] / divisor:.2f} {unit}" if stats[f"{key}_p{p}"] is not None else f"P{p} -" for p in (50, 90, 95, 99)]
        console.print(f"\n[bold]{title}[/]\n" + "  ".join(values))
    if stats.get("errors"):
        console.print("\n[bold]Errors[/]")
        for error, count in stats["errors"].items(): console.print(f"{error:<28} {count}")
    console.rule()
