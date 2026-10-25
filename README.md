# JobFit Agent

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-429%20passed-brightgreen)
![RAG](https://img.shields.io/badge/RAG-BM25%20%2B%20Vector%20%2B%20Rerank-blueviolet)

> 可解释的岗位匹配 Agent 后端：基于 RAG 检索简历证据、Function Calling 调用工具、LangGraph 编排工作流，输出每条结论都可追溯到原文 chunk 的匹配报告。

## 为什么做这个

大模型直接做岗位分析有两个问题：**结论不可解释、容易编造简历依据**。JobFit Agent 把流程拆成检索、工具调用、编排、引用校验和评估，让每条匹配结论都能指回真实简历证据；证据不足时明确输出 `insufficient_evidence`，而不是硬编一个结论。

## 核心亮点

- **RAG 检索链路**：BM25 + 向量混合召回 → RRF → Cross-Encoder 精排 → 阈值拒答；100 条评估集上回答样本引用精确率 **0.80**、覆盖率 **0.74**、正确弃答率 **0.75**。
- **工具调用**：Function Calling + ToolRegistry / ToolExecutor，统一白名单、Pydantic 参数校验、30s 超时与调用审计。
- **工作流编排**：手写 ReAct → LangGraph StateGraph，PostgreSQL Checkpoint + interrupt/Command 支持中断恢复；按风险触发人工确认，低风险任务自动放行。
- **可靠性与工程化**：chunk_id 引用白名单、三态匹配、Prompt Injection 隔离、Redis 限流 / Token 配额、结构化日志、429 条自动化测试、Docker 一键启动。

## 系统架构

```text
Client (/app)
   │
FastAPI
   ├─ Auth / Rate limit / Token quota (Redis)
   ├─ Agent Task API + SSE
   └─ LangGraph StateGraph
        prepare_run → load_context → agent_decide ⇄ execute_tools
             → assess_evidence → (risk-based) human_confirmation
             → save_report → finalize
   │
ToolExecutor (whitelist / Pydantic / 30s timeout / audit)
   ├─ RAG: BM25 + vector → RRF → Cross-Encoder rerank → EvidencePack
   └─ PostgreSQL / Chroma / Checkpoint
```

## 快速开始

### Docker

```bash
cp .env.example .env
# 填写 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
docker compose up --build
```

打开 <http://127.0.0.1:8000/app>，使用 `.env` 中的演示账号登录。

### 本地运行

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

> 需要先启动 PostgreSQL 和 Redis；Chroma 与 FastEmbed 使用本地缓存目录。

## 评估结果

### RAG（100 条，含 20 条负例）

| 指标 | 值 | 一句话 |
| --- | ---: | --- |
| 混合召回 Recall@5 | 0.9500 | 混合召回比单路更全 |
| 有效回答引用精确率 | 0.8028 | 给出证据的 59 条里，引用对得上原文 |
| 覆盖率 | 0.7375 | 80 条正例里 59 条敢答 |
| 正确弃答率 | 0.7500 | 20 条负例里 15 条正确拒答 |
| 整体引用精确率（拒答计 0） | 0.5921 | 拒答计 0 的保守口径 |
| 65/35 holdout 引用精确率 | 0.4762 | 换一批数据会掉，泛化有落差 |

### Agent 真实执行（50 条 case，执行 45 条）

| 指标 | 值 | 一句话 |
| --- | ---: | --- |
| 任务完成率 | 1.0000 | 45 条都跑到终态 |
| 必要工具覆盖率 | 1.0000 | 该调的 5 个工具没漏 |
| 工具成功率 | 1.0000 | 工具执行本身没报错 |
| 工具 F1 | 0.9557 | 工具选择整体稳定 |
| 匹配状态 F1 | 0.8704（过 0.85） | 三态判定达标，但仍有波动 |
| 弃答准确率 | 0.9556 | 证据不足时基本能正确拒答 |
| 引用有效率 | 0.9556 | 引用基本落在证据白名单内 |
| 证据支撑率 | 1.0000 | 结论都有证据 |
| 无依据建议率 | 0.0000 | 没有无证据建议 |
| 平均步数 / 平均 Token | 5.73 / 18,930 | 单次任务约 1.9 万 Token |
| p95 延迟 | 17,658 ms | 适合原型，不适合高并发 |

> 5 条未覆盖：3 条人工确认/中断契约 + 2 条 mock-only 循环 case；45 条真实执行覆盖 90% 的 case。

### 自动化测试

```text
429 passed
```

## 已知限制

- 评估集规模仍偏小（RAG 100 条、Agent 50 条 / 45 条真实执行），属于原型验证，不是大规模 benchmark。
- RAG 阈值 -2.9 在原 30 条子集上标定，holdout 表现有落差，尚未做大规模独立 holdout。
- `match_status_f1` 0.8704 已过 0.85 门槛，但 happy_path / mixed 类别仍偏低，三态边界还有提升空间。
- 未做长期 Memory、MCP、多 Agent；当前是单 Agent + 受控工具链。
- 未完成公网部署，提供本地端到端验证与 Docker 部署资产。

## 项目结构

```text
app/
  graphs/jobfit/   LangGraph 工作流、状态、节点、重试
  services/        RAG、工具调用、编排、评估、限流
  tools/           ToolRegistry / ToolExecutor / JobFit 工具
  schemas/         Pydantic 契约
  routers/         FastAPI 接口
tests/             429 条自动化测试
docs/              架构、评估、部署、面试问答
scripts/           评估与验收脚本
```

## 文档

- [系统架构](docs/ARCHITECTURE.md)
- [项目全景](docs/PROJECT_GUIDE.md)
- [RAG 评估](docs/RAG_EVALUATION.md)
- [Agent 真实执行评估](docs/AGENT_EVALUATION_LIVE.md)
- [持久化 RAG 真实执行评估](docs/AGENT_EVALUATION_PERSISTED_LIVE.md)
- [评估体系 V2](docs/EVALUATION_V2.md)
- [部署说明](docs/DEPLOYMENT.md)
- [安全设计](docs/SECURITY.md)
- [历史 STEP 与接口细节](docs/CHANGELOG.md)