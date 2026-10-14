"""Tests for clinic routing endpoint (Archetype 2)."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_routing_returns_clinic():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/routing/find-clinic",
            json={"zip_code": "90210", "urgent": False},
        )
    assert response.status_code == 200
    data = response.json()
    assert "routed_to" in data
    # At least one clinic in mock_data has available_slots > 0
    assert data["routed_to"] is not None


@pytest.mark.asyncio
async def test_routing_rejects_invalid_zip():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/routing/find-clinic",
            json={"zip_code": "ABCDE"},
        )
    assert response.status_code == 422
