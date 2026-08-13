FROM python:3.12-slim

WORKDIR /app

# system deps for PDFs/local vision sometimes
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmagic1 && rm -rf /var/lib/apt/lists/*

# shared package
COPY packages/python/rag_kro_shared /packages/python/rag_kro_shared
RUN pip install --no-cache-dir --retries 10 --default-timeout=120 -e /packages/python/rag_kro_shared

COPY services/ingestion/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --retries 10 --default-timeout=120 -r /app/requirements.txt

COPY services/ingestion/app /app/app
ENV PYTHONPATH=/app:/packages/python/rag_kro_shared

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]