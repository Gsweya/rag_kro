"""rag_kro_shared — shared library used by api, rag, ingestion and worker services.

Installable in any of those images via their requirements.txt:
    -e /packages/python/rag_kro_shared
"""
from .config import Settings, get_settings
from .crypto import Crypto
from .db import Base, run_migrations, session_scope, get_engine
from .embeddings import get_embedder
from .llm import LLMClient, get_llm_client
from .vectors import VectorStore
from .internal import internal_client
from .tenant_auth import require_tenant, ensure_matching_tenant

__all__ = [
    "Settings",
    "get_settings",
    "Crypto",
    "Base",
    "run_migrations",
    "session_scope",
    "get_engine",
    "get_embedder",
    "LLMClient",
    "get_llm_client",
    "VectorStore",
    "internal_client",
    "require_tenant",
    "ensure_matching_tenant",
]