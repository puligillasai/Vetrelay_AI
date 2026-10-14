"""Tests for triage evaluation endpoint (Archetype 3)."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_critical_toxin_forces_escalation():
    """xylitol must always produce escalation_required=True — deterministic gate."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/triage/evaluate",
            json={
                "symptoms": ["vomiting", "seizure"],
                "possible_toxin": "xylitol",
                "species": "canine",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["escalation_required"] is True
    assert data["severity"] == "critical"


@pytest.mark.asyncio
async def test_unknown_toxin_does_not_force_escalation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/triage/evaluate",
            json={"symptoms": ["lethargy"], "possible_toxin": None, "species": "feline"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["escalation_required"] is False
