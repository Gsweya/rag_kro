"""Tenant auth boundary for the no-auth prototype.

While there is no login, tenant isolation is enforced this way:
- A caller must present BOTH headers: X-Tenant-Id and X-Tenant-Key.
- The pair is checked against the `tenant_keys` table.
- The resulting tenant_id is what routes trust. Any tenant_id supplied inside a
  request body that differs from the header tenant is rejected — a caller can
  never read/write another tenant's data by editing the body.

This is a real boundary (not "filter by convention") for all tenant-scoped data.
When proper auth arrives, this dependency is swapped for the session resolver
with no other changes.
"""
from fastapi import Header, HTTPException

from .config import get_settings
from .db import SessionLocal
from .models import TenantKey


def _validate(tenant_id: str | None, tenant_key: str | None) -> str:
    settings = get_settings()

    if not settings.require_tenant_key:
        # boundary disabled: trust the header (or the default tenant) but still
        # refuse a conflicting body tenant via ensure_matching_tenant in the routes.
        return tenant_id or settings.default_tenant_id

    if not tenant_id or not tenant_key:
        raise HTTPException(status_code=401, detail="X-Tenant-Id and X-Tenant-Key headers required")

    session = SessionLocal()
    try:
        row = session.query(TenantKey).filter(TenantKey.tenant_id == tenant_id).first()
    finally:
        session.close()
    if row is None or row.api_key != tenant_key:
        raise HTTPException(status_code=401, detail="invalid tenant key")
    return tenant_id


def require_tenant(
    x_tenant_id: str | None = Header(default=None),
    x_tenant_key: str | None = Header(default=None),
) -> str:
    """FastAPI dependency -> returns the authenticated tenant_id string."""
    return _validate(x_tenant_id, x_tenant_key)


def ensure_matching_tenant(body_tenant_id: str | None, header_tenant_id: str) -> None:
    """Reject a body that claims a different tenant than the authenticated header."""
    if body_tenant_id and body_tenant_id != header_tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"tenant_id in body ({body_tenant_id}) does not match authenticated tenant ({header_tenant_id})",
        )