# 简历项目描述：JobFit Agent

## 1. 一句话描述

```text
基于 FastAPI、RAG、工具调用和 LangGraph 的可解释岗位匹配 Agent，
支持简历证据检索、引用校验、Checkpoint、人工确认、失败恢复和成本观测。
```

## 2. 简历 Bullet 版本

### 版本 A：偏 Agent 工程

```text
- 设计并实现 FastAPI Agent 后端，手写 ReAct 循环并迁移到 LangGraph StateGraph，支持多轮工具调用、最大步数、Token Usage 和可审计 trace。
- 基于 PostgreSQL Checkpoint 和 interrupt/Command 实现人工确认、审批、拒绝和中断恢复，确认后追加报告与简历版本。
- 建设 ToolRegistry、ToolExecutor 和 ToolContext 统一工具边界，完成白名单、Pydantic 参数校验、用户隔离、超时控制和工具审计。
```

### 版本 B：偏 RAG

```text
- 构建 PostgreSQL + FastEmbed + Chroma RAG 链路，实现 section-aware chunking、BM25/向量混合召回、RRF 和 Cross-Encoder Rerank。
- 通过 EvidencePack 和 chunk_id 引用校验约束模型结论，只允许引用真实检索证据，证据不足时输出 insufficient_evidence。
- 建立 30 条 RAG 评估集和 Agent 评估集，覆盖召回、引用、任务完成率、工具正确率和无依据建议比例。
```

### 版本 C：偏生产化

```text
- 为 Agent 增加 request_id、结构化日志、任务耗时分解、Token 成本和敏感字段脱敏。
- 增加 Prompt Injection 检测、输入长度限制、HTTP 安全头和工具权限边界。
- 使用 Redis 实现按用户/接口限流、每日请求配额和 Token 配额，统一返回 429 与 Retry-After。
- 读接口与 LLM 消耗接口分离配额策略，Token 配额耗尽后仍可查看历史任务和报告。
```

### 版本 D：全链路演示与部署准备

```text
- 实现岗位 CRUD、任务历史和当前报告查询，打通前端刷新后的状态恢复。
- 使用同源 HTML/CSS/JS 工作台，支持 SSE、人工确认、报告、引用和成本展示。
- 增加单演示账号 JWT 登录，支持会话恢复、退出和 401 自动清理。
- 为 Chroma / FastEmbed 挂载持久化卷，并在 staging 固定单 Uvicorn Worker。
- 提供幂等演示数据脚本，一键创建示例用户、简历和岗位。
```

## 3. 技术栈

```text
Python 3.12
FastAPI
Pydantic
SQLAlchemy Async
PostgreSQL
Alembic
Redis
OpenAI SDK / DeepSeek
LangGraph
LangChain Core
FastEmbed
Chroma
BM25 / RRF / Cross-Encoder
PyJWT
pytest
HTML / CSS / JavaScript
Docker / Docker Compose 配置
```

## 4. 可量化亮点

```text
自动化测试：379 passed
RAG 评估集：30 条
Agent 评估集：15 条
双引擎对比：answer/status/steps/usage/tool_trace/core_events 全部一致
Checkpoint 中断恢复：通过
人工确认修改后追加简历版本：通过
安全、限流、成本、就绪检查：通过
```

## 5. 项目难点

```text
1. Agent 循环容易把模型决策、工具执行和持久化终态混在一起。
   解决：拆分 ReAct、ToolExecutor、Repository 和任务状态。

2. RAG 结论容易编造引用。
   解决：EvidencePack、chunk_id 白名单和保存前引用校验。

3. 人机协作不能一直占用运行锁。
   解决：Checkpoint 持久化状态，interrupt 后释放 Redis 锁，恢复时重新校验。

4. 重试可能重复执行有副作用的工具。
   解决：只重试无副作用决策节点，写操作通过事务、状态和版本追加保护。

5. 成本和风险不可见。
   解决：结构化日志、request_id、任务指标、Usage 聚合、限流和配额。
```

## 6. STAR 回答模板

### Situation

```text
岗位分析通常是一次性 Prompt，结论不可解释，也不能证明引用了哪段简历证据。
```

### Task

```text
搭建一个可运行的 Agent 后端，既能多步工具调用，又能检索简历证据、
保存报告、支持人工确认，并在失败后恢复。
```

### Action

```text
先手写 ReAct 理解底层循环，再用 LangGraph 迁移状态图。
使用 ToolRegistry 统一工具边界，使用 PostgreSQL 和 Chroma 分离事实与向量索引。
使用 EvidencePack 和 chunk_id 引用校验约束结论。
使用 PostgreSQL Checkpoint 实现 interrupt/resume。
最后补充评估、日志、成本、Prompt Injection 防护和限流。
```

### Result

```text
形成可测试、可演示、可继续部署的 Agent 后端原型。
379 条自动化测试通过，Agent/RAG 评估通过，Checkpoint 恢复和人工确认验证通过。
远程 staging 和公网部署保留到 Linux 云服务器阶段。
```

## 7. 面试不要夸大的点

```text
不要说已经完成大规模生产验证
不要说 Prompt Injection 防护 100% 有效
不要说向量数据库是业务事实源
不要把 Multi-Agent 说成必要能力
不要把本地 Docker 配置说成已经公网部署
```
