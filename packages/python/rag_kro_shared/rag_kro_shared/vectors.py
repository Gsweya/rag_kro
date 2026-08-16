"""Qdrant vector-store client wrapper, tenant-scoped (section 6b metadata filters)."""
import hashlib
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from .config import get_settings


class VectorStore:
    def __init__(self, url: str | None = None, collection: str | None = None) -> None:
        s = get_settings()
        self._url = url or s.qdrant_url
        self._base_collection = collection or s.qdrant_collection
        self._per_tenant = s.qdrant_per_tenant_collections
        self._client = QdrantClient(url=self._url)

    def _collection_for(self, tenant_id: str) -> str:
        """Resolve the collection name for a tenant.

        With per-tenant collections enabled the Qdrant collection itself provides
        hard isolation on top of the tenant_id payload filter (defense in depth).
        """
        if self._per_tenant:
            return f"{self._base_collection}__{tenant_id}"
        return self._base_collection

    def _ensure_collection(self, collection: str) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if collection not in existing:
            s = get_settings()
            metric = getattr(Distance, s.vector_metric.upper(), Distance.COSINE)
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=s.vector_size, distance=metric),
            )

    # ---- writes ------------------------------------------------------------
    def upsert(self, points: list[tuple[str, list[float], dict]], tenant_id: str | None = None) -> None:
        collection = self._collection_for(tenant_id or "default")
        self._ensure_collection(collection)
        pts = [
            PointStruct(id=self._valid_point_id(pid), vector=vec, payload=meta)
            for pid, vec, meta in points
        ]
        self._client.upsert(collection_name=collection, points=pts)

    @staticmethod
    def _valid_point_id(pid: str | int) -> str | int:
        """Qdrant only accepts unsigned integers or UUIDs as point IDs."""
        if isinstance(pid, int):
            return pid
        try:
            return uuid.UUID(pid)
        except (ValueError, AttributeError, TypeError):
            pass
        if str(pid).isdigit():
            return int(pid)
        return uuid.UUID(hex=hashlib.md5(str(pid).encode()).hexdigest())

    def delete_by_metadata(self, tenant_id: str, **filters: Any) -> None:
        """Filtered delete, e.g. delete_by_metadata(tenant, doc_id=...) (6b stale cleanup)."""
        must = [FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))]
        for key, value in filters.items():
            must.append(FieldCondition(key=key, match=MatchValue(value=str(value))))
        collection = self._collection_for(tenant_id)
        self._ensure_collection(collection)
        self._client.delete(
            collection_name=collection,
            points_selector=Filter(must=must),
        )

    # ---- reads ------------------------------------------------------------
    def search(self, vector: list[float], tenant_id: str, top_k: int) -> list[dict]:
        must = [FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))]
        collection = self._collection_for(tenant_id)
        self._ensure_collection(collection)
        results = self._client.query_points(
            collection_name=collection,
            query=vector,
            query_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
        )
        out = []
        for r in results.points:
            score = getattr(r, "score", None)
            page = dict(r.payload or {})
            page["_score"] = score
            out.append(page)
        return out


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store