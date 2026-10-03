# STEP 12 生产化设计与验收方案

> 状态：设计冻结稿
>
> 创建日期：2026-10-03
>
> 分支：feature/step-12-production-ready
>
> 基线：main@8f2038a

---

## 1. 目标

把 JobFit Agent 从“功能闭环 Agent 后端原型”提升为：

```text
可评估
可观测
可统计成本
可限流
可防护 Prompt Injection
可安全部署
可演示
可用于面试表达
```

---

## 2. 非目标与边界

不处理：

```text
Multi-Agent
Kubernetes
微服务拆分
自研向量数据库
复杂多租户
自动批量投递
大规模招聘网站爬虫
```

部署边界：

```text
本机继续只做开发、测试和部署资产验证
不在 Windows 上安装或修复 WSL、Virtual Machine Platform、Docker Desktop
远程 staging 和正式公网部署需要 Linux 云服务器
没有 Linux 环境时，部署任务标记为“配置已准备，未远程验证”
```

---

## 3. 当前基线

STEP 11 已完成：

```text
FastAPI 服务
手写 ReAct
LangGraph StateGraph
PostgreSQL Checkpoint
人工确认和中断恢复
节点级重试
Graph SSE
RAG 混合检索和 EvidencePack
30 条 RAG 评估
279 条自动化测试
```

当前缺口：

```text
缺少完整 Agent 评估体系
缺少 request_id、结构化日志和任务耗时分解
内层模型 Usage 尚未完全合并
缺少 Token 成本统计
缺少 Prompt Injection 专门防护
缺少 Redis 限流和配额
缺少敏感日志统一脱敏
缺少生产部署检查
缺少架构图、演示脚本和面试材料
```

---

## 4. 总体原则

```text
不破坏 STEP 11 行为和接口
评估先行，优化在后
安全默认为拒绝，工具白名单继续保留
成本、延迟和安全统计不能改变主业务结果
外部 JD、简历、工具结果都视为不可信输入
所有新增上限必须可配置，不能硬编码在业务节点中
```

---

## 5. PART 划分

```text
PART 0：基线审计与分支冻结
PART 1：Agent 评估体系
PART 2：可观测性与性能统计
PART 3：Token 成本统计
PART 4：Prompt Injection 和安全加固
PART 5：限流、配额与访问保护
PART 6：生产部署资产与健康检查
PART 7：架构图、演示流程和面试材料
PART 8：质量门禁与 Git 闭环
```

每个 PART：

```text
独立设计
独立实现
独立测试
独立 commit
上一部分不通过，不进入下一部分
```

---

## 6. Agent 评估体系

数据：

```text
data/evaluation/agent_cases.json
```

评估维度：

```text
岗位要求提取准确率
证据引用准确率
匹配结论一致性
无依据建议比例
工具调用成功率
任务完成率
最大步数中断率
人工确认恢复成功率
Graph SSE 完成率
```

评估输出：

```text
JSON 详细结果
Markdown 汇总报告
按 case 记录失败原因
记录模型、检索、工具和总耗时
记录 Token Usage
```

门禁：

```text
所有 case 必须可重复运行
阈值由基线确定后再固定
不能为了通过评估修改测试数据
评估失败必须保留失败样本
```

---

## 7. 可观测性与性能统计

新增 request_id：

```text
客户端可选传入 X-Request-ID
未传入时由后端生成
响应头返回 X-Request-ID
日志和任务事件关联 request_id
```

任务耗时分解：

```text
模型调用耗时
RAG 索引耗时
检索耗时
Rerank 耗时
工具执行耗时
Graph 节点耗时
任务总耗时
```

日志边界：

```text
不记录 API Key
不记录 JD 正文
不记录简历正文
不记录报告正文
不记录隐藏思维链
参数日志只记录 key，不记录 value
```

---

## 8. Token 成本统计

模型调用：

```text
外层 ReAct / LangGraph 模型调用
内层提取和匹配工具模型调用
按 provider、model、task_id 聚合
```

成本计算：

```text
输入 Token 单价
输出 Token 单价
币种
模型名称
调用次数
任务总成本
```

规则：

```text
价格通过配置读取
未知模型价格不猜测
成本统计失败不能阻断业务
Token 统计必须与现有 Usage 来源一致
```

---

## 9. Prompt Injection 与安全加固

不可信输入：

```text
岗位 JD
简历原文
会话历史
工具检索结果
用户确认内容
```

防护：

```text
系统规则优先级高于外部内容
外部内容使用明确边界标记
检测常见“忽略以上指令”等注入语句
工具调用继续经过白名单和参数校验
模型输出继续经过 Pydantic 和引用校验
高风险操作继续要求人工确认
限制输入长度和输出长度
```

边界：

```text
Prompt Injection 检测是纵深防御，不宣称 100% 防护
检测结果不能直接把用户输入当可信指令执行
安全事件只记录安全码，不记录敏感正文
```

---

## 10. 限流、配额与访问保护

Redis 组件：

```text
令牌桶或滑动窗口限流
按用户和接口限制请求速率
按天限制请求数和 Token 数
限制同时执行的任务数
```

响应：

```text
429 Too Many Requests
Retry-After
统一错误响应结构
安全错误码
```

降级：

```text
Redis 故障时提供保守的本地或数据库降级策略
不能因为限流组件故障直接无限放行
健康检查不受业务限流影响
```

---

## 11. 生产部署资产

配置检查：

```text
APP_ENV
LLM_API_KEY
LLM_BASE_URL
LLM_MODEL
DATABASE_URL
REDIS_URL
限流参数
成本参数
日志参数
```

部署顺序：

```text
配置检查
→ Alembic upgrade
→ LangGraph Checkpoint setup
→ 启动应用
→ health check
→ readiness check
```

产出：

```text
scripts/check_deployment_config.py
docker-compose.prod.yml
docs/DEPLOYMENT.md
```

---

## 12. 面试材料与演示

架构图：

```text
API 层
Agent 编排层
Tool 层
RAG 层
Memory / Checkpoint
Persistence
Security / Observability
```

演示链路：

```text
创建任务
→ 运行 Agent
→ SSE 展示工具和节点事件
→ 等待人工确认
→ 修改确认
→ 保存报告
→ 展示引用证据
→ 展示 Checkpoint 恢复
→ 展示 Token、成本和耗时
```

材料：

```text
docs/ARCHITECTURE.md
docs/DEMO_GUIDE.md
docs/INTERVIEW_QA.md
docs/RESUME_PROJECT.md
```

---

## 13. 测试策略

单元测试：

```text
评估指标
限流算法
配额计算
成本计算
脱敏函数
Prompt Injection 检测
配置检查
```

服务测试：

```text
Agent 评估运行
可观测性聚合
成本聚合
限流响应
安全边界
```

接口测试：

```text
request_id
429
健康检查
就绪检查
错误响应
```

真实集成：

```text
PostgreSQL
Redis
Alembic
Checkpoint
Graph run / resume
```

---

## 14. 完成定义

```text
[x] PART 0：设计与基线
[x] PART 1：Agent 评估
[ ] PART 2：可观测性
[ ] PART 3：Token 成本
[ ] PART 4：安全加固
[ ] PART 5：限流与配额
[ ] PART 6：部署资产
[ ] PART 7：演示与面试材料
[ ] PART 8：质量门禁与 Git 闭环
```

---

## 15. PART 1 验证记录

新增 Agent 评估模块：

```text
app/services/agent_evaluation.py
scripts/evaluate_agent.py
data/evaluation/agent_cases.json
tests/test_agent_evaluation.py
```

评估维度：

```text
任务完成率
工具顺序准确率
工具 Precision / Recall / F1
工具成功率
匹配状态 F1
引用 Precision / Recall / F1
引用有效性
拒答准确率
人工确认恢复率
无依据建议比例
步数、Token Usage、p50 / p95 延迟
```

评估结果：

```text
case_count=15
task_completion_rate=1.0000
tool_sequence_accuracy=0.9333
tool_f1=0.9926
tool_success_rate=0.9778
match_status_f1=1.0000
citation_f1=0.9778
citation_validity_rate=0.9333
abstention_accuracy=1.0000
confirmation_recovery_rate=1.0000
unsupported_suggestion_rate=0.0667
strict_passed=true
```

生成报告：

```text
docs/agent_evaluation_results.json
docs/AGENT_EVALUATION.md
```

质量门禁：

```text
Agent 评估测试：8 passed
完整测试：287 passed
```
