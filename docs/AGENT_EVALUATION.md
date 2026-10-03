# STEP 12 Agent Evaluation

- Cases: 15
- Dataset: `data/evaluation/agent_cases.json`
- Threshold gate: PASS

## Summary

- Task completion rate: 1.0000
- Tool sequence accuracy: 0.9333
- Tool F1: 0.9926
- Tool success rate: 0.9778
- Match status F1: 1.0000
- Citation F1: 0.9778
- Citation validity rate: 0.9333
- Abstention accuracy: 1.0000
- Confirmation recovery rate: 1.0000
- Unsupported suggestion rate: 0.0667
- Average steps: 2.73
- Average total tokens: 1171.33
- p50 latency ms: 4400.00
- p95 latency ms: 7000.00

## Thresholds

| Metric | Value | Condition | Result |
|---|---:|---|---|
| task_completion_rate | 1.0000 | >= 0.8500 | PASS |
| tool_sequence_accuracy | 0.9333 | >= 0.6000 | PASS |
| tool_f1 | 0.9926 | >= 0.8500 | PASS |
| tool_success_rate | 0.9778 | >= 0.9500 | PASS |
| match_status_f1 | 1.0000 | >= 0.8500 | PASS |
| citation_f1 | 0.9778 | >= 0.8000 | PASS |
| citation_validity_rate | 0.9333 | >= 0.8000 | PASS |
| abstention_accuracy | 1.0000 | >= 0.9000 | PASS |
| confirmation_recovery_rate | 1.0000 | >= 0.9500 | PASS |
| unsupported_suggestion_rate | 0.0667 | <= 0.1500 | PASS |

## Failing Cases

- citation_missing_failure (citation): task_completed=True, citation_valid=False, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=0.0000
- unsupported_suggestion_failure (hallucination): task_completed=True, citation_valid=True, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=1.0000

## Notes

- 该评估集用于固定 Agent 行为回归，不代表真实模型质量上限。
- 失败样本用于验证指标可以发现引用缺失、无依据建议和工具多调用问题。
- 后续可以把真实任务执行结果转换成同结构 observation，再运行同一套指标。
