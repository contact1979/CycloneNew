# Build stage
FROM python:3.11-slim AS builder

# Set build arguments and environment variables
ARG APP_VERSION=0.1.0
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV POETRY_VERSION=1.5.1
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VIRTUALENVS_CREATE=false
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install production dependencies
RUN poetry install --no-dev --no-interaction --no-ansi \
    && poetry export -f requirements.txt --output requirements.txt

# Runtime stage
FROM python:3.11-slim

# Set runtime environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONOPTIMIZE=2
ENV PATH="/app/bin:$PATH"
ENV PORT=8000

# Add non-root user
RUN groupadd -r bot && useradd -r -g bot -d /app -s /sbin/nologin -c "Docker image user" bot

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && rm requirements.txt

# Copy application code
COPY . .

# Set permissions
RUN chown -R bot:bot /app && \
    chmod -R 755 /app

# Switch to non-root user
USER bot

# Expose Prometheus metrics port
EXPOSE $PORT

# Add health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Set entrypoint and default command
ENTRYPOINT ["python"]
CMD ["-m", "hydrobot.main"]