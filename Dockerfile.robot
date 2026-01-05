# Dockerfile cho robot server (nếu Render muốn deploy riêng)
FROM python:3.12-slim

WORKDIR /robot

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy từ repo
COPY requirements.txt . 2>/dev/null || echo "No requirements.txt"
RUN pip install --no-cache-dir flask flask-cors requests 2>/dev/null || true

# Copy code
COPY dogzilla_server . 2>/dev/null || echo "No dogzilla_server"

EXPOSE 9000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

CMD ["python", "-m", "dogzilla_server.app"]
