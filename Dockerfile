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
    HOST=0.0.0.0

EXPOSE 8000

# 关键：监听 Railway 注入的 $PORT（默认 8080），否则平台健康检查连不上
# 注意：单 worker——Railway 免费层内存有限，多 worker 启动会内存不足崩溃
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
