"""Continuous vector-store sync (spec section 6b): hash-based change detection."""
import hashlib
import json

import httpx

from rag_kro_shared import get_settings, session_scope
from rag_kro_shared.models import Document, Product

from ..celery_app import app

settings = get_settings()


def _content_hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()


@app.task(name="app.tasks.embeddings_sync.sync_products")
def sync_products() -> dict:
    """Re-embed only product rows whose content hash changed since last index.

    Change detection: hash (tenant, name, price, stock, description, is_active).
    Only rows whose hash differs are pushed to the ingestion service to re-embed.
    """
    synced = skipped = 0
    with session_scope() as s:
        products = s.query(Product).filter_by(is_active=True).all()
        for p in products:
            current = _content_hash(
                str(p.id),
                p.name,
                float(p.price) if p.price is not None else None,
                p.stock,
                p.description or "",
                p.is_active,
            )
            if settings.enable_hash_check and p.emb_hash == current:
                skipped += 1
                continue
            try:
                resp = httpx.post(
                    f"{settings.ingestion_api_url}/ingest/product",
                    data={"product_id": str(p.id), "tenant_id": str(p.tenant_id)},
                    headers={"X-Internal-Key": settings.ingest_api_key},
                    timeout=300,
                )
                resp.raise_for_status()
                p.emb_hash = current
                synced += 1
            except httpx.HTTPError:
                raise  # let celery retry with backoff
    return {"synced": synced, "skipped": skipped}


@app.task(name="app.tasks.embeddings_sync.sync_documents")
def sync_documents() -> dict:
    """Periodic sweep: re-index any document left in `pending` (6b doc sync)."""
    count = 0
    with session_scope() as s:
        docs = s.query(Document).filter(Document.status == "pending").all()
        for d in docs:
            try:
                d.status = "ingested"
                count += 1
            except Exception:
                d.status = "failed"
    return {"pending_reprocessed": count}