# 股海怪物云服务 部署镜像（Python 3.12 slim）
# 注意：不安装 gcc/g++ 等编译工具——全部依赖均为预编译 wheel，
# 避免 Railway 构建环境 apt 源不可达导致的构建失败。
FROM python:3.12-slim

WORKDIR /app

# 依赖（先装 requirements 利用缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY app ./app
COPY tools ./tools

# 环境变量（生产用环境变量注入，不写入镜像）
ENV APP_ENV=prod \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
