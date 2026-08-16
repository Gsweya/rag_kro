"""Isolation boundary tests (spec §4, SECURITY.md §1b).

Run inside a service image or CI: pytest tests/test_isolation.py
These prove the two behaviors that stop Company A/B context mixing:
  1. require_tenant rejects a wrong/missing tenant key.
  2. ensure_matching_tenant rejects a body tenant different from the header.
"""
import pytest
from fastapi import HTTPException, Header, Depends, FastAPI
from fastapi.testclient import TestClient

from rag_kro_shared.tenant_auth import require_tenant, ensure_matching_tenant
from rag_kro_shared import get_settings


def _app():
    app = FastAPI()

    @app.get("/protected")
    def protected(tenant_id: str = Depends(require_tenant)):
        return {"tenant_id": tenant_id}

    @app.post("/match")
    def match(body_tenant: str | None = None, tenant_id: str = Depends(require_tenant)):
        ensure_matching_tenant(body_tenant, tenant_id)
        return {"ok": True, "tenant_id": tenant_id}

    return app


@pytest.mark.skipif(
    not get_settings().require_tenant_key,
    reason="REQUIRE_TENANT_KEY is off; boundary is disabled",
)
class TestTenantBoundary:
    def _client(self):
        return TestClient(_app())

    def _headers(self):
        s = get_settings()
        return {"X-Tenant-Id": s.default_tenant_id, "X-Tenant-Key": s.tenant_default_key}

    def test_valid_tenant_pair_passes(self):
        r = self._client().get("/protected", headers=self._headers())
        assert r.status_code == 200
        assert r.json()["tenant_id"] == get_settings().default_tenant_id

    def test_missing_headers_rejected(self):
        assert self._client().get("/protected").status_code == 401

    def test_wrong_key_rejected(self):
        h = self._headers()
        h["X-Tenant-Key"] = "wrong-key"
        assert self._client().get("/protected", headers=h).status_code == 401

    def test_body_tenant_mismatch_rejected(self):
        h = self._headers()
        r = self._client().post(
            "/match", json={"body_tenant": "22222222-2222-2222-2222-222222222222"},
            headers=h,
        )
        assert r.status_code == 403

    def test_body_tenant_matching_header_ok(self):
        h = self._headers()
        r = self._client().post("/match", json={"body_tenant": h["X-Tenant-Id"]}, headers=h)
        assert r.status_code == 200


def test_ensure_matching_tenant_raises_on_mismatch():
    with pytest.raises(HTTPException) as ei:
        ensure_matching_tenant("22222222-2222-2222-2222-222222222222",
                               "00000000-0000-0000-0000-000000000001")
    assert ei.value.status_code == 403


def test_ensure_matching_tenant_ok_when_none_or_same():
    ensure_matching_tenant(None, "00000000-0000-0000-0000-000000000001")
    ensure_matching_tenant("00000000-0000-0000-0000-000000000001",
                           "00000000-0000-0000-0000-000000000001")


def test_vectors_search_always_filters_tenant():
    """Structural check: VectorStore.search must always carry a tenant_id filter."""
    import inspect
    from rag_kro_shared.vectors import VectorStore

    src = inspect.getsource(VectorStore.search)
    assert 'key="tenant_id"' in src
    assert 'query_filter=Filter(must=must)' in src