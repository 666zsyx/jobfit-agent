# Agent 评估（真实执行）

本报告由 scripts/evaluate_agent_live.py 真实调用 LLM 和工具生成，
不是回放固定观测值。

- 生成时间: 2026-10-25T10:08:49+00:00
- 模型: None
- commit: 7a7c879
- max_steps: 8
- 实际执行: 3 / 3 个 case
- 门槛结论: PASS

## 实测指标

- 任务完成率: 1.0000
- 必要工具覆盖率: 1.0000
- 工具精度: 0.7556
- 工具序列(严格全等，仅供参考): 0.0000
- 工具 F1: 0.8593
- 工具成功率: 1.0000
- 匹配状态 F1: 1.0000
- 弃答准确率: 1.0000
- 无依据建议比例: 0.0000
- 证据支撑率: 1.0000
- 平均步数: 5.33
- 平均 Token: 18579.67
- p50 延迟 ms: 13106.00
- p95 延迟 ms: 15667.00

## 门槛

| 指标 | 实测值 | 条件 | 结果 |
|---|---:|---|---|
| task_completion_rate | 1.0000 | >= 0.8500 | PASS |
| tool_recall | 1.0000 | >= 0.9000 | PASS |
| tool_f1 | 0.8593 | >= 0.8500 | PASS |
| tool_success_rate | 1.0000 | >= 0.9500 | PASS |
| match_status_f1 | 1.0000 | >= 0.8500 | PASS |
| abstention_accuracy | 1.0000 | >= 0.9000 | PASS |
| unsupported_suggestion_rate | 0.0000 | <= 0.1500 | PASS |
| evidence_backed_rate | 1.0000 | >= 0.8500 | PASS |

## 与回放基线对比

| 指标 | 回放基线 | 真实执行 |
|---|---:|---:|
| task_completion_rate | 1.0000 | 1.0000 |
| tool_sequence_accuracy | 0.9800 | 0.0000 |
| tool_precision | 0.9960 | 0.7556 |
| tool_recall | 1.0000 | 1.0000 |
| tool_f1 | 0.9978 | 0.8593 |
| tool_success_rate | 1.0000 | 1.0000 |
| match_status_f1 | 1.0000 | 1.0000 |
| abstention_accuracy | 1.0000 | 1.0000 |
| unsupported_suggestion_rate | 0.0200 | 0.0000 |
| average_steps | 3.1200 | 5.3333 |
| average_usage_total | 1294.2000 | 18579.6667 |
| p50_latency_ms | 4200.0000 | 13106.0000 |
| p95_latency_ms | 7000.0000 | 15667.0000 |

- 回放基线的 observed 字段是数据集里写死的常量。
- 本报告耗时和 Token 来自真实模型调用，会有波动。

## 按类别

| 类别 | case 数 | 任务完成 | 工具F1 | 匹配F1 | 弃答 | 证据支撑 |
|---|---:|---:|---:|---:|---:|---:|
| happy_path | 3 | 1.0000 | 0.8593 | 1.0000 | 1.0000 | 1.0000 |

## 逐条结果

| case | 类别 | 完成 | 工具F1 | 弃答 | 证据支撑 | 步数 | Token | 延迟ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| python_fastapi_happy | happy_path | Y | 0.8889 | Y | Y | 5 | 16505 | 13106 |
| redis_strong | happy_path | Y | 0.8000 | Y | Y | 6 | 23190 | 15667 |
| docker_deploy_happy | happy_path | Y | 0.8889 | Y | Y | 5 | 16044 | 9996 |

## 未覆盖 case

- 无。

## 说明

- tool_precision 会低于 1.0：当前 live 路径必须多调一次 extract_resume_sections，而评估集的 expected.tools 只列了 4 个工具，这是 fixture 与路径的差异，不是多余调用。
- 当前 live 路径不产生持久化 chunk_id，因此不计算引用 ID 维度的
  citation_f1 / citation_validity_rate；引用质量由
  evidence_backed_rate 和 unsupported_suggestion_rate 约束。
- 人工确认恢复率在当前 live 路径不适用，未纳入本次门槛。
- tool_sequence_accuracy 是严格全等（工具名/顺序/数量完全一致），仅作参考；门槛用 tool_recall（必要工具覆盖率）衡量。
- 需要 citation_ids 精确对比时，应把本脚本扩展到持久化 RAG 路径。
