# Stage 1: Install Python dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime image with Node.js + Claude CLI
FROM python:3.11-slim

WORKDIR /app

# Install Node.js 20 (required for Claude Code CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI globally
RUN npm install -g @anthropic-ai/claude-code

COPY --from=builder /install /usr/local

COPY src/ ./src/
COPY config/ ./config/
COPY pyproject.toml .
COPY scripts/entrypoint.sh /entrypoint.sh

# Non-root user required: Claude CLI refuses --dangerously-skip-permissions when run as root
RUN useradd --create-home appuser && chown -R appuser:appuser /app \
    && chmod +x /entrypoint.sh

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "src.cloud.main", "--mode", "scan", "--market", "both"]
