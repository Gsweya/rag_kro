"""Centralized ingestion API — one deployment ingests documents for ALL tenants.

Why centralized (not per-user instance):
  - One Qdrant collection, one embedding model cache, one place to run change-detection.
  - Tenants upload here; every tenant's RAG runtime queries the same index.
  - Applies spec sections 6 + 6b: PDFs/images/products/CSV -> chunk + embed -> Qdrant,
    with source_hash change detection and metadata filters {tenant_id, type, doc_id}.
"""
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware

from rag_kro_shared import get_settings, session_scope, get_vector_store, get_embedder
from rag_kro_shared.models import Document, Product

from .auth import require_internal_key
from .chunking import chunk_text
from .ingesters.pdf_ingester import parse_pdf
from .ingesters.image_ingester import caption_image
from .storage import save_object

settings = get_settings()

app = FastAPI(title="rag_kro ingestion", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

store = get_vector_store()


@app.get("/health")
def health():
    return {"service": "ingestion", "status": "ok"}


@app.post("/ingest/document")
async def ingest_document(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    doc_type: str = Form("pdf"),  # pdf | image
    api_key: str = Depends(require_internal_key),
):
    """Ingest a PDF or image into the shared vector store for a tenant."""
    raw = await file.read()
    title = file.filename
    object_key = await save_object(tenant_id, title, raw)

    text = ""
    if doc_type == "pdf":
        text = parse_pdf(raw)
    elif doc_type == "image":
        text = caption_image(raw)
    else:
        raise HTTPException(400, f"unsupported doc_type: {doc_type}")

    if not text.strip():
        raise HTTPException(400, "no extractable text (empty PDF or caption failed)")

    chunks = chunk_text(text)
    vectors = get_embedder().embed_documents([c["text"] for c in chunks])
    metas = [
        {
            "tenant_id": tenant_id,
            "type": doc_type,
            "doc_id": object_key,
            "title": title,
            "chunk_index": c["index"],
            "source": c["source"],
            "storage_path": object_key,
        }
        for c in chunks
    ]
    points = [(f"{object_key}::chunk::{m['chunk_index']}", v, m) for v, m in zip(vectors, metas)]
    store.upsert(points)

    with session_scope() as s:
        doc = Document(
            tenant_id=tenant_id,
            type=doc_type,
            title=title,
            storage_path=object_key,
            source_hash="__ingest__",
            status="indexed",
        )
        s.add(doc)
        s.commit()
        doc_id = doc.id

    return {"status": "indexed", "doc_id": str(doc_id), "chunks": len(chunks), "object_key": object_key}


@app.post("/ingest/product")
def ingest_product(
    product_id: str = Form(...),
    tenant_id: str = Form(...),
    api_key: str = Depends(require_internal_key),
):
    """Re-index a single product (called on insert/update, section 6b)."""
    with session_scope() as s:
        product = s.get(Product, product_id)
        if product is None:
            raise HTTPException(404, "product not found")
        text = (
            f"Name: {product.name}\n"
            f"Price: {product.price}\n"
            f"Stock: {product.stock}\n"
            f"Description: {product.description or ''}"
        )

    vector = get_embedder().embed_documents([text])[0]
    metas = [{
        "tenant_id": tenant_id,
        "type": "product",
        "doc_id": str(product_id),
        "title": product.name,
        "storage_path": None,
    }]
    store.delete_by_metadata(tenant_id, type="product", doc_id=str(product_id))
    store.upsert([(f"product::{product_id}", vector, metas[0])])
    return {"status": "indexed", "product_id": product_id}