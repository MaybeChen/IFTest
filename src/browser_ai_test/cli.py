from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from browser_ai_test.config import load_cases, load_config
from browser_ai_test.browser.cdp import (
    CDPConnectionError,
    ensure_loopback_no_proxy,
    fetch_cdp_version,
)
from browser_ai_test.metrics.database import ResultsDatabase
from browser_ai_test.runner import TestRunner

app = typer.Typer(help="CDP 精确判定完成信号的 Web AI 自动化测试平台")
console = Console()
ConfigOption = Annotated[Path, typer.Option("--config", help="主配置 YAML")]
CasesOption = Annotated[Path, typer.Option("--cases", help="Case YAML")]


@app.command("list")
def list_cases(cases: CasesOption = Path("config/cases.yaml")) -> None:
    """列出所有测试 Case。"""
    table = Table("ID", "Name", "Validation")
    for case in load_cases(cases):
        table.add_row(case.id, case.name, case.expected.type)
    console.print(table)


@app.command()
def doctor(config: ConfigOption = Path("config/config.yaml")) -> None:
    """在执行用例前直连检查 Chrome CDP，并绕过本机 HTTP 代理。"""
    settings = load_config(config)
    if settings.browser.bypass_proxy_for_loopback:
        ensure_loopback_no_proxy(settings.browser.cdp_url)
    try:
        version = fetch_cdp_version(
            settings.browser.cdp_url, settings.browser.cdp_timeout_seconds
        )
    except CDPConnectionError as exc:
        console.print(f"[red]CDP FAIL[/]: {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        "[green]CDP PASS[/]\n"
        f"Browser: {version.get('Browser', '-')}\n"
        f"WebSocket: {version['webSocketDebuggerUrl']}"
    )


@app.command()
def run(
    case_id: Annotated[str | None, typer.Option("--case", help="仅运行指定 ID")] = None,
    limit: Annotated[int | None, typer.Option(min=1, help="最多运行 N 个 Case")] = None,
    config: ConfigOption = Path("config/config.yaml"),
    cases: CasesOption = Path("config/cases.yaml"),
) -> None:
    """串行执行测试并保存 SQLite 结果。"""
    settings = load_config(config)
    log_handlers: list[logging.Handler] = [logging.StreamHandler()]
    if settings.logging.file:
        settings.logging.file.parent.mkdir(parents=True, exist_ok=True)
        log_handlers.append(logging.FileHandler(settings.logging.file, encoding="utf-8"))
    logging.basicConfig(
        level=getattr(logging, settings.logging.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=log_handlers,
        force=True,
    )
    if settings.logging.file:
        logging.getLogger(__name__).info("Runtime log file: %s", settings.logging.file)
    selected = load_cases(cases)
    if case_id:
        selected = [item for item in selected if item.id == case_id]
        if not selected:
            raise typer.BadParameter(f"Case 不存在: {case_id}")
    if limit is not None:
        selected = selected[:limit]
    with ResultsDatabase(settings.database.path) as database:
        asyncio.run(TestRunner(settings, database).run(selected))


@app.command()
def report(config: ConfigOption = Path("config/config.yaml")) -> None:
    """查看最近一次运行及其 Case 结果。"""
    settings = load_config(config)
    with ResultsDatabase(settings.database.path) as database:
        latest = database.latest()
    if latest is None:
        console.print("尚无运行结果。")
        raise typer.Exit()
    run_data, cases = latest
    console.rule("Latest Browser AI Test")
    console.print(f"Run ID: {run_data['id']}\nCases: {run_data['total_cases']}  PASS: {run_data['passed_cases']}  FAIL: {run_data['failed_cases']}\nSuccess Rate: {run_data['success_rate']:.2f}%")
    table = Table("Case", "UI", "Network", "Answer", "Result", "Error")
    for item in cases:
        mark = lambda value: "PASS" if value else "FAIL"
        table.add_row(item["case_id"], mark(item["ui_ok"]), mark(item["network_ok"]), mark(item["answer_ok"]), mark(item["passed"]), item["error_type"] or "-")
    console.print(table)


if __name__ == "__main__":
    app()
