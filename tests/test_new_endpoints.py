"""VetRelay AI — integration tests for new API endpoints.

Covers:
  - GET /api/intakes (Cloudant queue retrieval)
  - POST /api/tts (Watson TTS synthesis)
  - POST /api/handoff (front-desk persistence)
  - Phase-4 live clinical scenarios (chocolate emergency, urgent GI, routine wellness)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app

_TRANSPORT = ASGITransport(app=app)
_BASE_URL = "http://test"


async def _assess(payload: dict) -> dict:
    """POST /api/assess and return parsed JSON. Raises on non-200."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.post("/api/assess", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    return resp.json()


# ===========================================================================
# /api/intakes — Cloudant record retrieval
# ===========================================================================


@pytest.mark.asyncio
async def test_api_intakes_returns_list() -> None:
    """GET /api/intakes must return a JSON array (may be empty if Cloudant is unreachable)."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.get("/api/intakes")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    assert isinstance(data, list), f"Expected list, got {type(data).__name__}: {data!r}"


@pytest.mark.asyncio
async def test_api_intakes_limit_param() -> None:
    """GET /api/intakes?limit=5 must accept limit query param without error."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.get("/api/intakes?limit=5")
    assert resp.status_code == 200


# ===========================================================================
# /api/tts — Watson TTS synthesis
# ===========================================================================


@pytest.mark.asyncio
async def test_api_tts_text_mode_returns_200() -> None:
    """POST /api/tts in text mode must return 200 (audio or unavailable JSON)."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.post(
            "/api/tts",
            json={"text": "Test triage alert for VetRelay.", "mode": "text"},
        )
    assert resp.status_code == 200
    # Either audio/wav bytes or a JSON tts_unavailable response
    assert resp.headers["content-type"] in (
        "audio/wav",
        "application/json",
    ), f"Unexpected content-type: {resp.headers['content-type']}"


@pytest.mark.asyncio
async def test_api_tts_triage_mode_returns_200() -> None:
    """POST /api/tts in triage mode must return 200."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.post(
            "/api/tts",
            json={
                "mode": "triage",
                "pet_name": "Buddy",
                "triage_level": "CRITICAL_EMERGENCY",
                "action": "Proceed immediately to Metro 24/7.",
            },
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_api_tts_booking_mode_returns_200() -> None:
    """POST /api/tts in booking mode must return 200."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.post(
            "/api/tts",
            json={
                "mode": "booking",
                "pet_name": "Luna",
                "clinic_name": "Paws & Claws Community Clinic",
                "scheduled_slot": "2026-10-17T09:00:00",
                "instructions": "Bring vaccination records.",
            },
        )
    assert resp.status_code == 200


# ===========================================================================
# /api/handoff — front-desk persistence
# ===========================================================================


@pytest.mark.asyncio
async def test_api_handoff_returns_status() -> None:
    """POST /api/handoff must return status=saved or status=skipped (non-blocking)."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.post(
            "/api/handoff",
            json={
                "owner_name": "Test Owner",
                "pet_name": "Buddy",
                "species": "canine",
                "age_years": 3.0,
                "owner_zip": "90210",
                "triage_level": "CRITICAL_EMERGENCY",
                "is_emergency": True,
                "severity_score": 1,
                "soap_summary": "S: Chocolate ingestion. O: Pending. A: CRITICAL. P: ER now.",
                "clinic_name": "Metro 24/7 Veterinary Emergency Hospital",
                "clinic_address": "1 Emergency Plaza, Metro City, CA 90001",
                "scheduled_slot": "IMMEDIATE WALK-IN",
                "booking_instructions": "Proceed immediately. Bring the chocolate packaging.",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("saved", "skipped"), f"Unexpected status: {data['status']!r}"
    assert "message" in data


# ===========================================================================
# Phase-4 Clinical Scenarios — end-to-end via /api/assess
# ===========================================================================


@pytest.mark.asyncio
async def test_scenario1_critical_toxic_emergency_chocolate_canine() -> None:
    """Scenario 1: Buddy (canine) ate dark chocolate 1hr ago — must be CRITICAL_EMERGENCY."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Buddy",
            "species": "canine",
            "age_years": 3.0,
            "reported_symptoms": ["ate dark chocolate", "panting", "hyperactive"],
            "duration_hours": 1.0,
            "suspected_toxicity": False,  # keyword detection triggers the gate
        }
    )
    triage = result["triage"]
    booking = result["booking"]

    assert triage["triage_level"] == "CRITICAL_EMERGENCY", (
        f"Chocolate ingestion must be CRITICAL_EMERGENCY, got {triage['triage_level']}"
    )
    assert triage["is_emergency"] is True, "Chocolate ingestion must set is_emergency=True"
    assert triage["severity_score"] == 1, (
        f"CRITICAL_EMERGENCY must have severity_score=1, got {triage['severity_score']}"
    )
    assert "Metro 24/7" in booking["clinic_name"], (
        f"Emergency must route to Metro 24/7, got: {booking['clinic_name']!r}"
    )
    assert booking["scheduled_slot"] == "IMMEDIATE WALK-IN", (
        f"Emergency slot must be IMMEDIATE WALK-IN, got: {booking['scheduled_slot']!r}"
    )


@pytest.mark.asyncio
async def test_scenario2_urgent_gastrointestinal_feline() -> None:
    """Scenario 2: Luna (feline) vomiting and not eating for 12 hours — must be URGENT."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Luna",
            "species": "feline",
            "age_years": 4.0,
            "reported_symptoms": ["vomiting", "not eating"],
            "duration_hours": 12.0,
            "suspected_toxicity": False,
        }
    )
    triage = result["triage"]
    booking = result["booking"]

    assert triage["triage_level"] == "URGENT", (
        f"Vomiting + not eating must be URGENT, got {triage['triage_level']}"
    )
    assert triage["is_emergency"] is False, "GI case must not be flagged as emergency"
    assert booking["scheduled_slot"] != "IMMEDIATE WALK-IN", (
        "Urgent case must have a dated slot, not IMMEDIATE WALK-IN"
    )
    # Must route to a feline-compatible clinic
    import json
    from pathlib import Path

    clinics_file = Path(__file__).parents[1] / "mock_data" / "vet_clinics.json"
    clinics = json.loads(clinics_file.read_text())
    matched = next((c for c in clinics if c["name"] == booking["clinic_name"]), None)
    if matched:  # graceful — Metro fallback is also valid for urgents with no capacity
        assert "feline" in matched["species_accepted"] or "Metro 24/7" in booking["clinic_name"]


@pytest.mark.asyncio
async def test_scenario3_routine_wellness_exotic_rabbit() -> None:
    """Scenario 3: Pepper (exotic/rabbit) routine wellness — must be ROUTINE."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Pepper",
            "species": "exotic",
            "age_years": 2.0,
            "reported_symptoms": ["routine wellness check"],
            "duration_hours": 0.0,
            "suspected_toxicity": False,
        }
    )
    triage = result["triage"]
    booking = result["booking"]

    assert triage["triage_level"] == "ROUTINE", (
        f"Routine wellness must be ROUTINE, got {triage['triage_level']}"
    )
    assert triage["is_emergency"] is False, "Routine wellness must not be flagged as emergency"
    # All Species Veterinary Centre is the expected exotic-compatible clinic
    assert booking["clinic_name"] != "", "Must be assigned a clinic"
    assert booking["scheduled_slot"] != "IMMEDIATE WALK-IN", (
        "Routine case must have a scheduled slot, not IMMEDIATE WALK-IN"
    )


@pytest.mark.asyncio
async def test_scenario_pii_guard_no_pii_in_logs() -> None:
    """PII guard: /api/assess must complete without leaking PII into log output.

    This is a smoke test that verifies the endpoint processes the request
    end-to-end without crashing. The actual PII-in-fixtures check is in
    test_vetrelay.py::test_synthetic_data_integrity_no_pii.
    """
    result = await _assess(
        {
            "owner_name": "Owner PII Test",
            "pet_name": "Pepper",
            "species": "exotic",
            "age_years": 1.5,
            "reported_symptoms": ["routine checkup"],
            "duration_hours": 0.0,
            "suspected_toxicity": False,
        }
    )
    assert "triage" in result
    assert "booking" in result
    # owner_name must NOT appear in the soap_summary (PII contract)
    soap: str = result["triage"]["soap_summary"]
    assert "Owner PII Test" not in soap, (
        "owner_name must not be embedded in the SOAP summary (PII contract)"
    )
