# Browser AI Test

面向 iframe 内 AI/长任务页面的串行自动化测试 MVP。**Browser Use 决定怎样操作页面，Playwright/CDP 精确确认后端任务何时完成，Validator 判断页面实际答案是否正确**。最终通过条件始终为 `agent_ok AND network_ok AND answer_ok`；不会让 LLM、`networkidle`、页面静止或固定 `sleep` 猜测业务结束。

## 架构

```text
YAML Cases -> TestRunner -> Browser Use Agent -> iframe 页面操作
                                  | custom tools
                                  v
                         StreamMonitor <- CDP Network events
                            SSE / WS / HTTP
                                  |
页面实际答案 -> Keyword/Regex Validator -> Metrics -> SQLite -> Rich Console
```

Runner 在一个外部 Chrome、一个 Browser Use `BrowserSession`、一个 Playwright context 和一个 case-scoped monitor 上串行执行。每个 Case 在发送前 reset/arm；超时和网络错误被记录而不会污染下一 Case。SQLite 接口和 metrics 层相互独立，方便后续替换 PostgreSQL、接入 Grafana/Prometheus 或多 Chrome worker。

## 环境与安装

要求 Python 3.12+。项目声明的 Browser Use 兼容系列为 `>=0.11,<0.12`；关键构造参数会进行运行时签名检查，以便 patch 版本 API 变化时给出明确错误，而不是悄悄启动第二个浏览器。当前受限构建环境未预装 browser-use，真实依赖安装和页面联调仍需在目标环境执行。

虚拟环境的激活目录取决于操作系统：Linux/macOS 使用 `.venv/bin`，Windows 使用
`.venv/Scripts`（Windows 文件系统通常不区分 `Scripts` 的大小写）。

**Linux / macOS（bash/zsh）**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python -m playwright install chromium
cp .env.example .env
```

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m playwright install chromium
Copy-Item .env.example .env
```

如果 PowerShell 当前进程禁止执行激活脚本，可只为当前终端放开后再激活：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**Windows CMD**

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m playwright install chromium
copy .env.example .env
```

激活并不是必须步骤。也可以始终显式调用虚拟环境中的 Python，例如 Windows
PowerShell 使用 `.\.venv\Scripts\python.exe -m pip install -e ".[test]"`，Linux/macOS
使用 `./.venv/bin/python -m pip install -e '.[test]'`。

在 `.env` 中配置所选 Browser Use 模型提供方所需的凭据。不要提交 `.env`。

## 模型配置（包括私有/自定义模型）

`llm.provider` 支持 `browser_use`、`openai`、`openai_compatible`、
`anthropic`、`google` 和 `custom`。Runner 在创建 Agent 前通过工厂构造一次模型并注入
`AgentExecutor`，不再在 Executor 内硬编码 `ChatBrowserUse`。

OpenAI-compatible 私有网关示例：

```yaml
llm:
  provider: openai_compatible
  model: "company-agent-model"
  base_url: "https://llm-gateway.example/v1"
  api_key_env: "CUSTOM_LLM_API_KEY"
  kwargs:
    temperature: 0
    max_retries: 3
```

```bash
export CUSTOM_LLM_API_KEY="..."
```

API Key 只通过 `api_key_env` 指定的环境变量读取，不应直接写入 YAML。若环境变量缺失，
Runner 会在打开浏览器执行 Case 前给出明确的模型配置错误。

如果模型不是 OpenAI-compatible，可提供自己的 Browser Use 模型适配器：

```yaml
llm:
  provider: custom
  class_path: "my_company.browser_models.PrivateChatModel"
  model: "private-v2"
  base_url: "http://model-service.internal"
  api_key_env: "PRIVATE_MODEL_TOKEN"
  kwargs:
    tenant: "qa"
    request_timeout: 90
```

`class_path` 必须指向一个可导入的类。该类需要实现当前 browser-use 版本要求的 Chat
Model 接口；工厂会把 `model`、`base_url`、从环境变量解析出的 `api_key` 以及 `kwargs`
传给构造函数。显式的 `model`/`base_url`/`api_key_env` 优先于 `kwargs` 中的同名值。

## 启动同一个 Chrome/CDP

Playwright 和 Browser Use 都连接 `browser.cdp_url`，不会各自启动浏览器。

**Linux**

```bash
google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/browser-ai-test
```

**macOS**

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 --user-data-dir=/tmp/browser-ai-test
```

**Windows PowerShell**

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 --user-data-dir="$env:TEMP\browser-ai-test"
```

Chrome 版本若要求远程调试来源限制，请按组织安全策略显式配置；不要将调试端口暴露到公网。

## 主配置

编辑 `config/config.yaml`：

- `system.url`：被测主系统 URL。
- `llm.provider` / `llm.model`：模型提供方和模型名；私有模型参见上一节。
- `llm.base_url` / `llm.api_key_env`：自定义网关和密钥环境变量名。
- `llm.class_path` / `llm.kwargs`：完全自定义模型适配器及其扩展参数。
- `system.iframe_selector`：可选；有值时 Agent 优先使用，空值时结合 `iframe_hint` 做语义识别，因而不是唯一硬编码定位方式。
- `stream.url_keywords`：目标业务请求 URL 的稳定片段。只有匹配项会被统计，页面其他网络请求不会干扰结果。
- `stream.done_markers`：SSE/WS payload 中代表业务完成的标记；任意一个命中即完成。
- `stream.protocol`：`sse`、`websocket`、`http` 或 `auto`。`auto` 依据 EventSource MIME/CDP 事件、WebSocket 创建事件和普通 HTTP 完成事件识别。
- `stream.timeout_seconds`：默认等待上限；Case 可覆盖。
- `database.path`：SQLite 位置，默认 `data/results.db`。
- `runner.case_interval_seconds`：仅控制 Case 间节奏，不参与业务完成判断。
- `logging.level`：`DEBUG`、`INFO`、`WARNING` 或 `ERROR`。

CDP timestamp 是 monotonic 值。TTFT 和 stream total 仅在 CDP timestamp 之间相减；Agent 总耗时独立使用 Python monotonic clock，不与 CDP 混算。

## 编写 Case

编辑 `config/cases.yaml`：

```yaml
cases:
  - id: QA_001
    name: 日本首都测试
    question: "日本的首都是哪里？"
    expected:
      type: keyword       # keyword 或 regex
      values: [东京]
      match_mode: all     # keyword 支持 all/any
    stream:
      protocol: sse       # 可覆盖全局协议
    timeout_seconds: 120
```

Keyword 默认要求全部关键词出现；Regex 要求全部模式匹配。`exact`、`json`、`llm_judge` 已为模型扩展预留类型，但 MVP 会对未实现策略明确报错。

## 执行与查看结果

```bash
browser-ai-test list
browser-ai-test run
browser-ai-test run --case QA_001
browser-ai-test run --limit 10
browser-ai-test report
# 也可：python -m browser_ai_test.cli run
```

结果写入 `data/results.db` 的 `runs` 与 `case_results` 表。SQL 写入和查询均参数化。控制台展示总体/UI/网络/答案成功率、TTFT 与 Stream 的 AVG/P50/P90/P95/P99，以及单一主错误分类和详细信息。

运行本地单元测试：

```bash
pytest
```

这些测试直接向 monitor handler 注入 mock CDP event，无需启动真实浏览器。

## 完成判定细节

- **SSE**：匹配请求后，`Network.eventSourceMessageReceived` 第一条业务消息形成 TTFT，payload 命中 done marker 才完成。
- **WebSocket**：匹配 `Network.webSocketCreated` 后检查 frame payload 的 done marker，**不等待 close**，因为 socket 可能被复用并长期打开。
- **HTTP**：匹配请求的 `Network.loadingFinished` 代表完成；`loadingFailed` 是明确网络失败。
- arm 会清空 event、request IDs、错误和所有时间点。timeout 抛出明确异常，不会 silently ignore。

## 常见问题

### 创建 `.venv` 后没有 `.venv/bin`，只有 `.venv/Scripts`

这是 Windows 的正常目录结构，不代表虚拟环境创建失败。PowerShell 执行
`.\.venv\Scripts\Activate.ps1`，CMD 执行 `.venv\Scripts\activate.bat`；不要在 Windows
上执行只适用于 Linux/macOS 的 `source .venv/bin/activate`。如果不想激活，可直接执行
`.\.venv\Scripts\python.exe -m browser_ai_test.cli list`。激活成功后，`python -c
"import sys; print(sys.executable)"` 应指向项目的 `.venv\Scripts\python.exe`。

### 没有检测到 SSE

检查真实请求 URL 是否命中 `url_keywords`，并在 `DEBUG` 日志与 DevTools Network 中确认它是否真是 EventSource。代理有时会把 SSE 改成 fetch streaming；此时 CDP 不产生 EventSource message，需依据实际协议配置 HTTP 或调整服务端完成信号方案。

### WebSocket 一直不关闭

这是正常的。本项目不等待 close，而等待 frame payload 命中 `done_markers`。请配置真实业务 completed 消息。

### iframe 跨域怎么办

Browser Use/Playwright 在浏览器自动化上下文中可以操作跨域 frame，不依赖页面 JavaScript 的同源访问。若有稳定 selector 请配置；否则提供清晰 `iframe_hint`。登录、CSP 或 frame 尚未加载仍可能造成 `PAGE_ERROR`。

### Agent 自己认为成功但 Case 失败

Agent history 不是最终通过依据。CDP 未确认完成、网络失败或页面实际答案未通过 Validator 时，Case 都会失败。Prompt 明确禁止 Agent 根据自身知识回答。

### 为什么不能用 `networkidle`？

AI 页面常有遥测、心跳和共享 WebSocket，网络可能永不 idle；反过来，业务尚未 completed 时也可能短暂无流量。它不是业务完成信号。

### 为什么不能固定 sleep？

固定等待既可能过早读取半成品，也浪费快速 Case 的时间。业务负载变化后不可复现。本项目只等待 CDP 业务事件；sleep 仅允许作为 Case 间限速。

## 当前边界与扩展

没有真实业务 URL、Chrome 会话和模型 API 凭据时，只能验证配置、模型工厂、Validator、统计、SQLite 和 CDP 状态机，不能声称验证了真实页面链路。接入时通常只需修改 `llm`、`system.url`、可选 `system.iframe_selector`、`stream.url_keywords`、`stream.done_markers`、`stream.protocol` 和 `config/cases.yaml`。

后续可在清晰边界上增加 PostgreSQL repository、Grafana/Prometheus exporter、HTML report、LLM Judge、截图/录像/trace、CI 和多浏览器 worker；MVP 刻意不并发共享 monitor。
