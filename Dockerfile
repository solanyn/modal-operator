FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml uv.lock ./
COPY modal_operator/ ./modal_operator/
COPY README.md ./

# Install dependencies and the package
RUN uv sync --frozen && uv pip install -e .

# Run the operator
CMD ["uv", "run", "python", "-m", "modal_operator"]
