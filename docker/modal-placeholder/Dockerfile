FROM python:3.11-alpine

WORKDIR /app

# Install dependencies
RUN pip install aiohttp

# Copy placeholder logic
COPY main.py .

# Default port exposure
EXPOSE 8080

CMD ["python", "main.py"]
