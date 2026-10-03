# STEP 12 Observability

## 1. 目标

让每次 Agent 任务都能回答：

```text
请求是谁发起的
执行了哪些节点
模型花了多久
工具花了多久
RAG 和 Rerank 花了多久
总共花了多少时间
使用了多少 Token
失败发生在哪个节点
```

---

## 2. request_id

客户端可以传入：

```http
X-Request-ID: client-request-1234
```

规则：

```text
合法 ID 原样透传
未提供或格式非法时后端生成 UUID
响应头返回 X-Request-ID
请求上下文中的日志自动带上 request_id
```

实现：

```text
app/middleware/request_context.py
app/core/observability.py
```

---

## 3. 结构化日志

环境变量：

```text
LOG_LEVEL=INFO
LOG_FORMAT=json
```

支持：

```text
request_id
task_id
level
logger
message
timestamp
exception
```

安全边界：

```text
不记录 API Key
不记录密码
不记录 Bearer Token
不记录 JD 正文
不记录简历正文
不记录报告正文
不记录隐藏思维链
```

脱敏覆盖：

```text
sk-xxxx
Bearer xxxx
api_key=xxxx
password=xxxx
secret=xxxx
token=xxxx
```

---

## 4. 任务指标

数据模型：

```text
TaskMetrics
  request_id
  total_ms
  model_ms
  tool_ms
  index_ms
  retrieval_ms
  rerank_ms
  node_ms
  steps
  usage
  node_metrics
  error_code
```

Graph State 字段：

```text
model_ms
tool_ms
node_metrics
usage
current_step
```

Graph 节点包装器自动记录：

```text
node
duration_ms
```

---

## 5. 数据库持久化

`analysis_tasks` 新增字段：

```text
last_request_id
metrics_json
```

Alembic：

```text
59152edc1d2e
add task observability fields
```

任务等待确认或完成时写入部分或完整指标。

---

## 6. SSE 事件

SSE 继续只发送安全事件：

```text
node_started
node_finished
node_failed
retry_scheduled
tool_started
tool_finished
waiting_confirmation
resumed
task_completed
cancelled
heartbeat
error
done
```

不发送：

```text
隐藏思维链
敏感参数值
简历和 JD 正文
Checkpoint 原始内容
```

---

## 7. 验证

测试：

```text
tests/test_observability.py
```

真实 Graph 任务验证：

```text
scripts/verify_step11_graph_agent.py
```

验证结果包含：

```text
request_id 写入 analysis_tasks.last_request_id
metrics_json 写入 analysis_tasks.metrics_json
model_ms / tool_ms / node_metrics 存在
X-Request-ID 响应头返回
敏感日志被脱敏
```
