FROM python:3.11-slim

WORKDIR /app

# System deps for common scientific/Python wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Lean compose deps (see also root requirements.txt for full local/dev set).
COPY prop_algo/deploy/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Layout: /app/{core,infra,trading,risk,learning,services,mission_ui,...}
COPY prop_algo/ /app/

ENV PYTHONPATH=/app
ENV REDIS_HOST=redis
ENV REDIS_PORT=6379
ENV PYTHONUNBUFFERED=1

# Default entrypoint overridden per service in compose
CMD ["python", "-m", "services.market_data_service.main"]
