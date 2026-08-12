"""rag_kro API — orchestration + message flow (spec section 4).

Responsibilities:
  - ingest gateway webhooks (wa/ig)
  - enforce allowlist (section 4.2)
  - respect pause/resume (section 4.3 / 5)
  - identity resolution + combined cross-platform history (section 4.4)
  - build RAG context, call rag service, forward reply back to the gateway
  - log messages + activity, trigger order/reminder/escalation notifications
"""
import os
import sys
import uuid

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rag_kro_shared import (
    get_settings,
    session_scope,
)
from rag_kro_shared.models import (
    ActivityLog,
    AllowedSender,
    Conversation,
    Document,
    Message,
    NotificationTarget,
    Order,
    Product,
    Reminder,
    WaSession,
    IgSession,
)

from .services.context_builder import build_context, resolve_contact
from .services.notifier import log_activity
from .gateway_client import send_message

settings = get_settings()

app = FastAPI(title="rag_kro api", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---- schemas --------------------------------------------------------------
class WebhookMessage(BaseModel):
    tenant_id: str = "00000000-0000-0000-0000-000000000001"
    platform: str  # whatsapp | instagram
    contact_identifier: str
    body: str | None = None
    media_url: str | None = None


class ConversationPatch(BaseModel):
    status: str  # bot_active | paused


class SenderCreate(BaseModel):
    tenant_id: str = "00000000-0000-0000-0000-000000000001"
    platform: str
    identifier: str
    label: str | None = None


class ProductCreate(BaseModel):
    tenant_id: str = "00000000-0000-0000-0000-000000000001"
    name: str
    price: float | None = None
    stock: int = 0
    description: str | None = None


class ReminderCreate(BaseModel):
    tenant_id: str = "00000000-0000-0000-0000-000000000001"
    platform: str = "whatsapp"
    contact_identifier: str
    remind_at: str  # ISO timestamp
    message: str


class ChatRequest(BaseModel):
    tenant_id: str = "00000000-0000-0000-0000-000000000001"
    conversation_id: str
    body: str


# ---- health ----------------------------------------------------------------
@app.get("/health")
def health():
    from sqlalchemy import text

    from rag_kro_shared import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        return {"service": "api", "status": "degraded", "postgres": str(exc)}
    return {"service": "api", "status": "ok", "postgres": "ok"}


# ---- webhooks ---------------------------------------------------------------
@app.post("/webhook/message")
def webhook_message(req: WebhookMessage):
    """Step 1: gateway posts inbound message here."""
    tenant_id = req.tenant_id

    # step 2: allowlist
    with session_scope() as s:
        allowed = (
            s.query(AllowedSender)
            .filter(
                AllowedSender.tenant_id == tenant_id,
                AllowedSender.platform.in_([req.platform, "*"]),
            )
            .all()
        )
        idents = {a.identifier for a in allowed}
        if "*" not in idents and req.contact_identifier not in idents:
            log_activity(s, tenant_id, "allowlist_rejected", {"platform": req.platform, "contact": req.contact_identifier})
            return {"status": "rejected", "reason": "sender not allowed"}

    # resolve or create conversation (step 2.5)
    with session_scope() as s:
        conv = (
            s.query(Conversation)
            .filter_by(
                tenant_id=tenant_id,
                platform=req.platform,
                contact_identifier=req.contact_identifier,
            )
            .first()
        )
        if conv is None:
            resolved = resolve_contact(s, tenant_id, req.platform, req.contact_identifier, req.body)
            conv = Conversation(
                tenant_id=tenant_id,
                platform=req.platform,
                contact_identifier=req.contact_identifier,
                resolved_contact_id=resolved.id if resolved else None,
                status="bot_active",
            )
            s.add(conv)
            s.commit()

        conv_id = conv.id

        s.add(Message(conversation_id=conv_id, direction="inbound", body=req.body, media_url=req.media_url))
        s.commit()

        status = conv.status

    # step 3: paused -> store only, notify dashboard
    if status == "paused":
        with session_scope() as s:
            log_activity(s, tenant_id, "paused_message", {"conversation_id": str(conv_id)})
        return {"status": "stored_paused", "conversation_id": str(conv_id)}

    # steps 4-6: build context + RAG answer
    context = build_context(tenant_id, conv_id, req.body)

    import httpx

    rag_resp = httpx.post(
        f"{settings.rag_api_url}/chat",
        json={
            "tenant_id": tenant_id,
            "conversation_history": context["history"],
            "contact_context": context["contact_context"],
            "system_prompt": settings.rag_system_prompt,
        },
        headers={"X-Internal-Key": settings.rag_api_key},
        timeout=120,
    )
    if rag_resp.status_code != 200:
        with session_scope() as s:
            log_activity(s, tenant_id, "rag_error", {"status": rag_resp.status_code, "detail": rag_resp.text[:500]})
        return {"status": "rag_error", "detail": rag_resp.text[:500]}

    data = rag_resp.json()
    answer = data["answer"]
    sources = data.get("sources", [])

    # send reply out through the originating gateway
    try:
        send_message(req.platform, req.contact_identifier, answer, tenant_id=tenant_id)
        sent = True
    except Exception as exc:  # pragma: no cover
        sent = False
        with session_scope() as s:
            log_activity(s, tenant_id, "send_failure", {"error": str(exc), "contact": req.contact_identifier})

    # store outbound
    with session_scope() as s:
        s.add(Message(conversation_id=conv_id, direction="outbound", body=answer, meta={"sources": sources}))
        log_activity(s, tenant_id, "bot_reply", {"conversation_id": str(conv_id), "sources": sources})
        s.commit()

    return {"status": "replied", "conversation_id": str(conv_id), "answer": answer, "sent": sent}


# ---- conversations (pause/resume, section 5) ---------------------------------
@app.get("/conversations")
def list_conversations(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        rows = (
            s.query(Conversation)
            .filter_by(tenant_id=tenant_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
        return [
            {
                "id": str(c.id),
                "platform": c.platform,
                "contact_identifier": c.contact_identifier,
                "status": c.status,
                "updated_at": c.updated_at.isoformat(),
            }
            for c in rows
        ]


@app.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, patch: ConversationPatch):
    with session_scope() as s:
        conv = s.get(Conversation, uuid.UUID(conversation_id))
        if conv is None:
            raise HTTPException(404, "conversation not found")
        conv.status = patch.status
        s.commit()
        return {"id": str(conv.id), "status": conv.status}


# ---- allowed senders -----------------------------------------------------------
@app.get("/senders")
def list_senders(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        rows = s.query(AllowedSender).filter_by(tenant_id=tenant_id).all()
        return [
            {"id": str(a.id), "platform": a.platform, "identifier": a.identifier, "label": a.label}
            for a in rows
        ]


@app.post("/senders")
def create_sender(sender: SenderCreate):
    with session_scope() as s:
        a = AllowedSender(
            tenant_id=sender.tenant_id,
            platform=sender.platform,
            identifier=sender.identifier,
            label=sender.label,
        )
        s.add(a)
        s.commit()
        return {"id": str(a.id)}


@app.delete("/senders/{sender_id}")
def delete_sender(sender_id: str):
    with session_scope() as s:
        a = s.get(AllowedSender, uuid.UUID(sender_id))
        if a is None:
            raise HTTPException(404, "sender not found")
        s.delete(a)
        s.commit()
        return {"deleted": sender_id}


# ---- products ------------------------------------------------------------
@app.get("/products")
def list_products(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        rows = (
            s.query(Product)
            .filter_by(tenant_id=tenant_id, is_active=True)
            .order_by(Product.created_at.desc())
            .all()
        )
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "price": float(p.price) if p.price is not None else None,
                "stock": p.stock,
                "description": p.description,
            }
            for p in rows
        ]


@app.post("/products")
def create_product(p: ProductCreate):
    with session_scope() as s:
        prod = Product(
            tenant_id=p.tenant_id, name=p.name, price=p.price, stock=p.stock, description=p.description
        )
        s.add(prod)
        s.commit()
        prod_id = prod.id

    # push a re-embed job (6b product sync) to the ingestion service
    import httpx

    httpx.post(
        f"{settings.ingestion_api_url}/ingest/product",
        data={"product_id": str(prod_id), "tenant_id": p.tenant_id},
        headers={"X-Internal-Key": settings.ingest_api_key},
        timeout=120,
    )
    return {"id": str(prod_id)}


# ---- documents (upload -> ingestion service) -----------------------------
@app.get("/documents")
def list_documents(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        rows = s.query(Document).filter_by(tenant_id=tenant_id).order_by(Document.created_at.desc()).all()
        return [
            {
                "id": str(d.id),
                "type": d.type,
                "title": d.title,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
            }
            for d in rows
        ]


# ---- orders/reminders/notification targets -------------------------------
@app.get("/orders")
def list_orders(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        rows = s.query(Order).filter_by(tenant_id=tenant_id).order_by(Order.created_at.desc()).all()
        return [
            {
                "id": str(o.id),
                "product_id": str(o.product_id) if o.product_id else None,
                "qty": o.qty,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
            }
            for o in rows
        ]


@app.post("/reminders")
def create_reminder(r: ReminderCreate):
    from datetime import datetime

    remind_at = datetime.fromisoformat(r.remind_at)
    with session_scope() as s:
        rem = Reminder(
            tenant_id=r.tenant_id,
            platform=r.platform,
            contact_identifier=r.contact_identifier,
            remind_at=remind_at,
            message=r.message,
        )
        s.add(rem)
        s.commit()
        rem_id = rem.id
    return {"id": str(rem_id), "remind_at": r.remind_at}


@app.get("/notifications")
def list_notifications(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        rows = s.query(NotificationTarget).filter_by(tenant_id=tenant_id).all()
        return [{"id": str(n.id), "type": n.type, "destination": n.destination} for n in rows]


# ---- activity log ----------------------------------------------------------
@app.get("/activity")
def list_activity(tenant_id: str = "00000000-0000-0000-0000-000000000001", limit: int = 50):
    with session_scope() as s:
        rows = (
            s.query(ActivityLog)
            .filter_by(tenant_id=tenant_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"id": str(a.id), "event_type": a.event_type, "payload": a.payload, "created_at": a.created_at.isoformat()}
            for a in rows
        ]


# ---- sessions (connect status for dashboard) ------------------------------
@app.get("/sessions")
def list_sessions(tenant_id: str = "00000000-0000-0000-0000-000000000001"):
    with session_scope() as s:
        wa = s.query(WaSession).filter_by(tenant_id=tenant_id).first()
        ig = s.query(IgSession).filter_by(tenant_id=tenant_id).first()
        return {
            "whatsapp": {"status": wa.status if wa else "disconnected"},
            "instagram": {"status": ig.status if ig else "disconnected"},
        }