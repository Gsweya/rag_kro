# Shared Python base for the ML services (rag / ingestion / worker).
#
# The heavy layers — torch + sentence-transformers (~1GB) — are installed
# HERE ONCE instead of per-service. rag/ingestion/worker build FROM this image,
# so the big download happens a single time and is cached across all three.
FROM python:3.12-slim

WORKDIR /app

COPY infra/docker/python-base/requirements.txt /requirements.txt
RUN pip install --no-cache-dir --retries 10 --default-timeout=120 -r /requirements.txt

ENV PYTHONUNBUFFERED=1
