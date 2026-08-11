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

## 快速使用流程

对于“上传一个文件，再输入问题”的问答场景，首次接入按下面 7 步完成：

1. **安装工程**：创建并激活 Python 3.12 虚拟环境，执行
   `python -m pip install -e ".[test]"`。
2. **准备模型凭据**：复制 `.env.example` 为 `.env`，填写所选模型的 API Key；在
   `config/config.yaml` 的 `llm` 中配置 provider、model 和可选 base URL。
3. **准备 Chrome**：使用 `--remote-debugging-port=9222` 启动外部 Chrome。Browser Use、
   Playwright 和 CDP 都连接这个 Chrome，不要另外启动浏览器。
4. **配置被测系统和网络完成信号**：修改 `system.url`、可选
   `system.iframe_selector`、`stream.protocol`、`stream.url_keywords` 和
   `stream.done_markers`。
5. **准备上传文件**：把文件放入 `upload.directory`；根据页面实际 file input 调整
   `upload.input_selector`，`target` 通常先使用 `auto`。
6. **编写 Case**：在 `config/cases.yaml` 中配置 `id`、`name`、`question`、相对文件名
   `file` 和标准答案 `expected`。不同 Case 通常只需要更换这几个字段。
7. **检查并运行**：先执行 `browser-ai-test list`，再执行
   `browser-ai-test run --case FILE_QA_001`；完成后用 `browser-ai-test report` 查看最近结果。

单个文件问答 Case 的运行时流程是：

```text
读取 YAML Case
  -> 检查 upload.directory/file
  -> 连接同一个 Chrome/CDP
  -> Browser Use 打开系统并识别业务 iframe
  -> Playwright set_input_files 上传附件
  -> Browser Use 原样输入 question
  -> arm_stream_monitor
  -> 只点击一次发送
  -> wait_stream_done 等待 CDP 业务完成信号
  -> Browser Use 从页面读取最终答案
  -> Validator 校验 expected
  -> 保存 SQLite 指标并输出控制台报告
```

最终结果不是由 Agent 单独决定。只有 `agent_ok`、`network_ok` 和 `answer_ok` 同时为真，
Case 才会 PASS。

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

## 定制 Browser Use 操作步骤

Browser Use 的步骤分成两层：

1. `config/config.yaml` 中的 `agent.instructions` 是所有 Case 共用的前置步骤，适合登录、
   选择租户、关闭公告等公共操作。
2. `config/cases.yaml` 中每个 Case 的 `steps` 只对该 Case 生效，适合切换业务模块、选择
   知识库或设置表单选项。

公共步骤示例：

```yaml
agent:
  max_steps: 120
  instructions:
    - 如果出现登录页，使用浏览器中已有的登录态继续，不要输入或猜测密码
    - 关闭欢迎弹窗
    - 从左侧菜单进入“智能问答”
```

Case 专属步骤示例：

```yaml
cases:
  - id: QA_KB_001
    name: 产品知识库测试
    question: "产品 A 的保修期是多久？"
    steps:
      - 在知识库下拉框选择“产品手册”
      - 将回答模式切换为“详细”
      - 确认输入框为空；如果不为空则先清空
    expected:
      type: keyword
      values: ["保修"]
```

最终 Prompt 会严格按“公共步骤在前、Case 步骤在后”的顺序编号，然后再追加框架不可覆盖
的操作：原样输入问题、调用 `arm_stream_monitor`、只点击一次发送、调用
`wait_stream_done`、从页面读取答案。自定义步骤不能要求跳过网络监听，也不能让 Agent
自己回答问题。

`agent.max_steps` 是 Browser Use 单个 Case 的最大操作步数，用于防止 Agent 在页面上
无限循环。它不是业务 timeout，流等待时间仍由 `stream.timeout_seconds` 或 Case 的
`timeout_seconds` 控制。

这里的 `instructions`/`steps` 是给 Browser Use 的语义步骤，Agent 会根据页面结构寻找
控件。如果必须保证精确 selector、固定参数或原子操作，应仿照
`src/browser_ai_test/agent/tools.py` 注册新的自定义 Tool，再在步骤中明确要求调用该 Tool；
不要期待自然语言步骤具有 Playwright 脚本一样的确定性。

### 配置精确 Playwright 步骤

需要提供详细 selector 的操作可以直接写在 Case 的 `playwright_steps` 中，不必为每个
Case 编写 Python。支持 `click`、`fill`、`select_option`、`check`、`press` 和
`wait_visible`：

```yaml
system:
  iframe_selector: "#business-frame"  # target=iframe 时必须配置
```

```yaml
cases:
  - id: QA_EXACT_001
    name: 精确页面操作
    question: "产品 A 的保修期是多久？"
    playwright_steps:
      - action: click
        target: main
        selector: "[data-testid='ai-menu']"
      - action: wait_visible
        target: iframe
        selector: "[data-testid='knowledge-base']"
        timeout_ms: 15000
      - action: select_option
        target: iframe
        selector: "[data-testid='knowledge-base']"
        value: "product-manual"
      - action: check
        target: iframe
        selector: "#detailed-mode"
```

当 Case 存在 `playwright_steps` 时，Browser Use 打开页面后会被要求调用一次
`run_playwright_steps` Tool。该 Tool 使用共享 Playwright Page 和同一个 Chrome/CDP，严格
按 YAML 顺序执行；任何 selector 超时或 action 失败都会返回明确错误，不会让 Agent 猜测
已经完成。`target: main` 定位主页面，`target: iframe` 使用
`system.iframe_selector` 进入 iframe。

建议分工如下：

- 页面结构稳定、必须可重复的点击/填写：使用 `playwright_steps`。
- 页面结构经常变化、需要视觉或语义理解：使用 `steps`。
- 提交 AI 问题和等待生成完成：仍由 Browser Use + StreamMonitor 的强制流程处理，避免
  Playwright 步骤绕过 `arm_stream_monitor`。

## “输入问题 + 上传文件”问答场景

这类 Case 不需要重复编写上传 selector 或详细步骤。上传目录和文件控件只在主配置中
定义一次，Case 通常只写问题、文件名和标准答案。

主配置：

```yaml
system:
  url: "https://your-system.example"
  iframe_selector: "#business-frame"  # 有稳定 selector 时建议配置

upload:
  directory: "D:/browser-ai-test-files"  # Windows 也可以写 D:\\qa-files
  input_selector: "input[type='file']"
  target: auto       # main / iframe / auto
  timeout_ms: 10000
```

最简 Case：

```yaml
cases:
  - id: FILE_QA_001
    name: 文档问答
    question: "请总结这份文件的主要内容"
    file: "产品说明书.pdf"
    expected:
      type: keyword
      values:
        - "产品功能"
        - "使用限制"
    stream:
      protocol: sse
    timeout_seconds: 120
```

执行时框架会：

1. 将 `upload.directory` 与 Case 的 `file` 安全拼接，并确认文件存在且没有通过 `..`
   越过指定目录；
2. 在主页面、配置 iframe 或自动发现的 frame 中定位 `upload.input_selector`；
3. 使用 Playwright `set_input_files()` 上传该文件；
4. 上传工具返回成功后，Browser Use 才会输入 `question`；
5. 发送前 arm StreamMonitor，发送后等待真实的 SSE/WS/HTTP 完成信号；
6. 从页面读取答案并与 `expected` 验证。

`file` 是相对于 `upload.directory` 的路径，也可以包含目录内的子目录，例如
`manuals/产品说明书.pdf`。出于安全和可复现性考虑，它不是任意绝对路径，也不允许
`../`。如果不同 Case 使用不同文件，只修改各 Case 的 `file` 即可。没有附件的 Case
设置 `file: null` 或省略该字段。

如果页面没有标准 `<input type="file">`，应在浏览器 DevTools 中找到真正的隐藏 file
input，并把 `upload.input_selector` 改为稳定 selector。Playwright 可以直接对隐藏 file
input 调用 `set_input_files()`，通常不需要操作系统文件选择窗口。

## 不使用大模型：完全固定的 Playwright 流程

可以。将 `execution.mode` 设置为 `playwright` 后，Runner 不会创建 LLM，也不会创建或运行
Browser Use Agent；Playwright 负责登录、初始化页面、逐 Case 上传/提问/发送/读取答案和
刷新，CDP StreamMonitor 仍负责判断问答何时真正完成。

下面是与你描述的流程对应的配置模板。selector 必须替换成实际页面的稳定 selector：

```yaml
execution:
  mode: playwright

system:
  url: "https://your-system.example"
  iframe_selector: "#business-frame"

workflow:
  login:
    enabled: true
    detect_selector: "#login-form"
    username_env: TEST_USERNAME
    password_env: TEST_PASSWORD
    username_selector: "input[name='username']"
    password_selector: "input[name='password']"
    submit_selector: "button[type='submit']"

  setup_steps:
    # 1. 点击产品列表中 testcc 的卡片
    - action: click
      target: main
      selector: "[data-product-name='testcc']"
    # 2. 点击新增
    - action: click
      target: main
      selector: "[data-testid='add-api']"
    # 3. 输入 API 名称 auto_api
    - action: fill
      target: main
      selector: "input[name='apiName']"
      value: "auto_api"
    # 4. 保存/确定
    - action: click
      target: main
      selector: "[data-testid='save-api']"
    # 5. 打开 AI 助手
    - action: click
      target: main
      selector: ".ai-toggle-btn"

  question_selector: "textarea[data-testid='question-input']"
  send_selector: "button[data-testid='send-question']"
  answer_selector: "[data-testid='assistant-answer']:last-child"
  target: iframe
  ui_timeout_ms: 15000

  # 每个 Case 结束后刷新。若页面有专用“新会话”按钮，建议改为 click。
  refresh_action: reload       # reload / click / none
  refresh_selector: null

upload:
  directory: "D:/browser-ai-test-files"
  input_selector: "input[type='file']"
  target: iframe
  timeout_ms: 10000

report:
  html_directory: "reports"
```

用户名密码放在 `.env`，而不是 YAML：

```dotenv
TEST_USERNAME=your-user
TEST_PASSWORD=your-password
```

Case 仍然只需要文件、问题和标准答案：

```yaml
cases:
  - id: FILE_QA_001
    name: 文件问答 001
    file: "产品说明书.pdf"
    question: "请总结产品的主要功能"
    expected:
      type: keyword
      values: ["功能一", "功能二"]
      match_mode: all
    stream:
      protocol: sse
    timeout_seconds: 120
```

固定模式的执行边界为：

```text
一次性初始化：访问 URL -> 登录（仅登录界面可见时） -> testcc -> 新增 API
             -> 输入 auto_api -> 保存 -> 点击 .ai-toggle-btn

逐 Case 循环：上传 file -> 填入 question -> arm CDP -> 点击发送
             -> 等待真实 done -> 读取 answer_selector -> Validator
             -> 保存 SQLite -> 刷新 -> 下一个 Case

Run 结束：汇总成功率/TTFT/Stream/Error -> 生成 reports/<run_id>.html
```

`refresh_action: reload` 会刷新当前 URL。如果刷新后应用会退回产品列表，建议使用页面的
“新会话/清空对话”按钮并配置：

```yaml
workflow:
  refresh_action: click
  refresh_selector: "button[data-testid='new-chat']"
```

这样不会重复创建 `auto_api`。HTML 中包含每个 Case 的 UI/网络/答案状态、页面答案、TTFT、
Stream 耗时和错误详情；页面答案会 HTML escape，报告默认写入 `reports/`。

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

在存在系统代理/公司代理的 Windows 环境中，建议显式绑定回环地址：

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-address=127.0.0.1 `
  --remote-debugging-port=9222 `
  --remote-allow-origins=* `
  --user-data-dir="$env:TEMP\browser-ai-test"
```

Chrome 版本若要求远程调试来源限制，请按组织安全策略显式配置；不要将调试端口暴露到公网。

## 主配置

编辑 `config/config.yaml`：

- `system.url`：被测主系统 URL。
- `llm.provider` / `llm.model`：模型提供方和模型名；私有模型参见上一节。
- `llm.base_url` / `llm.api_key_env`：自定义网关和密钥环境变量名。
- `llm.class_path` / `llm.kwargs`：完全自定义模型适配器及其扩展参数。
- `agent.instructions`：所有 Case 共用的 Browser Use 前置步骤。
- `agent.max_steps`：单 Case 最大 Agent 操作步数，不是网络 timeout。
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
    steps:
      - 确认当前位于问答页面
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

### Browser Use 访问 `/json/version` 返回 `504 Gateway Time-out`

如果日志包含：

```text
GET http://localhost:9222/json/version "HTTP/1.1 504 Gateway Time-out"
JSONDecodeError: Expecting value: line 1 column 1
Root CDP client not initialized
```

根因通常不是 JSON，而是 `localhost:9222` 被系统或公司 HTTP 代理转发到了网关；网关返回
504 HTML，browser-use 再把 HTML 当作 CDP JSON 解析，才出现 `JSONDecodeError`。开头的
“Newer version available” 只是版本提示，与这次 CDP 失败无关。

新版工程默认使用 `http://127.0.0.1:9222`，并在连接前完成两件事：

1. 将 `localhost`、`127.0.0.1`、`::1` 合并进 `NO_PROXY` 和 `no_proxy`，使 browser-use
   使用的 httpx 不经过代理；
2. 使用明确禁用代理的请求预检 `/json/version`，确认它返回包含
   `webSocketDebuggerUrl` 的 JSON。预检失败会直接报告 CDP/代理问题，不再暴露含糊的
   `JSONDecodeError`。

对应配置如下：

```yaml
browser:
  cdp_url: "http://127.0.0.1:9222"
  cdp_timeout_seconds: 10
  bypass_proxy_for_loopback: true
```

运行测试前可在同一个 PowerShell 窗口检查：

```powershell
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = $env:NO_PROXY
curl.exe --noproxy "*" http://127.0.0.1:9222/json/version
```

也可以直接运行项目内置诊断，它不会启动 Agent 或执行 Case：

```powershell
browser-ai-test doctor
```

正确响应应是 JSON，并包含 `webSocketDebuggerUrl`。如果直连仍失败：

- 确认 Chrome 进程确实使用 `--remote-debugging-port=9222` 启动；
- 使用独立的 `--user-data-dir`，避免已有 Chrome 进程吞掉启动参数；
- 确认本机防火墙或安全软件没有阻止 9222；
- 确认配置没有写成带 Markdown 的 `[http://...](http://...)`，必须是纯 URL；
- 不要把 9222 暴露到公网。

### `AgentOutput` 提示 `Protocol` is not fully defined

browser-use 0.11 会根据自定义 Tool 的函数签名动态创建 Pydantic `AgentOutput`。旧实现启用了
postponed annotations，并把项目内的 `Protocol` 类型别名暴露在 action 参数上，导致动态
模型只看到无法解析的字符串 `"Protocol"`，从而每一步都报：

```text
AgentOutput is not fully defined; you should define Protocol
```

现在 `arm_stream_monitor` 对 browser-use 暴露具体的 `str` 参数，在 Tool 内显式验证
`sse`、`websocket`、`http`、`auto` 后再转换为内部类型，因此不再产生 Pydantic forward
reference。这个错误与网页、Chrome CDP 和 Qwen 本身无关。

如果修复后只剩：

```text
ModelProviderError: Connection error
```

这是另一个独立问题，表示 OpenAI-compatible 模型端点不可达。检查 `llm.base_url` 是否包含
服务要求的 `/v1`、API Key 环境变量是否在当前终端生效、网关证书/代理/防火墙以及 Qwen
服务是否支持 `/chat/completions`。不要把模型连接错误当成 CDP 或 StreamMonitor 错误。

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
