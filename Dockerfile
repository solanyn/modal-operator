FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY modal_operator/ ./modal_operator/
COPY README.md ./

RUN uv venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv sync --frozen && uv pip install -e .

FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/modal_operator /app/modal_operator

ENV PATH="/app/.venv/bin:/usr/local/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/.venv/lib/python3.13/site-packages:/app

ENTRYPOINT ["python3", "-m", "modal_operator"]
