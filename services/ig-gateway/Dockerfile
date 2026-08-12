FROM python:3.12-slim

WORKDIR /app

COPY packages/python/rag_kro_shared /packages/python/rag_kro_shared
RUN pip install --no-cache-dir --default-timeout=120 -e /packages/python/rag_kro_shared

COPY services/ig-gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --default-timeout=120 -r /app/requirements.txt

COPY services/ig-gateway/app /app/app
ENV PYTHONPATH=/app:/packages/python/rag_kro_shared

EXPOSE 8200

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]