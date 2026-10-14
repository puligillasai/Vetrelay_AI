"""Tests for POST /api/triage — Human-AI Boundary Manager."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app

_CLIENT_KWARGS = {"transport": ASGITransport(app=app), "base_url": "http://test"}

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_BASE_INTAKE = {
    "owner_name": "Test Owner",
    "pet_name": "Rex",
    "species": "canine",
    "age_years": 4.0,
    "reported_symptoms": ["mild lethargy"],
    "duration_hours": 12.0,
    "suspected_toxicity": False,
}


def _intake(**overrides) -> dict:
    return {**_BASE_INTAKE, **overrides}


# ---------------------------------------------------------------------------
# Critical-emergency gate tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspected_toxicity_flag_forces_critical():
    """suspected_toxicity=True must always yield CRITICAL_EMERGENCY, score=1, is_emergency=True."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(suspected_toxicity=True, reported_symptoms=["vomiting"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_emergency"] is True
    assert data["triage_level"] == "CRITICAL_EMERGENCY"
    assert data["severity_score"] == 1


@pytest.mark.asyncio
async def test_chocolate_symptom_token_forces_critical():
    """Toxin keyword in reported_symptoms must trigger CRITICAL_EMERGENCY."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["ate chocolate bar"], suspected_toxicity=False),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_emergency"] is True
    assert data["triage_level"] == "CRITICAL_EMERGENCY"


@pytest.mark.asyncio
async def test_seizure_symptom_forces_critical():
    """Critical symptom keyword must trigger CRITICAL_EMERGENCY."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["seizure", "collapse"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_emergency"] is True
    assert data["triage_level"] == "CRITICAL_EMERGENCY"
    assert data["severity_score"] == 1


@pytest.mark.asyncio
async def test_pale_gums_forces_critical():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["pale gums", "weakness"]),
        )
    data = resp.json()
    assert data["is_emergency"] is True


@pytest.mark.asyncio
async def test_bloat_forces_critical():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["bloat", "distended abdomen"]),
        )
    data = resp.json()
    assert data["is_emergency"] is True
    assert data["triage_level"] == "CRITICAL_EMERGENCY"


# ---------------------------------------------------------------------------
# Urgent (non-emergency) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vomiting_yields_urgent():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["vomiting", "not eating"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_emergency"] is False
    assert data["triage_level"] == "URGENT"
    assert data["severity_score"] in (2, 3)


@pytest.mark.asyncio
async def test_multiple_urgent_symptoms_score_2():
    """3+ urgent symptoms should yield severity_score=2."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["vomiting", "diarrhea", "lethargy", "fever"]),
        )
    data = resp.json()
    assert data["triage_level"] == "URGENT"
    assert data["severity_score"] == 2


# ---------------------------------------------------------------------------
# Routine tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_serious_symptoms_yields_routine():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["needs annual checkup"]),
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_emergency"] is False
    assert data["triage_level"] == "ROUTINE"
    assert data["severity_score"] in (4, 5)


# ---------------------------------------------------------------------------
# SOAP brief structural check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soap_summary_contains_all_sections():
    """soap_summary must contain S:, O:, A:, P: markers."""
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=["vomiting"]),
        )
    data = resp.json()
    soap = data["soap_summary"]
    for marker in ("S:", "O:", "A:", "P:"):
        assert marker in soap, f"Missing SOAP section marker: {marker}"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_symptoms_rejected():
    async with AsyncClient(**_CLIENT_KWARGS) as client:
        resp = await client.post(
            "/api/triage",
            json=_intake(reported_symptoms=[]),
        )
    assert resp.status_code == 422
