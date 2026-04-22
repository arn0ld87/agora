FROM python:3.11

# 安装 Node.js （满足 >=18）及必要工具
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm curl \
  && rm -rf /var/lib/apt/lists/*

# 从 uv 官方镜像复制 uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Create a non-root user
RUN useradd -m -u 1000 agora

# Create necessary directories and set permissions
RUN mkdir -p /app/backend/uploads /app/backend/logs \
  && chown -R agora:agora /app

# 先复制依赖描述文件以利用缓存
COPY --chown=agora:agora package.json package-lock.json ./
COPY --chown=agora:agora frontend/package.json frontend/package-lock.json ./frontend/
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/

# 安装依赖（Node + Python）
RUN npm ci \
  && npm ci --prefix frontend \
  && cd backend && uv sync

# 复制项目源码
COPY --chown=agora:agora . .

# Switch to non-root user
USER agora

# Im Container bindet Flask auf 0.0.0.0, damit der Port-Publish greift.
# Außerhalb von Docker defaultet run.py auf 127.0.0.1.
ENV FLASK_HOST=0.0.0.0

EXPOSE 5173 5001

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5001/health || exit 1

# 同时启动前后端（开发模式）
CMD ["npm", "run", "dev"]
