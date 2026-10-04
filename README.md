# JobFit Agent

> 项目全景、模块职责、数据流和 STEP 变更记录见 [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md)。

基于 RAG 和工具调用的可解释岗位匹配与差距分析 Agent。

STEP 14 新增能力：

- 新增岗位持久化 CRUD API，Agent 任务可直接使用数据库 `job_id`。
- 新增任务历史列表和当前报告查询 API，刷新页面后可恢复结果。
- 新增同源静态工作台 `/app`，覆盖简历、岗位、任务、SSE、人工确认和报告。
- 新增演示账号登录和 HS256 JWT；开发环境兼容 `demo-token`，生产环境禁用。
- 新增 Chroma 与 FastEmbed 持久化 Volume，生产服务固定单 Uvicorn Worker。
- 新增幂等演示数据脚本，创建示例用户、简历和岗位。


## 项目文档

- [项目全景与维护文档](docs/PROJECT_GUIDE.md)
- [系统架构](docs/ARCHITECTURE.md)
- [演示指南](docs/DEMO_GUIDE.md)
- [面试问答](docs/INTERVIEW_QA.md)
- [简历项目描述](docs/RESUME_PROJECT.md)
- [RAG 评估](docs/RAG_EVALUATION.md)
- [Agent 评估](docs/AGENT_EVALUATION.md)
- [可观测性](docs/OBSERVABILITY.md)
- [成本统计](docs/COST_TRACKING.md)
- [安全设计](docs/SECURITY.md)
- [限流设计](docs/RATE_LIMIT.md)
- [部署说明](docs/DEPLOYMENT.md)
- [简历文件接入](docs/RESUME_INGESTION.md)

## 当前阶段

STEP 14：岗位 API、任务/报告查询、最小前端、JWT 登录、部署持久化和演示数据。

当前已经支持：

- `GET /`：跳转到同源工作台
- `GET /app`：静态前端工作台
- `GET /health`：健康检查
- `POST /api/auth/login`：演示账号登录并签发 JWT
- `GET /api/auth/me`：解析 JWT 或开发 Token
- `GET /api/users/me`：当前用户
- `POST /api/jobs`、`GET /api/jobs`、`GET /api/jobs/{job_id}`：岗位持久化 CRUD
- `GET /api/agent/tasks`：任务历史
- `GET /api/agent/tasks/{task_id}/report`：当前报告
- `POST /api/chat`：非流式聊天，返回答案、Token Usage 和耗时
- `POST /api/chat/stream`：SSE 流式聊天，返回内容事件、Usage 事件和结束标记
- `POST /api/jobs/extract`：从岗位 JD 中结构化提取岗位职责、必备技能和加分项
- `POST /api/agent/match`：运行兼容版受控 ReAct 岗位匹配分析。
- `POST /api/agent/tasks`：创建可持久化的岗位分析任务。
- `POST /api/agent/tasks/{task_id}/run`：执行持久化任务。
- `GET /api/agent/tasks/{task_id}`：从 Redis/PostgreSQL 查询任务状态。
- `GET /api/agent/tasks/{task_id}/stream`：通过 SSE 返回手写 ReAct 执行事件。
- `POST /api/agent/tasks/{task_id}/graph/run`：执行 LangGraph 版岗位分析任务。
- `POST /api/agent/tasks/{task_id}/graph/resume`：提交人工确认并恢复 Graph 任务。
- `GET /api/agent/tasks/{task_id}/graph/confirmation`：查询待确认报告。
- `GET /api/agent/tasks/{task_id}/graph/stream`：通过 SSE 返回 Graph 节点和执行事件。

STEP 12 新增能力：

- 15 条固定 Agent 评估集：任务完成率、工具正确率、引用、拒答、确认恢复和无依据建议。
- request_id、结构化日志、任务耗时分解和敏感字段脱敏。
- 外层与内层模型 Usage 合并、Token 成本估算和成本报表。
- Prompt Injection 检测、安全提示、边界标签转义和 HTTP 安全头。
- Redis 按用户/接口限流、每日请求配额、每日 Token 配额和 429 响应。
- `/ready` 就绪检查：PostgreSQL、Checkpoint、Redis。
- 生产 Docker Compose、非 root Dockerfile 和部署配置检查。


STEP 08 新增 RAG 能力：

- PostgreSQL `knowledge_chunks`：持久化简历 Chunk、版本、位置和索引状态。
- FastEmbed `BAAI/bge-small-zh-v1.5` + Chroma：本地 Embedding 和向量检索。
- BM25 关键词召回 + RRF 混合排序。
- `BAAI/bge-reranker-base` 重排、EvidencePack 和 chunk_id 引用校验。
- 持久化 Agent 自动完成 Chunking、向量索引、混合检索和引用报告。
- 30 条固定评估集和 Markdown/JSON 评估报告。

STEP 11 新增能力：

- 显式 LangGraph StateGraph：`prepare_run → load_context → agent_decide → execute_tools → assess_evidence → human_confirmation → save_report → finalize`。
- PostgreSQL Checkpoint：`thread_id = jobfit-task-{task_id}-attempt-{attempt}`。
- 人工确认：支持 approve、revise、reject 和中断恢复。
- 修改确认后可追加新的 `resume_version`。
- `agent_decide` 节点级重试，只重试临时 LLM、网络和超时错误。
- SSE 增加 Graph 节点、重试、等待确认和恢复事件。
- 保留手写 ReAct，并通过契约脚本验证两版最终回答、工具轨迹、Usage 和核心事件一致。


岗位提取接口使用 Prompt、JSON Schema、JSON 模式和 Pydantic 双重校验。模型调用成功但输出为空或不符合 Schema 时，最多尝试两次；认证、限流、超时和网络错误不会进入结构重试。

STEP 05 已增加工具注册与单次 Function Calling 编排基础。当前注册六个真实工具：

- `extract_job_requirements`：从岗位 JD 提取职责、必备技能和加分项。
- `extract_resume_sections`：从简历原文提取教育、项目、技能等结构化分段。
- `search_resume_evidence`：RAG 任务执行 BM25 + 向量混合召回和 Rerank；旧流程可传入 sections 回退。
- `assess_requirement_match`：根据证据评估 `strong_match`、`partial_match` 或 `insufficient_evidence`。
- `get_resume_profile`：读取当前任务绑定的持久化简历。
- `save_match_report`：暂存并持久化结构化匹配报告。

STEP 06 新增 `app/services/react_agent.py` 和 `POST /api/agent/match`。ReAct 服务最多执行 8 轮模型决策；模型每轮可以选择调用工具或给出最终回答。每次工具调用都会写入 `trace`，所有外层模型调用的 Token Usage 会累计，达到最大步数时返回 `max_steps_reached`。

外层编排的一次工具往返最多调用模型两次；工具 handler 内部可能再次调用模型，例如岗位或简历结构化提取，当前内层模型 Usage 尚未合并到外层统计。工具参数统一使用 Pydantic 校验，用户身份由后端 `ToolContext` 注入，工具 handler 最多执行 30 秒；调用日志只记录工具名、用户 ID、参数键、状态和耗时，不记录 JD、简历或报告正文。数据库持久化、报告版本和工具审计已于 STEP 07 完成。

当前鉴权仍为演示版本：

```http
Authorization: Bearer demo-token
```

真实用户系统将在后续阶段实现。远程私有 staging 延期到 Linux 云服务器，STEP 12 后完成正式公网部署。

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
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh-v1.5
EMBEDDING_CACHE_PATH=.cache/fastembed
VECTOR_INDEX_PATH=.cache/chroma
VECTOR_COLLECTION_NAME=jobfit_resume_chunks_v1
RERANKER_MODEL_NAME=BAAI/bge-reranker-base
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

数据库结构由 Alembic 管理：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe .\scripts\setup_langgraph_checkpoint.py
```

初始化演示用户、示例简历和示例岗位：

```powershell
.\.venv\Scripts\python.exe .\scripts\seed_demo_data.py
```

## 本地启动

```powershell
cd "D:\agentstudy\jobfit_agent"

.\.venv\Scripts\python.exe .\scripts\run_dev_server.py
```

服务地址：

```text
http://127.0.0.1:8000/app
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

该脚本会真实调用 DeepSeek，验收岗位提取、RAG 证据检索、匹配评估、trace、引用报告和最终回答。

运行 RAG 检索评估：

```powershell
.\\.venv\\Scripts\\python.exe .\\scripts\\evaluate_rag.py
```

评估报告：

```text
docs/RAG_EVALUATION.md
docs/rag_evaluation_results.json
```

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
