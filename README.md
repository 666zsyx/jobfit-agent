# JobFit Agent

基于 RAG 和工具调用的可解释岗位匹配与差距分析 Agent。

## 当前阶段

STEP 02：FastAPI 服务骨架。

## 本地启动

```bash
python -m uvicorn app.main:app --reload
```

## 健康检查

```http
GET /health
```

## Docker

构建并启动：

```bash
docker compose up --build
```

后台启动：

```bash
docker compose up -d --build
```

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

容器内服务监听 8000 端口，宿主机访问：

```text
http://127.0.0.1:8000
```
