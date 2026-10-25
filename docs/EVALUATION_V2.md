# 评估体系 V2（Day 1）

> 目标：先补覆盖缺口，再扩数量。Day 1 不追求把评估集堆到 1000 条。

## 1. 本次改了什么

- 评估集从 **30 条扩到 50 条**：
  - 新增 10 条 mock：工具错误、循环控制、引用违规；
  - 新增 10 条 live：三态边界（strong / partial / insufficient）。
- 新增 `expected_tool_error_count`：
  - 区分“预期内的故障注入/恢复”和“真实异常”；
  - 避免错误恢复 case 把 `tool_success_rate` 错误拉低。
- 修复重复引用校验：
  - `citation_valid` 现在同时检查集合相等和长度相等，重复引用会被判为无效。
- 回放报告和真实执行报告都新增 **按类别（by category）** 汇总。

## 2. 当前评估集构成

- 总 case 数：**50**
- Mock / 回放：**50 条**
- Live 可执行：**45 条**（3 条持久化人工确认/中断 case + 2 条 mock-only 循环 case 在 live 脚本中跳过）
- 契约测试覆盖：3 条人工确认/中断路径（Graph revise / Graph reject / ReAct max_steps）

### 新增 mock case（10）

- `mock_unknown_tool_recovered`
- `mock_invalid_arguments_recovered`
- `mock_tool_timeout_recovered`
- `mock_tool_handler_error_recovered`
- `mock_max_steps_loop`
- `mock_repeated_tool_loop`
- `mock_citation_missing`
- `mock_citation_unknown_id`
- `mock_citation_duplicate_id`
- `mock_empty_evidence_abstain`

### 新增 live case（10）

- `live_strong_match_exact`
- `live_partial_match_weak`
- `live_insufficient_no_evidence`
- `live_partial_vs_insufficient`
- `live_mixed_three_states`
- `live_multi_requirement_partial`
- `live_long_resume_partial`
- `live_short_resume_insufficient`
- `live_cross_section_match`
- `live_weak_evidence_partial`

## 3. 回放结果（50 条，mock）

- task_completion_rate：**1.0000**
- tool_sequence_accuracy：**0.9800**
- tool_precision：**0.9960**
- tool_recall：**1.0000**
- tool_f1：**0.9978**
- tool_success_rate：**1.0000**
- match_status_f1：**1.0000**
- citation_f1：**0.9467**
- citation_validity_rate：**0.9200**
- abstention_accuracy：**1.0000**
- confirmation_recovery_rate：**1.0000**
- unsupported_suggestion_rate：**0.0200**
- average_steps：**3.12**
- average_usage_total：**1294.20**
- p50 latency：**4200 ms**
- p95 latency：**7000 ms**
- 门槛结论：**PASS**

## 4. 真实执行结果（45 条观测）

- task_completion_rate：**1.0000**
- tool_recall：**0.9822**
- tool_f1：**0.8473**（低于 0.85，FAIL）
- tool_success_rate：**1.0000**
- match_status_f1：**0.4341**（低于 0.85，FAIL）
- abstention_accuracy：**0.8444**（低于 0.90，FAIL）
- unsupported_suggestion_rate：**0.0000**
- evidence_backed_rate：**1.0000**
- average_steps：**5.69**
- average_usage_total：**18616.16**
- p95 latency：**14584 ms**
- 门槛结论：**REVIEW**（5 PASS / 3 FAIL）

### 关键发现

- 扩样到 45 条后，match_status_f1 从 0.5765 降到 **0.4341**，弃答准确率从 0.9630 降到 **0.8444**：三态边界和弃答行为是当前最弱的地方。
- tool_f1 0.8473 低于 0.85，但 tool_recall 0.9822 通过；差异主要来自当前 live 路径多调一次 extract_resume_sections，不是漏调关键工具。
- 评估集里的 expected 目前仍是回放口径，不是 45 条 live 观测的人工标注真值；下一步必须人工校准，不能靠改阈值让它变绿。

## 5. 已知限制

1. **live 脚本仍不执行 3 条持久化人工确认/中断 case**：
   - 它们需要持久化任务路径；
   - 目前由 `tests/test_jobfit_graph_runtime.py` 的 Graph/ReAct 契约测试覆盖；
   - Day 1 没有实现持久化 live runner。
2. **当前 live 路径不产生 chunk_id**：
   - live 报告中的 citation ID 维度指标不具代表性；
   - 引用质量仍以 `evidence_backed_rate` 和 `unsupported_suggestion_rate` 约束；
   - 真正的 chunk_id 校验在持久化 RAG 路径中。
3. **50 条仍是原型规模**：
   - 足够验证链路和暴露问题；
   - 不足以证明强泛化；
   - holdout / 双人标注 / 置信区间是下一阶段工作。

## 6. 运行方式

```bash
# 回放 / mock 报告（50 条）
python scripts/evaluate_agent.py

# 真实执行（会调用 LLM；可先用 dry-run 看覆盖）
python scripts/evaluate_agent_live.py --dry-run
python scripts/evaluate_agent_live.py

# 人工确认/中断契约测试
python -m pytest tests/test_jobfit_graph_runtime.py -q
```

## 7. 下一步

1. 对 45 条 live 观测做人工标注，校准 expected 三态标签；不要用回放口径代替 live 真值。
2. 实现持久化 live runner，把 3 条人工确认 case 从 contract-only 提升为 live。
3. 加 bootstrap 95% 置信区间和三态混淆矩阵。
4. 若时间允许，再把 RAG 评估集从 100 扩到 300，并锁 60 条 holdout。
