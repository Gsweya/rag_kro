"""Authenticated HTTP client for internal service-to-service calls."""
import httpx

from .config import get_settings


class InternalClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Internal-Key": self._settings.internal_api_key}

    def post_json(self, url: str, payload: dict, timeout: int = 60) -> dict:
        resp = httpx.post(url, json=payload, headers=self.headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


_internal: InternalClient | None = None


def internal_client() -> InternalClient:
    global _internal
    if _internal is None:
        _internal = InternalClient()
    return _internal