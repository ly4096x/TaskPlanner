# Stage 1: Build web client
FROM node:22-slim AS web-builder
WORKDIR /app/client_web
COPY client_web/package.json client_web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY client_web/ ./
COPY shared/ /app/shared/
RUN pnpm build

# Stage 2: Python server
FROM python:3.13-slim
WORKDIR /app

# Copy source
COPY pyproject.toml ./
COPY server/ server/
COPY client_cli/ client_cli/
COPY shared/ shared/

# Copy web dist before pip install (pyproject.toml force-includes it)
COPY --from=web-builder /app/client_web/dist client_web/dist/

RUN pip install --no-cache-dir .

# Runtime
ENV TASKPLANNER_DATA_DIR=/data
EXPOSE 8000
VOLUME /data

ENTRYPOINT ["TaskPlannerServer", "/data", "--host", "0.0.0.0"]
CMD ["--port", "8000"]
