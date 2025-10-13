FROM python:3.11-slim

# Install dependencies
RUN pip install modal kubernetes asyncio-mqtt websockets

# Copy proxy script
COPY modal_proxy.py /app/modal_proxy.py
COPY tunnel_manager.py /app/tunnel_manager.py

WORKDIR /app

# Run the proxy
CMD ["python", "modal_proxy.py"]
