# JobFit Agent 项目全景与维护文档

> 最后更新：2026-09-29
>
> 适用对象：未来的项目维护者、面试准备者、协作者和几周后重新阅读代码的自己。
>
> 维护规则：每完成一个大 STEP，必须更新本文档的状态、功能、架构、数据流、技术选型、限制和变更记录。

---

# 一、项目一句话说明

JobFit Agent 是一个基于 RAG 和工具调用的可解释岗位匹配与差距分析 Agent。

目标链路：

```text
简历
→ 岗位 JD
→ 岗位要求提取
→ 简历证据检索
→ 匹配分析
→ 差距分析
→ 修改建议
→ 面试问题
→ 用户确认
→ 报告保存
```

当前项目已完成模型 API、聊天接口、结构化提取、工具注册、简历分段、关键词证据检索、三态匹配评估、ReAct 循环、PostgreSQL/Alembic 持久化、Redis 缓存与运行锁、工具审计、失败恢复、SSE 流式任务和真实模型持久化验收。

---

# 二、当前状态

```text
STEP 01：完成
STEP 02：完成
STEP 03：完成，部署按下述新节奏延期
STEP 04：功能、测试、文档、Git 和 tag 完成
STEP 05：功能、测试、真实验收、文档、Git、远程 push 和 tag 全部完成
STEP 06：完成；功能、测试、真实模型、HTTP、部署就绪、文档和本地 Git 闭环均已完成
STEP 07：代码、数据库/Redis、SSE、真实模型持久化、自动化测试和本地验收完成；私有 staging 待 Docker 环境。
```

当前代码分支：

```text
main
```

STEP 06 对应版本：

```text
feature commits:
  da124b7 feat: add react agent loop and match api
  4c2033b test: cover react agent loop and api
  713834b docs: document STEP 06 react agent
merge commit: a989091e3756a15ec5c800a6e253a07e9d8b69ca
tag: step-06-react-loop
```

STEP 04 对应版本：

```text
tag: step-04-structured-output
merge commit: 088cf0a17a9b1c563d10c7f0fbad321854ebbc0c
```

STEP 04 的功能、测试、文档、Git 合并和 tag 均已完成。STEP 05 已完成四个真实工具、统一工具执行边界、超时与安全日志，并通过真实 DeepSeek 手工验收；本地 merge、远程 push 和 tag 均已完成。部署计划已调整：STEP 06 只做部署就绪检查，不公开部署；STEP 07 后建立私有 staging；STEP 12 后正式公网部署。

STEP 03 对应版本：

```text
tag: step-03-llm-api
commit: 6d32d56
```

公网部署延期原因：

- 当前仍使用固定 `demo-token`，并且没有真实登录、限流、配额和并发保护。
- 一次 ReAct 请求可能触发多轮模型和嵌套工具调用，直接公开有 API 余额被滥用风险。
- STEP 06 只验证项目能够部署和启动，不向公网开放。
- STEP 07 后建立私有 staging，STEP 12 后完成正式公网部署。

---

# 三、当前已经实现的功能

## 1. 健康检查

```http
GET /health
```

返回：

```json
{"status": "ok"}
```

用途：

- 本地确认服务启动。
- Docker healthcheck。
- 部署平台可用性检查。

## 2. 当前用户接口

```http
GET /api/users/me
Authorization: Bearer demo-token
```

用途：

- 验证 Bearer 鉴权依赖。
- 为后续真实用户系统保留接口位置。

当前为演示鉴权，不是生产级认证。

## 3. 非流式聊天

```http
POST /api/chat
Authorization: Bearer demo-token
Content-Type: application/json
```

输入：

```json
{
  "messages": [
    {"role": "user", "content": "用一句话解释 Agent。"}
  ]
}
```

返回：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "answer": "模型回答",
    "usage": {
      "prompt_tokens": 35,
      "completion_tokens": 178,
      "total_tokens": 213
    },
    "latency_ms": 2501
  }
}
```

包含能力：

- 调用 DeepSeek。
- 支持多轮消息历史。
- 返回输入、输出和总 Token。
- 返回模型调用耗时。
- 统一成功响应结构。
- 将模型异常翻译为项目异常。

## 4. 流式聊天

```http
POST /api/chat/stream
Authorization: Bearer demo-token
Content-Type: application/json
```

返回 SSE：

```text
data: {"type":"content","content":"第一段"}

data: {"type":"content","content":"第二段"}

data: {"type":"usage","usage":{"prompt_tokens":20,"completion_tokens":30,"total_tokens":50},"latency_ms":1234}

data: [DONE]
```

包含能力：

- 模型内容逐段返回。
- 使用 SSE 协议。
- 最后返回完整 Token Usage。
- 最后返回流式调用耗时。
- 流开始后出错时发送安全错误事件。
- 避免把第三方异常原样返回客户端。

## 5. 岗位 JD 结构化提取

```http
POST /api/jobs/extract
Authorization: Bearer demo-token
Content-Type: application/json
```

输入：

```json
{
  "job_description": "负责 FastAPI 后端开发，要求熟悉 Python。"
}
```

返回：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "responsibilities": ["负责 FastAPI 后端开发"],
    "required_skills": ["熟悉 Python"],
    "nice_to_have": []
  }
}
```

包含能力：

- Prompt 明确角色、JD 数据边界、任务和输出约束。
- Pydantic 模型生成 JSON Schema 并加入 Prompt。
- `chat_json()` 使用 `response_format={"type": "json_object"}`。
- 使用 Pydantic 对模型输出执行硬校验。
- 输出为空或校验失败时，携带错误反馈最多重试一次。
- 认证、限流、超时和网络异常不进入结构重试。
- 请求层限制 JD 长度，纯空白输入直接返回 422。

## 6. 工具注册与统一执行边界

当前工具基础层位于：

```text
app/tools/base.py
app/tools/registry.py
app/tools/executor.py
app/tools/jobfit.py
```

包含能力：

- `ToolContext` 注入后端确认的 `CurrentUser`。
- `ToolSpec` 将工具名、描述、Pydantic 参数模型和异步 handler 绑定。
- `ToolRegistry` 作为白名单，拒绝重复或未注册工具。
- `execute_tool()` 统一执行 JSON 对象检查、Pydantic 校验、用户上下文注入、超时和异常脱敏。
- 工具结果必须是 JSON 兼容字典。
- 工具 handler 默认最多执行 30 秒。
- 工具调用日志记录工具名、用户 ID、参数键、状态和耗时，不记录参数值和结果正文。

当前未通过 HTTP 路由暴露工具调用，也未实现工具调用记录的数据库持久化。

## 7. 简历分段提取

业务服务：

```text
app/services/resume_extraction.py
```

输入简历原文，通过 Prompt、JSON Schema、JSON 模式和 Pydantic 校验提取：

```text
summary
education
work_experience
project_experience
skills
certificates
other
```

空响应和 Schema 校验失败最多尝试两次，API 异常不进入结构重试。当前要求保留原文，不允许总结、润色、推断或补全。

## 8. 简历证据检索

业务服务：

```text
app/services/evidence_search.py
```

当前是 RAG 之前的关键词检索基线：

- 英文、数字和技术词按 token 匹配。
- 中文生成整串和双字 n-gram。
- 使用最低分数阈值过滤明显的弱双字误匹配。
- 每条要求只返回命中证据。
- 没有足够证据时返回空列表，不编造原文。
- 证据内容保留简历分段原文。
- 按分数降序、原始 section 顺序稳定排序。

该实现后续会在 STEP 08 升级为混合检索、向量检索和重排。

## 9. 要求匹配评估

业务服务：

```text
app/services/matching.py
```

根据证据检索结果输出三种状态：

```text
strong_match
partial_match
insufficient_evidence
```

当前规则使用最高证据分与强匹配阈值判断，并汇总各状态数量。没有输出 `not_match`，因为关键词证据不足不能证明候选人明确不满足要求。

## 10. 单次 Function Calling 编排（STEP 05 基线）

编排服务：

```text
app/services/tool_calling.py
```

一次调用最多执行一轮工具：

```text
第一次模型调用
→ 有 tool_calls 时执行工具
→ assistant tool_calls 与 role=tool 结果加入消息
→ 第二次模型调用生成最终回答
```

模型直接回答时不执行工具，也只调用一次模型。该服务保留为 STEP 05 的单次编排基线；多轮 ReAct 循环已在 STEP 06 的服务层中实现。

## 11. 最小 ReAct 循环（STEP 06）

服务入口：

```text
app/services/react_agent.py
```

HTTP 接口：

```http
POST /api/agent/match
```

输入：

```text
job_description
resume_text
```

处理流程：

```text
system/user 消息
→ chat_with_tools()
→ 模型返回 tool_calls 或最终回答
→ 有 tool_calls 时执行 execute_tool()
→ assistant 消息写入历史
→ tool 结果写入历史
→ 继续下一轮模型决策
→ 无 tool_calls 时返回最终回答
→ 达到 max_steps 时返回 max_steps_reached
```

核心边界：

- `max_steps` 默认 8，不接受客户端传入。
- 每轮模型调用都携带完整 tools 定义。
- `arguments` 先经过 JSON 解析，再由 `execute_tool()` 做 Pydantic 校验。
- 每个工具结果都写入 `trace`，并转换成 role=tool 消息。
- Usage 累计所有外层模型调用，但不包含工具内部嵌套模型调用。
- 参数解析失败、未知工具和工具异常都会返回安全 Observation，不直接暴露内部异常。

## 12. 四个真实 JobFit 工具

```text
extract_job_requirements
→ JD 提取职责、必备技能和加分项

extract_resume_sections
→ 简历原文提取结构化分段

search_resume_evidence
→ 岗位要求 + 简历分段返回原文证据

assess_requirement_match
→ 证据结果返回三态评估和 summary
```

四个工具均通过 `ToolRegistry` 注册，使用 Pydantic 参数模型，并通过 `execute_tool()` 执行。

---

# 四、当前技术栈与选型原因

## 1. FastAPI

用途：

- HTTP API。
- 请求校验。
- 依赖注入。
- 全局异常处理。
- OpenAPI/Swagger 文档。
- 流式响应。

选型原因：

- 与 Pydantic 和异步 Python 结合自然。
- 适合快速构建可测试的 AI/Agent 后端。
- 后续可以继续承载 RAG、工具调用和工作流接口。

## 2. Uvicorn

用途：

- 运行 ASGI 应用。
- 本机和容器环境启动 FastAPI。

选型原因：

- FastAPI 官方常用运行方式。
- 支持异步请求和流式响应。

## 3. Pydantic

用途：

- 请求模型。
- 响应数据模型。
- 配置模型。
- 参数校验。
- 生成模型输出 JSON Schema。
- 将模型返回文本校验为可信的 Pydantic 对象。

当前使用位置：

```text
app/schemas/auth.py
app/schemas/chat.py
app/schemas/extraction.py
app/schemas/resume.py
app/schemas/evidence.py
app/schemas/matching.py
app/schemas/tool_calling.py
app/core/config.py
```

结构化输出边界：

- JSON 模式只保证返回 JSON 对象。
- 字段名、类型和约束由 Pydantic 强制校验。
- 校验失败不会返回空业务对象，而是反馈并重试或抛出 `StructuredOutputError`。

## 4. python-dotenv

用途：

- 本地开发时读取 `.env`。

安全边界：

- `.env` 只存在本地或被部署平台注入。
- `.env` 已被 `.gitignore` 忽略。
- `.env.example` 只能包含空值和示例配置。

## 5. OpenAI Python SDK

用途：

- 通过 OpenAI 兼容接口访问 DeepSeek。

当前使用：

```text
AsyncOpenAI
client.chat.completions.create()
response_format={"type": "json_object"}
stream=True
stream_options={"include_usage": True}
tools=[...]
tool_choice="auto"
```

选型原因：

- DeepSeek 支持 OpenAI 兼容 API。
- 后续更换兼容服务商时主要修改环境变量。

## 6. DeepSeek API

当前配置：

```dotenv
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
```

说明：

- `deepseek-flash` 是 API model 标识。
- `DeepSeek V4 Flash` 是展示名称，不能直接作为当前接口的 `model` 参数。
- API Key 只能通过环境变量读取。

## 7. pytest 与 httpx

用途：

- 自动化测试 FastAPI 接口。
- 使用 `TestClient` 在进程内调用 ASGI 应用。
- 使用 mock 替代真实模型调用。

测试依赖单独放在：

```text
requirements-dev.txt
```

## 8. Tool Registry 与 ToolSpec

用途：

- 将工具名、说明、参数模型和异步 handler 集中注册。
- 防止未注册工具执行。
- 拒绝重复工具名。
- 从 Pydantic `model_json_schema()` 生成模型工具定义。
- 统一参数校验、用户注入、超时、异常脱敏和调用日志。

选型原因：

- 先手写注册机制，避免被 Agent 框架 API 绑定。
- 白名单比动态导入安全。
- 参数模型和 OpenAI 工具定义来自同一份契约，避免漂移。

## 9. asyncio.wait_for

用途：

- 为异步工具 handler 设置 30 秒执行上限。
- 超时后取消协程并返回安全错误。

选型原因：

- Python 标准库，无新增依赖。
- 能避免外部服务或数据库长期挂起占满请求资源。
- 超时与普通业务异常可分别记录和返回。

## 10. 三态证据评估

用途：

- 区分强证据、部分证据和证据不足。
- 防止把“未检索到证据”误判为“明确不匹配”。

选型原因：

- 当前只有关键词检索基线，语义判断能力有限。
- 三态结果能保留不确定性，后续再接入更可靠的 RAG 与语义分析。

---

# 五、当前目录结构

```text
jobfit_agent/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── response.py
│   ├── dependencies/
│   │   └── auth.py
│   ├── routers/
│   │   ├── health.py
│   │   ├── users.py
│   │   ├── chat.py
│   │   ├── jobs.py
│   │   └── agent.py
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── extraction.py
│   │   ├── resume.py
│   │   ├── evidence.py
│   │   ├── matching.py
│   │   ├── tool_calling.py
│   │   └── react_agent.py
│   ├── services/
│   │   ├── llm.py
│   │   ├── extraction.py
│   │   ├── resume_extraction.py
│   │   ├── evidence_search.py
│   │   ├── matching.py
│   │   ├── tool_calling.py
│   │   └── react_agent.py
│   └── tools/
│       ├── base.py
│       ├── registry.py
│       ├── executor.py
│       └── jobfit.py
├── scripts/
│   ├── verify_step05_tool_calling.py
│   ├── verify_step05_resume_tool_calling.py
│   ├── verify_step05_evidence_tool_calling.py
│   ├── verify_step05_assess_tool_calling.py
│   └── verify_step06_react_agent.py
├── tests/
│   ├── conftest.py
│   ├── test_chat_api.py
│   ├── test_llm_service.py
│   ├── test_llm_tools_service.py
│   ├── test_extraction_service.py
│   ├── test_job_extraction_api.py
│   ├── test_resume_extraction_service.py
│   ├── test_evidence_search_service.py
│   ├── test_matching_service.py
│   ├── test_tool_registry.py
│   ├── test_jobfit_tools.py
│   ├── test_tool_calling_service.py
│   ├── test_react_agent_service.py
│   └── test_react_agent_api.py
├── docs/
│   └── PROJECT_GUIDE.md
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── README.md
└── test_main.http
```

真实 `.env` 属于本地私密文件，不进入版本控制。

---

# 六、模块职责

## `app/main.py`

- 创建 FastAPI 应用。
- 注册全局异常处理。
- 注册 health、users、chat、jobs、agent 路由。
- 将 JobFit ReAct 匹配请求转发到服务层。

## `app/core/config.py`

- 加载 `.env`。
- 读取环境变量。
- 校验 LLM 配置。
- 向其他模块提供统一 `settings`。

## `app/core/exceptions.py`

- 定义 `AppError`。
- 定义 `LLMServiceError`，表示模型服务调用失败。
- 定义 `StructuredOutputError`，表示模型调用成功但最终输出无效。
- 定义全局异常响应处理函数。

## `app/core/response.py`

- 定义统一成功响应结构。
- 保证接口返回 `code/message/data`。

## `app/dependencies/auth.py`

- 读取 Bearer Token。
- 校验当前演示 Token。
- 返回演示用户对象。

当前限制：

- Token 固定为 `demo-token`。
- 未连接数据库。
- 未实现真实用户登录和身份隔离。

## `app/routers/chat.py`

- 接收并校验聊天消息。
- 调用 LLM 服务层。
- 返回非流式 JSON。
- 将流式事件转换为 SSE。

## `app/schemas/chat.py`

定义：

```text
ChatMessage
ChatRequest
TokenUsage
ChatResult
LLMStreamEvent
ToolCall
LLMWithToolsResult
```

## `app/services/llm.py`

职责：

- 创建异步 DeepSeek 客户端。
- 封装非流式聊天。
- 封装流式聊天。
- 封装 `chat_with_tools()`，验证普通文本或工具调用响应。
- 将 OpenAI SDK 工具调用对象转换为项目自己的 `ToolCall`。
- 统计 Token 和耗时。
- 将 SDK 异常转换为 `LLMServiceError`。

重要边界：

- 路由不直接接触 `AsyncOpenAI`。
- 服务层不直接返回完整 SDK Response。
- 第三方异常不原样返回客户端。
- `chat()` 保持普通文本模式。
- `chat_json()` 增加 JSON object 模式。
- 两者复用 `_chat()` 的异常映射、Usage 和耗时统计。
- `chat_with_tools()` 不解析 `arguments`，也不执行工具，只负责拿取和稳定化模型响应。

## `app/routers/jobs.py`

- 接收并校验 `JobExtractionRequest`。
- 使用 Bearer Token 鉴权。
- 调用 `services.extraction.extract_job()`。
- 统一返回 `success_response`。
- 不捕获 `LLMServiceError` 和 `StructuredOutputError`，交给全局处理器。

## `app/schemas/extraction.py`

- `JobExtraction`：模型输出契约。
- `JobExtractionRequest`：HTTP 请求契约。
- 拒绝空值、纯空白和超过 20000 字符的 JD。
- 清理 JD 首尾空白后才进入服务层。

## `app/services/extraction.py`

- 构造包含 JSON Schema 的 Prompt。
- 调用 `chat_json()`。
- 使用 `model_validate_json()` 校验模型输出。
- 校验失败时生成精简反馈并追加到消息历史。
- 最多调用模型两次；`max_attempts` 由服务端控制。
- 最终失败抛出 `StructuredOutputError` 并保留异常链。

## `app/schemas/resume.py`

- `ResumeSection`：分段类型、标题和原文内容契约。
- `ResumeExtraction`：简历分段列表契约。
- 限制分段类型、长度和额外字段。

## `app/services/resume_extraction.py`

- 构造简历分段 Prompt 和 JSON Schema。
- 使用 `chat_json()` 调用模型。
- 使用 Pydantic 校验 `ResumeExtraction`。
- 空响应或校验失败最多重试两次，API 异常不进入结构重试。
- 不允许总结、润色、推断或补全简历原文。

## `app/schemas/evidence.py`

- `EvidenceSearchRequest`：检索工具参数契约。
- `EvidenceItem`：保留 section 类型、标题、原文和匹配分。
- `RequirementEvidence`：岗位要求与证据列表。
- `EvidenceSearchResult`：要求和结果的顺序对应契约。

## `app/services/evidence_search.py`

- 当前使用英文 token、中文整串和双字 n-gram 做关键词匹配。
- 过滤低于最低阈值的弱证据。
- 按分数降序和原始 section 顺序稳定排序。
- 没有足够证据时返回空列表。
- 不调用 LLM，不访问数据库。

## `app/schemas/matching.py`

- `MatchStatus`：`strong_match`、`partial_match`、`insufficient_evidence`。
- `RequirementAssessment`：单条要求的状态、理由和证据。
- `MatchSummary`：三种状态的统计。
- `MatchAssessmentResult`：评估列表与汇总一致性契约。

## `app/services/matching.py`

- 没有 evidence 时标记 `insufficient_evidence`。
- 最高证据分达到阈值时标记 `strong_match`。
- 有证据但未达到阈值时标记 `partial_match`。
- 不输出 `not_match`，不把证据不足解释成明确不满足。
- 汇总数量必须与 assessment 状态一致。

## `app/schemas/tool_calling.py`

- `ToolExecutionRecord`：记录一次工具调用和结果。
- `ToolCallingResult`：返回最终回答、工具调用、执行记录、Usage 和总耗时。

## `app/services/tool_calling.py`

- 完成一次工具往返。
- 第一次调用 `chat_with_tools()`。
- 无工具调用时直接返回模型文本。
- 有工具调用时解析 `arguments`，调用 `execute_tool()`，构造 assistant 和 tool 消息，再调用 `chat()`。
- 最多调用模型两次，不实现 ReAct 循环。
- 汇总外层两次调用的 Usage；内层工具模型 Usage 尚未汇总。

## `app/tools/base.py`

- `ToolContext`：由后端注入 `CurrentUser`。
- `ToolSpec`：绑定工具名、描述、参数模型和异步 handler。
- `openai_definition()`：从 Pydantic 参数模型生成 OpenAI 工具定义。

## `app/tools/registry.py`

- `ToolRegistry` 工具白名单。
- 注册工具并拒绝重复工具名。
- 按名称查找工具。
- 输出模型可使用的工具定义列表。

## `app/tools/executor.py`

- 拒绝未注册工具。
- 要求参数是 JSON 对象。
- 使用对应 Pydantic 模型校验参数。
- 注入 `ToolContext`。
- 使用 `asyncio.wait_for()` 限制 handler 最多执行 30 秒。
- 统一返回参数错误、超时、内部异常和非序列化结果的安全错误。
- 记录不含参数值的工具调用日志。

## `app/tools/jobfit.py`

- 注册四个 JobFit 工具。
- 将工具参数模型绑定到既有业务服务。
- 所有 handler 返回 `model_dump(mode="json")` 的 JSON 字典。
- 当前不读取数据库，也不持久化调用记录。

## `scripts/` 下的 STEP 05 验收脚本

- 使用真实 DeepSeek 验证岗位提取、简历分段、证据检索和匹配评估工具。
- 检查工具名、参数、`tool_call_id`、结果结构和最终回答。
- 手工验收脚本不进入 pytest，不自动消耗 API。

## `app/routers/agent.py`

- 暴露 `POST /api/agent/match`。
- 依赖 `get_current_user` 完成 Bearer 鉴权。
- 从可信 `CurrentUser` 构造 `ToolContext`。
- 调用 `run_jobfit_agent()` 并返回统一成功响应。
- 不接受客户端传入 `max_steps` 或用户身份字段。

## `app/schemas/react_agent.py`

- 定义 `JobFitAgentRequest`。
- 定义 `ReactToolExecution` 和 `ReactAgentResult`。
- 限制 JD 和简历长度，拒绝空值和额外字段。

## `app/services/react_agent.py`

- 定义 `run_react_loop()` 通用循环。
- 构造 assistant/tool 消息。
- 累计 Token Usage 和耗时。
- 执行工具并记录 trace。
- 提供 JobFit 消息构造和 `run_jobfit_agent()` 入口。

## `scripts/verify_step06_react_agent.py`

- 使用真实 DeepSeek 运行完整 JobFit ReAct 链路。
- 校验四个工具调用、顺序、结果结构、最终三态回答、Usage 和 trace。
- 只输出安全摘要，不打印完整简历参数和工具正文。

## `tests/test_react_agent_service.py`

- 验证直接回答、多轮工具调用、max_steps、非法 JSON 和未知工具。
- 使用假 `chat_with_tools`，不访问真实模型。

## `tests/test_react_agent_api.py`

- 验证鉴权、请求清洗、长度限制、额外字段、成功响应和异常映射。
- 替换路由中的 `run_jobfit_agent()`，不访问真实模型。

---

# 七、请求数据流

## 1. 非流式聊天

```text
客户端
→ POST /api/chat
→ FastAPI 校验 ChatRequest
→ get_current_user 校验 Bearer Token
→ chat_endpoint 将 Pydantic 消息转成 dict
→ llm.chat()
→ AsyncOpenAI 调用 DeepSeek
→ 读取 answer、usage
→ 计算 latency_ms
→ 返回 ChatResult
→ success_response 统一包装
→ 返回 JSON
```

## 2. 流式聊天

```text
客户端
→ POST /api/chat/stream
→ FastAPI 校验 ChatRequest
→ get_current_user 校验 Bearer Token
→ 返回 StreamingResponse
→ event_generator 异步迭代 llm.stream_chat()
→ DeepSeek 返回 delta content
→ 服务层产生 LLMStreamEvent
→ 路由将事件编码为 SSE
→ 最终发送 usage 和 [DONE]
```

## 3. 岗位 JD 结构化提取

```text
客户端
→ POST /api/jobs/extract
→ get_current_user 校验 Bearer Token
→ FastAPI 校验 JobExtractionRequest
→ 清理 JD 首尾空白
→ extract_job() 构造带 JSON Schema 的 Prompt
→ chat_json() 启用 JSON object 模式
→ AsyncOpenAI 调用 DeepSeek
→ JobExtraction.model_validate_json()
→ 成功：返回 JobExtraction
→ 失败：反馈错误，最多重试一次
→ 仍失败：抛出 StructuredOutputError
→ success_response 统一包装
→ 返回 JSON
```

## 4. ReAct 岗位匹配

```text
客户端
→ POST /api/agent/match
→ get_current_user 校验 Bearer Token
→ FastAPI 校验 JobFitAgentRequest
→ ToolContext(current_user=current_user)
→ run_jobfit_agent()
→ build_jobfit_react_messages()
→ 循环调用 chat_with_tools()
→ 模型返回 tool_calls 或最终回答
→ execute_tool() 校验并执行注册工具
→ assistant/tool 消息加入 messages
→ ReactToolExecution 写入 trace
→ 累计外层 Token Usage 和 latency_ms
→ completed 或 max_steps_reached
→ success_response()
```

---

# 八、错误处理设计

统一异常基类：

```text
AppError
```

异常边界：

```text
LLMServiceError
→ 模型服务调用失败，例如认证、限流、超时、网络异常。
→ 请求没有得到正常响应，立即向上传播，不进入 JSON 校验重试。

StructuredOutputError
→ 模型调用成功，但内容为空或多次校验仍不符合结构化 Schema。
→ 保留最后一次 ValidationError/RuntimeError 作为异常链。

工具执行错误
→ 未注册工具、参数不是 JSON 对象、Pydantic 校验失败、超时、handler 异常或结果不可序列化。
→ execute_tool() 转换为稳定字典结果，不把内部异常原文交给模型。
→ 当前没有 HTTP 路由，因此不直接映射为 HTTP 状态码。
```

状态码映射：

```text
AuthenticationError       → 500
RateLimitError            → 503
APITimeoutError           → 504
APIConnectionError        → 502
BadRequestError           → 500
其他 APIStatusError       → 502
StructuredOutputError     → 502
```

设计原则：

- 保留服务端异常链：`raise ... from exc`。
- 客户端只收到安全、可理解的信息。
- 不把原始 DeepSeek SDK 异常或完整 Pydantic 错误返回给用户。
- 调用失败和输出失败必须保持不同错误类型，避免把服务故障伪装成空提取结果。

ReAct 循环错误边界：

- 外层模型认证、限流、超时、连接和状态错误继续映射为 `LLMServiceError`。
- 工具参数不是合法 JSON 时返回 `工具参数解析失败`。
- 工具名不在白名单时返回 `工具未注册`。
- 工具参数不符合 Pydantic 模型时返回 `工具参数校验失败`。
- 工具 handler 抛出内部异常时只返回 `工具执行失败`，不暴露原始异常。
- 业务不存在、证据不足等预期失败作为 Observation 返回模型。
- 达到 `max_steps` 时停止调用模型并返回 `max_steps_reached`。

---

# 九、安全设计

当前已做到：

- API Key 只从环境变量读取。
- 本地 `.env` 被 `.gitignore` 忽略。
- `.env.example` 不含真实 Key。
- 第三方异常不直接返回客户端。
- 流式错误使用安全错误事件。
- 文档明确提示 Key 泄漏后的处理方式。
- JD 提取接口需要 Bearer 鉴权。
- JD 最大长度为 20000 字符，纯空白输入在请求层拒绝。
- 简历原文最大长度为 50000 字符，岗位要求数量、长度和证据数量受 Pydantic 限制。
- `max_attempts` 不接受客户端输入，避免放大 Token 成本和请求延迟。
- 工具调用必须经过白名单注册表。
- 工具参数必须通过对应 Pydantic 模型校验。
- 用户身份由 `ToolContext` 注入，模型不能决定 `user_id`。
- 工具 handler 默认最多执行 30 秒。
- 工具日志不记录 JD、简历、报告正文和完整参数值。
- 内部工具异常不会以原始异常文本返回给模型。

当前仍未完成：

- 固定 `demo-token` 未改成环境变量。
- 没有真实用户数据库和简历版本表。
- 当前四个工具处理请求直接传入的数据，因此尚未发生数据库归属查询。
- 后续 `get_resume_profile` 和 `save_match_report` 必须按 `current_user.id` 过滤数据。
- 没有请求频率限制。
- 没有公网访问保护。
- 没有工具调用日志的数据库持久化和生产级审计。

因此当前项目不适合作为公开生产服务。STEP 06 只做部署就绪检查，STEP 07 后建立私有 staging，STEP 12 后正式公网部署。

ReAct 服务安全边界：

- 用户身份只来自 Bearer 鉴权后的 `CurrentUser`，请求体不能传入 `user_id`。
- 工具名必须存在于 `ToolRegistry` 白名单。
- 工具参数必须经过 Pydantic 校验。
- `max_steps` 由后端控制，客户端不能提高循环上限。
- JD 和简历以数据边界标签传给模型，并明确不作为指令执行。
- `trace` 只包含工具调用和 Observation，不记录模型隐藏思维链。
- trace 中可能包含用户提交的 JD、简历和工具结果，不能未经脱敏直接写生产日志或发送给其他用户。

---

# 十、测试策略

自动化测试文件：

```text
tests/conftest.py
tests/test_chat_api.py
tests/test_llm_service.py
tests/test_llm_tools_service.py
tests/test_extraction_service.py
tests/test_job_extraction_api.py
tests/test_resume_extraction_service.py
tests/test_evidence_search_service.py
tests/test_matching_service.py
tests/test_tool_registry.py
tests/test_jobfit_tools.py
tests/test_tool_calling_service.py
tests/test_react_agent_service.py
tests/test_react_agent_api.py
```

测试方式：

- 使用 `TestClient` 在进程内调用 ASGI 应用。
- 使用 mock、假客户端或假服务替代真实模型调用。
- 不依赖真实网络和 API 额度。
- 覆盖 API 调用参数、结构化输出、有限重试、鉴权、统一错误映射、工具注册、工具参数校验、超时、日志脱敏和单次工具编排。
- 使用 fake client、fake service 和 fake handler 替代真实模型、数据库或外部服务。
- ReAct 服务测试替换 `chat_with_tools()`，接口测试替换路由中的 `run_jobfit_agent()`。

当前测试范围：

```text
健康检查
无 Token 401
非法消息 422
非流式成功响应
模型异常映射
SSE content/usage/[DONE]
SSE 错误事件
普通模式不携带 response_format
JSON 模式携带 response_format
JobExtraction 首次成功
校验失败后携带反馈重试
空响应后携带反馈重试
两次无效输出后抛出 StructuredOutputError
LLMServiceError 原样传播
JD 提取接口鉴权
JD 空值、纯空白、超长 422
JD 提取成功响应
StructuredOutputError → 502
LLMServiceError → 503
chat_with_tools 文本与工具调用映射
一个和多个工具调用的稳定数据结构
空白模型响应拒绝
简历首次成功与校验失败重试
简历空响应重试和 StructuredOutputError
证据中英文匹配、阈值过滤、排序和空证据
匹配三态评估与 summary 一致性
工具注册表重复名和未知工具拒绝
四个 JobFit 工具参数、结果和描述
工具超时、异常脱敏和日志不记录参数值
单次 Function Calling 消息顺序、tool_call_id 和 Usage 汇总
ReAct 直接回答、多轮工具调用和消息历史
ReAct max_steps 终止和非法参数拒绝
ReAct 非法 JSON、未知工具和 Usage 累计
ReAct HTTP 鉴权、请求清洗、长度限制和异常映射
```

测试不能替代真实模型 smoke test。

真实模型调用用于验证：

- API Key 是否有效。
- Base URL 是否正确。
- 模型名是否正确。
- 网络是否可达。
- JSON 模式参数是否被兼容接口支持。
- SSE 经过网络和代理后是否正常。
- 模型是否会正确选择四个 JobFit 工具。
- 模型工具参数是否保持原始输入。
- 工具结果返回后，模型是否保留“证据不足”的不确定性。
- 模型是否按依赖顺序调用四个 JobFit 工具。
- ReAct 最终回答是否包含三态标记并可追溯到 trace。

---

# 十一、当前限制与后续依赖

当前已经具备：

- 四个真实工具和工具注册机制
- 单次 Function Calling 往返
- 最小 ReAct 循环、执行轨迹和最大步数保护
- `POST /api/agent/match` 与参数/接口测试
- 关键词证据检索基线
- 三态证据充分性评估

还没有实现：

- 真实用户登录和数据库身份体系
- 简历管理和版本控制
- PDF 解析
- 岗位 JD 与结构化结果持久化
- 会话状态和任务恢复
- Embedding、向量检索和重排
- `get_resume_profile` 和 `save_match_report` 的数据库实现
- 匹配报告和差距分析完整闭环
- 工具调用记录的数据库持久化
- 包含内层工具模型调用的统一 Token 成本统计
- Agent 执行过程的 SSE 流式输出
- 正式评估数据集和正式公网部署

这些功能将在后续 STEP 按依赖顺序实现，不删除已有能力。

---

# 十二、各功能完整链路

本节按层记录每个功能的完整链路，避免只描述“实现了什么”，而忽略数据如何经过各层。

## 1. 一次 Function Calling 往返

```text
用户消息
→ run_tool_calling_once()
→ registry.openai_definitions()
→ chat_with_tools()
→ 外层模型返回 content 或 tool_calls
→ 无 tool_calls：直接返回文本
→ 有 tool_calls：解析 arguments
→ execute_tool()
→ ToolRegistry 按名称白名单查找
→ Pydantic 校验参数
→ 注入 ToolContext.current_user
→ asyncio.wait_for() 执行 handler
→ 工具结果转成 role=tool 消息
→ assistant tool_calls 与 tool 消息加入历史
→ chat() 第二次调用模型
→ 合并外层 Usage
→ 返回 ToolCallingResult
```

## 2. 岗位 JD 提取

HTTP：

```text
客户端
→ POST /api/jobs/extract
→ Bearer 鉴权
→ JobExtractionRequest 校验
→ extract_job()
→ Prompt + JobExtraction JSON Schema
→ chat_json()
→ DeepSeek JSON object 模式
→ Pydantic 校验
→ 空响应/校验失败最多反馈重试一次
→ StructuredOutputError 或 JobExtraction
→ success_response
→ 客户端
```

工具：

```text
外层模型
→ extract_job_requirements
→ 工具参数校验 job_description
→ handler 调用 extract_job()
→ JobExtraction.model_dump(mode="json")
→ 工具结果返回外层模型
```

## 3. 简历分段提取

```text
简历原文
→ extract_resume_sections()
→ 空值和 50000 字符边界校验
→ Prompt + ResumeExtraction JSON Schema
→ chat_json()
→ DeepSeek 返回 JSON
→ Pydantic 校验 ResumeExtraction
→ 空响应/校验失败最多反馈重试一次
→ 保留原文的 ResumeSection 列表
→ 工具层转为 JSON 字典
```

## 4. 简历证据检索

```text
岗位要求列表 + 简历分段列表
→ EvidenceSearchRequest 校验
→ 每条 requirement 单独检索
→ 英文 token、中文整串和双字 n-gram
→ title + content 匹配评分
→ 过滤低于最低阈值的弱证据
→ 按 score 降序、原始顺序稳定排序
→ 截取每条要求最多 3 条证据
→ RequirementEvidence 列表
→ EvidenceSearchResult
```

没有命中时保留空 evidence，不借用其他要求的证据，也不生成原文。

## 5. 要求匹配评估

```text
EvidenceSearchResult
→ 逐条读取 RequirementEvidence
→ evidence 为空：insufficient_evidence
→ 最高分 >= 0.6：strong_match
→ 有证据但低于 0.6：partial_match
→ 保留全部 EvidenceItem
→ 汇总三种状态数量
→ MatchAssessmentResult
```

该结果只表达当前证据充分性，不表达候选人真实能力结论。

## 6. 工具执行边界

```text
模型 tool_calls
→ tool_name 白名单查询
→ arguments JSON 对象检查
→ ToolSpec.args_model Pydantic 校验
→ ToolContext 注入当前用户
→ asyncio.wait_for(handler, 30 秒)
→ handler 返回 JSON 字典
→ json.dumps 可序列化检查
→ 统一 ok/result 或 ok/error
→ 安全日志
```

日志只包含工具名、用户 ID、参数键、状态和耗时。

## 7. ReAct 岗位匹配

```text
JobFitAgentRequest
→ get_current_user
→ ToolContext
→ build_jobfit_react_messages()
→ run_react_loop()
→ chat_with_tools()
→ 模型决策 tool_calls 或最终内容
→ execute_tool()
→ ReactToolExecution 写入 trace
→ tool 消息回传模型
→ 重复直至 completed
→ 达到 max_steps 时 max_steps_reached
→ ReactAgentResult
→ success_response()
```

失败的完整链路：

```text
模型参数不是 JSON
→ 不执行工具
→ 构造“工具参数解析失败” Observation
→ 写入 tool 消息和 trace
→ 模型基于失败结果继续决策

工具名未注册
→ execute_tool 返回“工具未注册”
→ 写入 tool 消息和 trace

工具 handler 异常
→ execute_tool 捕获并返回“工具执行失败”
→ 不暴露内部异常文本
```

---

# 十三、部署节奏

采用“持续保持可部署、分阶段公网验证”的策略。

```text
STEP 02：建立 Dockerfile、健康检查和环境变量基线
STEP 03：只做私密 smoke test（可选），公网部署延期
STEP 04～05：继续维护依赖、镜像和测试，不新增公开环境
STEP 06：只做部署就绪检查和本地 HTTP 验收，不公开部署
STEP 07：加入数据库和 Redis 后建立第一次私有 staging
STEP 08：在私有 staging 更新带 RAG 的作品集版本
STEP 11：LangGraph 工作流完成后更新私有 staging
STEP 12：安全、评估、监控和性能优化完成后正式公网部署
```

本阶段 Docker 状态：

- 没有新增第三方依赖。
- 没有新增端口。
- 没有新增数据库、Redis、向量库或其他容器。
- `Dockerfile` 和 `docker-compose.yml` 无需修改。
- 部署延期；STEP 06 只做部署就绪检查，STEP 07 后建立私有 staging，STEP 12 后正式公网部署。

为什么 STEP 06 不公开部署：

- 当前仍使用公开的 `demo-token`。
- 没有真实登录、限流、配额和并发保护。
- 一次 ReAct 请求可能触发多轮模型和嵌套工具调用，成本较高。
- 没有持久化、用户归属、监控和告警。

为什么 STEP 07 后先做私有 staging：

- 数据库、Redis、持久化和恢复能力已经具备。
- 只部署到私有环境或白名单访问。
- 用于验证真实部署架构，不开放任意用户。

为什么 STEP 12 后正式公网部署：

- 强随机 Token、限流和配额已经完成。
- 权限隔离、Prompt Injection 防护和成本统计已经完成。
- 可观测性、健康检查和告警已经完成。

部署前必须完成：

- 将 `demo-token` 改为环境变量中的强随机值。
- 确认 `.env` 不进入镜像和仓库。
- 确认 API Key 不输出到日志。
- 验证 SSE 经过平台代理不被完全缓冲。
- 增加基本限流和访问保护。

---

# 十四、STEP 变更记录

## STEP 01：Python 基础

完成：

- 类型标注
- Pydantic
- 异常处理
- async / await
- 命令行练习

## STEP 02：FastAPI 服务骨架

完成：

- FastAPI
- APIRouter
- 依赖注入
- Bearer 演示鉴权
- 统一响应与异常
- Dockerfile
- docker-compose

## STEP 03：大模型 API

完成：

- DeepSeek API 调通
- OpenAI 兼容客户端
- 环境变量配置
- 非流式聊天
- 多轮消息
- Token Usage
- 调用耗时
- SSE 流式聊天
- 流式 Usage 和错误事件
- pytest 自动化测试
- README 和 HTTP 示例
- Git feature 分支、合并和 tag

暂缓：

- 部署延期；STEP 06 只做部署就绪检查，STEP 07 后建立私有 staging，STEP 12 后正式公网部署。

## STEP 04：Prompt 与结构化输出

完成：

- 学习 Prompt 的角色、数据边界、任务和输出约束。
- 使用 Pydantic 定义 `JobExtraction` 模型输出契约。
- 使用 `model_json_schema()` 生成 JSON Schema 并加入 Prompt。
- 在模型服务层新增 `chat_json()`。
- 使用 `response_format={"type": "json_object"}` 请求 JSON 对象。
- 使用 `model_validate_json()` 执行 Pydantic 硬校验。
- 对空响应和校验失败执行最多两次的结构化输出尝试。
- 校验失败反馈只包含字段、错误类型和说明。
- 调用失败保持 `LLMServiceError`，输出失败最终抛出 `StructuredOutputError`。
- 新增 `POST /api/jobs/extract` 接口。
- 请求层校验空值、纯空白和 20000 字符上限。
- `max_attempts` 由服务端控制，不接受客户端输入。
- 增加服务层、提取层和接口层自动化测试。
- 更新 README、HTTP 示例和项目指南。

为什么使用 JSON 模式与 Pydantic 双重边界：

- JSON 模式保证响应至少是 JSON 对象，不保证字段名、类型和约束。
- Pydantic 才能把模型输出变成可信的后端数据结构。
- 只有两类错误同时分开处理，才能避免把 API 故障当成空提取结果。

暂缓：

- 数据库持久化、简历结构化提取和结构化版本保存按依赖顺序在后续 STEP 实现。
- 部署延期；STEP 06 只做部署就绪检查，STEP 07 后建立私有 staging，STEP 12 后正式公网部署。

## STEP 05：Function Calling 与工具注册

完成：

- 学习 OpenAI 兼容 Function Calling 的消息闭环。
- 新增 `chat_with_tools()`，稳定转换模型文本或 `ToolCall`。
- 新增 `ToolContext`、`ToolSpec` 和 `ToolRegistry`。
- 新增统一 `execute_tool()`，负责参数校验、用户注入、超时和异常脱敏。
- 注册四个真实工具：
  - `extract_job_requirements`
  - `extract_resume_sections`
  - `search_resume_evidence`
  - `assess_requirement_match`
- 新增简历分段提取服务。
- 新增关键词证据检索基线。
- 新增三态要求匹配评估。
- 新增单次 Function Calling 编排，最多调用模型两次。
- 工具调用日志不记录参数值和结果正文。
- 增加真实 DeepSeek 手工验收脚本。
- 四个工具均完成真实模型调用验收。

为什么这样设计：

- 模型只负责提出工具调用，后端负责校验、权限上下文和执行。
- 工具 Schema 和 Pydantic 参数模型来自同一契约，避免漂移。
- 工具结果必须先变成 JSON 兼容字典，才能安全进入模型消息。
- 没有证据时返回 `insufficient_evidence`，不伪造“明确不匹配”。
- 当前关键词检索是可测试基线，STEP 08 再升级为混合检索和 RAG。

暂缓：

- `get_resume_profile` 和 `save_match_report` 依赖数据库、用户归属和事务，延期到 STEP 07。
- STEP 06 已通过 `/api/agent/match` 暴露 ReAct 业务流程，原单次 Function Calling 服务继续保留为基线。
- 内层模型调用的 Usage 尚未合并到外层统计。
- 工具调用日志尚未持久化。
- 部署延期；STEP 06 只做部署就绪检查，STEP 07 后建立私有 staging，STEP 12 后正式公网部署。

## STEP 06：最小 ReAct 循环与 HTTP 接入

完成：

- 在 study-roads 手写独立订单物流 ReAct Agent，完成真实模型多轮工具调用。
- 新增 `ReactToolExecution` 和 `ReactAgentResult`。
- 新增 `run_react_loop()`，实现 assistant/tool 消息闭环、trace、Usage 累计和最大步数终止。
- 新增 JobFit system prompt、消息构造和 `run_jobfit_agent()` 入口。
- 新增 `POST /api/agent/match`，使用 Bearer 鉴权和 `ToolContext`。
- 拒绝客户端传入 `max_steps`，后端默认最多 8 轮模型决策。
- 增加服务层测试和接口测试。
- 新增真实 DeepSeek 手工验收脚本，四个工具均成功调用并生成三态最终回答。
- 更新 README、PROJECT_GUIDE、HANDOFF 和部署节奏。

为什么这样设计：

- 模型只提出工具调用，真正执行仍由后端白名单和 Pydantic 校验控制。
- 每轮都保留 assistant/tool 消息，模型才能基于前序 Observation 继续决策。
- trace 提供可审计执行过程，但明确不记录隐藏思维链。
- max_steps 同时控制延迟、成本和无限循环风险。
- 嵌套工具调用的 Usage 尚不能统一统计，因此明确记录为当前限制。

暂缓：

- 数据库、Redis、任务恢复和报告持久化在 STEP 07 实现。
- RAG 混合检索和重排在 STEP 08 实现。
- 内层工具模型 Usage 合并、SSE Agent 过程和正式评估在后续 STEP 实现。
- STEP 06 只做部署就绪检查；STEP 07 后私有 staging，STEP 12 后正式公网部署。

---

# 十四点五、STEP 07：状态、记忆、持久化与 SSE

完成：

- 设计并创建 PostgreSQL `jobfit` Schema 九张表。
- 增加 SQLAlchemy 2.x 异步模型、AsyncSession 和 Repository。
- 使用 Alembic 建立 baseline migration 并验证空库升级与现有库 stamp。
- 持久化用户、简历版本、岗位、会话消息、分析任务、报告和工具调用记录。
- 使用用户所有权过滤、软删除过滤、行锁和短事务保护数据安全。
- Redis 任务状态缓存、TTL、Cache-Aside、`SET NX EX` 运行锁和 Lua owner-token 释放。
- 工具调用 started/success/validation_error/timeout/error/unknown_tool 审计。
- 可恢复 interrupted 状态、attempt 重试和失败终态。
- ReAct 过程事件和 SSE 接口。
- 客户端断开时保存 interrupted 状态。
- 会话上下文压缩和 assistant 回答落库。
- Docker Compose 配置 PostgreSQL、Redis 和应用迁移启动命令。

关键边界：

- PostgreSQL 是权威事实来源，Redis 只做缓存、短期状态和锁。
- 模型不能提交 user_id、task_id、报告版本或任务终态。
- SSE 不包含隐藏思维链，只包含可审计状态、工具事件和最终回答。
- 同一任务报告版本追加保存，不覆盖历史。
- 真实 Redis 已本地验收；Docker staging 和公网开放留待后续阶段。

# 十五、每个大 STEP 完成后的维护清单

每完成一个大 STEP，必须更新本文档：

1. 更新“最后更新”日期。
2. 更新当前 STEP 状态。
3. 添加新功能。
4. 更新接口列表。
5. 更新目录结构。
6. 更新模块职责。
7. 更新请求数据流。
8. 更新技术栈和选型原因。
9. 更新错误处理和安全边界。
10. 更新测试范围。
11. 更新当前限制。
12. 更新部署状态。
13. 在“STEP 变更记录”中增加本次完成了什么、为什么这样做。
14. 更新 README 和 HANDOFF 中的当前状态。
15. 新增功能时必须补充该功能的完整数据链路。

文档原则：

```text
记录为什么这样设计
记录数据如何流动
记录失败如何恢复
记录安全和边界
不要只粘贴代码
不要只写“用了某某技术”
```

---

# 十六、快速恢复上下文

如果几周后重新进入项目，按以下顺序阅读：

```text
1. README.md
2. docs/PROJECT_GUIDE.md
3. app/main.py
4. app/tools/base.py
5. app/tools/registry.py
6. app/tools/executor.py
7. app/tools/jobfit.py
8. app/services/tool_calling.py
9. app/services/llm.py
10. app/services/resume_extraction.py
11. app/services/evidence_search.py
12. app/services/matching.py
13. tests/test_jobfit_tools.py
14. tests/test_tool_calling_service.py
```

重点关注：

```text
当前完成到哪个 STEP
下一项待做功能是什么
哪些配置需要本地环境变量
哪些功能不能公开部署
```

---

# 十七、常用命令

安装运行依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启动服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

检查当前分支：

```powershell
git status --short --branch
```

检查 Key 是否被忽略：

```powershell
git check-ignore -v .env
```
