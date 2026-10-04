# JobFit Agent 演示指南

## 1. 演示目标

在 5～10 分钟内展示：

```text
FastAPI Agent 后端
手写 ReAct
LangGraph StateGraph
RAG 混合检索和引用
PostgreSQL Checkpoint
人工确认和中断恢复
失败重试
SSE
评估、可观测性、成本、安全和限流
```

---

## 2. 演示前准备

```powershell
cd "D:\agentstudy\jobfit_agent"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe .\scripts\setup_langgraph_checkpoint.py
.\.venv\Scripts\python.exe -m pytest -q
```

启动 Redis 和 FastAPI：

```powershell
& "D:\agentstudy\runtime\start-redis.ps1"
.\.venv\Scripts\python.exe .\scripts\run_dev_server.py
```

打开展示页：

```text
http://127.0.0.1:8000/app
```

Swagger：

```text
http://127.0.0.1:8000/docs
```

---

## 3. 五分钟版本

### 第 1 分钟：服务与就绪检查

```text
GET /health
GET /ready
```

讲解：

```text
/health 只判断进程存活
/ready 检查 PostgreSQL、Checkpoint 和 Redis
```

### 第 2 分钟：结构化输出和工具边界

```text
POST /api/jobs/extract
```

展示：

```text
Prompt
JSON Schema
Pydantic 校验
结构错误重试
工具白名单
```

### 第 3 分钟：RAG 证据链

展示：

```text
knowledge_chunks
FastEmbed + Chroma
BM25 + 向量召回
RRF
Rerank
EvidencePack
chunk_id 引用校验
```

运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_rag.py
```

### 第 4 分钟：LangGraph 和 Checkpoint

```text
POST /api/agent/tasks
POST /api/agent/tasks/{task_id}/graph/run
GET  /api/agent/tasks/{task_id}/graph/confirmation
POST /api/agent/tasks/{task_id}/graph/resume
```

讲解：

```text
human_confirmation 使用 interrupt
Command(resume=...) 恢复
thread_id = jobfit-task-{task_id}-attempt-{attempt}
```

### 第 5 分钟：评估和工程化

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_agent.py
.\.venv\Scripts\python.exe .\scripts\report_agent_cost.py
.\.venv\Scripts\python.exe .\scripts\compare_step11_engines.py
```

展示：

```text
Agent 评估指标
Token 成本和延迟
手写 ReAct 与 LangGraph 行为一致
```

---

## 4. 十分钟完整版本

```text
1. 项目背景和用户问题
2. 系统架构图
3. 普通聊天和 SSE
4. JD 结构化提取
5. 工具注册与统一执行边界
6. 手写 ReAct 循环
7. LangGraph 状态图
8. RAG 混合检索和 Rerank
9. 引用校验和 EvidencePack
10. PostgreSQL Checkpoint
11. 人工确认和恢复
12. 失败重试
13. 评估、成本、可观测性
14. 安全和限流
15. 部署资产和限制
```

---

## 5. 演示命令

运行完整测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Agent 评估：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_agent.py
```

RAG 评估：

```powershell
.\.venv\Scripts\python.exe .\scripts\evaluate_rag.py
```

双引擎对比：

```powershell
.\.venv\Scripts\python.exe .\scripts\compare_step11_engines.py
```

Checkpoint 验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_step11_checkpoint.py
```

Graph Agent 验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_step11_graph_agent.py
```

安全和限流验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_step12_security.py
.\.venv\Scripts\python.exe .\scripts\verify_step12_rate_limit.py
```

部署配置检查：

```powershell
.\.venv\Scripts\python.exe .\scripts\check_deployment_config.py --strict --connect
```

---

## 6. 演示注意事项

```text
不要展示真实 API Key
不要展示完整简历和 JD 正文截图
不要宣称已经完成公网部署
不要说 Checkpoint 是 Redis 保存的
不要把 Chroma 说成事实数据库
不要把 Prompt Injection 检测说成 100% 防护
```

可以诚实的表达：

```text
远程 staging 和公网部署需要 Linux 云服务器，
当前已完成本机测试、部署资产和依赖就绪检查。
```
