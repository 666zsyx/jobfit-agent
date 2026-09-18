# JobFit Agent 项目全景与维护文档

> 最后更新：2026-09-18
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

当前项目处于早期阶段，已经完成模型 API 与聊天接口，尚未实现完整岗位匹配业务。

---

# 二、当前状态

```text
STEP 01：完成
STEP 02：完成
STEP 03：功能完成
STEP 03：测试与文档完成
STEP 03：Git 与 tag 完成
STEP 03：公网部署延期到 STEP 06
STEP 04：未开始
```

当前代码分支：

```text
main
```

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

当前使用位置：

```text
app/schemas/auth.py
app/schemas/chat.py
app/core/config.py
```

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
│   │   └── chat.py
│   ├── schemas/
│   │   ├── auth.py
│   │   └── chat.py
│   └── services/
│       └── llm.py
├── tests/
│   ├── conftest.py
│   └── test_chat_api.py
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
- 注册 health、users、chat 路由。

## `app/core/config.py`

- 加载 `.env`。
- 读取环境变量。
- 校验 LLM 配置。
- 向其他模块提供统一 `settings`。

## `app/core/exceptions.py`

- 定义 `AppError`。
- 定义 `LLMServiceError`。
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

---

# 八、错误处理设计

统一异常基类：

```text
AppError
```

模型服务异常：

```text
LLMServiceError
```

状态码映射：

```text
AuthenticationError     → 500
RateLimitError          → 503
APITimeoutError         → 504
APIConnectionError      → 502
BadRequestError         → 500
其他 APIStatusError     → 502
```

设计原则：

- 保留服务端异常链：`raise ... from exc`。
- 客户端只收到安全、可理解的信息。
- 不把原始 DeepSeek SDK 异常返回给用户。

---

# 九、安全设计

当前已做到：

- API Key 只从环境变量读取。
- 本地 `.env` 被 `.gitignore` 忽略。
- `.env.example` 不含真实 Key。
- 第三方异常不直接返回客户端。
- 流式错误使用安全错误事件。
- 文档明确提示 Key 泄漏后的处理方式。

当前仍未完成：

- 固定 `demo-token` 未改成环境变量。
- 没有真实用户数据库。
- 没有用户级数据隔离。
- 没有请求频率限制。
- 没有公网访问保护。
- 没有生产级日志与审计。

因此当前项目不适合作为公开生产服务。

---

# 十、测试策略

自动化测试文件：

```text
tests/conftest.py
tests/test_chat_api.py
```

测试方式：

- 使用 `TestClient` 在进程内调用 ASGI 应用。
- 使用 mock 替换真实 LLM 调用。
- 不依赖真实网络和 API 额度。
- 覆盖成功、鉴权、校验、异常、SSE 和结束标记。

当前测试范围：

```text
健康检查
无 Token 401
非法消息 422
非流式成功响应
模型异常映射
SSE content/usage/[DONE]
SSE 错误事件
```

测试不能替代真实模型 smoke test。

真实模型调用用于验证：

- API Key 是否有效。
- Base URL 是否正确。
- 模型名是否正确。
- 网络是否可达。
- SSE 经过网络和代理后是否正常。

---

# 十一、当前限制与后续依赖

还没有实现：

- 真实用户登录
- 数据库
- 简历管理和版本控制
- PDF 解析
- 岗位 JD 管理
- 结构化岗位要求提取
- Function Calling
- ReAct 循环
- 会话状态
- RAG 与证据检索
- 匹配报告
- 调用日志
- 成本统计
- 评估
- 公网部署

这些功能将在后续 STEP 按依赖顺序实现，不删除已有能力。

---

# 十二、部署节奏

采用“持续保持可部署、分阶段公网验证”的策略。

```text
STEP 02：建立 Dockerfile、健康检查和环境变量基线
STEP 03：只做私密 smoke test（可选），公网部署延期
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
4. app/routers/chat.py
5. app/services/llm.py
6. app/schemas/chat.py
7. tests/test_chat_api.py
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
