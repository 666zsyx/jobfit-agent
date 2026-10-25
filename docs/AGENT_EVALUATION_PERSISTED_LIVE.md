# Agent 评估（真实执行）

本报告由 scripts/evaluate_agent_live.py 真实调用 LLM 和工具生成，
不是回放固定观测值。

- 生成时间: 2026-10-25T10:23:08+00:00
- 模型: None
- commit: 7bc39cb
- max_steps: 8
- 实际执行: 45 / 50 个 case
- 门槛结论: PASS

## 实测指标

- 任务完成率: 1.0000
- 必要工具覆盖率: 1.0000
- 工具精度: 0.9159
- 工具序列(严格全等，仅供参考): 0.6222
- 工具 F1: 0.9520
- 工具成功率: 1.0000
- 匹配状态 F1: 0.8519
- 弃答准确率: 0.9556
- 无依据建议比例: 0.0000
- 证据支撑率: 1.0000
- 平均步数: 5.84
- 平均 Token: 19538.20
- p50 延迟 ms: 11406.00
- p95 延迟 ms: 17866.00

## 门槛

| 指标 | 实测值 | 条件 | 结果 |
|---|---:|---|---|
| task_completion_rate | 1.0000 | >= 0.8500 | PASS |
| tool_recall | 1.0000 | >= 0.9000 | PASS |
| tool_f1 | 0.9520 | >= 0.8500 | PASS |
| tool_success_rate | 1.0000 | >= 0.9500 | PASS |
| match_status_f1 | 0.8519 | >= 0.8500 | PASS |
| abstention_accuracy | 0.9556 | >= 0.9000 | PASS |
| unsupported_suggestion_rate | 0.0000 | <= 0.1500 | PASS |
| evidence_backed_rate | 1.0000 | >= 0.8500 | PASS |

## 与回放基线对比

| 指标 | 回放基线 | 真实执行 |
|---|---:|---:|
| task_completion_rate | 1.0000 | 1.0000 |
| tool_sequence_accuracy | 0.9800 | 0.6222 |
| tool_precision | 0.9960 | 0.9159 |
| tool_recall | 1.0000 | 1.0000 |
| tool_f1 | 0.9978 | 0.9520 |
| tool_success_rate | 1.0000 | 1.0000 |
| match_status_f1 | 1.0000 | 0.8519 |
| abstention_accuracy | 1.0000 | 0.9556 |
| unsupported_suggestion_rate | 0.0200 | 0.0000 |
| average_steps | 3.1200 | 5.8444 |
| average_usage_total | 1294.2000 | 19538.2000 |
| p50_latency_ms | 4200.0000 | 11406.0000 |
| p95_latency_ms | 7000.0000 | 17866.0000 |

- 回放基线的 observed 字段是数据集里写死的常量。
- 本报告耗时和 Token 来自真实模型调用，会有波动。

## 按类别

| 类别 | case 数 | 任务完成 | 工具F1 | 匹配F1 | 弃答 | 证据支撑 |
|---|---:|---:|---:|---:|---:|---:|
| abstention | 8 | 1.0000 | 0.8556 | 1.0000 | 1.0000 | 1.0000 |
| citation | 5 | 1.0000 | 1.0000 | 0.9333 | 1.0000 | 1.0000 |
| hallucination | 2 | 1.0000 | 0.9000 | 1.0000 | 1.0000 | 1.0000 |
| happy_path | 9 | 1.0000 | 0.9798 | 0.6111 | 0.7778 | 1.0000 |
| mixed | 5 | 1.0000 | 0.9121 | 0.7000 | 1.0000 | 1.0000 |
| partial_match | 8 | 1.0000 | 0.9773 | 0.9583 | 1.0000 | 1.0000 |
| recovery | 4 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| tooling | 4 | 1.0000 | 1.0000 | 0.7500 | 1.0000 | 1.0000 |

## 逐条结果

| case | 类别 | 完成 | 工具F1 | 弃答 | 证据支撑 | 步数 | Token | 延迟ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| python_fastapi_happy | happy_path | Y | 1.0000 | Y | Y | 5 | 16347 | 12518 |
| postgresql_partial | partial_match | Y | 1.0000 | Y | Y | 6 | 18990 | 10376 |
| redis_strong | happy_path | Y | 1.0000 | Y | Y | 5 | 16141 | 9524 |
| rag_hybrid_strong | happy_path | Y | 1.0000 | Y | Y | 6 | 19011 | 10157 |
| agent_loop_strong | happy_path | Y | 1.0000 | N | Y | 5 | 15961 | 11406 |
| no_mongodb_abstain | abstention | Y | 0.8889 | Y | Y | 6 | 18348 | 9693 |
| no_rust_abstain | abstention | Y | 0.8000 | Y | Y | 7 | 22465 | 14291 |
| mixed_requirement | mixed | Y | 1.0000 | Y | Y | 5 | 16358 | 8944 |
| tool_retry_recovered | recovery | Y | 1.0000 | Y | Y | 6 | 18334 | 9664 |
| citation_missing_failure | citation | Y | 1.0000 | Y | Y | 5 | 15765 | 7669 |
| unsupported_suggestion_failure | hallucination | Y | 1.0000 | Y | Y | 6 | 18001 | 7720 |
| extra_tool_call_failure | tooling | Y | 1.0000 | Y | Y | 5 | 15676 | 8749 |
| docker_deploy_happy | happy_path | Y | 1.0000 | Y | Y | 5 | 16318 | 11059 |
| langgraph_checkpoint_happy | happy_path | Y | 1.0000 | Y | Y | 5 | 16426 | 10607 |
| redis_limiter_happy | happy_path | Y | 1.0000 | Y | Y | 5 | 16188 | 10772 |
| no_golang_abstain | abstention | Y | 0.8889 | Y | Y | 5 | 16870 | 11800 |
| no_kafka_abstain | abstention | Y | 0.8000 | Y | Y | 6 | 20074 | 14268 |
| no_kubernetes_abstain | abstention | Y | 0.8889 | Y | Y | 6 | 19108 | 11591 |
| mysql_partial | partial_match | Y | 1.0000 | Y | Y | 6 | 18811 | 10668 |
| k8s_partial | partial_match | Y | 1.0000 | Y | Y | 6 | 20639 | 14073 |
| typescript_partial | partial_match | Y | 0.9091 | Y | Y | 7 | 23348 | 12386 |
| python_kafka_mixed | mixed | Y | 0.9091 | Y | Y | 6 | 23291 | 15194 |
| fastapi_redis_mixed | mixed | Y | 0.9091 | Y | Y | 7 | 26600 | 17866 |
| postgres_transaction_recovered | recovery | Y | 1.0000 | Y | Y | 5 | 16077 | 9863 |
| citation_redis_limiter | citation | Y | 1.0000 | Y | Y | 6 | 18818 | 11776 |
| hallucination_no_fastapi | hallucination | Y | 0.8000 | Y | Y | 6 | 22733 | 15821 |
| tooling_python_strong | tooling | Y | 1.0000 | Y | Y | 5 | 15929 | 10194 |
| mock_unknown_tool_recovered | tooling | Y | 1.0000 | Y | Y | 5 | 16445 | 10391 |
| mock_invalid_arguments_recovered | tooling | Y | 1.0000 | Y | Y | 6 | 18327 | 8651 |
| mock_tool_timeout_recovered | recovery | Y | 1.0000 | Y | Y | 5 | 15796 | 7577 |
| mock_tool_handler_error_recovered | recovery | Y | 1.0000 | Y | Y | 6 | 18571 | 9636 |
| mock_citation_missing | citation | Y | 1.0000 | Y | Y | 6 | 19415 | 11358 |
| mock_citation_unknown_id | citation | Y | 1.0000 | Y | Y | 6 | 18301 | 9725 |
| mock_citation_duplicate_id | citation | Y | 1.0000 | Y | Y | 5 | 15690 | 9070 |
| mock_empty_evidence_abstain | abstention | Y | 0.8000 | Y | Y | 7 | 24067 | 14691 |
| live_strong_match_exact | happy_path | Y | 0.9091 | Y | Y | 7 | 27579 | 14929 |
| live_partial_match_weak | partial_match | Y | 1.0000 | Y | Y | 5 | 16667 | 11553 |
| live_insufficient_no_evidence | abstention | Y | 0.8889 | Y | Y | 6 | 18589 | 12588 |
| live_partial_vs_insufficient | partial_match | Y | 0.9091 | Y | Y | 7 | 26827 | 18607 |
| live_mixed_three_states | mixed | Y | 0.9091 | Y | Y | 7 | 28313 | 17458 |
| live_multi_requirement_partial | mixed | Y | 0.8333 | Y | Y | 8 | 35009 | 20003 |
| live_long_resume_partial | partial_match | Y | 1.0000 | Y | Y | 6 | 19338 | 13232 |
| live_short_resume_insufficient | abstention | Y | 0.8889 | Y | Y | 6 | 18125 | 11539 |
| live_cross_section_match | happy_path | Y | 0.9091 | N | Y | 6 | 20315 | 14277 |
| live_weak_evidence_partial | partial_match | Y | 1.0000 | Y | Y | 6 | 19218 | 11490 |

## 未覆盖 case

- confirmation_revise_recovered（human_confirmation）: 需要持久化人工确认/中断契约测试，不在本 runner 范围
- user_reject_cancelled（human_confirmation）: 需要持久化人工确认/中断契约测试，不在本 runner 范围
- max_steps_interrupted（failure）: 需要持久化人工确认/中断契约测试，不在本 runner 范围
- mock_max_steps_loop（failure）: mock-only 循环 case，不在持久化 RAG runner 范围
- mock_repeated_tool_loop（failure）: mock-only 循环 case，不在持久化 RAG runner 范围

## 说明

- tool_precision 会低于 1.0：当前 live 路径必须多调一次 extract_resume_sections，而评估集的 expected.tools 只列了 4 个工具，这是 fixture 与路径的差异，不是多余调用。
- 当前 live 路径不产生持久化 chunk_id，因此不计算引用 ID 维度的
  citation_f1 / citation_validity_rate；引用质量由
  evidence_backed_rate 和 unsupported_suggestion_rate 约束。
- 人工确认恢复率在当前 live 路径不适用，未纳入本次门槛。
- tool_sequence_accuracy 是严格全等（工具名/顺序/数量完全一致），仅作参考；门槛用 tool_recall（必要工具覆盖率）衡量。
- 需要 citation_ids 精确对比时，应把本脚本扩展到持久化 RAG 路径。
