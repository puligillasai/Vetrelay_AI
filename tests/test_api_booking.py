"""Tests for POST /api/route-booking — Invisible Coordinator."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app

_CLIENT_KWARGS = {"transport": ASGITransport(app=app), "base_url": "http://test"}

_BASE_INTAKE = {
    "owner_name": "Test Owner",
    "pet_name": "Whiskers",
    "species": "feline",
    "age_years": 2.0,
    "reported_symptoms": ["lethargy"],
    "duration_hours": 6.0,
    "suspected_toxicity": False,
}


def _intake(**overrides) -> dict:
    return {**_BASE_INTAKE, **overrides}


# Emergency triage stubs used in booking tests
_EMERGENCY_TRIAGE = {
    "is_emergency": True,
    "triage_level": "CRITICAL_EMERGENCY",
    "severity_score": 1,
    "soap_summary": "S: test O: test A: test P: test",
    "action_required": "Go to emergency hospital.",
}

_ROUTINE_TRIAGE = {
    "is_emergency": False,
    "triage_level": "ROUTINE",
    "severity_score": 5,
    "soap_summary": "S: test O: test A: test P: test",
    "action_required": "Schedule routine appointment.",
}

_URGENT_TRIAGE = {
    "is_emergency": False,
    "triage_level": "URGENT",
    "severity_score": 3,
    "soap_summary": "S: test O: test A: test P: test",
    "action_required": "Same-day evaluation required.",
}


# ---------------------------------------------------------------------------
# Emergency fast-path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emergency_routes_to_metro_24_7():
    """is_emergency=True must always route to Metro 24/7 with IMMEDIATE WALK-IN slot."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/route-booking",
            json={"intake": _intake(), "triage": _EMERGENCY_TRIAGE},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "Metro 24/7" in data["clinic_name"]
    assert data["scheduled_slot"] == "IMMEDIATE WALK-IN"


@pytest.mark.asyncio
async def test_emergency_ignores_species():
    """Emergency fast-path must work even for species with no community clinic coverage."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/route-booking",
            json={"intake": _intake(species="reptile"), "triage": _EMERGENCY_TRIAGE},
        )
    data = resp.json()
    assert "Metro 24/7" in data["clinic_name"]
    assert data["scheduled_slot"] == "IMMEDIATE WALK-IN"


# ---------------------------------------------------------------------------
# Non-emergency species-aware routing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routine_feline_routes_to_available_clinic():
    """Routine feline case must route to a feline-accepting clinic (not Metro 24/7)."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/route-booking",
            json={"intake": _intake(species="feline"), "triage": _ROUTINE_TRIAGE},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["clinic_name"] != "Metro 24/7 Veterinary Emergency Hospital"
    assert data["scheduled_slot"] != "IMMEDIATE WALK-IN"


@pytest.mark.asyncio
async def test_avian_routes_to_all_species_or_avian_clinic():
    """Avian species must match a clinic that lists 'avian' in species_accepted."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/route-booking",
            json={"intake": _intake(species="avian"), "triage": _ROUTINE_TRIAGE},
        )
    data = resp.json()
    # Should be routed to All Species or Avian & Exotic — not Metro 24/7
    assert resp.status_code == 200
    assert "clinic_name" in data
    assert "scheduled_slot" in data


# ---------------------------------------------------------------------------
# Composite /api/assess endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assess_endpoint_returns_triage_and_booking():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/assess",
            json=_intake(reported_symptoms=["vomiting", "lethargy"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "triage" in data
    assert "booking" in data
    assert "triage_level" in data["triage"]
    assert "clinic_name" in data["booking"]


@pytest.mark.asyncio
async def test_assess_emergency_intake_books_metro():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/assess",
            json=_intake(suspected_toxicity=True, reported_symptoms=["vomiting"]),
        )
    data = resp.json()
    assert data["triage"]["is_emergency"] is True
    assert "Metro 24/7" in data["booking"]["clinic_name"]
    assert data["booking"]["scheduled_slot"] == "IMMEDIATE WALK-IN"
