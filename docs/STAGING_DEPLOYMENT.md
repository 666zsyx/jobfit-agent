# 私有 Linux Staging 部署

## 1. 目标

在 Linux 云服务器上部署一套仅供自己验收和面试演示的 HTTPS staging：

```text
Caddy HTTPS
→ FastAPI /app
→ PostgreSQL
→ Redis
→ Chroma Volume
→ FastEmbed Volume
```

不对外开放注册，只使用一个演示账号和合成数据。

---

## 2. 服务器准备

最低建议：

```text
Ubuntu 22.04 / 24.04
2 vCPU / 4 GB RAM
40 GB SSD
开放 22、80、443 端口
```

更稳妥：

```text
2 vCPU / 8 GB RAM
```

服务器安装：

```bash
sudo apt update
sudo apt install -y git curl ca-certificates
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

重新登录后确认：

```bash
docker --version
docker compose version
```

---

## 3. 域名

在域名服务商添加 A 记录：

```text
jobfit.example.com → 服务器公网 IP
```

等待解析：

```bash
dig +short jobfit.example.com
```

返回服务器 IP 后再继续。

---

## 4. 拉取代码和配置

```bash
git clone https://github.com/666zsyx/jobfit-agent.git
cd jobfit-agent

cp .env.staging.example .env
chmod 600 .env
```

编辑 `.env`，至少修改：

```dotenv
DOMAIN=jobfit.example.com
AUTH_JWT_SECRET=强随机值
DEMO_PASSWORD=强演示密码
LLM_API_KEY=真实Key
JOBFIT_DB_PASSWORD=URL安全的强数据库密码
```

生成随机值：

```bash
openssl rand -hex 32
```

注意：

```text
JOBFIT_DB_PASSWORD 先使用字母、数字、-、_、.、~，避免 DSN 特殊字符解析问题。
ALLOW_DEMO_TOKEN 必须保持 false。
不要提交 .env。
```

---

## 5. 部署

```bash
bash scripts/deploy_staging.sh
```

脚本会：

```text
docker compose config 检查
构建应用镜像
启动 PostgreSQL / Redis / FastAPI / Caddy
等待 /ready
```

查看状态：

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.staging.yml ps
docker compose -f docker-compose.prod.yml -f docker-compose.staging.yml logs -f jobfit-agent
docker compose -f docker-compose.prod.yml -f docker-compose.staging.yml logs -f caddy
```

---

## 6. 初始化演示数据

首次部署后执行：

```bash
bash scripts/seed_staging.sh
```

它会幂等创建：

```text
demo_user
演示简历
演示岗位
```

访问：

```text
https://jobfit.example.com/app
```

演示账号使用 `.env` 中的：

```text
DEMO_USERNAME
DEMO_PASSWORD
```

---

## 7. 验证

服务器本机：

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

公网：

```bash
curl -fsS https://jobfit.example.com/health
curl -fsS https://jobfit.example.com/ready
```

验收顺序：

```text
登录
→ 选择演示简历
→ 选择演示岗位
→ 开始分析
→ SSE 执行
→ 人工确认
→ 查看报告
→ 刷新页面确认历史仍存在
```

---

## 8. 更新版本

```bash
git pull origin main
bash scripts/deploy_staging.sh
```

数据库迁移和 Checkpoint 初始化会在容器启动命令中执行。

---

## 9. 备份

```bash
bash scripts/backup_postgres.sh
```

默认输出到：

```text
backups/jobfit_YYYYMMDD_HHMMSS.dump
```

Chroma 是可重建索引；PostgreSQL 是业务事实源，必须优先备份。

---

## 10. 安全边界

```text
应用端口只绑定 127.0.0.1
公网只开放 Caddy 的 80/443
Caddy 自动签发和续期 HTTPS
生产关闭 demo-token
登录接口有限流
不接收真实个人简历
staging 只使用合成演示数据
Token 配额仍不是并发原子预留，不开放任意用户消耗额度
```

---

## 11. 回滚

```bash
git log --oneline -10
git checkout <上一个稳定提交>
bash scripts/deploy_staging.sh
```

紧急停止：

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.staging.yml down
```

不要使用 `down -v`，除非明确要删除数据库和向量卷。
