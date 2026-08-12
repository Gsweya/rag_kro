"""Reminders + external notifications (spec sections 4.7-4.8, 8).

  - notify_reminders: fire due reminders via the originating gateway
  - notify_order: push order/escalation events to notification_targets
"""
from datetime import datetime, timezone

from rag_kro_shared import get_settings, session_scope
from rag_kro_shared.models import Reminder, NotificationTarget, ActivityLog

from ..celery_app import app

settings = get_settings()


@app.task(name="app.tasks.reminders.notify_reminders")
def notify_reminders() -> dict:
    """Fire any reminder whose remind_at <= now and not yet fired."""
    import httpx

    now = datetime.now(timezone.utc)
    fired = 0
    with session_scope() as s:
        due = (
            s.query(Reminder)
            .filter(Reminder.fired.is_(False), Reminder.remind_at <= now)
            .all()
        )
        for rem in due:
            try:
                platform = rem.platform
                host = "wa-gateway" if platform == "whatsapp" else "ig-gateway"
                port = 8100 if platform == "whatsapp" else 8200
                resp = httpx.post(
                    f"http://{host}:{port}/send",
                    json={
                        "tenant_id": str(rem.tenant_id),
                        "contact_identifier": rem.contact_identifier,
                        "body": rem.message,
                    },
                    headers={"X-Internal-Key": settings.internal_api_key},
                    timeout=30,
                )
                resp.raise_for_status()
                rem.fired = True
                rem.fired_at = now
                fired += 1
            except Exception:
                continue  # retry next beat
    return {"fired": fired}


@app.task(name="app.tasks.reminders.notify_order")
def notify_order(tenant_id: str, payload: dict) -> None:
    """Push order placed / human escalation to notification targets (section 4.7)."""
    import smtplib
    from email.mime.text import MIMEText

    with session_scope() as s:
        targets = s.query(NotificationTarget).filter_by(tenant_id=tenant_id).all()
        s.add(ActivityLog(tenant_id=tenant_id, event_type="order_notify", payload=payload))

    for t in targets:
        if t.type == "email" and settings.smtp_user and settings.smtp_password:
            msg = MIMEText(payload.get("message", ""))
            msg["Subject"] = payload.get("subject", "rag_kro order/alert")
            msg["From"] = settings.smtp_from or settings.smtp_user
            msg["To"] = t.destination
            try:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(settings.smtp_user, settings.smtp_password)
                    server.send_message(msg)
            except Exception:
                pass


@app.task(name="app.tasks.notifications.health_beat")
def health_beat() -> dict:
    """Liveness marker: worker writes into Redis so /admin health checks see it."""
    import redis

    r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    r.set("worker:last_beat", datetime.now(timezone.utc).isoformat())
    return {"beat": r.get("worker:last_beat")}