# STEP 11 Engine Comparison

## 双版本入口

手写 ReAct：

```text
POST /api/agent/tasks/{task_id}/run
GET  /api/agent/tasks/{task_id}/stream
```

LangGraph：

```text
POST /api/agent/tasks/{task_id}/graph/run
POST /api/agent/tasks/{task_id}/graph/resume
GET  /api/agent/tasks/{task_id}/graph/confirmation
GET  /api/agent/tasks/{task_id}/graph/stream
```

两者共享 Repository、ToolRegistry、ToolExecutor、ToolContext、RAG、
报告版本、工具审计和用户隔离。

## 核心差异

```text
手写 ReAct：控制流在 Python for 循环中
LangGraph：控制流在显式 StateGraph 中
```

Graph 版新增：

```text
PostgreSQL Checkpoint
human_confirmation interrupt
Command resume
approve / revise / reject
agent_decide RetryPolicy
node_started / node_finished / node_failed / retry_scheduled
```

Checkpoint：

```text
thread_id = jobfit-task-{task_id}-attempt-{attempt}
```

## 行为等价验证

脚本：

```text
scripts/compare_step11_engines.py
```

验证结果：

```text
answer_equal=true
status_equal=true
steps_equal=true
usage_equal=true
tool_trace_equal=true
core_events_equal=true
executed_tools_equal=true
```

核心事件对比：

```text
step_started
tool_started
tool_finished
content
```

Graph 额外事件：

```text
graph_started
node_started
node_finished
node_failed
retry_scheduled
waiting_confirmation
resumed
task_completed
cancelled
```

## 面试表达

```text
我先手写 ReAct，掌握消息历史、工具调用、Observation 回填、
Token 累计、最大步数和终止条件。
随后用 LangGraph 将同一业务逻辑迁移为显式状态图，
新增 PostgreSQL Checkpoint、人工确认、中断恢复、节点重试和 SSE 节点事件。
两套实现共享 ToolRegistry、Repository、RAG 和权限边界，
并通过契约测试验证最终回答、工具轨迹、Usage 和核心事件顺序一致。
```
