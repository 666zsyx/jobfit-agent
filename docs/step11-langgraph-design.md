# STEP 11 LangGraph 重构设计

> 状态：设计冻结稿
>
> 创建日期：2026-10-03
>
> 分支：feature/step-11-langgraph
>
> 基线：main@2e2cd0d

---

## 1. 目标

STEP 11 使用 LangGraph 重构现有 JobFit Agent 的任务执行层，增加：

```text
StateGraph
Checkpoint
人工确认
中断恢复
失败重试
手写 ReAct / LangGraph 对比
```

本步骤遵循：

```text
迁移分层边界，不重写业务服务。
```

不删除现有手写 ReAct 实现。

---

## 2. 非目标

本步骤不处理：

```text
Multi-Agent
Kubernetes 或微服务拆分
公网部署
远程 staging
WSL、Virtual Machine Platform、Docker Desktop 修复
生产级认证、限流和配额
完整 STEP 09～10 源码定向学习
```

远程私有 staging 继续延期到 Linux 云服务器。

---

## 3. 当前基线

现有持久化主链路：

```text
POST /api/agent/tasks
→ 创建 analysis_tasks
→ POST /api/agent/tasks/{task_id}/run
→ 获取 Redis 运行锁
→ PostgreSQL 短事务生成运行快照
→ RAG 准备
→ run_react_loop
→ save_match_report
→ 保存报告和工具审计
→ completed / interrupted / failed
→ 释放 Redis 运行锁
```

现有可复用能力：

```text
LLMService
ToolRegistry
ToolExecutor
RAG services
Repositories
PostgreSQL 事务边界
Redis 运行锁和短期状态缓存
AgentEvent / SSE
引用校验
报告版本追加
工具调用审计
```

LangGraph 节点只能编排这些能力，不能绕过它们直接访问数据库。

---

## 4. 双引擎边界

保留两套引擎：

```text
legacy
  /api/agent/tasks/{task_id}/run
  app/services/persisted_agent.py
  app/services/react_agent.py

langgraph
  /api/agent/tasks/{task_id}/graph/run
  /api/agent/tasks/{task_id}/graph/status
  /api/agent/tasks/{task_id}/graph/resume
  /api/agent/tasks/{task_id}/graph/stream
  app/graphs/jobfit/
```

边界规则：

```text
旧接口行为保持不变
新接口明确标识为 LangGraph 路径
同一个任务不能同时由两个引擎运行
两层共享 Repository、ToolContext、RAG、审计和报告版本规则
```

---

## 5. Graph 拓扑

推荐初始拓扑：

```text
prepare_run
→ load_context
→ agent_decide
→ route_after_agent
    ├─ execute_tools → agent_decide
    └─ assess_evidence
         → human_confirmation
         → route_after_confirmation
             ├─ approve / revise → save_report → finalize
             └─ reject → cancel
```

节点职责：

```text
prepare_run
  获取运行锁
  校验任务状态和资源归属
  初始化或读取 Graph State
  标记任务 running

load_context
  读取 job、resume_version、conversation
  生成运行快照
  准备 RAG 索引
  构造运行时 ToolContext

agent_decide
  调用 LLM
  解析 assistant 消息和 tool_calls
  累计 Token Usage
  不直接写报告

execute_tools
  使用现有 ToolRegistry 和 ToolExecutor
  校验工具白名单和参数
  注入可信 ToolContext
  记录工具审计和 SSE 事件
  把工具 observation 写回消息状态

assess_evidence
  做确定性证据和引用校验
  校验报告中的 chunk_id 是否来自本轮 EvidencePack
  准备 pending_report
  不信任模型直接给出的终态

human_confirmation
  使用 LangGraph interrupt 暂停
  保存待确认摘要和允许修改的字段
  不在确认前保存最终报告

save_report
  在一个事务中追加报告版本
  使用幂等键避免恢复后重复保存

finalize
  更新任务 completed
  写入缓存状态
  释放运行锁
  返回执行结果

cancel
  用户拒绝后标记 cancelled
  不保存报告
```

---

## 6. Graph State

Graph State 使用显式 Schema，优先采用 `TypedDict + Annotated reducer`；具体类型在 PART 2 固化。

计划字段：

```text
task_id
job_id
resume_version_id
conversation_id
attempt
max_steps
current_step
current_node

job_description
resume_profile
conversation_context

messages
tool_trace
tool_audit_events
usage
final_answer

rag_enabled
requirements
evidence_pack
citation_validation

pending_report
report_id
pending_confirmation
confirmation_decision
confirmation_comment
resume_revision_text
new_resume_version_id

error_code
failed_node
retry_count
last_checkpoint_id
```

状态边界：

```text
State 保存能够恢复工作流所需的最小业务状态
原始简历正文是否进入 State 需要控制，能通过 ID 重载就不重复保存
向量本身不进入 State，只保存 chunk_id、摘要和 EvidencePack
数据库 Session、API Key、Redis 连接、隐藏思维链不得进入 State
用户身份由请求认证上下文和后端 Repository 校验，不信任模型输出
```

---

## 7. Checkpoint 设计

选择 PostgreSQL 作为 Checkpoint 持久化后端。

职责边界：

```text
PostgreSQL Checkpoint 保存 Graph 执行状态
PostgreSQL 业务表保存任务、报告、审计和简历版本事实
Redis 只保存短期状态缓存和运行锁
Chroma 只保存可重建的向量索引
```

线程标识：

```text
thread_id = jobfit-task-{task_id}
```

恢复规则：

```text
同一任务使用同一 thread_id
恢复前必须重新验证 current_user 对 task_id 的归属
恢复时从最近成功的 Checkpoint 继续
中断期间不长期持有 Redis 运行锁
恢复执行时重新获取运行锁
```

Checkpoint 不保存：

```text
API Key
数据库连接
Redis 连接
完整敏感日志
隐藏思维链
与恢复无关的大段原文副本
```

---

## 8. 人工确认与恢复

新增任务状态：

```text
waiting_confirmation
```

暂停点：

```text
assess_evidence
→ human_confirmation
→ interrupt
```

确认动作：

```text
approve
  保存原始 pending_report

revise
  保存经后端校验后的修改结果
  如提供简历修改文本，追加新的 resume_version

reject
  标记任务 cancelled，不保存报告
```

恢复接口请求语义：

```text
action: approve / revise / reject / retry
comment: 可选
edited_summary: revise 时可选
resume_revision_text: revise 时可选
```

幂等要求：

```text
报告写入必须有稳定 idempotency_key
恢复后重复执行 save_report 不得新增重复报告
简历版本必须通过 Repository 追加，不覆盖历史版本
工具调用审计允许重复记录原始尝试，但不得改变工具业务终态
```

---

## 9. 重试与失败恢复

错误分类：

```text
可重试
  LLM 超时
  临时网络错误
  临时数据库连接错误
  工具执行超时

不可重试
  参数校验失败
  权限和资源归属错误
  引用校验失败
  任务状态冲突
  报告结构错误
```

重试规则：

```text
节点级 RetryPolicy 处理短暂错误
图级错误边负责记录安全 error_code 和 failed_node
超过最大重试次数后进入 failed 或 interrupted
用户可通过 resume 接口从最近成功 Checkpoint 恢复
写操作必须幂等，避免恢复导致重复报告或重复简历版本
```

---

## 10. 数据模型变更

计划通过 Alembic 增加：

```text
analysis_tasks.status 增加 waiting_confirmation
analysis_tasks.current_node 可空
analysis_tasks.workflow_engine 默认 legacy
reports.idempotency_key 可空且唯一
```

约束：

```text
workflow_engine IN ('legacy', 'langgraph')
current_node 只记录安全节点名
idempotency_key 不包含简历正文、JD 或 API Key
```

具体字段和索引在 PART 4/5 实现前再次审查，避免为框架内部状态重复建模。

---

## 11. SSE 事件扩展

保留现有事件，新增：

```text
graph_started
node_started
node_finished
checkpoint_saved
retry_scheduled
node_failed
waiting_confirmation
resumed
cancelled
```

安全边界：

```text
不发送隐藏思维链
不发送简历正文、JD 正文和敏感参数值
不发送 Checkpoint 原始内容
只发送节点名、阶段、状态、安全错误码和最终内容
```

---

## 12. 测试策略

每个 PART 都必须有独立测试。

测试层次：

```text
单元测试
  State reducer
  node 输入输出
  条件路由
  错误分类
  确认动作

服务测试
  Fake LLM 和 Fake Tool
  Graph happy path
  人工中断和恢复
  重试与幂等

集成测试
  PostgreSQL Checkpoint 保存和恢复
  用户和任务隔离
  进程重启恢复

接口测试
  graph run / status / resume / stream
  鉴权和 404 / 409 边界

契约测试
  手写 ReAct 与 LangGraph 输出结构和工具顺序一致
```

---

## 13. 分阶段实施

```text
PART 0：设计冻结、分支创建
PART 1：study-roads LangGraph 最小闭环
PART 2：JobFit Graph 骨架，使用假数据
PART 3：迁移核心业务节点
PART 4：PostgreSQL Checkpoint
PART 5：人工确认和 Resume
PART 6：失败重试、恢复和 SSE
PART 7：双引擎对比和兼容
PART 8：文档、质量门禁和 Git 闭环
```

质量门禁：

```text
本 PART 测试不通过，不进入下一 PART
现有测试不通过，不进入下一 PART
每 PART 单独 commit
运行代码改动必须附带测试
接口变化必须更新文档
不删除手写 ReAct
```

---

## 14. 重构前后必须回答的问题

```text
哪些状态从 Python 变量变成 Graph State
Checkpoint 保存什么，不保存什么
人工确认节点在哪个状态暂停
失败从哪个节点恢复
手写版本和 LangGraph 版本的行为是否一致
哪些能力复用，哪些能力由框架接管
为什么没有为了框架而绕过 Repository、ToolContext 和安全边界
```

---

## 15. 完成定义

```text
[x] 设计冻结
[x] LangGraph 最小闭环
[x] JobFit Graph 骨架
[x] 核心业务节点迁移
[x] PostgreSQL Checkpoint
[x] 人工确认与 Resume
[x] 失败重试与恢复
[x] SSE 扩展
[x] 双引擎对比
[x] 文档、测试、Git、push 和 tag
```

---

## 16. PART 1 验证记录

学习轨目录：

```text
D:\agentstudy\study-roads\step11_langgraph
```

已验证：

```text
State / Node / Edge / 条件跳转
SqliteSaver Checkpoint
interrupt 人工暂停
Command(resume=...) 恢复
批准 / 修改 / 拒绝
两个独立 Python 进程之间恢复
```

依赖版本：

```text
langgraph==1.2.12
langgraph-checkpoint-sqlite==3.1.1
pytest==9.1.1
```

验证命令与结果：

```text
python -m pytest D:\agentstudy\study-roads\step11_langgraph\tests -q
6 passed
```

---

## 17. PART 2 验证记录

新增 JobFit Graph 骨架：

```text
app/graphs/jobfit/state.py
app/graphs/jobfit/nodes.py
app/graphs/jobfit/graph.py
tests/test_jobfit_graph_skeleton.py
```

已验证拓扑：

```text
prepare_run
→ load_context
→ agent_decide
→ execute_tools
→ agent_decide
→ assess_evidence
→ human_confirmation
→ save_report
→ finalize
```

同时验证拒绝分支：

```text
human_confirmation
→ cancel
```

本部分使用假数据和确定性节点，不修改旧 ReAct 路径，不接入 HTTP 或数据库。

测试结果：

```text
python -m pytest -q
264 passed
```

---

## 18. PART 3 验证记录

Graph 已接入真实运行时能力：

```text
LLM chat_with_tools
ToolRegistry
ToolExecutor
ToolContext
工具审计
RAG search_resume_evidence
EvidencePack 状态保留
max_steps 循环终止
SSE step/tool/content 事件
```

运行时依赖通过 LangGraph `context_schema` 注入：

```text
chat_with_tools
tool_registry
tool_context_factory
event_sink
```

这些对象不进入 Graph State，也不会被 Checkpoint 序列化。

已建立手写 ReAct 与 Graph 版契约测试：

```text
最终回答一致
ReAct 状态一致
模型决策步数一致
Token Usage 一致
工具调用轨迹一致
工具审计事件一致
SSE 事件顺序一致
max_steps 终止行为一致
```

新增真实 RAG 工具测试，验证 Graph 执行
`search_resume_evidence` 后会把 EvidencePack 写回 Graph State。

测试结果：

```text
python -m pytest -q
265 passed
```

---

## 19. PART 4 验证记录

新增 PostgreSQL Checkpoint 支持：

```text
app/db/checkpoint.py
app/core/event_loop.py
scripts/setup_langgraph_checkpoint.py
scripts/verify_step11_checkpoint.py
tests/test_checkpoint_config.py
```

线程标识：

```text
task_id
→ jobfit-task-{task_id}
→ LangGraph configurable.thread_id
```

数据库职责：

```text
PostgreSQL Checkpoint 保存 Graph State 和控制位置
PostgreSQL 业务表保存任务、报告、审计和简历事实
Redis 只保存短期缓存和运行锁
Chroma 只保存可重建的向量索引
```

Windows 兼容处理：

```text
psycopg 3 异步连接不支持 ProactorEventLoop
应用启动前切换到 SelectorEventLoop
```

Checkpoint 表初始化：

```text
python scripts/setup_langgraph_checkpoint.py
```

真实 PostgreSQL 验证：

```text
写入 Graph State
关闭 Checkpoint 连接
重新打开连接
读取同一 thread_id 的 State
验证 final_answer 和 report_id
删除验证线程
```

验证结果：

```text
python -m pytest -q
272 passed

python scripts/verify_step11_checkpoint.py
checkpoint_reopened=true
cleanup_completed=true
```

---

## 20. PART 5 验证记录

人工确认已使用 LangGraph `interrupt`：

```text
assess_evidence
→ human_confirmation
→ interrupt
→ Command(resume=...)
→ save_report / cancel
```

支持确认动作：

```text
approve
revise
reject
```

修改确认支持：

```text
edited_report
resume_revision_text
```

数据库变更：

```text
analysis_tasks.status 增加 waiting_confirmation
analysis_tasks.current_node 增加可空字段
Alembic revision: c2508fd83a64
```

新增服务：

```text
app/services/graph_agent.py
run_graph_persisted_task
resume_graph_persisted_task
get_graph_task_confirmation
```

新增接口：

```text
POST /api/agent/tasks/{task_id}/graph/run
POST /api/agent/tasks/{task_id}/graph/resume
GET /api/agent/tasks/{task_id}/graph/confirmation
```

持久化行为：

```text
Graph 暂停时任务状态为 waiting_confirmation
恢复后批准报告写入 reports
修改确认后追加新的 resume_version
拒绝时任务状态为 cancelled，不保存报告
工具审计只在最终完成或取消时写入一次，避免恢复造成重复记录
```

真实 PostgreSQL 验证：

```text
graph run
→ interrupt
→ 关闭连接
→ 重新打开连接
→ Command resume
→ completed
```

验证结果：

```text
python -m pytest -q
277 passed

python scripts/verify_step11_checkpoint.py
interrupted=true
waiting_node=human_confirmation
resume_decision=revise
cleanup_completed=true

python scripts/verify_step11_graph_agent.py
waiting_status=waiting_confirmation
final_status=completed
report saved
resume version appended
cleanup_completed=true
```

---

## 21. PART 6 验证记录

失败分类和重试已实现：

```text
app/graphs/jobfit/retry.py

LLMServiceError 502 / 503 / 504
TimeoutError
ConnectionError
OSError
```

以上错误可以重试，其他业务错误不盲目重试。

重试策略：

```text
仅在 agent_decide 节点启用 RetryPolicy
max_attempts=3
指数退避
不自动重试 execute_tools，避免重复副作用
```

节点事件包装：

```text
node_started
node_finished
node_failed
retry_scheduled
waiting_confirmation
```

Graph SSE 事件：

```text
graph_started
task_started
node_started
step_started
tool_started
tool_finished
node_finished
retry_scheduled
waiting_confirmation
resumed
task_completed
cancelled
heartbeat
error
done
```

新增接口：

```text
GET /api/agent/tasks/{task_id}/graph/stream
```

安全边界：

```text
不发送隐藏思维链
不发送简历正文、JD 正文和敏感参数
只发送节点名、阶段、安全状态和最终内容
```

测试结果：

```text
python -m pytest -q
279 passed

新增验证：
短时 LLM 503 失败后自动重试成功
Graph SSE 返回事件流和 done
```

真实 PostgreSQL 回归：

```text
verify_step11_checkpoint.py 通过
verify_step11_graph_agent.py 通过
测试线程和业务数据清理完成
```

---

## 22. PART 7 验证记录

双版本入口保持隔离：

```text
手写 ReAct:
POST /api/agent/tasks/{task_id}/run
GET  /api/agent/tasks/{task_id}/stream

LangGraph:
POST /api/agent/tasks/{task_id}/graph/run
POST /api/agent/tasks/{task_id}/graph/resume
GET  /api/agent/tasks/{task_id}/graph/confirmation
GET  /api/agent/tasks/{task_id}/graph/stream
```

新增对比脚本：

```text
scripts/compare_step11_engines.py
```

新增对比文档：

```text
docs/STEP11_ENGINE_COMPARISON.md
```

相同模型响应和工具注册表下验证：

```text
最终回答一致
ReAct 状态一致
模型决策步数一致
Token Usage 一致
工具调用轨迹一致
核心 SSE 事件顺序一致
工具实际执行输入一致
```

Graph 版额外提供：

```text
显式状态图
PostgreSQL Checkpoint
人工确认
中断恢复
节点级重试
节点事件
```

对比脚本输出：

```text
answer_equal=true
status_equal=true
steps_equal=true
usage_equal=true
tool_trace_equal=true
core_events_equal=true
executed_tools_equal=true
```

测试结果：

```text
python -m pytest -q
279 passed
```

---

## 23. STEP 11 最终验收

完整测试：

```text
279 passed
```

真实 PostgreSQL 验证：

```text
Checkpoint 中断恢复通过
Graph Agent 人工确认与恢复通过
报告保存和 resume_version 追加通过
测试线程与业务数据清理通过
```

双引擎对比：

```text
answer_equal=true
status_equal=true
steps_equal=true
usage_equal=true
tool_trace_equal=true
core_events_equal=true
executed_tools_equal=true
```

最终 Git 闭环：

```text
feature/step-11-langgraph
→ merge main
→ push origin main
→ delete feature branch
→ tag step-11-langgraph
→ push tag
```
