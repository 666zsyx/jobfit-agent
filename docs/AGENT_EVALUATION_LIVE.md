# Agent 评估（真实执行）

本报告由 scripts/evaluate_agent_live.py 真实调用 LLM 和工具生成，
不是回放固定观测值。

- 生成时间: 2026-10-25T09:18:51+00:00
- 模型: deepseek-flash
- commit: 7a7c879
- max_steps: 8
- 实际执行: 45 / 50 个 case
- 门槛结论: REVIEW

## 实测指标

- 任务完成率: 1.0000
- 必要工具覆盖率: 0.9822
- 工具精度: 0.7511
- 工具序列(严格全等，仅供参考): 0.0000
- 工具 F1: 0.8473
- 工具成功率: 1.0000
- 匹配状态 F1: 0.4341
- 弃答准确率: 0.8444
- 无依据建议比例: 0.0000
- 证据支撑率: 1.0000
- 平均步数: 5.69
- 平均 Token: 18616.16
- p50 延迟 ms: 11625.00
- p95 延迟 ms: 14584.00

## 门槛

| 指标 | 实测值 | 条件 | 结果 |
|---|---:|---|---|
| task_completion_rate | 1.0000 | >= 0.8500 | PASS |
| tool_recall | 0.9822 | >= 0.9000 | PASS |
| tool_f1 | 0.8473 | >= 0.8500 | FAIL |
| tool_success_rate | 1.0000 | >= 0.9500 | PASS |
| match_status_f1 | 0.4341 | >= 0.8500 | FAIL |
| abstention_accuracy | 0.8444 | >= 0.9000 | FAIL |
| unsupported_suggestion_rate | 0.0000 | <= 0.1500 | PASS |
| evidence_backed_rate | 1.0000 | >= 0.8500 | PASS |

## 与回放基线对比

| 指标 | 回放基线 | 真实执行 |
|---|---:|---:|
| task_completion_rate | 1.0000 | 1.0000 |
| tool_sequence_accuracy | 0.9800 | 0.0000 |
| tool_precision | 0.9960 | 0.7511 |
| tool_recall | 1.0000 | 0.9822 |
| tool_f1 | 0.9978 | 0.8473 |
| tool_success_rate | 1.0000 | 1.0000 |
| match_status_f1 | 1.0000 | 0.4341 |
| abstention_accuracy | 1.0000 | 0.8444 |
| unsupported_suggestion_rate | 0.0200 | 0.0000 |
| average_steps | 3.1200 | 5.6889 |
| average_usage_total | 1294.2000 | 18616.1556 |
| p50_latency_ms | 4200.0000 | 11625.0000 |
| p95_latency_ms | 7000.0000 | 14584.0000 |

- 回放基线的 observed 字段是数据集里写死的常量。
- 本报告耗时和 Token 来自真实模型调用，会有波动。

## 按类别

| 类别 | case 数 | 任务完成 | 工具F1 | 匹配F1 | 弃答 | 证据支撑 |
|---|---:|---:|---:|---:|---:|---:|
| abstention | 8 | 1.0000 | 0.7500 | 0.8333 | 0.8750 | 1.0000 |
| citation | 5 | 1.0000 | 0.8889 | 0.0000 | 1.0000 | 1.0000 |
| hallucination | 2 | 1.0000 | 0.7750 | 1.0000 | 1.0000 | 1.0000 |
| happy_path | 9 | 1.0000 | 0.8790 | 0.0741 | 0.7778 | 1.0000 |
| mixed | 5 | 1.0000 | 0.8889 | 0.7067 | 1.0000 | 1.0000 |
| partial_match | 8 | 1.0000 | 0.8778 | 0.4167 | 0.5000 | 1.0000 |
| recovery | 4 | 1.0000 | 0.8444 | 0.4167 | 1.0000 | 1.0000 |
| tooling | 4 | 1.0000 | 0.8444 | 0.4167 | 1.0000 | 1.0000 |

## 逐条结果

| case | 类别 | 完成 | 工具F1 | 弃答 | 证据支撑 | 步数 | Token | 延迟ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| python_fastapi_happy | happy_path | Y | 0.8889 | Y | Y | 5 | 18700 | 12972 |
| postgresql_partial | partial_match | Y | 0.8000 | Y | Y | 6 | 21855 | 15825 |
| redis_strong | happy_path | Y | 0.8000 | Y | Y | 7 | 23520 | 14748 |
| rag_hybrid_strong | happy_path | Y | 0.8889 | Y | Y | 6 | 20031 | 14246 |
| agent_loop_strong | happy_path | Y | 0.8889 | N | Y | 6 | 20190 | 14584 |
| no_mongodb_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 18658 | 12191 |
| no_rust_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 17843 | 10389 |
| mixed_requirement | mixed | Y | 0.8889 | Y | Y | 6 | 18675 | 11129 |
| tool_retry_recovered | recovery | Y | 0.8889 | Y | Y | 6 | 18284 | 10009 |
| citation_missing_failure | citation | Y | 0.8889 | Y | Y | 6 | 18318 | 9875 |
| unsupported_suggestion_failure | hallucination | Y | 0.8000 | Y | Y | 6 | 19745 | 10621 |
| extra_tool_call_failure | tooling | Y | 0.8889 | Y | Y | 6 | 18368 | 12196 |
| docker_deploy_happy | happy_path | Y | 0.8889 | Y | Y | 6 | 19836 | 13198 |
| langgraph_checkpoint_happy | happy_path | Y | 0.8889 | Y | Y | 5 | 18641 | 13846 |
| redis_limiter_happy | happy_path | Y | 0.8889 | Y | Y | 5 | 17474 | 10790 |
| no_golang_abstain | abstention | Y | 0.7500 | Y | Y | 5 | 15357 | 9419 |
| no_kafka_abstain | abstention | Y | 0.7500 | Y | Y | 5 | 15374 | 10083 |
| no_kubernetes_abstain | abstention | Y | 0.7500 | Y | Y | 6 | 19134 | 12394 |
| mysql_partial | partial_match | Y | 0.8889 | Y | Y | 6 | 19926 | 12984 |
| k8s_partial | partial_match | Y | 0.8889 | Y | Y | 5 | 17317 | 11463 |
| typescript_partial | partial_match | Y | 0.8889 | Y | Y | 6 | 18763 | 10906 |
| python_kafka_mixed | mixed | Y | 0.8889 | Y | Y | 6 | 19900 | 11408 |
| fastapi_redis_mixed | mixed | Y | 0.8889 | Y | Y | 5 | 17935 | 11275 |
| postgres_transaction_recovered | recovery | Y | 0.8889 | Y | Y | 5 | 16342 | 11556 |
| citation_redis_limiter | citation | Y | 0.8889 | Y | Y | 6 | 19669 | 13374 |
| hallucination_no_fastapi | hallucination | Y | 0.7500 | Y | Y | 5 | 15296 | 9605 |
| tooling_python_strong | tooling | Y | 0.8889 | Y | Y | 6 | 19216 | 12755 |
| mock_unknown_tool_recovered | tooling | Y | 0.8000 | Y | Y | 5 | 17496 | 13560 |
| mock_invalid_arguments_recovered | tooling | Y | 0.8000 | Y | Y | 6 | 18909 | 10497 |
| mock_tool_timeout_recovered | recovery | Y | 0.8000 | Y | Y | 6 | 20076 | 11559 |
| mock_tool_handler_error_recovered | recovery | Y | 0.8000 | Y | Y | 6 | 20583 | 12104 |
| mock_citation_missing | citation | Y | 0.8889 | Y | Y | 6 | 18965 | 11625 |
| mock_citation_unknown_id | citation | Y | 0.8889 | Y | Y | 6 | 18414 | 11560 |
| mock_citation_duplicate_id | citation | Y | 0.8889 | Y | Y | 5 | 15986 | 10628 |
| mock_empty_evidence_abstain | abstention | Y | 0.7500 | N | Y | 6 | 18994 | 11688 |
| live_strong_match_exact | happy_path | Y | 0.8889 | Y | Y | 6 | 20562 | 14092 |
| live_partial_match_weak | partial_match | Y | 0.8889 | N | Y | 6 | 18695 | 12196 |
| live_insufficient_no_evidence | abstention | Y | 0.7500 | Y | Y | 5 | 16638 | 10738 |
| live_partial_vs_insufficient | partial_match | Y | 0.8889 | N | Y | 5 | 16281 | 12589 |
| live_mixed_three_states | mixed | Y | 0.8889 | Y | Y | 6 | 21000 | 12458 |
| live_multi_requirement_partial | mixed | Y | 0.8889 | Y | Y | 5 | 17427 | 11186 |
| live_long_resume_partial | partial_match | Y | 0.8889 | N | Y | 6 | 19281 | 12799 |
| live_short_resume_insufficient | abstention | Y | 0.7500 | Y | Y | 6 | 18402 | 11244 |
| live_cross_section_match | happy_path | Y | 0.8889 | N | Y | 6 | 18790 | 11499 |
| live_weak_evidence_partial | partial_match | Y | 0.8889 | N | Y | 5 | 16861 | 12001 |

## 未覆盖 case

- confirmation_revise_recovered（human_confirmation）: 需要持久化人工确认路径
- user_reject_cancelled（human_confirmation）: 需要持久化人工确认路径
- max_steps_interrupted（failure）: 需要持久化任务状态或强制步数上限
- mock_max_steps_loop（failure）: 需要持久化任务状态或强制步数上限
- mock_repeated_tool_loop（failure）: 需要持久化任务状态或强制步数上限

## 说明

- tool_precision 会低于 1.0：当前 live 路径必须多调一次 extract_resume_sections，而评估集的 expected.tools 只列了 4 个工具，这是 fixture 与路径的差异，不是多余调用。
- 当前 live 路径不产生持久化 chunk_id，因此不计算引用 ID 维度的
  citation_f1 / citation_validity_rate；引用质量由
  evidence_backed_rate 和 unsupported_suggestion_rate 约束。
- 人工确认恢复率在当前 live 路径不适用，未纳入本次门槛。
- tool_sequence_accuracy 是严格全等（工具名/顺序/数量完全一致），仅作参考；门槛用 tool_recall（必要工具覆盖率）衡量。
- 需要 citation_ids 精确对比时，应把本脚本扩展到持久化 RAG 路径。
