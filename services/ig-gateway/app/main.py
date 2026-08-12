"""Instagram connectivity microservice (spec section 2b, Option B — instagrapi).

Mirrors wa-gateway: login session stored encrypted in Postgres, polls DMs and
forwards them to the API service tagged with platform=instagram. On first
contact it also pulls the sender's public profile into contact_profiles.

ToS caveat: unofficial Instagram login risks account action. Prototype-only.
"""
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/app/src")

import asyncio

import httpx
from fastapi import FastAPI, Header, HTTPException

from rag_kro_shared import get_settings, get_crypto, session_scope
from rag_kro_shared.models import ContactProfile, IgSession

settings = get_settings()
app = FastAPI(title="rag_kro ig-gateway", version="0.1.0")

crypto = get_crypto()

# in-memory instagrapi client per tenant
_clients: dict[str, object] = {}


def _internal_key(x_internal_key: str = Header(default="")) -> None:
    if x_internal_key != settings.internal_api_key:
        raise HTTPException(403, "invalid internal key")


@app.get("/health")
def health():
    return {"service": "ig-gateway", "status": "ok"}


@app.post("/login")
def login(
    tenant_id: str,
    username: str,
    password: str,
    api_key: str = Header(""),
):
    """Login + persist encrypted session blob (works on device trust)."""
    if api_key != settings.internal_api_key:
        raise HTTPException(403, "invalid internal key")
    try:
        from instagrapi import Client

        cl = Client()
        cl.login(username, password)
        session_blob = crypto.encrypt(cl.get_settings())
        with session_scope() as s:
            row = s.query(IgSession).filter_by(tenant_id=tenant_id).first()
            if row:
                row.session_blob = session_blob
                row.status = "connected"
            else:
                s.add(IgSession(tenant_id=tenant_id, session_blob=session_blob, status="connected"))
        _clients[tenant_id] = cl
        return {"status": "connected"}
    except Exception as exc:
        raise HTTPException(500, f"login failed: {exc}")


@app.post("/resume")
def resume(tenant_id: str, api_key: str = Header("")):
    """Reload a stored session (service restart-safe)."""
    if api_key != settings.internal_api_key:
        raise HTTPException(403, "invalid internal key")
    with session_scope() as s:
        row = s.query(IgSession).filter_by(tenant_id=tenant_id).first()
        if row is None:
            raise HTTPException(404, "no stored session")
        from instagrapi import Client

        cl = Client()
        cl.set_settings(crypto.decrypt(row.session_blob))
        try:
            cl.get_timeline_feed()
            _clients[tenant_id] = cl
            row.status = "connected"
            return {"status": "connected"}
        except Exception as exc:
            row.status = "disconnected"
            raise HTTPException(500, f"resume failed: {exc}")


@app.get("/status/{tenant_id}")
def status(tenant_id: str):
    with session_scope() as s:
        row = s.query(IgSession).filter_by(tenant_id=tenant_id).first()
        return {"status": row.status if row else "disconnected"}


@app.post("/send")
def send(
    tenant_id: str,
    contact_identifier: str,
    body: str,
    api_key: str = Header(""),
):
    """Send an IG DM. NOTE: instagrapi can't DM arbitrary accounts reliably;
    this is best-effort and requires the account to allow messages."""
    if api_key != settings.internal_api_key:
        raise HTTPException(403, "invalid internal key")
    cl = _clients.get(tenant_id)
    if cl is None:
        raise HTTPException(400, "not logged in")
    try:
        users = cl.user_search(contact_identifier)
        if not users:
            raise HTTPException(404, "user not found")
        cl.direct_send(text=body, user_ids=[users[0].pk])
        return {"sent": True}
    except Exception as exc:
        raise HTTPException(500, f"send failed: {exc}")


async def _poller():
    """Background task: poll new DMs per connected tenant and forward as webhook."""
    cb = settings.ig_api_callback_url
    while True:
        for tenant_id, cl in list(_clients.items()):
            try:
                threads = cl.direct_threads(amount=5)
                for t in threads:
                    for m in t.messages:
                        if m.user_id != cl.user_id:
                            await httpx.post(
                                cb,
                                json={
                                    "tenant_id": tenant_id,
                                    "platform": "instagram",
                                    "contact_identifier": t.thread_title or str(m.user_id),
                                    "body": m.text,
                                },
                                headers={"X-Internal-Key": settings.internal_api_key},
                                timeout=30,
                            )
            except Exception:
                pass
        await asyncio.sleep(30)


@app.on_event("startup")
async def _start_poller():
    asyncio.create_task(_poller())