# JobFit Agent

> 项目全景、模块职责、数据流和 STEP 变更记录见 [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md)。

基于 RAG 和工具调用的可解释岗位匹配与差距分析 Agent。

## 当前阶段

STEP 07：状态、记忆、PostgreSQL/Redis 持久化与 Agent SSE 流式服务。

当前已经支持：

- `GET /health`：健康检查
- `GET /api/users/me`：演示鉴权与当前用户
- `POST /api/chat`：非流式聊天，返回答案、Token Usage 和耗时
- `POST /api/chat/stream`：SSE 流式聊天，返回内容事件、Usage 事件和结束标记
- `POST /api/jobs/extract`：从岗位 JD 中结构化提取岗位职责、必备技能和加分项
- `POST /api/agent/match`：运行兼容版受控 ReAct 岗位匹配分析。
- `POST /api/agent/tasks`：创建可持久化的岗位分析任务。
- `POST /api/agent/tasks/{task_id}/run`：执行持久化任务。
- `GET /api/agent/tasks/{task_id}`：从 Redis/PostgreSQL 查询任务状态。
- `GET /api/agent/tasks/{task_id}/stream`：通过 SSE 返回 Agent 执行事件。

岗位提取接口使用 Prompt、JSON Schema、JSON 模式和 Pydantic 双重校验。模型调用成功但输出为空或不符合 Schema 时，最多尝试两次；认证、限流、超时和网络错误不会进入结构重试。

STEP 05 已增加工具注册与单次 Function Calling 编排基础。当前注册六个真实工具：

- `extract_job_requirements`：从岗位 JD 提取职责、必备技能和加分项。
- `extract_resume_sections`：从简历原文提取教育、项目、技能等结构化分段。
- `search_resume_evidence`：按岗位要求检索简历分段中的原文证据。
- `assess_requirement_match`：根据证据评估 `strong_match`、`partial_match` 或 `insufficient_evidence`。
- `get_resume_profile`：读取当前任务绑定的持久化简历。
- `save_match_report`：暂存并持久化结构化匹配报告。

STEP 06 新增 `app/services/react_agent.py` 和 `POST /api/agent/match`。ReAct 服务最多执行 8 轮模型决策；模型每轮可以选择调用工具或给出最终回答。每次工具调用都会写入 `trace`，所有外层模型调用的 Token Usage 会累计，达到最大步数时返回 `max_steps_reached`。

外层编排的一次工具往返最多调用模型两次；工具 handler 内部可能再次调用模型，例如岗位或简历结构化提取，当前内层模型 Usage 尚未合并到外层统计。工具参数统一使用 Pydantic 校验，用户身份由后端 `ToolContext` 注入，工具 handler 最多执行 30 秒；调用日志只记录工具名、用户 ID、参数键、状态和耗时，不记录 JD、简历或报告正文。当前有数据库持久化工具等待 STEP 07 实现。

当前鉴权仍为演示版本：

```http
Authorization: Bearer demo-token
```

真实用户系统将在后续阶段实现。STEP 06 只做部署就绪检查，不新增公开环境；STEP 07 后建立私有 staging，STEP 12 后正式公网部署。

## 环境准备

要求 Python 3.12。

```powershell
cd "D:\agentstudy\jobfit_agent"

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后在本地 `.env` 中填写真实 DeepSeek API Key：

```dotenv
APP_ENV=development
LLM_API_KEY=你的真实Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
DATABASE_URL=postgresql+asyncpg://jobfit_app:你的密码@127.0.0.1:5432/jobfit_dev
REDIS_URL=redis://127.0.0.1:6379/0
```

安全要求：

- `.env` 已被 `.gitignore` 忽略。
- 不要把真实 Key 写入代码、截图、聊天或 GitHub。
- 如果 Key 曾经提交到远程仓库，应立即撤销并重新生成。

## 本地依赖服务

确保 PostgreSQL 17 正在运行，并启动本地 Redis：

```powershell
& "D:\agentstudy\runtime\start-redis.ps1"
```

初始化演示用户：

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_dev_user.py
```

数据库结构由 Alembic 管理：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## 本地启动

```powershell
cd "D:\agentstudy\jobfit_agent"

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

服务地址：

```text
http://127.0.0.1:8000
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

## 非流式聊天

请求：

```http
POST /api/chat
Authorization: Bearer demo-token
Content-Type: application/json
```

```json
{
  "messages": [
    {
      "role": "user",
      "content": "用一句话解释 Agent。"
    }
  ]
}
```

响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "answer": "Agent 是……",
    "usage": {
      "prompt_tokens": 20,
      "completion_tokens": 30,
      "total_tokens": 50
    },
    "latency_ms": 1234
  }
}
```

## 流式聊天

接口使用 SSE：

```http
POST /api/chat/stream
Authorization: Bearer demo-token
Content-Type: application/json
```

PowerShell 验证：

```powershell
$headers = @{
    Authorization = "Bearer demo-token"
}

$body = @{
    messages = @(
        @{
            role = "user"
            content = "用大约300个字解释什么是 Agent。"
        }
    )
} | ConvertTo-Json -Depth 5

curl.exe -N -X POST "http://127.0.0.1:8000/api/chat/stream" `
    -H "Authorization: Bearer demo-token" `
    -H "Content-Type: application/json" `
    -d $body
```

事件格式：

```text
data: {"type":"content","content":"第一段"}

data: {"type":"content","content":"第二段"}

data: {"type":"usage","usage":{"prompt_tokens":20,"completion_tokens":30,"total_tokens":50},"latency_ms":1234}

data: [DONE]
```

## 岗位 JD 结构化提取

请求：

```http
POST /api/jobs/extract
Authorization: Bearer demo-token
Content-Type: application/json
```

请求体：

```json
{
  "job_description": "负责 FastAPI 后端服务开发，要求熟悉 Python、Pydantic 和异步编程。"
}
```

说明：

- `job_description` 不能为空或只包含空白。
- 最大长度为 20000 个字符。
- 客户端不能传入重试次数，`max_attempts` 由服务端控制。
- 服务最多调用模型两次。
- 第一次输出不符合 Pydantic 契约时，会把校验错误作为下一轮反馈。

成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "responsibilities": [
      "负责 FastAPI 后端服务开发"
    ],
    "required_skills": [
      "熟悉 Python、Pydantic 和异步编程"
    ],
    "nice_to_have": []
  }
}
```

主要错误：

- `422`：岗位描述为空、纯空白或超过长度限制。
- `502`：模型调用成功，但输出为空或多次校验仍不符合 Schema。
- `503`：模型服务限流或暂时不可用。
- `504`：模型调用超时。
- 上游认证和网络异常不会伪装成空提取结果。

## JobFit ReAct 岗位匹配

请求：

```http
POST /api/agent/match
Authorization: Bearer demo-token
Content-Type: application/json
```

请求体：

```json
{
  "job_description": "负责 FastAPI 后端开发，要求熟悉 Python。",
  "resume_text": "熟悉 Python 和 FastAPI，完成过课程项目。"
}
```

说明：

- `job_description` 最大长度为 20000 个字符。
- `resume_text` 最大长度为 50000 个字符。
- 两个字段都会去掉首尾空白，空值和纯空白返回 `422`。
- 客户端不能传入 `max_steps`，轮数上限由后端控制，默认是 8。
- 模型需要依次调用岗位提取、简历分段、证据检索和匹配评估工具。

成功响应包含：

```text
answer        最终匹配回答
status        completed 或 max_steps_reached
steps         实际执行的模型决策轮数
max_steps     后端允许的最大轮数
trace         每次工具调用的参数和结果
usage         外层模型调用累计 Token Usage
latency_ms    整个 ReAct 循环耗时
```

主要错误：

- `401`：没有 Bearer Token 或 Token 无效。
- `422`：JD/简历为空、超长，或客户端传入额外字段。
- `5xx`：外层模型服务异常由统一异常处理器映射。

## 持久化任务、Redis 与 SSE

STEP 07 增加：

- PostgreSQL 九表模型与 Alembic 迁移。
- Repository、事务边界和用户所有权检查。
- 分析任务、报告版本、消息和工具调用审计。
- Redis 任务状态缓存、TTL、分布式运行锁和用户隔离。
- 短事务 prepare/execute/finalize 执行流程。
- 可恢复 interrupted 状态与失败分类。
- Agent SSE 事件、heartbeat、客户端断开处理和上下文压缩。

持久化任务示例：

```http
POST /api/agent/tasks
Authorization: Bearer demo-token
Content-Type: application/json
```

```json
{
  "job_id": 1,
  "resume_version_id": 1,
  "conversation_id": null
}
```

执行和流式观察：

```text
POST /api/agent/tasks/{task_id}/run
GET  /api/agent/tasks/{task_id}/stream
```

SSE 事件包括：

```text
task_started
step_started
tool_started
tool_finished
content
task_completed
task_interrupted
task_failed
heartbeat
```

AI 不输出隐藏思维链，SSE 只包含可审计状态、工具元信息和最终回答。

Docker Compose 已配置 PostgreSQL、Redis 和应用服务。当前本机真实 Redis 已完成本地验收；Docker staging 等 Docker 环境可用后执行。

## 自动化测试

安装测试依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试使用 mock 或假客户端替代真实模型调用，因此不会消耗 DeepSeek API 额度。ReAct 服务测试位于 `tests/test_react_agent_service.py`，接口测试位于 `tests/test_react_agent_api.py`。

真实模型手工验收：

```powershell
cd D:\agentstudy\jobfit_agent
.\.venv\Scripts\python.exe .\scripts\verify_step06_react_agent.py
```

该脚本会真实调用 DeepSeek，验收岗位提取、简历分段、证据检索、匹配评估、trace 和最终回答。

## Docker

构建并启动：

```bash
docker compose up --build
```

后台启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

容器内服务监听 8000 端口，宿主机访问：

```text
http://127.0.0.1:8000
```

STEP 06 只验证部署就绪，不公开部署。当前机器没有安装 Docker，实际镜像构建和私有 staging 放到 STEP 07；正式公网部署放到 STEP 12。
