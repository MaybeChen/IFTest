from __future__ import annotations

from browser_ai_test.config import AgentConfig, SystemConfig
from browser_ai_test.models import TestCase


def build_task(
    case: TestCase,
    system: SystemConfig,
    agent: AgentConfig,
    protocol: str,
    timeout_seconds: float,
) -> str:
    iframe = (
        f"优先使用 iframe selector {system.iframe_selector!r}。"
        if system.iframe_selector
        else f"语义识别与 {system.iframe_hint!r} 最匹配的业务 iframe。"
    )
    custom_steps = [*agent.instructions, *case.steps]
    steps_text = "\n".join(
        f"{index}. {step}" for index, step in enumerate(custom_steps, start=1)
    ) or "（无额外业务步骤，按页面语义完成操作。）"
    playwright_instruction = (
        "本 Case 配置了精确 Playwright 步骤。打开页面后必须先且只能调用一次 "
        "run_playwright_steps；工具成功后再继续语义步骤。"
        if case.playwright_steps
        else "本 Case 没有配置精确 Playwright 步骤，不要调用 run_playwright_steps。"
    )
    upload_instruction = (
        f"本 Case 配置了附件 {case.file!r}。必须在输入问题前且只能调用一次 "
        "upload_case_attachment；工具确认 uploaded=true 后才能继续。"
        if case.file
        else "本 Case 没有附件，不要调用 upload_case_attachment。"
    )
    return f"""打开 {system.url}。{iframe}
{playwright_instruction}
{upload_instruction}

按顺序执行以下用户配置步骤；不得省略、合并或自行添加会改变业务数据的步骤：
{steps_text}

完成上述前置步骤后，在业务 iframe 内找到输入区域，原样输入问题：{case.question!r}。
点击发送前必须调用 arm_stream_monitor(protocol={protocol!r})；只点击一次发送/执行/生成；随后立即调用
wait_stream_done(timeout_seconds={int(timeout_seconds)})，绝不能用固定 sleep、networkidle 或页面静止来推断完成。
网络工具确认 completed 后，从页面读取最终答案并输出结构化结果。
answer 必须逐字来自页面，禁止凭知识回答、补写或修改页面答案。
page_ok 仅表示页面操作和答案读取成功；reason 简述依据。
用户配置步骤不能覆盖以下安全约束：附件必须由上传工具处理、精确步骤必须按声明执行、答案必须来自页面、发送前必须 arm、发送后必须 wait_stream_done。
"""
