# JobFit Agent

> 项目全景、模块职责、数据流和 STEP 变更记录见 [docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md)。

基于 RAG 和工具调用的可解释岗位匹配与差距分析 Agent。

## 当前阶段

STEP 04：学习 Prompt 与结构化输出，并接入 JobFit Agent。

当前已经支持：

- `GET /health`：健康检查
- `GET /api/users/me`：演示鉴权与当前用户
- `POST /api/chat`：非流式聊天，返回答案、Token Usage 和耗时
- `POST /api/chat/stream`：SSE 流式聊天，返回内容事件、Usage 事件和结束标记
- `POST /api/jobs/extract`：从岗位 JD 中结构化提取岗位职责、必备技能和加分项

岗位提取接口使用 Prompt、JSON Schema、JSON 模式和 Pydantic 双重校验。模型调用成功但输出为空或不符合 Schema 时，最多尝试两次；认证、限流、超时和网络错误不会进入结构重试。

当前鉴权仍为演示版本：

```http
Authorization: Bearer demo-token
```

真实用户系统将在后续阶段实现。公网部署仍延期到 STEP 06，本阶段不新增公开环境。

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
```

安全要求：

- `.env` 已被 `.gitignore` 忽略。
- 不要把真实 Key 写入代码、截图、聊天或 GitHub。
- 如果 Key 曾经提交到远程仓库，应立即撤销并重新生成。

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

## 自动化测试

安装测试依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

测试使用 mock 或假客户端替代真实模型调用，因此不会消耗 DeepSeek API 额度。

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
