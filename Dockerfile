# Multi-stage build: Frontend + Backend
# Stage 1: Build Frontend (Next.js)
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install --frozen-lockfile
COPY frontend .
RUN npm run build

# Stage 2: Build Backend (Django)
FROM python:3.12-slim AS backend-builder
WORKDIR /backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend .
RUN python manage.py collectstatic --noinput || true

# Stage 3: Final Runtime (Nginx + Daphne)
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    nginx curl && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages
COPY --from=backend-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy backend
COPY --from=backend-builder /backend /app/backend

# Copy frontend build
COPY --from=frontend-builder /frontend/.next /app/frontend/.next
COPY --from=frontend-builder /frontend/public /app/frontend/public
COPY --from=frontend-builder /frontend/node_modules /app/frontend/node_modules
COPY --from=frontend-builder /frontend/package.json /app/frontend/

# Copy Nginx config + entrypoint
COPY nginx.conf /etc/nginx/nginx.conf
COPY docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

CMD ["/app/docker-entrypoint.sh"]
