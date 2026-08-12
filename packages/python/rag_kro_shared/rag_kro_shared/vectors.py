"""Qdrant vector-store client wrapper, tenant-scoped (section 6b metadata filters)."""
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
        self._collection = collection or s.qdrant_collection
        self._client = QdrantClient(url=self._url)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        s = get_settings()
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            metric = getattr(Distance, s.vector_metric.upper(), Distance.COSINE)
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=s.vector_size, distance=metric),
            )

    # ---- writes ------------------------------------------------------------
    def upsert(self, points: list[tuple[str, list[float], dict]]) -> None:
        pts = [
            PointStruct(id=pid, vector=vec, payload=meta)
            for pid, vec, meta in points
        ]
        self._client.upsert(collection_name=self._collection, points=pts)

    def delete_by_metadata(self, tenant_id: str, **filters: Any) -> None:
        """Filtered delete, e.g. delete_by_metadata(tenant, doc_id=...) (6b stale cleanup)."""
        must = [FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))]
        for key, value in filters.items():
            must.append(FieldCondition(key=key, match=MatchValue(value=str(value))))
        self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(must=must),
        )

    # ---- reads ------------------------------------------------------------
    def search(self, vector: list[float], tenant_id: str, top_k: int) -> list[dict]:
        must = [FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))]
        results = self._client.query_points(
            collection_name=self._collection,
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