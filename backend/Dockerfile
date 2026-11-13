FROM python:3.13-slim
WORKDIR /app/backend
COPY pyproject.toml ./
COPY malgraph ./malgraph
RUN pip install --no-cache-dir .
# Jikan/MAL response cache lives at /app/data/cache (matches CACHE_DIR=data/cache relative to the repo root).
RUN mkdir -p /app/data/cache
WORKDIR /app
EXPOSE 8000
# Caddy is the only thing that can reach the API (no published port), so trust the client IP it passes on.
CMD ["uvicorn", "malgraph.api.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
