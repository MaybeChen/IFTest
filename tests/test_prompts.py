from browser_ai_test.agent.prompts import build_task
from browser_ai_test.config import AgentConfig, SystemConfig
from browser_ai_test.models import ExpectedConfig, PlaywrightStep, TestCase as CaseModel


def test_custom_steps_are_ordered_before_mandatory_network_steps():
    case = CaseModel(
        id="QA_CUSTOM",
        name="custom",
        question="页面实际问题",
        steps=["选择知识库", "切换详细模式"],
        expected=ExpectedConfig(type="keyword", values=["答案"]),
    )
    prompt = build_task(
        case,
        SystemConfig(url="https://example.test", iframe_selector="#business"),
        AgentConfig(instructions=["关闭欢迎弹窗"]),
        "websocket",
        45,
    )

    assert prompt.index("1. 关闭欢迎弹窗") < prompt.index("2. 选择知识库")
    assert prompt.index("2. 选择知识库") < prompt.index("3. 切换详细模式")
    assert prompt.index("3. 切换详细模式") < prompt.index("arm_stream_monitor")
    assert "protocol='websocket'" in prompt
    assert "timeout_seconds=45" in prompt
    assert "页面实际问题" in prompt


def test_prompt_keeps_mandatory_steps_when_no_custom_steps():
    case = CaseModel(
        id="QA_DEFAULT",
        name="default",
        question="question",
        expected=ExpectedConfig(type="regex", values=["answer"]),
    )
    prompt = build_task(
        case,
        SystemConfig(url="https://example.test"),
        AgentConfig(),
        "sse",
        120,
    )

    assert "无额外业务步骤" in prompt
    assert "只点击一次" in prompt
    assert "答案必须来自页面" in prompt
    assert "不要调用 run_playwright_steps" in prompt


def test_prompt_requires_upload_tool_before_question():
    case = CaseModel(
        id="QA_FILE", name="file", question="summarize",
        file="manual.pdf",
        expected=ExpectedConfig(type="keyword", values=["answer"]),
    )
    prompt = build_task(case, SystemConfig(url="https://example.test"), AgentConfig(), "sse", 60)
    assert "附件 'manual.pdf'" in prompt
    assert prompt.index("upload_case_attachment") < prompt.index("原样输入问题")


def test_prompt_requires_exact_step_tool_when_configured():
    case = CaseModel(
        id="QA_EXACT",
        name="exact",
        question="question",
        playwright_steps=[PlaywrightStep(action="click", selector="#menu")],
        expected=ExpectedConfig(type="keyword", values=["answer"]),
    )
    prompt = build_task(
        case,
        SystemConfig(url="https://example.test", iframe_selector="#frame"),
        AgentConfig(),
        "http",
        30,
    )
    assert "必须先且只能调用一次 run_playwright_steps" in prompt
