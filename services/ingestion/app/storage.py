"""Object storage (MinIO, S3-compatible). Keeps raw source files for retrieval/regression."""
import io

import httpx

from rag_kro_shared import get_settings


def save_object(tenant_id: str, filename: str, raw: bytes) -> str:
    settings = get_settings()
    from minio import Minio

    client = Minio(
        settings.minio_endpoint.replace("http://", "").replace("https://", ""),
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_endpoint.startswith("https://"),
    )
    bucket = settings.minio_bucket
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    key = f"{tenant_id}/documents/{filename}"
    client.put_object(bucket, key, io.BytesIO(raw), length=len(raw))
    return key


def sign_url(path: str) -> str:
    settings = get_settings()
    from minio import Minio

    client = Minio(
        settings.minio_endpoint.replace("http://", "").replace("https://", ""),
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=settings.minio_endpoint.startswith("https://"),
    )
    return client.presigned_get_object(settings.minio_bucket, path, expires=3600)


def http_download(url: str) -> bytes:
    resp = httpx.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content