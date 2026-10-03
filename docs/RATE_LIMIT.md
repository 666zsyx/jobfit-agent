# STEP 12 Rate Limit

## 1. 目标

防止单用户或异常客户端耗尽模型额度和服务资源。

保护对象：

```text
聊天接口
岗位 JD 提取接口
手写 ReAct 岗位匹配
LangGraph Graph run / resume
SSE 接口
```

---

## 2. 限制维度

```text
每用户每分钟请求数
每用户每天请求数
每用户每天 Token 数
并发任务运行锁
```

配置：

```dotenv
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
DAILY_REQUEST_QUOTA=200
DAILY_TOKEN_QUOTA=200000
```

---

## 3. Redis Key

请求限流：

```text
jobfit:rate:{user_id}:{scope}:{minute_window}
```

每日请求：

```text
jobfit:quota:requests:{user_id}:{date}
```

每日 Token：

```text
jobfit:quota:tokens:{user_id}:{date}
```

---

## 4. 算法

当前实现使用 Redis 固定窗口计数：

```text
INCR
EXPIRE
TTL
```

优点：

```text
实现简单
Redis 原子 INCR
容易测试和观察
```

限制：

```text
固定窗口边界可能出现短时间突增
后续可升级为滑动窗口或令牌桶
```

---

## 5. 降级策略

Redis 正常：

```text
使用 Redis 做跨进程限流和配额
```

Redis 故障：

```text
使用进程内保守计数器
保证单进程不会无限放行
不伪装成分布式共享配额
```

---

## 6. 429 响应

超限返回：

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
```

响应体：

```json
{
  "code": 429,
  "message": "请求过于频繁，请稍后重试",
  "data": {
    "limit_type": "rate:chat"
  }
}
```

---

## 7. API 集成

已接入：

```text
/api/chat
/api/chat/stream
/api/jobs/extract
/api/agent/match
/api/agent/tasks
/api/agent/tasks/{task_id}/run
/api/agent/tasks/{task_id}/stream
/api/agent/tasks/{task_id}/graph/run
/api/agent/tasks/{task_id}/graph/resume
/api/agent/tasks/{task_id}/graph/stream
```

Token 记录：

```text
聊天：完成后记录
岗位提取：记录内层模型 Token
手写 Agent：完成后记录
Graph Agent：完成后记录
```

---

## 8. 验证

测试：

```text
tests/test_rate_limit.py
```

脚本：

```powershell
.\.venv\Scripts\python.exe .\scripts\verify_step12_rate_limit.py
```

验证结果：

```text
请求限流：第 3 次被拒绝
每日请求配额：超限被拒绝
每日 Token 配额：超限被拒绝
429 响应带 Retry-After
```
