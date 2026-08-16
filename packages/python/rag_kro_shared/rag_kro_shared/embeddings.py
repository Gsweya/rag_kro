"""Embedding clients: local sentence-transformers (needs the extra) or HF Inference API.

The ingestion/worker images install `sentence_transformers` for the `local` backend
(truly $0, no rate limits). The `hf` backend calls the free HF Inference API.
"""
from .config import get_settings


class Embedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class LocalEmbedder(Embedder):
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer  # local extra

        settings = get_settings()
        self._model = SentenceTransformer(settings.hf_embeddings_model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


class HFEmbedder(Embedder):
    def __init__(self) -> None:
        import httpx

        settings = get_settings()
        self._url = (
            f"{settings.hf_api_url}"
            f"/pipeline/feature-extraction/{settings.hf_embeddings_model}"
        )
        self._headers = {"Authorization": f"Bearer {settings.hf_token}"} if settings.hf_token else {}
        self._client = httpx.Client(timeout=60)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.post(self._url, json={"inputs": texts}, headers=self._headers)
        resp.raise_for_status()
        vectors = resp.json()
        # HF returns shape (batch, tokens, dim); mean-pool over tokens
        out = []
        for item in vectors:
            tokens = item if isinstance(item, list) and item and isinstance(item[0], list) else [item]
            out.append([sum(col) / len(tokens) for col in zip(*tokens)])
        return out


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        backend = get_settings().embeddings_backend
        _embedder = LocalEmbedder() if backend == "local" else HFEmbedder()
    return _embedder