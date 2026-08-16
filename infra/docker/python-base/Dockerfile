# Shared Python base for the ML services (rag / ingestion / worker).
#
# The heavy layers — torch + sentence-transformers (~1GB) — are installed
# HERE ONCE instead of per-service. rag/ingestion/worker build FROM this image,
# so the big download happens a single time and is cached across all three.
#
# On slow/flaky connections, pre-fetch wheels first (resumable):
#     bash infra/docker/python-base/fetch-wheels.sh
# then the build below installs from ./wheels/*.whl instead of the network.
FROM python:3.12-slim

WORKDIR /app

COPY infra/docker/python-base/requirements.txt /requirements.txt

# install pre-downloaded wheels when present (offline-friendly)
COPY infra/docker/python-base/wheels/ /wheels/
RUN pip install --no-cache-dir --retries 10 --default-timeout=120 /wheels/*.whl \
    || pip install --no-cache-dir --retries 10 --default-timeout=120 -r /requirements.txt

ENV PYTHONUNBUFFERED=1
