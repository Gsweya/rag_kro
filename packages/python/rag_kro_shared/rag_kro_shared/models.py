"""ORM models mirroring infra/postgres/init/001_schema.sql.

The SQL file is the source of truth on first boot; these models power service
queries and are intentionally kept in sync.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TenantKey(Base):
    __tablename__ = "tenant_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    api_key: Mapped[str] = mapped_column(String, nullable=False)
    label: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class WaSession(Base):
    __tablename__ = "wa_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    session_blob: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="disconnected")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IgSession(Base):
    __tablename__ = "ig_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    session_blob: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, default="disconnected")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AllowedSender(Base):
    __tablename__ = "allowed_senders"
    __table_args__ = (UniqueConstraint("tenant_id", "platform", "identifier"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    identifier: Mapped[str] = mapped_column(String, nullable=False)  # phone | username | '*'
    label: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("tenant_id", "platform", "contact_identifier"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    contact_identifier: Mapped[str] = mapped_column(String, nullable=False)
    resolved_contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contact_profiles.id"))
    status: Mapped[str] = mapped_column(String, default="bot_active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String, nullable=False)  # inbound|outbound
    body: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(String)
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ContactProfile(Base):
    __tablename__ = "contact_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "platform", "contact_identifier"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    contact_identifier: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    bio: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)  # running relationship summary
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # pdf|image|csv|product|contact_profile
    title: Mapped[str | None] = mapped_column(String)
    storage_path: Mapped[str | None] = mapped_column(String)  # minio object key
    source_hash: Mapped[str | None] = mapped_column(Text)  # change detection (6b)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|indexed|failed
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    emb_hash: Mapped[str | None] = mapped_column(Text)  # change detection (6b)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="placed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    platform: Mapped[str] = mapped_column(String, default="whatsapp")
    contact_identifier: Mapped[str] = mapped_column(String, nullable=False)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotificationTarget(Base):
    __tablename__ = "notification_targets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # email|webhook|sms
    destination: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )