# STEP 12 Cost Tracking

## 1. 目标

统计一次 Agent 任务中所有模型调用，包括：

```text
外层 ReAct / LangGraph 决策模型
内层岗位 JD 提取模型
内层简历分段提取模型
流式模型调用
```

输出：

```text
输入 Token
输出 Token
总 Token
模型调用次数
按模型聚合
估算成本
币种
```

---

## 2. 实现

模块：

```text
app/core/cost_tracking.py
app/services/llm.py
app/graphs/jobfit/nodes.py
app/services/graph_agent.py
app/services/persisted_agent.py
```

上下文收集：

```text
start_usage_collection()
record_usage()
finish_usage_collection()
```

在模型调用完成后记录：

```text
model
call_type
prompt_tokens
completion_tokens
total_tokens
latency_ms
```

call_type：

```text
chat
chat_json
chat_with_tools
stream_chat
```

---

## 3. 价格配置

`.env`：

```dotenv
LLM_INPUT_PRICE_PER_1M=0
LLM_OUTPUT_PRICE_PER_1M=0
COST_CURRENCY=USD
```

规则：

```text
价格单位是每 100 万 Token
未配置价格时成本为 0
不猜测模型供应商价格
价格变化只需要改环境变量
```

---

## 4. Graph 集成

Graph State 新增：

```text
usage_records
```

节点行为：

```text
agent_decide
  记录外层模型调用

execute_tools
  记录内层工具模型调用
  把内层 Usage 合并到 State.usage
```

Checkpoint 会保存：

```text
模型名
调用类型
Token 数量
调用耗时
```

不会保存：

```text
API Key
模型原始 Prompt
简历正文
JD 正文
隐藏思维链
```

---

## 5. 任务指标

`analysis_tasks.metrics_json` 增加：

```text
estimated_cost
currency
usage_call_count
usage_by_model
```

每个模型聚合：

```text
calls
prompt_tokens
completion_tokens
total_tokens
estimated_cost
```

---

## 6. 成本报表

脚本：

```powershell
.\.venv\Scripts\python.exe .\scripts\report_agent_cost.py
```

输出：

```text
docs/agent_cost_results.json
docs/COST_REPORT.md
```

查询范围：

```text
analysis_tasks.metrics_json IS NOT NULL
```

---

## 7. 测试

```text
tests/test_cost_tracking.py
tests/test_jobfit_graph_runtime.py
```

覆盖：

```text
上下文外调用不记录
上下文内调用记录
按模型聚合
输入/输出价格计算
非法 Token 总数拒绝
内层工具 Usage 合并到 Graph State
```

当前验证结果：

```text
cost tests: 5 passed
graph inner usage: 通过
完整测试：待最终门禁统计
```
