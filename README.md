# Browser AI Test

基于 **Playwright + Chrome DevTools Protocol（CDP）** 的固定脚本 Web 问答测试平台。工程不使用大模型，不依赖 Browser Use；所有页面操作均由 YAML 中的稳定 selector 和 Playwright 动作确定执行。

CDP 只负责判断 SSE、WebSocket 或长 HTTP 请求何时真正完成，Validator 负责校验页面实际答案。不会使用固定 `sleep`、`networkidle` 或页面静止推断业务完成。

## 架构

```text
YAML Cases
   -> 串行 TestRunner
   -> 固定 Playwright 工作流
      -> 登录（仅登录页可见时）
      -> 一次性页面初始化
      -> 上传文件 / 输入问题 / 点击发送
   -> CDP StreamMonitor 等待业务 done
   -> 从页面读取答案
   -> Keyword / Regex Validator
   -> SQLite + Console + HTML Report
```

最终通过条件为：

```text
ui_ok AND network_ok AND answer_ok
```

## 安装

要求 Python 3.12+。

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -m playwright install chromium
Copy-Item .env.example .env
```

如果 PowerShell 禁止执行激活脚本：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
python -m playwright install chromium
cp .env.example .env
```

## 启动 Chrome/CDP

Playwright 连接外部 Chrome，不会另外启动浏览器。

### Windows PowerShell

```powershell
& "$env:ProgramFiles\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-address=127.0.0.1 `
  --remote-debugging-port=9222 `
  --remote-allow-origins=* `
  --user-data-dir="$env:TEMP\browser-ai-test"
```

### Linux

```bash
google-chrome \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/browser-ai-test
```

先检查 CDP：

```bash
browser-ai-test doctor
```

成功时输出 `CDP PASS` 和 `webSocketDebuggerUrl`。

## 目标场景配置

以下模板对应：登录 → 点击 `testcc` → 新增 `auto_api` → 打开 `.ai-toggle-btn` → 循环文件问答 → HTML 报告。请把示例 selector 替换为页面真实 selector。

```yaml
browser:
  cdp_url: "http://127.0.0.1:9222"
  cdp_timeout_seconds: 10
  bypass_proxy_for_loopback: true

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
    - action: click
      target: main
      selector: "[data-product-name='testcc']"
    - action: click
      target: main
      selector: "[data-testid='add-api']"
    - action: fill
      target: main
      selector: "input[name='apiName']"
      value: "auto_api"
    - action: click
      target: main
      selector: "[data-testid='save-api']"
    - action: click
      target: main
      selector: ".ai-toggle-btn"

  question_selector: "textarea[data-testid='question-input']"
  send_selector: "button[data-testid='send-question']"
  answer_selector: "[data-testid='assistant-answer']:last-child"
  target: iframe
  ui_timeout_ms: 15000

  # reload / click / none
  refresh_action: click
  refresh_selector: "button[data-testid='new-chat']"

upload:
  directory: "D:/browser-ai-test-files"
  input_selector: "input[type='file']"
  target: iframe
  timeout_ms: 10000

stream:
  protocol: sse                 # sse / websocket / http / auto
  url_keywords:
    - "/api/chat/stream"
  timeout_seconds: 120
  done_markers:
    - "[DONE]"
    - '"status":"completed"'

database:
  path: "data/results.db"

runner:
  continue_on_failure: true
  case_interval_seconds: 1

report:
  html_directory: "reports"
```

## 登录凭据

只在 `.env` 中保存，不要写入 YAML：

```dotenv
TEST_USERNAME=your-user
TEST_PASSWORD=your-password
```

`workflow.login.enabled=true` 时，程序检查 `detect_selector`（未配置则检查用户名输入框）。只有登录界面可见时才填写账号密码。

## Playwright 初始化步骤

### 具体在哪个文件编辑？

日常接入**不需要修改 Python 源码**，主要编辑两个 YAML 文件：

| 内容 | 编辑文件 | 配置位置 |
|---|---|---|
| 登录 selector、testcc 卡片、新增 API、`auto_api`、`.ai-toggle-btn` | `config/config.yaml` | `workflow.login`、`workflow.setup_steps` |
| 问题输入框、发送按钮、答案区域、刷新按钮 | `config/config.yaml` | `workflow.question_selector`、`send_selector`、`answer_selector`、`refresh_*` |
| 文件目录和上传 input | `config/config.yaml` | `upload` |
| SSE/WS/HTTP URL 和完成标记 | `config/config.yaml` | `stream` |
| 每条用例的文件、问题和标准答案 | `config/cases.yaml` | `cases[]` |

也就是说，你描述的固定页面步骤应直接写在：

```text
config/config.yaml -> workflow.setup_steps
```

例如：

```yaml
workflow:
  setup_steps:
    - action: click
      target: main
      selector: "[data-product-name='testcc']"
    - action: click
      target: main
      selector: "[data-testid='add-api']"
    - action: fill
      target: main
      selector: "input[name='apiName']"
      value: "auto_api"
    - action: click
      target: main
      selector: "[data-testid='save-api']"
    - action: click
      target: main
      selector: ".ai-toggle-btn"
```

只有需要新增 YAML DSL 尚未支持的动作类型时，才修改源码：

```text
src/browser_ai_test/browser/playwright_steps.py
```

完整问答循环（上传、输入、arm CDP、发送、等待、读取答案、刷新）的编排实现在：

```text
src/browser_ai_test/browser/fixed_workflow.py
```

通常不要为单个业务系统修改这两个 Python 文件；优先通过 YAML selector 完成接入。

`workflow.setup_steps` 在整个 Run 开始时只执行一次，支持：

- `click`
- `fill`
- `select_option`
- `check`
- `press`
- `wait_visible`

字段：

- `target: main`：主页面；
- `target: iframe`：`system.iframe_selector` 指定的 iframe；
- `selector`：稳定 CSS/Playwright selector；
- `value`：`fill`、`select_option`、`press` 必填；
- `timeout_ms`：可选的步骤超时。

建议优先使用 `data-testid`、稳定 ID 或业务属性，避免脆弱的绝对 XPath。

## Case 编写

每个 Case 只需要文件名、问题和标准答案：

```yaml
cases:
  - id: FILE_QA_001
    name: 产品说明书问答
    file: "产品说明书.pdf"
    question: "请总结产品的主要功能"
    expected:
      type: keyword
      values: ["功能一", "功能二"]
      match_mode: all
    stream:
      protocol: sse
    timeout_seconds: 120

  - id: FILE_QA_002
    name: 安装手册问答
    file: "manuals/安装手册.docx"
    question: "安装时有哪些注意事项？"
    expected:
      type: regex
      values: ["注意|警告|限制"]
    timeout_seconds: 120
```

`file` 相对于 `upload.directory`。允许目录内子路径，不允许绝对路径或 `../` 越界。无附件时省略 `file` 或设为 `null`。

## Case 循环流程

```text
上传 file
 -> 填入 question
 -> arm StreamMonitor
 -> 点击发送
 -> 等待 CDP 业务完成
 -> 读取 answer_selector
 -> Validator 评估 expected
 -> 保存 SQLite
 -> 刷新/新会话
 -> 下一个 Case
```

刷新在 `finally` 中执行，即使上传、selector 或网络等待失败，也会清理界面后继续下一 Case。

### 刷新策略

推荐使用新会话按钮：

```yaml
workflow:
  refresh_action: click
  refresh_selector: "button[data-testid='new-chat']"
```

整页刷新：

```yaml
workflow:
  refresh_action: reload
```

如果 reload 会返回产品列表，请使用 `click`，否则后续 Case 将离开问答页。

## 网络完成判定

- SSE：`Network.eventSourceMessageReceived` payload 命中 done marker；
- WebSocket：frame payload 命中 done marker，不等待 socket close；
- HTTP：目标请求收到 `Network.loadingFinished`；
- `auto`：根据实际 CDP 事件自动识别。

只监听 URL 命中 `stream.url_keywords` 的请求。TTFT 和 Stream Total 全部使用 CDP monotonic timestamp 计算。

## 执行

```bash
browser-ai-test list
browser-ai-test run
browser-ai-test run --case FILE_QA_001
browser-ai-test run --limit 10
browser-ai-test report
```

也可以：

```bash
python -m browser_ai_test.cli run
```

## HTML 报告

每次成功完成 Run 后自动生成：

```text
reports/<run_id>.html
```

报告包含总数、PASS/FAIL、UI/网络/答案成功率，以及每个 Case 的页面答案、TTFT、Stream 耗时和错误详情。所有页面文本都会 HTML escape。

## SQLite

默认数据库：

```text
data/results.db
```

包含 `runs` 和 `case_results`。程序会自动迁移早期版本的列名。

## 常见问题

### `/json/version` 返回 504

通常是本机 CDP 请求被系统代理接管。配置 `127.0.0.1`，保留 `bypass_proxy_for_loopback: true`，并运行：

```powershell
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = $env:NO_PROXY
curl.exe --noproxy "*" http://127.0.0.1:9222/json/version
browser-ai-test doctor
```

### 找不到 iframe

固定脚本模式不会猜测 iframe。请在 DevTools 中确认并配置 `system.iframe_selector`。

### 找不到上传按钮

需要定位真实的 `<input type="file">`，包括隐藏 input，并修改 `upload.input_selector`。Playwright 使用 `set_input_files()`，不操作系统文件选择窗口。

### WebSocket 一直不关闭

这是正常的。平台等待业务 done marker，不等待 WebSocket close。

### 为什么不用 `networkidle` 或固定 sleep

心跳、遥测和共享长连接会让 `networkidle` 不可靠；固定 sleep 可能读取半成品或浪费时间。平台只等待配置的 CDP 业务完成信号。

## 测试

```bash
pytest
```

单元测试通过 mock Playwright/CDP 事件运行，不要求真实业务网址。
