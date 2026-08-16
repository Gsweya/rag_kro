"""Context builder (spec section 4.4-4.5).

  - identity resolution: match incoming contact to a contact_profile, and share
    history across the same real person on WA + IG
  - short-term memory: last N messages from Redis
  - long-term memory: last M messages from Postgres
  - contact_context: contact_profile notes (who they are, tone, prior topics/orders)
"""
import json

from rag_kro_shared import get_settings, session_scope
from rag_kro_shared.models import ContactProfile, Conversation, Message

settings = get_settings()


def _redis_client():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def resolve_contact(session, tenant_id: str, platform: str, identifier: str, body: str) -> ContactProfile | None:
    """Find or create a contact_profile for this (platform, identifier).

    Cross-platform identity merging (manual linking via dashboard is the safe
    default; auto-merge by identical identifier is attempted when the identifier
    is a phone number or Instagram username that appears on the other platform).
    """
    profile = (
        session.query(ContactProfile)
        .filter_by(tenant_id=tenant_id, platform=platform, contact_identifier=identifier)
        .first()
    )
    if profile is not None:
        return profile

    # try to link to an existing profile on the other platform with the same identifier
    merged = (
        session.query(ContactProfile)
        .filter(
            ContactProfile.tenant_id == tenant_id,
            ContactProfile.platform != platform,
            ContactProfile.contact_identifier == identifier,
        )
        .first()
    )
    if merged is not None:
        profile = merged
    else:
        profile = ContactProfile(
            tenant_id=tenant_id,
            platform=platform,
            contact_identifier=identifier,
            name=identifier,
            notes="",  # worker summarization will fill this
        )
    session.add(profile)
    session.commit()
    return profile


def build_context(tenant_id: str, conversation_id: str, current_body: str) -> dict:
    """Assemble the memory + profile context handed to the rag service."""
    r = _redis_client()

    # ---- short-term memory (Redis, last 20) ----
    key = f"ctx:{conversation_id}"
    history: list[dict] = []
    raw = r.lrange(key, 0, -1)
    for item in raw[-20:]:
        try:
            history.append(json.loads(item))
        except Exception:
            continue

    # seed with current message as the final user turn
    history = [m for m in history if m.get("role") != "user"]
    history.append({"role": "user", "content": current_body})

    # ---- long-term memory (Postgres, last 12 prior) ----
    with session_scope() as s:
        conv = s.get(Conversation, conversation_id)
        if conv is not None and conv.resolved_contact_id is not None:
            # pull history across ALL conversations of the same resolved contact
            convs = (
                s.query(Conversation.id)
                .filter_by(tenant_id=tenant_id, resolved_contact_id=conv.resolved_contact_id)
                .all()
            )
            conv_ids = [c[0] for c in convs]
            older = (
                s.query(Message)
                .filter(Message.conversation_id.in_(conv_ids))
                .order_by(Message.created_at.desc())
                .limit(12)
                .all()
            )
        else:
            older = (
                s.query(Message)
                .filter(Message.conversation_id == conversation_id, Message.direction == "outbound")
                .order_by(Message.created_at.desc())
                .limit(12)
                .all()
            )

        contact_context = ""
        if conv is not None and conv.resolved_contact_id is not None:
            profile = s.get(ContactProfile, conv.resolved_contact_id)
            if profile is not None:
                contact_context = (
                    f"Name: {profile.name or profile.contact_identifier}. "
                    f"Relationship notes: {profile.notes or '(none yet)'}"
                )

        # collect long-term memory while the session is open (objects detach on close)
        for m in reversed(older):
            role = "user" if m.direction == "inbound" else "assistant"
            if m.body:
                history.insert(0, {"role": role, "content": m.body})

    # persist this turn to short-term memory
    r.rpush(key, json.dumps({"role": "user", "content": current_body}))
    r.ltrim(key, -50, -1)

    return {"history": history[-16:], "contact_context": contact_context}