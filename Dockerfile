# Multi-stage: Frontend + Backend
# Stage 1: Build Frontend
FROM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install --frozen-lockfile
COPY frontend .
RUN npm run build

# Stage 2: Build Backend
FROM python:3.12-slim AS backend-build
WORKDIR /backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend .
RUN python manage.py collectstatic --noinput || true

# Stage 3: Runtime (Node + Python)
FROM node:20-alpine
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NODE_ENV=production

# Cài Python
RUN apk add --no-cache python3 py3-pip

# Copy Node deps
COPY frontend/package*.json frontend/
RUN cd frontend && npm install --production

# Copy frontend build
COPY --from=frontend-build /frontend/.next frontend/.next
COPY --from=frontend-build /frontend/public frontend/public

# Copy Python packages
COPY --from=backend-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-build /backend backend

# Entrypoint
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

EXPOSE 3000 8000

CMD ["./docker-entrypoint.sh"]
