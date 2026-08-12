"""RAG service — retrieval + generation (spec sections 7-8).

Deployed as its own service (`services/rag`). Queries the shared Qdrant index
(tenant-scoped), builds context, and calls the configured LLM backend
(HF Inference API by default; swap via LLM_BACKEND=ollama|openai_compatible).

NOT responsible for ingestion — that lives in `services/ingestion` so knowledge
is indexed once, centrally, for all tenants.
"""
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_kro_shared import get_settings, get_vector_store, get_embedder, get_llm_client

from .auth import require_internal_key

settings = get_settings()

app = FastAPI(title="rag_kro RAG", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---- request/response models -------------------------------------------
class ChatRequest(BaseModel):
    tenant_id: str
    conversation_history: list[dict] = []  # [{"role": "user"|"assistant", "content": str}]
    contact_context: str = ""              # contact_profile.notes + tone/identity
    system_prompt: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]


# ---- RAG core -----------------------------------------------------------
def _format_history(history: list[dict]) -> list[dict]:
    """Take last N turns (memory window, section 8)."""
    return history[-12:]


def _retrieve(query: str, tenant_id: str) -> list[dict]:
    embedder = get_embedder()
    query_vec = embedder.embed_query(query)
    return get_vector_store().search(query_vec, tenant_id=tenant_id, top_k=settings.retrieve_top_k)


@app.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    api_key: str = Depends(require_internal_key),
):
    """Answer a user message grounded on the tenant's indexed knowledge."""
    if not req.conversation_history:
        raise HTTPException(400, "conversation_history is required")

    last_user_msg = next(
        (m["content"] for m in reversed(req.conversation_history)
         if m.get("role") == "user"),
        "",
    )
    if not last_user_msg:
        raise HTTPException(400, "no user message in conversation_history")

    retrieved = _retrieve(last_user_msg, tenant_id=req.tenant_id)

    context_block = "\n\n".join(
        f"[source: {s.get('title', s.get('doc_id', 'unknown'))}] {s.get('text', s)}"
        for s in retrieved
    )

    system = req.system_prompt or settings.rag_system_prompt
    if req.contact_context:
        system += (
            "\n\nAbout this contact: " + req.contact_context
            + "\nAdapt your tone and flow to the ongoing relationship."
        )

    messages = [{"role": "system", "content": system}]
    if context_block:
        messages.append(
            {"role": "system", "content": f"RAG context (use only if relevant):\n{context_block}"}
        )
    messages.extend(_format_history(req.conversation_history))

    llm = get_llm_client()
    answer = llm.chat(messages)

    sources = [
        {
            "title": s.get("title"),
            "doc_id": s.get("doc_id"),
            "type": s.get("type"),
            "score": s.get("_score"),
        }
        for s in retrieved
    ]
    return ChatResponse(answer=answer, sources=sources)


@app.post("/generate")
def generate(
    req: ChatRequest,
    api_key: str = Depends(require_internal_key),
):
    """Same as /chat but keeps raw context for agents/tools debugging (admin drill-in)."""
    out = chat(req, api_key)
    return {"answer": out.answer, "sources": out.sources}


@app.get("/health")
def health():
    return {"service": "rag", "status": "ok"}