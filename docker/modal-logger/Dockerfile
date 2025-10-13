FROM ghcr.io/astral-sh/uv:python3.11-alpine

# Install minimal system dependencies
RUN apk add --no-cache curl bash

# Install modal (not modal-client) using uv
RUN uv pip install --system --no-cache modal

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/

# Add log streaming script
COPY stream-logs.sh /usr/local/bin/stream-logs.sh
RUN chmod +x /usr/local/bin/stream-logs.sh

ENTRYPOINT ["/usr/local/bin/stream-logs.sh"]
