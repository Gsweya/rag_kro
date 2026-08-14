FROM rag_kro-python-base:latest

WORKDIR /app

COPY packages/python/rag_kro_shared /packages/python/rag_kro_shared
RUN pip install --no-cache-dir --retries 10 --default-timeout=120 -e /packages/python/rag_kro_shared

COPY services/rag/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --retries 10 --default-timeout=120 -r /app/requirements.txt

COPY services/rag/app /app/app
ENV PYTHONPATH=/app:/packages/python/rag_kro_shared

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
