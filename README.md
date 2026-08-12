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

## 为什么当前工程选择纯 Playwright

对于本项目的固定流程——登录、点击 `testcc`、创建 `auto_api`、点击
`.ai-toggle-btn`、上传文件、输入问题、等待完成、校验答案——**纯 Playwright 更合适**：

| 维度 | 纯 Playwright | 基于大模型的浏览器操作 |
|---|---|---|
| 固定流程稳定性 | 高，selector 和动作完全确定 | 可能因模型判断不同而改变步骤 |
| 执行速度 | 快，不等待模型推理 | 慢，需要多轮模型请求 |
| 成本 | 无模型调用成本 | 有 Token/API 成本 |
| 可重复性 | 高，适合回归测试和 CI | 相同页面也可能产生不同决策 |
| 错误定位 | selector、网络或断言错误较清晰 | 还需区分模型、Prompt 和工具调用错误 |
| 页面变化适应 | selector 变化时需要维护配置 | 更擅长语义寻找未知控件 |
| 无固定步骤的探索任务 | 不擅长 | 更合适 |

选择原则：

- 页面和操作路径明确、需要大量重复 Case、需要稳定指标和 CI：使用纯 Playwright；
- 页面结构未知、不同页面差异很大、任务需要临时探索：大模型浏览器操作更方便；
- 固定回归测试不应让模型决定是否点击、何时结束或答案是什么。

因此当前工程只保留纯 Playwright + CDP：Playwright 负责确定性 UI 操作，CDP 负责业务
完成信号，Keyword/Regex Validator 负责标准答案。这个选择更符合你的文件问答批量回归
场景。

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
  url: "http://7.212.32.169:8081/index.html#/login"
  iframe_selector: "#methodCopilot"

workflow:
  login:
    enabled: true
    detect_selector: "input[placeholder='w3账号']"
    username_env: USER_NAME
    password_env: USER_PASSWORD
    username_selector: "input[placeholder='w3账号']"
    password_selector: "input[type='password']"
    submit_selector: "button:has-text('登录')"

  setup_steps:
    - action: click
      target: main
      locator_type: text
      selector: "Auto_EVA存量BES"
      exact: false
      timeout_ms: 30000
    - action: wait_visible
      target: main
      locator_type: role
      selector: button
      name: "新增"
      exact: false
      nth: 0
      timeout_ms: 30000
    - action: click
      target: main
      locator_type: role
      selector: button
      name: "新增"
      exact: false
      nth: 0
      timeout_ms: 30000
    - action: fill
      target: main
      selector: ".el-form-item:has-text('API名称') input"
      value: "auto_api"
    - action: click
      target: main
      locator_type: role
      selector: button
      name: "确认"
      exact: true
    - action: click
      target: main
      selector: ".ai-toggle-btn"

  before_case_steps: []
  after_upload_steps:
    - action: click
      target: iframe
      selector: ".cb-chatbot-content"
    - action: click
      target: iframe
      selector: ".wise-input"

  question_selector: "span"
  question_nth: 3
  send_selector: ".wise-input-send"
  answer_selector: "[data-testid='assistant-answer']:last-child"
  target: iframe
  ui_timeout_ms: 15000
  step_interval_seconds: 1

  # reload / iframe_reload / click / none
  refresh_action: click
  refresh_selector: "button[data-testid='new-chat']"

upload:
  directory: "D:/browser-ai-test-files"
  input_selector: ".el-upload input[type='file'], input.el-upload"
  trigger_selector: ".chat-input-icon"
  target: iframe
  timeout_ms: 10000

stream:
  protocol: sse                 # sse / websocket / http / auto
  url_keywords:
    - "/api/chat/stream"
  # 最长等待 2 小时；收到业务 done marker 后立即结束等待。
  timeout_seconds: 7200
  done_markers:
    - "event:onComplete"
  done_event_names:
    - "onComplete"

database:
  path: "data/results.db"

runner:
  continue_on_failure: true
  # network_complete: 收到业务结束事件即 PASS；all: UI、网络、答案全部通过才 PASS。
  pass_condition: network_complete
  case_interval_seconds: 1

report:
  html_directory: "reports"
```

## 登录凭据

只在 `.env` 中保存，不要写入 YAML：

```dotenv
USER_NAME=your-user
USER_PASSWORD=your-password
```

`workflow.login.enabled=true` 时，程序检查 `detect_selector`（未配置则检查用户名输入框）。只有登录界面可见时才填写账号密码。

登录页的 `el-id-*` 是 Element Plus/Vue 运行时生成 ID，重新打包后可能变化，因此不要使用
`#el-id-8974-8` 定位密码框。当前配置使用稳定属性：

```yaml
username_selector: "input[placeholder='w3账号']"
password_selector: "input[type='password']"
submit_selector: "button:has-text('登录')"
```

如果同一页面将来出现多个 password input，可以进一步收窄为：

```yaml
password_selector: ".login_form input[type='password']"
```

这比依赖动态 ID 更能抵抗前端重新构建。

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
    timeout_seconds: 7200

  - id: FILE_QA_002
    name: 安装手册问答
    file: "manuals/安装手册.docx"
    question: "安装时有哪些注意事项？"
    expected:
      type: regex
      values: ["注意|警告|限制"]
    timeout_seconds: 7200
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

`workflow.step_interval_seconds` 控制普通 UI 动作之间的节奏，当前为 1 秒。这个暂停只用于
避免页面操作过快，不用于判断后台问答是否完成；发送后仍然立即进入 CDP
`wait_stream_done`。

文件上传按钮会打开操作系统文件选择框，因此不能先普通 click 再调用
`set_input_files()`。配置 `upload.trigger_selector` 后，执行器使用 Playwright
`expect_file_chooser()` 在点击 `.chat-input-icon` 的同时捕获选择器，并通过
`FileChooser.set_files()` 设置 Case 文件，弹窗不会遗留并阻塞流程。

文件设置完成后不能直接使用原先的 `.wise-input span` 后代定位，因为 Recorder 的真实
顺序是先点击 `.cb-chatbot-content` 关闭上传层，再点击 `.wise-input` 聚焦，最后从 iframe
全局的 `span` 中选择 `nth(3)` 填写。因此当前流程增加：

```yaml
workflow:
  after_upload_steps:
    - action: click
      target: iframe
      selector: ".cb-chatbot-content"
    - action: click
      target: iframe
      selector: ".wise-input"
  question_selector: "span"
  question_nth: 3
  send_selector: ".wise-input-send"
```

运行日志会分别打印 `uploading file`、`filling question` 和 `clicking send`。如果再次中断，
可以直接判断失败发生在上传、输入定位还是发送按钮。

### 刷新策略

推荐使用新会话按钮：

```yaml
workflow:
  refresh_action: click
  refresh_selector: "button[data-testid='new-chat']"
```

当前 IF 页面更推荐只刷新问答 iframe，这样不会丢失外层已经选择的产品和 `auto_api`：

```yaml
workflow:
  refresh_action: iframe_reload
  case_ready_selector: ".wise-input"
  after_refresh_steps:
    - action: wait_visible
      target: iframe
      selector: ".wise-input"
      timeout_ms: 30000
```

整页刷新：

```yaml
workflow:
  refresh_action: reload
```

如果 reload 会返回产品列表，请使用 `iframe_reload` 或 `click`，否则后续 Case 将离开问答页。

## 网络完成判定

- SSE：`Network.eventSourceMessageReceived` 的 `eventName` 与 `data` 组合内容命中 done marker；
- WebSocket：frame payload 命中 done marker，不等待 socket close；
- HTTP：目标请求收到 `Network.loadingFinished`；
- `auto`：根据实际 CDP 事件自动识别。

只监听 URL 命中 `stream.url_keywords` 的请求。TTFT 和 Stream Total 全部使用 CDP monotonic timestamp 计算。

例如服务最后返回空数据事件：

```text
event:onComplete
data:
```

应配置 `done_markers: ["event:onComplete"]`。不要使用 `"done":false`、
`event:onPlan` 或 `state:success` 作为结束条件，因为它们在真正结束前也会出现。
SSE 已发出 `onComplete` 后，即便 Chrome 随后对连接报告 `net::ERR_ABORTED`，该请求也按
业务成功处理。

如果页面使用 `fetch` 消费 SSE，并且读取完结果后主动取消连接，CDP 可能只报告
`Network.loadingFailed: net::ERR_ABORTED`。确认这是该系统的正常结束方式后，可以开启：

```yaml
stream:
  aborted_sse_is_complete: true
```

兼容模式只会在响应 MIME 或 CDP 事件已经确认请求是 SSE 后，将
`net::ERR_ABORTED` 作为完成；其他网络错误仍然失败。它也兼容 Chrome 不产生
`eventSourceMessageReceived` 的 fetch-streaming 实现。普通系统应保持默认值 `false`。

如果某些环境使用 fetch-streaming，可能在完整响应体结束时只产生
`Network.loadingFinished`，而不会产生 `eventSourceMessageReceived`，这时可以配置：

```yaml
stream:
  sse_loading_finished_is_complete: true
```

此开关只对 MIME 已确认为 `text/event-stream` 的目标请求生效；收到
`Network.loadingFinished` 后会立即退出等待，随后执行整页刷新。

当前系统明确使用原生 EventSource，因此保持该开关为 `false`，并使用
`done_event_names: ["onComplete"]` 对 CDP 的 `eventName` 做精确匹配。运行日志会输出每条
`SSE event received`；看到 `SSE business completion event matched` 后，才表示
`wait_done()` 已经返回并将开始整页刷新。

### 查看 SSE 日志

运行 `python -m browser_ai_test.cli run` 的 PowerShell 窗口会实时显示 SSE/CDP 日志，
同时默认写入：

```text
reports/browser-ai-test.log
```

PowerShell 可另开窗口实时查看：

```powershell
Get-Content .\reports\browser-ai-test.log -Wait
```

只筛选 SSE：

```powershell
Get-Content .\reports\browser-ai-test.log -Wait |
  Select-String "SSE event received|SSE business completion|ERR_ABORTED"
```

应重点检查 `tracked=true`、`armed=true`，以及最后是否出现
`event_name='onComplete'` 和 `SSE business completion event matched`。日志文件位置可通过
`logging.file` 修改；设置为 `null` 时只输出到控制台。

如果连 `SSE event received` 都没有，Runner 会在每条 Case 发送前检查 iframe 的 CDP
归属。跨进程 iframe（OOPIF）会创建独立 Session；同进程 iframe 已经包含在主页面
Session 中，Playwright 不允许重复创建，此时会安全复用父 Session，而不是让 Case 失败。
正常日志会出现以下二者之一：

```text
CDP Network monitor attached to separate iframe: #methodCopilot
# 或
iframe uses parent CDP session; existing Network monitor retained: #methodCopilot
Tracked stream request: request_id=... type=EventSource url=...
```

你日志中的 `This frame does not have a separate CDP session` 表示 `#methodCopilot` 是
**同进程 iframe**，并不是 SSE 或页面错误。旧实现错误地把 Playwright 的这个说明当成
WORKFLOW_ERROR，所以在输入问题前就进入了 `finally` 刷新。现在该情况会继续使用已经在
启动时挂载的 Page CDP Session，然后正常输入、发送并等待 SSE。

如果日志停在 `clicking send`，但没有 `Tracked stream request`，程序实际卡在
`wait_done()` 等待，并不是刷新卡住。此时查看以下诊断：

```text
EventSource request ignored because URL does not match stream.url_keywords
# 或
SSE response ignored because URL does not match stream.url_keywords
```

日志会打印真实 `url=` 和当前 `configured_keywords=`。请把真实 URL 中稳定且唯一的
Chat 路径片段写入 `stream.url_keywords`；配置里的 `/api/chat/stream` 和
`/api/generate` 只是示例，不保证匹配测试环境。

整页刷新会自动销毁 OOPIF 的旧 CDP Session。下一条 Case 重新 attach 前如果 Playwright
返回 `CDPSession.detach: Target page, context or browser has been closed`，现在会将其视为
旧 Target 已正常销毁并继续创建新 Session；该清理状态不再导致后续 Case
`WORKFLOW_ERROR`，Run 结束时也不会再因重复 detach 崩溃。

当前 `pass_condition: network_complete` 且真实答案 selector 尚未确认，因此示例配置使用
`answer_selector: null`。收到网络完成信号后会直接刷新，不再为不存在的
`[data-testid='answer']` 额外等待 10 秒并打印 Timeout traceback。需要恢复内容校验时，
请将它改成页面真实答案元素的 selector。

当前默认 `runner.pass_condition: network_complete`：只要目标请求收到完整的
`event:onComplete`，Case 就记为 PASS。Keyword/Regex 校验仍会执行并记录到
`answer_ok` 和报告中，但不会改变最终 PASS。若需要恢复严格标准，可配置：

```yaml
runner:
  pass_condition: all
```

此时必须同时满足 `ui_ok AND network_ok AND answer_ok`。

## 执行

### 单步调试方法详情 postMessage

主页面监听 iframe 发出的 `getApiDetail` 后，会查询所有方法并把结果通过
`postMessage` 返回 iframe。配置如下：

```yaml
api_detail:
  request_event: "getApiDetail"
  response_event: "getApiDetail"
  request_data: {}
  target_origin: "*"
  timeout_ms: 30000
```

只调试该功能，不执行 Case：

```powershell
python -m browser_ai_test.cli debug-api-detail
# 或
browser-ai-test debug-api-detail
```

该命令**不会**访问 `system.url`，也不会执行登录、`setup_steps`、上传、问答或刷新。
请先在通过 9222 端口启动的同一个 Chrome 中手动进入目标界面，并确保
`#methodCopilot` 已经存在；命令将直接使用 Chrome 当前 Page，在 iframe 内先注册
`message` 监听，再执行：

```javascript
window.parent.postMessage({event: "getApiDetail", data: {}}, "*")
```

收到 `event === "getApiDetail"` 的响应后，会将响应的 `data` 以格式化 JSON 打印到
控制台，同时写入 `reports/browser-ai-test.log`。监听器在成功或 timeout 后都会移除。
如果生产环境已知父页面 origin，建议把 `target_origin: "*"` 改成明确 origin。

获取后会将 `tableData` 转换成纯方法数组：方法名来自 `operationName`；request/response
从 `elements` 展开为 `{path, type, lenth, required}`。复杂类型会通过 `complexTypes` 的
`type/key/name` 递归展开，路径从 `$` 开始以 `.` 连接；`RequestHeader`、
`ResponseHeader`、`ResultHeader`、`Page` 会被忽略。若消息根节点的 `elements` 为空，
还会尝试通过 `type/operationKey/key` 查找对应复杂类型。输出示例：

```json
[
  {
    "name": "accessToken",
    "request": [
      {"path": "$.client_id", "type": "string", "lenth": null, "required": true}
    ],
    "response": [
      {"path": "$.access_token", "type": "string", "lenth": null, "required": true}
    ]
  }
]
```

推荐调试顺序：

```text
1. 手动在 Chrome 中登录
2. 手动进入产品/API 页面
3. 手动打开 AI 助手，确认 #methodCopilot 已显示
4. 保持该标签页为当前标签页
5. 执行 browser-ai-test debug-api-detail
```

推荐使用模块方式执行，它不依赖 Windows 是否把 console script 加入当前 PATH：

```powershell
python -m browser_ai_test.cli doctor
python -m browser_ai_test.cli list
python -m browser_ai_test.cli run
python -m browser_ai_test.cli run --case FILE_QA_001
python -m browser_ai_test.cli report
```

Windows 还可以直接使用仓库自带的启动脚本；它会固定调用项目的
`.venv\Scripts\python.exe`：

```powershell
.\browser-ai-test.cmd doctor
.\browser-ai-test.cmd list
.\browser-ai-test.cmd run --case FILE_QA_001
.\browser-ai-test.cmd report
```

完成 `python -m pip install -e ".[test]"` 且已激活虚拟环境后，也可以使用安装生成的短命令：

```bash
browser-ai-test list
browser-ai-test run
browser-ai-test run --case FILE_QA_001
browser-ai-test run --limit 10
browser-ai-test report
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

### PowerShell 提示 `browser-ai-test is not recognized`

这表示当前 PowerShell 找不到安装时生成的 console script，通常有以下原因：

1. `.venv` 尚未激活；
2. 项目还没有执行 editable install；
3. 安装使用的 Python 和当前终端的 Python 不是同一个；
4. PowerShell 是在安装前打开的，PATH 尚未刷新。

在项目根目录依次运行：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
python -m pip show browser-ai-test
python -c "import sys, browser_ai_test; print(sys.executable); print(browser_ai_test.__file__)"
Get-ChildItem .\.venv\Scripts\browser-ai-test*
```

正常情况下，最后一条命令会显示类似：

```text
.venv\Scripts\browser-ai-test.exe
```

无论 console script 是否进入 PATH，以下两种方式都可以运行：

```powershell
python -m browser_ai_test.cli doctor
.\browser-ai-test.cmd doctor
```

注意：PowerShell 默认不会从当前目录搜索可执行文件，因此即使项目根目录存在
`browser-ai-test.cmd`，也必须写成 `.\browser-ai-test.cmd`，不能省略 `.\`。

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

### 第一条 Case 结束后没有执行下一条

Runner 的继续条件是 `runner.continue_on_failure`，不是上一条 Case 必须 PASS：

```yaml
runner:
  continue_on_failure: true
```

此前默认使用整页 `reload`，测试环境刷新后可能丢失产品/API 选择，或者 AI 面板状态与
预期相反，导致再次点击 `.ai-toggle-btn` 反而关闭面板。当前配置改用
`iframe_reload`，只刷新 `#methodCopilot`，并用 `case_ready_selector` 等待输入区恢复；
日志出现 `Case cleanup: refresh completed; next Case may start` 后才会开始下一条。

```yaml
workflow:
  refresh_action: iframe_reload
  case_ready_selector: ".wise-input"
  after_refresh_steps:
    - action: wait_visible
      target: iframe
      selector: ".wise-input"
      timeout_ms: 30000
```

Case 的 `timeout_seconds` 单位为秒。耗时文档问答建议填写 `7200`（最长两小时），
而不是按毫秒填写 `120000`。该值是最长等待上限，不是固定 sleep；只要 CDP 收到
业务 done marker，就会立即继续读取答案并运行下一条 Case。

### WebSocket 一直不关闭

这是正常的。平台等待业务 done marker，不等待 WebSocket close。

### 为什么不用 `networkidle` 或固定 sleep

心跳、遥测和共享长连接会让 `networkidle` 不可靠；固定 sleep 可能读取半成品或浪费时间。平台只等待配置的 CDP 业务完成信号。

## 测试

```bash
pytest
```

单元测试通过 mock Playwright/CDP 事件运行，不要求真实业务网址。
