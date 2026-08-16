"""Contact profile re-summarization (spec section 4.8).

Periodically condenses recent conversation history into compact relationship
notes so RAG context stays bounded instead of growing forever.
"""
from rag_kro_shared import get_settings, get_llm_client, session_scope
from rag_kro_shared.models import ContactProfile, Conversation, Message

from ..celery_app import app

settings = get_settings()


@app.task(name="app.tasks.summarize.summarize_contacts")
def summarize_contacts(limit: int = 20) -> dict:
    """For the most recent contacts, regenerate `notes` from their last ~30 messages."""
    import uuid

    processed = 0
    llm = get_llm_client()

    with session_scope() as s:
        # most recently touched resolved contacts
        conv_rows = (
            s.query(Conversation.resolved_contact_id)
            .filter(Conversation.resolved_contact_id.isnot(None))
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .all()
        )
        profile_ids = {r[0] for r in conv_rows if r[0]}
        for pid in profile_ids:
            convs = (
                s.query(Conversation.id)
                .filter_by(resolved_contact_id=pid)
                .all()
            )
            conv_ids = [c[0] for c in convs]
            recent = (
                s.query(Message)
                .filter(Message.conversation_id.in_(conv_ids))
                .order_by(Message.created_at.desc())
                .limit(30)
                .all()
            )
            profile = s.get(ContactProfile, uuid.UUID(str(pid)))
            if profile is None or not recent:
                continue

            transcript = "\n".join(
                f"{'Customer' if m.direction == 'inbound' else 'Bot'}: {m.body or '[media]'}"
                for m in reversed(recent)
            )
            try:
                summary = llm.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Summarize this customer relationship in 3-4 lines: who they are, "
                                "their tone/preferences, products/orders discussed, pending items. "
                                "Output plain text only."
                            ),
                        },
                        {"role": "user", "content": transcript},
                    ]
                )
            except Exception:
                summary = transcript[:800]  # graceful degradation

            profile.notes = summary
            profile.last_synced_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            processed += 1

    return {"summarized": processed}