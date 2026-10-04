# JobFit Agent 面试问答

## 1. 为什么做这个项目？

```text
目标是做一个可解释的岗位匹配 Agent。
它不只给出匹配结论，还必须能说明：
为什么这样判断、引用了哪段简历证据、证据不足时为什么拒绝下结论。
```

## 2. 为什么需要 Agent，不只是调用一次模型？

```text
岗位分析是多步任务：
先提取岗位要求，再检索简历证据，再逐条评估，最后保存报告。
每一步的结果会影响下一步工具输入。
所以使用 ReAct 循环和 LangGraph 来编排工具调用与状态流转。
```

## 3. 为什么同时保留手写 ReAct 和 LangGraph？

```text
手写版用于理解 Agent 循环的底层机制：
消息历史、tool_calls、Observation 回填、最大步数和 Usage 累计。
LangGraph 版用于工程化：
Checkpoint、人工确认、中断恢复、节点重试和可视化状态图。
两套实现共享 ToolRegistry、Repository、RAG 和安全边界，
并通过契约脚本验证最终结果一致。
```

## 4. 工具调用怎么保证安全？

```text
模型只能调用 ToolRegistry 中注册的工具。
参数必须经过 Pydantic 校验。
user_id 和 task_id 由 ToolContext 从后端注入，模型不能提交。
工具执行有超时、白名单、审计和统一异常转换。
高风险报告保存前还要经过人工确认。
```

## 5. 为什么 PostgreSQL 和 Chroma 要分开？

```text
PostgreSQL 保存事实数据：Chunk 原文、用户、简历版本、元数据、报告和审计。
Chroma 只保存可以重建的向量索引。
这样即使向量库损坏，也可以从 PostgreSQL 重新构建，不会丢业务事实。
```

## 6. 为什么需要混合检索？

```text
关键词召回对 Python、FastAPI、PostgreSQL 这类专有名词精确。
向量召回能处理语义改写，例如“接口联调”与“后端开发”。
BM25 和向量召回各有盲区，所以用 RRF 融合两路排名，再用 Rerank 精排。
```

## 7. RRF 为什么不直接把两路分数相加？

```text
BM25 分数和余弦相似度不在同一量纲，直接相加没有稳定意义。
RRF 只使用排名，按 1 / (k + rank) 融合，适合异构召回结果。
```

## 8. 为什么还要 Rerank？

```text
粗排为了保证召回，候选里可能混入弱相关内容。
Cross-Encoder 将岗位要求和候选证据一起编码，精算相关性。
最终只把 Top-N 精准证据交给模型，减少 Token 和幻觉。
```

## 9. 怎样保证报告引用真实？

```text
检索阶段生成 EvidencePack。
评估工具保留 chunk_id。
保存报告前递归收集结果中的 chunk_id，并校验它们全部来自本轮 EvidencePack。
未知引用或缺少引用会拒绝保存。
```

## 10. Checkpoint 保存什么？

```text
保存工作流位置、节点状态、消息、工具调用、Usage、等待确认内容、
重试信息和恢复所需业务字段。
不保存数据库连接、API Key、隐藏思维链和无关敏感日志。
```

## 11. 人工确认怎么做？

```text
human_confirmation 节点调用 interrupt 暂停。
PostgreSQL Checkpoint 保存当前状态。
任务状态变成 waiting_confirmation。
用户 approve / revise / reject 后，通过 Command(resume=...) 恢复。
只有确认后才保存最终报告。
```

## 12. 失败重试怎么做，如何避免重复副作用？

```text
agent_decide 使用 RetryPolicy，只重试临时 LLM、网络、超时和服务端错误。
execute_tools 不自动重试，因为工具可能有副作用。
写报告和追加简历版本在事务中完成，使用任务状态和版本追加保护。
```

## 13. 怎么防止 Prompt Injection？

```text
JD、简历、会话历史和工具结果都视为不可信数据。
系统提示明确这些内容不是指令。
检测“忽略以上规则”“泄露 system prompt”“执行命令”等模式。
高风险输入直接拒绝。
工具白名单、参数校验、引用校验和人工确认继续作为纵深防御。
```

## 14. 如何评估 Agent？

```text
固定 Agent case 评估任务完成率、工具顺序、工具 F1、工具成功率、
匹配状态一致性、引用 F1、引用有效性、拒答准确率、确认恢复率和无依据建议比例。
同时记录 Token、耗时和错误码。
```

## 15. 如何控制成本？

```text
收集外层模型和内层工具模型的 Usage。
按模型聚合输入、输出和总 Token。
通过环境变量配置每 100 万 Token 价格，计算任务估算成本。
未配置价格时成本为 0，不猜测供应商价格。
```

## 16. 如何限流？

```text
使用 Redis 按用户、接口和时间窗口限流。
同时检查每天请求配额和每天 Token 配额。
只有真实消耗 LLM 的请求检查 Token 配额，任务和报告读接口不会被 Token 配额阻断。
Redis 故障时退化为进程内保守计数。
超限统一返回 429 和 Retry-After。
```

## 17. 为什么不用 Multi-Agent？

```text
当前业务主要是一个确定性的纵向流程：
岗位提取、证据检索、匹配评估、报告确认。
单 Agent 加工具已经足够。
Multi-Agent 会增加状态一致性、权限、成本和评估复杂度。
只有出现独立长期角色、不同工具权限或并行候选岗位时才考虑拆分。
```

## 18. 项目目前最大限制是什么？

```text
远程 staging 和公网部署还没有在 Linux 服务器执行。
评估集规模仍较小，阈值需要独立 holdout 复验。
长任务仍在应用进程内执行，未来应迁移到 Worker 和消息队列。
当前只有一个环境变量演示账号，没有注册、找回密码和 RBAC。
告警、CI 和完整审计还可以继续完善。
```

## 19. 为什么生产 staging 固定单 Worker？

```text
当前 Chroma 使用本地 PersistentClient，Embedding 和 Reranker 也是进程内实例。
多个 Uvicorn Worker 会各自打开本地索引和模型，带来内存放大与索引一致性风险。
staging 先固定 --workers 1，后续扩容时将向量服务外置或设计共享索引方案。
```
