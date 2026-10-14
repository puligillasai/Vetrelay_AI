"""Tests for SOAP summarisation endpoint (Archetype 1)."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_soap_summarise_returns_sections():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/soap/summarise",
            json={
                "owner_statement": "My dog has been vomiting and not eating for two days.",
                "species": "canine",
                "age_years": 3.0,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert "soap" in data
    for section in ("subjective", "objective", "assessment", "plan"):
        assert section in data["soap"]
    assert 0.0 <= data["confidence_score"] <= 1.0


@pytest.mark.asyncio
async def test_soap_summarise_requires_statement():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/soap/summarise",
            json={"owner_statement": "short", "species": "canine"},
        )
    assert response.status_code == 422
