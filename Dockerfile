# Multi-stage build for single distroless image containing operator, logger, and proxy
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY modal_operator/ ./modal_operator/
COPY README.md ./

# Copy sidecar components into the package
COPY docker/modal-logger/logger.py ./modal_operator/logger.py
COPY tunnel/proxy.py ./modal_operator/proxy.py

# Install dependencies in a virtual environment
RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies and the package
RUN uv sync --frozen && uv pip install -e .

# Runtime stage - distroless Python
FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy the installed package with all components
COPY --from=builder /app/modal_operator /app/modal_operator

# Set up environment
ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/.venv/lib/python3.11/site-packages:/app

# Default to running operator (can be overridden in pod spec)
# Logger: modal-logger
# Proxy: modal-proxy
ENTRYPOINT ["modal-operator"]
