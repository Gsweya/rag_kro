from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment for every python service."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # general
    env: str = "development"
    admin_token: str = "admin"
    internal_api_key: str = "internal-key"

    # postgres
    database_url: str = (
        "postgresql+psycopg://rag_kro:rag_kro@localhost:5432/rag_kro"
    )

    # redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "rag_kro_vectors"
    # true = one collection per tenant (hard Qdrant-level isolation).
    #       collection names become "{qdrant_collection}__{tenant_id}".
    #       NOTE: creation is lazy (first upsert). Safe to flip on when the
    #       second real tenant goes live.
    qdrant_per_tenant_collections: bool = False
    vector_size: int = 384
    vector_metric: str = "cosine"

    # minio
    minio_endpoint: str = "http://localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "rag-kro-documents"

    # embeddings
    embeddings_backend: str = "local"  # local | hf
    hf_embeddings_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hf_token: str = ""

    # llm
    llm_backend: str = "openai_compatible"  # hf | ollama | openai_compatible
    hf_inference_model: str = "Qwen/Qwen2.5-7B-Instruct"
    hf_api_url: str = "https://router.huggingface.co"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    llm_temperature: float = 0.4
    llm_max_tokens: int = 512
    openai_compatible_base_url: str = ""
    openai_compatible_api_key: str = ""
    openai_compatible_model: str = ""

    # ingestion
    ingestion_api_url: str = "http://localhost:8001"
    ingest_api_key: str = "internal-key"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    enable_hash_check: bool = True
    sweep_interval: int = 3600

    # rag
    rag_api_url: str = "http://localhost:8002"
    rag_api_key: str = "internal-key"
    retrieve_top_k: int = 4
    rag_system_prompt: str = (
        "You are a helpful sales assistant. Answer using only the provided context."
    )

    # api
    api_port: int = 8000
    api_api_key: str = "internal-key"

    # tenant auth boundary (steers TENANT_KEY event when a second tenant appears)
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"
    tenant_default_key: str = "admin"  # seeded into tenant_keys at api startup
    require_tenant_key: bool = True    # reject calls without a valid tenant key

    # gateways
    ig_api_callback_url: str = "http://api:8000/webhook/message"
    wa_api_callback_url: str = "http://api:8000/webhook/message"

    # encryption
    fernet_secret_key: str = ""

    # smtp
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()