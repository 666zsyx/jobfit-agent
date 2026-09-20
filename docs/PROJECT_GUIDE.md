# JobFit Agent 项目全景与维护文档

> 最后更新：2026-09-20
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

当前项目处于早期阶段，已经完成模型 API、聊天接口和岗位 JD 结构化提取，尚未实现完整岗位匹配业务。

---

# 二、当前状态

```text
STEP 01：完成
STEP 02：完成
STEP 03：完成，公网部署延期到 STEP 06
STEP 04：功能、测试、文档完成，Git 待收尾
```

当前代码分支：

```text
feature/step-04-structured-output
```

STEP 04 的代码、测试和文档已完成，当前等待 Git 提交、合并和 tag。

STEP 03 对应版本：

```text
tag: step-03-llm-api
commit: 6d32d56
```

公网部署延期原因：

- 当前仍使用固定 `demo-token`。
- 该 Token 出现在源码和文档中，直接公网部署有 API 余额被滥用风险。
- STEP 06 完成后项目才具备结构化输出、工具调用和最小 ReAct 循环，更适合作为第一版公开测试环境。

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
│   │   └── jobs.py
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── chat.py
│   │   └── extraction.py
│   └── services/
│       ├── llm.py
│       └── extraction.py
├── tests/
│   ├── conftest.py
│   ├── test_chat_api.py
│   ├── test_llm_service.py
│   ├── test_extraction_service.py
│   └── test_job_extraction_api.py
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
- 注册 health、users、chat、jobs 路由。

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
```

## `app/services/llm.py`

职责：

- 创建异步 DeepSeek 客户端。
- 封装非流式聊天。
- 封装流式聊天。
- 统计 Token 和耗时。
- 将 SDK 异常转换为 `LLMServiceError`。

重要边界：

- 路由不直接接触 `AsyncOpenAI`。
- 服务层不直接返回完整 SDK Response。
- 第三方异常不原样返回客户端。
- `chat()` 保持普通文本模式。
- `chat_json()` 增加 JSON object 模式。
- 两者复用 `_chat()` 的异常映射、Usage 和耗时统计。

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
→ 模型调用成功，但内容为空或多次校验仍不符合 JobExtraction Schema。
→ 保留最后一次 ValidationError/RuntimeError 作为异常链。
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
- `max_attempts` 不接受客户端输入，避免放大 Token 成本和请求延迟。
- 不向客户端返回完整 Pydantic 校验错误。

当前仍未完成：

- 固定 `demo-token` 未改成环境变量。
- 没有真实用户数据库。
- 没有用户级数据隔离。
- 没有请求频率限制。
- 没有公网访问保护。
- 没有生产级日志与审计。

因此当前项目不适合作为公开生产服务，公网部署继续延期到 STEP 06。

---

# 十、测试策略

自动化测试文件：

```text
tests/conftest.py
tests/test_chat_api.py
tests/test_llm_service.py
tests/test_extraction_service.py
tests/test_job_extraction_api.py
```

测试方式：

- 使用 `TestClient` 在进程内调用 ASGI 应用。
- 使用 mock、假客户端或假服务替代真实模型调用。
- 不依赖真实网络和 API 额度。
- 覆盖 API 调用参数、结构化输出、有限重试、鉴权和统一错误映射。

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
```

测试不能替代真实模型 smoke test。

真实模型调用用于验证：

- API Key 是否有效。
- Base URL 是否正确。
- 模型名是否正确。
- 网络是否可达。
- JSON 模式参数是否被兼容接口支持。
- SSE 经过网络和代理后是否正常。

---

# 十一、当前限制与后续依赖

还没有实现：

- 真实用户登录
- 数据库
- 简历管理和版本控制
- PDF 解析
- 岗位 JD 管理
- 简历结构化提取
- 结构化提取结果持久化
- Function Calling
- ReAct 循环
- 会话状态
- RAG 与证据检索
- 匹配报告
- 调用日志
- Token 成本和延迟持续统计
- 评估
- 公网部署

这些功能将在后续 STEP 按依赖顺序实现，不删除已有能力。

---

# 十二、部署节奏

采用“持续保持可部署、分阶段公网验证”的策略。

```text
STEP 02：建立 Dockerfile、健康检查和环境变量基线
STEP 03：只做私密 smoke test（可选），公网部署延期
STEP 04～05：继续维护依赖、镜像和测试，不新增公开环境
STEP 06：第一次公开测试部署
STEP 07：加入数据库和 Redis 后更新部署
STEP 08：部署带 RAG 的作品集版本
STEP 11：LangGraph 工作流完成后更新线上版本
STEP 12：生产化、安全、监控和性能优化
```

为什么 STEP 06 首次公开部署：

- STEP 03 只是通用聊天能力。
- STEP 06 已经具备结构化输出、工具调用和最小 ReAct 循环。
- 此时项目第一次具备明确 Agent 特征。

为什么 STEP 08 作为作品集版本：

- RAG、证据检索和岗位匹配开始形成项目差异化。
- 更适合简历、演示和面试讲解。

部署前必须完成：

- 将 `demo-token` 改为环境变量中的强随机值。
- 确认 `.env` 不进入镜像和仓库。
- 确认 API Key 不输出到日志。
- 验证 SSE 经过平台代理不被完全缓冲。
- 增加基本限流和访问保护。

---

# 十三、STEP 变更记录

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

- 公网部署，计划在 STEP 06 完成第一次公开测试。

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
- 公网部署仍延期到 STEP 06。

---

# 十四、每个大 STEP 完成后的维护清单

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

# 十五、快速恢复上下文

如果几周后重新进入项目，按以下顺序阅读：

```text
1. README.md
2. docs/PROJECT_GUIDE.md
3. app/main.py
4. app/routers/jobs.py
5. app/services/extraction.py
6. app/services/llm.py
7. app/schemas/extraction.py
8. tests/test_job_extraction_api.py
9. tests/test_extraction_service.py
10. tests/test_llm_service.py
```

重点关注：

```text
当前完成到哪个 STEP
下一项待做功能是什么
哪些配置需要本地环境变量
哪些功能不能公开部署
```

---

# 十六、常用命令

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
