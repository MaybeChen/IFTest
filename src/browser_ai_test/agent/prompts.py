from __future__ import annotations

from browser_ai_test.config import SystemConfig
from browser_ai_test.models import TestCase


def build_task(case: TestCase, system: SystemConfig, protocol: str, timeout_seconds: float) -> str:
    iframe = (
        f"优先使用 iframe selector {system.iframe_selector!r}。"
        if system.iframe_selector
        else f"语义识别与 {system.iframe_hint!r} 最匹配的业务 iframe。"
    )
    return f"""打开 {system.url}。{iframe}
在业务 iframe 内找到输入区域，原样输入问题：{case.question!r}。
点击发送前必须调用 arm_stream_monitor(protocol={protocol!r})；只点击一次发送/执行/生成；随后立即调用
wait_stream_done(timeout_seconds={int(timeout_seconds)})，绝不能用固定 sleep、networkidle 或页面静止来推断完成。
网络工具确认 completed 后，从页面读取最终答案并输出结构化结果。
answer 必须逐字来自页面，禁止凭知识回答、补写或修改页面答案。
page_ok 仅表示页面操作和答案读取成功；reason 简述依据。
"""
