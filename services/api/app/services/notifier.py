"""Notification + activity-logging helpers (spec section 4.7-4.8)."""
import smtplib
import uuid
from email.mime.text import MIMEText

from rag_kro_shared import get_settings
from rag_kro_shared.models import ActivityLog, NotificationTarget

settings = get_settings()


def log_activity(session, tenant_id: str, event_type: str, payload: dict | None = None) -> None:
    session.add(
        ActivityLog(
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
        )
    )


def notify(targets: list[str], subject: str, body: str) -> dict:
    """Send to configured notification targets (email/webhook) — section 4.7."""
    results = {"email": [], "webhook": []}
    for destination in targets:
        if "@" in destination:  # naive email detection
            results["email"].append(_send_email(destination, subject, body))
        elif destination.startswith("http"):
            results["webhook"].append(_send_webhook(destination, body))
    return results


def _send_email(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_user or not settings.smtp_password:
        return False  # SMTP not configured
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except smtplib.SMTPException:
        return False


def _send_webhook(url: str, body: str) -> bool:
    import httpx

    try:
        httpx.post(url, json={"text": body}, timeout=15)
        return True
    except Exception:
        return False


def targets_for(session, tenant_id: str) -> list[str]:
    rows = session.query(NotificationTarget).filter_by(tenant_id=tenant_id).all()
    return [row.destination for row in rows]


def log_order(session, tenant_id: str, conversation_id: str, product: str, qty: int) -> None:
    log_activity(
        session,
        tenant_id,
        "order_placed",
        {"conversation_id": str(conversation_id), "product": product, "qty": qty},
    )


def default_tenant() -> str:
    return str(uuid.UUID("00000000-0000-0000-0000-000000000001"))