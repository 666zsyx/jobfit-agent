# STEP 12 Agent Evaluation

- Cases: 50
- Dataset: `data/evaluation/agent_cases.json`
- Threshold gate: PASS

## Summary

- Task completion rate: 1.0000
- Tool sequence accuracy: 0.9800
- Tool F1: 0.9978
- Tool success rate: 1.0000
- Match status F1: 1.0000
- Citation F1: 0.9467
- Citation validity rate: 0.9200
- Abstention accuracy: 1.0000
- Confirmation recovery rate: 1.0000
- Unsupported suggestion rate: 0.0200
- Average steps: 3.12
- Average total tokens: 1294.20
- p50 latency ms: 4200.00
- p95 latency ms: 7000.00

## Thresholds

| Metric | Value | Condition | Result |
|---|---:|---|---|
| task_completion_rate | 1.0000 | >= 0.8500 | PASS |
| tool_sequence_accuracy | 0.9800 | >= 0.6000 | PASS |
| tool_f1 | 0.9978 | >= 0.8500 | PASS |
| tool_success_rate | 1.0000 | >= 0.9500 | PASS |
| match_status_f1 | 1.0000 | >= 0.8500 | PASS |
| citation_f1 | 0.9467 | >= 0.8000 | PASS |
| citation_validity_rate | 0.9200 | >= 0.8000 | PASS |
| abstention_accuracy | 1.0000 | >= 0.9000 | PASS |
| confirmation_recovery_rate | 1.0000 | >= 0.9500 | PASS |
| unsupported_suggestion_rate | 0.0200 | <= 0.1500 | PASS |

## By Category

| Category | Cases | Task Completion | Tool F1 | Match F1 | Citation Validity | Abstention |
|---|---:|---:|---:|---:|---:|---:|
| abstention | 8 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| citation | 5 | 1.0000 | 1.0000 | 1.0000 | 0.2000 | 1.0000 |
| failure | 3 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hallucination | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| happy_path | 9 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| human_confirmation | 2 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| mixed | 5 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| partial_match | 8 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| recovery | 4 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| tooling | 4 | 1.0000 | 0.9722 | 1.0000 | 1.0000 | 1.0000 |

## Failing Cases

- citation_missing_failure (citation): task_completed=True, citation_valid=False, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=0.0000
- unsupported_suggestion_failure (hallucination): task_completed=True, citation_valid=True, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=1.0000
- mock_citation_missing (citation): task_completed=True, citation_valid=False, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=0.0000
- mock_citation_unknown_id (citation): task_completed=True, citation_valid=False, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=0.0000
- mock_citation_duplicate_id (citation): task_completed=True, citation_valid=False, abstention_correct=True, confirmation_recovered=True, unsupported_suggestion_rate=0.0000

## Notes

- 该评估集用于固定 Agent 行为回归，不代表真实模型质量上限。
- 失败样本用于验证指标可以发现引用缺失、无依据建议和工具多调用问题。
- 后续可以把真实任务执行结果转换成同结构 observation，再运行同一套指标。
