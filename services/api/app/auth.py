from fastapi import Header, HTTPException

from rag_kro_shared import get_settings


async def require_internal_key(x_internal_key: str = Header(default="")) -> None:
    """Shared-secret guard for internal endpoints (matches internal_api_key)."""
    if x_internal_key != get_settings().internal_api_key:
        raise HTTPException(status_code=403, detail="invalid internal key")