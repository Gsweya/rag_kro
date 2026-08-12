"""Forward outbound messages to the correct gateway over HTTP.

Gateways expose POST /send and authenticate with the shared internal key.
"""
import httpx

from rag_kro_shared import get_settings

_settings = get_settings()

GATEWAYS = {
    "whatsapp": {"host": "wa-gateway", "port": 8100},
    "instagram": {"host": "ig-gateway", "port": 8200},
}

PLATFORM_ENV = {
    "whatsapp": {"host": "WA_GATEWAY_HOST", "port": "WA_GATEWAY_PORT"},
    "instagram": {"host": "IG_GATEWAY_HOST", "port": "IG_GATEWAY_PORT"},
}


def send_message(platform: str, contact_identifier: str, body: str, tenant_id: str) -> dict:
    import os

    cfg = GATEWAYS.get(platform)
    if cfg is None:
        raise ValueError(f"unsupported platform: {platform}")

    host = os.getenv(PLATFORM_ENV[platform]["host"], cfg["host"])
    port = os.getenv(PLATFORM_ENV[platform]["port"], str(cfg["port"]))
    url = f"http://{host}:{port}/send"

    resp = httpx.post(
        url,
        json={
            "tenant_id": tenant_id,
            "contact_identifier": contact_identifier,
            "body": body,
        },
        headers={"X-Internal-Key": _settings.internal_api_key},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()