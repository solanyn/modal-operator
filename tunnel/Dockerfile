FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install aiohttp

# Copy proxy files
COPY main.py .
COPY proxy.py .

EXPOSE 8080

# Use main.py which has Modal Functions support
CMD ["python", "main.py"]
