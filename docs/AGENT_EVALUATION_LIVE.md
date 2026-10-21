# Agent 评估（真实执行）

本报告由 scripts/evaluate_agent_live.py 真实调用 LLM 和工具生成，
不是回放固定观测值。入口函数为 run_jobfit_agent，
与 POST /api/agent/match 使用同一条非持久化关键词 ReAct 路径。

- 生成时间: 2026-10-21T10:28:13+00:00
- 模型: deepseek-flash
- commit: af4b6d6
- max_steps: 8
- 实际执行: 27 / 30 个 case
- 门槛结论: REVIEW

## 实测指标

- 任务完成率: 1.0000
- 必要工具覆盖率: 1.0000
- 工具精度: 0.7506
- 工具序列(严格全等，仅供参考): 0.0000
- 工具 F1: 0.8547
- 工具成功率: 1.0000
- 匹配状态 F1: 0.5765
- 弃答准确率: 0.9630
- 无依据建议比例: 0.0000
- 证据支撑率: 1.0000
- 平均步数: 5.85
- 平均 Token: 19043.44
- p50 延迟 ms: 11309.00
- p95 延迟 ms: 13965.00

## 门槛

| 指标 | 实测值 | 条件 | 结果 |
|---|---:|---|---|
| task_completion_rate | 1.0000 | >= 0.8500 | PASS |
| tool_recall | 1.0000 | >= 0.9000 | PASS |
| tool_f1 | 0.8547 | >= 0.8500 | PASS |
| tool_success_rate | 1.0000 | >= 0.9500 | PASS |
| match_status_f1 | 0.5765 | >= 0.8500 | FAIL |
| abstention_accuracy | 0.9630 | >= 0.9000 | PASS |
| unsupported_suggestion_rate | 0.0000 | <= 0.1500 | PASS |
| evidence_backed_rate | 1.0000 | >= 0.8500 | PASS |

## 与回放基线对比

| 指标 | 回放基线 | 真实执行 |
|---|---:|---:|
| task_completion_rate | 1.0000 | 1.0000 |
| tool_sequence_accuracy | 0.9667 | 0.0000 |
| tool_precision | 0.9933 | 0.7506 |
| tool_recall | 1.0000 | 1.0000 |
| tool_f1 | 0.9963 | 0.8547 |
| tool_success_rate | 0.9889 | 1.0000 |
| match_status_f1 | 1.0000 | 0.5765 |
| abstention_accuracy | 1.0000 | 0.9630 |
| unsupported_suggestion_rate | 0.0333 | 0.0000 |
| average_steps | 2.9333 | 5.8519 |
| average_usage_total | 1185.6667 | 19043.4444 |
| p50_latency_ms | 4200.0000 | 11309.0000 |
| p95_latency_ms | 6100.0000 | 13965.0000 |

- 回放基线的 observed 字段是数据集里写死的常量。
- 本报告耗时和 Token 来自真实模型调用，会有波动。

## 逐条结果

| case | 类别 | 完成 | 工具F1 | 弃答 | 证据支撑 | 步数 | Token | 延迟ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| python_fastapi_happy | happy_path | Y | 0.8889 | Y | Y | 6 | 20376 | 12948 |
| postgresql_partial | partial_match | Y | 0.8889 | Y | Y | 6 | 19162 | 11058 |
| redis_strong | happy_path | Y | 0.8889 | Y | Y | 6 | 20593 | 13965 |
| rag_hybrid_strong | happy_path | Y | 0.8889 | Y | Y | 6 | 21310 | 14032 |
| agent_loop_strong | happy_path | Y | 0.8889 | N | Y | 6 | 18532 | 11090 |
| no_mongodb_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 18455 | 10946 |
| no_rust_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 17748 | 9142 |
| mixed_requirement | mixed | Y | 0.8889 | Y | Y | 6 | 19918 | 11997 |
| tool_retry_recovered | recovery | Y | 0.8889 | Y | Y | 6 | 20473 | 12871 |
| citation_missing_failure | citation | Y | 0.8889 | Y | Y | 6 | 18535 | 11086 |
| unsupported_suggestion_failure | hallucination | Y | 0.8889 | Y | Y | 6 | 18162 | 9934 |
| extra_tool_call_failure | tooling | Y | 0.8000 | Y | Y | 7 | 23333 | 12030 |
| docker_deploy_happy | happy_path | Y | 0.8889 | Y | Y | 5 | 17791 | 11284 |
| langgraph_checkpoint_happy | happy_path | Y | 0.8889 | Y | Y | 6 | 19747 | 11539 |
| redis_limiter_happy | happy_path | Y | 0.8889 | Y | Y | 6 | 20622 | 12066 |
| no_golang_abstain | abstention | Y | 0.7500 | Y | Y | 5 | 15504 | 8939 |
| no_kafka_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 18487 | 10748 |
| no_kubernetes_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 18324 | 11266 |
| mysql_partial | partial_match | Y | 0.8889 | Y | Y | 5 | 16841 | 11476 |
| k8s_partial | partial_match | Y | 0.8889 | Y | Y | 6 | 20601 | 11635 |
| typescript_partial | partial_match | Y | 0.8889 | Y | Y | 6 | 19283 | 11309 |
| python_kafka_mixed | mixed | Y | 0.8889 | Y | Y | 5 | 16872 | 10938 |
| fastapi_redis_mixed | mixed | Y | 0.8889 | Y | Y | 6 | 20272 | 12050 |
| postgres_transaction_recovered | recovery | Y | 0.8889 | Y | Y | 5 | 16233 | 11531 |
| citation_redis_limiter | citation | Y | 0.8889 | Y | Y | 6 | 19834 | 10501 |
| hallucination_no_fastapi | hallucination | Y | 0.7500 | Y | Y | 6 | 18568 | 11716 |
| tooling_python_strong | tooling | Y | 0.8889 | Y | Y | 6 | 18597 | 10619 |

## 未覆盖 case

- confirmation_revise_recovered（human_confirmation）: 需要持久化人工确认路径
- user_reject_cancelled（human_confirmation）: 需要持久化人工确认路径
- max_steps_interrupted（failure）: 需要持久化任务状态或强制步数上限

## 说明

- tool_precision 会低于 1.0：关键词路径必须多调一次 extract_resume_sections，而评估集的 expected.tools 只列了 4 个工具，这是 fixture 与路径的差异，不是多余调用。
- 关键词路径不产生持久化 chunk_id，因此不计算引用 ID 维度的
  citation_f1 / citation_validity_rate；引用质量由
  evidence_backed_rate 和 unsupported_suggestion_rate 约束。
- 人工确认恢复率在关键词路径不适用，未纳入本次门槛。
- tool_sequence_accuracy 是严格全等（工具名/顺序/数量完全一致），仅作参考；门槛用 tool_recall（必要工具覆盖率）衡量。
- 需要 citation_ids 精确对比时，应把本脚本扩展到持久化 RAG 路径。
