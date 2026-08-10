# 股海怪物云服务 部署镜像（Python 3.12 slim）
FROM python:3.12-slim

WORKDIR /app

# 系统依赖（akshare 需要编译/网络库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# 依赖（先装 requirements 利用缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY app ./app
COPY tools ./tools

# skill 引擎（可选：需要 akshare 等分析依赖；也可不挂载，仅用鉴权/发卡）
ARG SKILL_DIR=/app/skill
COPY skill ./skill

# 环境变量（生产用环境变量注入，不写入镜像）
ENV APP_ENV=prod \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fs http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
