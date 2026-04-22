FROM python:3.11

# Install Node.js (>=18) and required tools
RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm curl \
  && rm -rf /var/lib/apt/lists/*

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

WORKDIR /app

# Create a non-root user
RUN useradd -m -u 1000 agora

# Create necessary directories and set permissions
RUN mkdir -p /app/backend/uploads /app/backend/logs \
  && chown -R agora:agora /app

# Copy dependency manifests first to leverage layer caching
COPY --chown=agora:agora package.json package-lock.json ./
COPY --chown=agora:agora frontend/package.json frontend/package-lock.json ./frontend/
COPY --chown=agora:agora backend/pyproject.toml backend/uv.lock ./backend/

# Install dependencies (Node + Python). uv runs as root here, so fix up
# the venv ownership afterwards so the agora user can refresh it at runtime.
RUN npm ci \
  && npm ci --prefix frontend \
  && cd backend && uv sync \
  && chown -R agora:agora /app

# Copy project sources
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

# Start backend and frontend in parallel (dev mode)
CMD ["npm", "run", "dev"]
