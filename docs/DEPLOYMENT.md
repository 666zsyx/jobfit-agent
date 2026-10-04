# STEP 12 Deployment

私有 staging 的完整操作见 [STAGING_DEPLOYMENT.md](STAGING_DEPLOYMENT.md)。

## 0. 当前缺口

```text
当前只有一个共享演示账号，不允许收藏或上传真实个人简历。
公网 staging 前必须保持 demo 数据为合成数据，并定期清理。
```

公网访问必须通过 HTTPS 反向代理，应用端口只绑定 127.0.0.1。


## 1. 目标

让 JobFit Agent 具备 Linux 云服务器部署所需的：

```text
环境配置检查
数据库迁移
LangGraph Checkpoint 初始化
Redis
健康检查
就绪检查
生产 Compose
日志和限流配置
```

---

## 2. 本机边界

```text
当前 Windows 本机只做代码、测试和部署配置验证
不安装或修复 WSL、Virtual Machine Platform、Docker Desktop
实际 staging 和公网部署需要 Linux 云服务器
```

---

## 3. 必需配置

```dotenv
APP_ENV=production
AUTH_JWT_SECRET=至少32位强随机值
AUTH_JWT_EXPIRE_MINUTES=1440
DEMO_USERNAME=demo_user
DEMO_PASSWORD=至少12位强密码
ALLOW_DEMO_TOKEN=false
LLM_API_KEY=真实Key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
DATABASE_URL=postgresql+asyncpg://jobfit_app:密码@postgres:5432/jobfit_prod
REDIS_URL=redis://redis:6379/0
JOBFIT_DB_PASSWORD=强密码
LOG_LEVEL=INFO
LOG_FORMAT=json
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60
DAILY_REQUEST_QUOTA=200
DAILY_TOKEN_QUOTA=200000
LLM_INPUT_PRICE_PER_1M=实际价格
LLM_OUTPUT_PRICE_PER_1M=实际价格
COST_CURRENCY=CNY
```

安全要求：

```text
不要把真实 .env 提交到 Git
不要输出或记录真实 Key
生产环境禁止使用 CHANGE_ME
```

---

## 4. 配置检查

```powershell
.\.venv\Scripts\python.exe .\scripts\check_deployment_config.py --strict
```

连接依赖检查：

```powershell
.\.venv\Scripts\python.exe .\scripts\check_deployment_config.py --connect
```

检查内容：

```text
必需环境变量
生产环境占位符
数据库 URL 类型
Redis URL 类型
限流是否启用
日志格式
模型价格提醒
数据库连接
Checkpoint 表
Redis PING
```

---

## 5. 启动顺序

```text
读取 .env
→ check_deployment_config.py
→ alembic upgrade head
→ setup_langgraph_checkpoint.py
→ uvicorn app.main:app
→ /health
→ /ready
→ seed_demo_data.py（仅全新 staging）
```

`/health` 只表示进程存活。

`/ready` 检查：

```text
PostgreSQL SELECT 1
checkpoint_migrations 表
Redis PING
```

---

## 6. 生产 Compose

文件：

```text
docker-compose.prod.yml
```

服务：

```text
postgres
redis
jobfit-agent
```

持久化与并发约束：

```text
Chroma 挂载 chroma_prod_data 到 /app/.cache/chroma
FastEmbed 挂载 fastembed_prod_data 到 /app/.cache/fastembed
Uvicorn 显式使用 --workers 1
```

原因：当前 Chroma 和 FastEmbed 都是进程内本地实例。staging 阶段固定单 Worker，避免多个进程同时访问本地索引造成一致性风险。

本机可先检查生产 Compose 资产：

```powershell
.\.venv\Scripts\python.exe .\scripts\check_prod_compose.py
```

启动：

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

查看状态：

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f jobfit-agent
```

首次初始化演示数据：

```bash
docker compose -f docker-compose.prod.yml exec jobfit-agent   python scripts/seed_demo_data.py
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

数据库备份：

```bash
mkdir -p backups
docker compose -f docker-compose.prod.yml exec -T postgres   pg_dump -U jobfit_app -d jobfit_prod -Fc   > "backups/jobfit_$(date +%Y%m%d_%H%M%S).dump"
```

恢复前先停止应用写入：

```bash
docker compose -f docker-compose.prod.yml stop jobfit-agent
docker compose -f docker-compose.prod.yml exec -T postgres   pg_restore -U jobfit_app -d jobfit_prod --clean --if-exists   < backups/jobfit_YYYYMMDD_HHMMSS.dump
docker compose -f docker-compose.prod.yml start jobfit-agent
```

---

## 7. Dockerfile

已更新：

```text
复制 app、alembic、scripts
非 root 用户运行
健康检查使用 /ready
```

---

## 8. 远程部署检查清单

```text
Linux 主机可用
Docker Engine 可用
.env 权限最小化
LLM_API_KEY 已配置
JOBFIT_DB_PASSWORD 已配置
Alembic upgrade 成功
Checkpoint setup 成功
/health 返回 200
/ready 返回 200
日志为 JSON
限流已开启
测试数据未混入生产库
```

在当前没有 Linux 服务器的情况下，以上远程步骤标记为“待远程验证”。
