# Multi-stage build for Accessible News Aggregator
# Builder stage
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

COPY app/ /app/app/
COPY config/ /app/config/
COPY alembic/ /app/alembic/
COPY alembic.ini /app/

ENV PYTHONPATH=/app
ENV FLASK_APP=app:create_app

WORKDIR /app

CMD ["gunicorn", "-b", "0.0.0.0:5000", "app:create_app"]
