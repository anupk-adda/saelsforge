# syntax=docker/dockerfile:1

FROM node:20-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONPATH=/app \
    PORT=8080 \
    CRM_MCP_URL=http://127.0.0.1:3001

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx supervisor curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY crm_mcp/requirements.txt /tmp/crm-requirements.txt
RUN pip install --no-cache-dir \
    -r /tmp/backend-requirements.txt \
    -r /tmp/crm-requirements.txt

COPY backend/ /app/backend/
COPY crm_mcp/ /app/crm_mcp/
COPY --from=frontend-builder /build/dist/ /usr/share/nginx/html/
COPY deploy/ibmcloud/nginx.conf /etc/nginx/nginx.conf
COPY deploy/ibmcloud/supervisord.conf /etc/supervisor/conf.d/salesforge.conf

RUN mkdir -p /run/nginx /var/log/supervisor /tmp/salesforge

EXPOSE 8080

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
