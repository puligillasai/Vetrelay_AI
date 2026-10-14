"""Comprehensive agentic-behaviour test suite for VetRelay AI.

Covers three verification dimensions:
  1. Safety boundary — toxic emergency escalation end-to-end
  2. Happy-path routing — routine care scheduling
  3. Data integrity — no PII in synthetic clinic fixtures
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_TRANSPORT = ASGITransport(app=app)
_BASE_URL = "http://test"

_CLINICS_FILE = Path(__file__).parents[1] / "mock_data" / "vet_clinics.json"

# Patterns that indicate real PII — none should appear in fixture data.
# Synthetic phone numbers must use the 555-XXXX convention.
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Real US phone numbers (10-digit, not 555-xxxx)
    (
        "real_phone",
        re.compile(r"\b(?!555)[2-9]\d{2}[-.)\s]?\d{3}[-.]\d{4}\b"),
    ),
    # SSN
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    # Email address
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ),
    # Credit-card-like 16-digit run
    (
        "credit_card",
        re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),
    ),
    # Full name patterns: "FirstName LastName" with common first names
    # (broad heuristic — flags obvious real names embedded in fixture strings)
    (
        "likely_real_name",
        re.compile(
            r"\b(John|Jane|Michael|Sarah|David|Emily|Robert|Jessica)"
            r"\s+[A-Z][a-z]{2,}\b"
        ),
    ),
]

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _assess(payload: dict) -> dict:
    """POST /api/assess and return parsed JSON. Raises on non-200."""
    async with AsyncClient(transport=_TRANSPORT, base_url=_BASE_URL) as client:
        resp = await client.post("/api/assess", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    return resp.json()


# ===========================================================================
# 1. test_toxic_emergency_boundary
#    A dog that ingested dark chocolate must trigger CRITICAL_EMERGENCY and
#    be routed exclusively to the Metro 24/7 ER with an immediate walk-in slot.
# ===========================================================================


@pytest.mark.asyncio
async def test_toxic_emergency_boundary_chocolate_dog() -> None:
    """Dark chocolate ingestion → CRITICAL_EMERGENCY → Metro 24/7 IMMEDIATE WALK-IN."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Biscuit",
            "species": "canine",
            "age_years": 3.0,
            "reported_symptoms": ["ate dark chocolate bar", "trembling"],
            "duration_hours": 1.0,
            "suspected_toxicity": False,  # keyword detection (not the flag) triggers escalation
        }
    )

    triage = result["triage"]
    booking = result["booking"]

    # ── Triage assertions ──────────────────────────────────────────────────
    assert triage["is_emergency"] is True, (
        "Dark chocolate contains theobromine — must always be CRITICAL_EMERGENCY"
    )
    assert triage["triage_level"] == "CRITICAL_EMERGENCY", (
        f"Expected CRITICAL_EMERGENCY, got {triage['triage_level']}"
    )
    assert triage["severity_score"] == 1, (
        f"Critical cases must have severity_score=1, got {triage['severity_score']}"
    )

    # ── SOAP brief structural assertions ──────────────────────────────────
    soap: str = triage["soap_summary"]
    for marker in ("S:", "O:", "A:", "P:"):
        assert marker in soap, f"SOAP brief missing section marker: {marker}"
    assert "canine" in soap.lower() or "Canine" in soap, "SOAP brief must include species"

    # ── Booking assertions ─────────────────────────────────────────────────
    assert "Metro 24/7" in booking["clinic_name"], (
        f"Emergency must route to Metro 24/7, got: {booking['clinic_name']!r}"
    )
    assert booking["scheduled_slot"] == "IMMEDIATE WALK-IN", (
        f"Emergency slot must be 'IMMEDIATE WALK-IN', got: {booking['scheduled_slot']!r}"
    )
    assert "1 Emergency Plaza" in booking["address"], (
        "Metro 24/7 address must include '1 Emergency Plaza'"
    )


@pytest.mark.asyncio
async def test_toxic_emergency_boundary_suspected_flag() -> None:
    """suspected_toxicity=True must force CRITICAL_EMERGENCY even with mild symptoms."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Max",
            "species": "canine",
            "age_years": 5.0,
            "reported_symptoms": ["slightly lethargic"],
            "duration_hours": 0.5,
            "suspected_toxicity": True,
        }
    )
    triage = result["triage"]
    assert triage["is_emergency"] is True, (
        "suspected_toxicity=True must always trigger is_emergency=True"
    )
    assert triage["triage_level"] == "CRITICAL_EMERGENCY"
    assert triage["severity_score"] == 1
    assert "Metro 24/7" in result["booking"]["clinic_name"]


@pytest.mark.asyncio
async def test_toxic_emergency_boundary_xylitol() -> None:
    """Xylitol keyword in symptoms must force CRITICAL_EMERGENCY."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Daisy",
            "species": "canine",
            "age_years": 2.0,
            "reported_symptoms": ["ate xylitol gum", "vomiting"],
            "duration_hours": 0.25,
            "suspected_toxicity": False,
        }
    )
    assert result["triage"]["is_emergency"] is True
    assert result["triage"]["triage_level"] == "CRITICAL_EMERGENCY"
    assert result["booking"]["scheduled_slot"] == "IMMEDIATE WALK-IN"


@pytest.mark.asyncio
async def test_toxic_emergency_boundary_seizure() -> None:
    """Seizure keyword must force CRITICAL_EMERGENCY independent of toxin flag."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Rocky",
            "species": "canine",
            "age_years": 4.0,
            "reported_symptoms": ["seizure", "collapse"],
            "duration_hours": 0.1,
            "suspected_toxicity": False,
        }
    )
    assert result["triage"]["is_emergency"] is True
    assert result["triage"]["triage_level"] == "CRITICAL_EMERGENCY"
    assert result["triage"]["severity_score"] == 1
    assert "Metro 24/7" in result["booking"]["clinic_name"]


# ===========================================================================
# 2. test_routine_checkup_routing
#    A cat needing a routine vaccination must produce ROUTINE status with a
#    real scheduled appointment slot (not IMMEDIATE WALK-IN) and must NOT
#    route to the 24/7 emergency hospital.
# ===========================================================================


@pytest.mark.asyncio
async def test_routine_checkup_routing_cat_vaccination() -> None:
    """Routine cat vaccination → ROUTINE triage → community clinic with scheduled slot."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Mittens",
            "species": "feline",
            "age_years": 1.5,
            "reported_symptoms": ["annual vaccination due"],
            "duration_hours": None,
            "suspected_toxicity": False,
        }
    )

    triage = result["triage"]
    booking = result["booking"]

    # ── Triage assertions ──────────────────────────────────────────────────
    assert triage["is_emergency"] is False, "Annual vaccination must not be flagged as emergency"
    assert triage["triage_level"] == "ROUTINE", f"Expected ROUTINE, got {triage['triage_level']}"
    assert triage["severity_score"] in (4, 5), (
        f"Routine cases must have severity_score 4 or 5, got {triage['severity_score']}"
    )

    # ── Booking assertions ─────────────────────────────────────────────────
    assert booking["clinic_name"] != "Metro 24/7 Veterinary Emergency Hospital", (
        "Routine case must NOT route to the 24/7 emergency hospital"
    )
    assert booking["scheduled_slot"] != "IMMEDIATE WALK-IN", (
        "Routine case must have a real scheduled appointment slot, not IMMEDIATE WALK-IN"
    )
    # Slot must be a parseable ISO-8601 datetime
    try:
        from datetime import datetime

        datetime.fromisoformat(booking["scheduled_slot"])
    except ValueError as exc:
        pytest.fail(f"scheduled_slot {booking['scheduled_slot']!r} is not valid ISO-8601: {exc}")

    # Clinic must accept feline species
    clinics = json.loads(_CLINICS_FILE.read_text())
    matched = next((c for c in clinics if c["name"] == booking["clinic_name"]), None)
    assert matched is not None, (
        f"Booked clinic {booking['clinic_name']!r} not found in vet_clinics.json"
    )
    assert "feline" in matched["species_accepted"], (
        f"Routed clinic {booking['clinic_name']!r} does not accept feline species"
    )
    assert matched["available_slots"] > 0, (
        f"Routed clinic {booking['clinic_name']!r} reported available_slots=0"
    )


@pytest.mark.asyncio
async def test_routine_checkup_routing_soap_sections() -> None:
    """SOAP brief for routine case must contain all four section markers."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Luna",
            "species": "feline",
            "age_years": 3.0,
            "reported_symptoms": ["routine wellness check"],
            "duration_hours": None,
            "suspected_toxicity": False,
        }
    )
    soap: str = result["triage"]["soap_summary"]
    for marker in ("S:", "O:", "A:", "P:"):
        assert marker in soap, f"Routine SOAP brief missing section: {marker}"


@pytest.mark.asyncio
async def test_routine_checkup_routing_action_text() -> None:
    """action_required for routine case must mention scheduling / 48-72 hours."""
    result = await _assess(
        {
            "owner_name": "Test Owner",
            "pet_name": "Leo",
            "species": "feline",
            "age_years": 2.0,
            "reported_symptoms": ["annual checkup"],
            "duration_hours": None,
            "suspected_toxicity": False,
        }
    )
    action: str = result["triage"]["action_required"].lower()
    assert any(kw in action for kw in ("schedule", "appointment", "48", "72", "routine")), (
        f"Routine action_required text should mention scheduling, got: {action!r}"
    )


# ===========================================================================
# 3. test_synthetic_data_integrity
#    Ensure mock_data/vet_clinics.json contains no real PII — names,
#    addresses, phone numbers, emails, or other identifying data must
#    conform to the synthetic-only contract defined in AGENTS.md.
# ===========================================================================


def test_synthetic_data_integrity_file_exists() -> None:
    """vet_clinics.json must exist and be valid JSON."""
    assert _CLINICS_FILE.exists(), f"mock_data/vet_clinics.json not found at {_CLINICS_FILE}"
    try:
        clinics = json.loads(_CLINICS_FILE.read_text())
    except json.JSONDecodeError as exc:
        pytest.fail(f"mock_data/vet_clinics.json is not valid JSON: {exc}")
    assert isinstance(clinics, list), "vet_clinics.json must be a JSON array"
    assert len(clinics) > 0, "vet_clinics.json must have at least one clinic"


def test_synthetic_data_integrity_no_pii() -> None:
    """No PII patterns (real phones, SSNs, emails, credit cards) in vet_clinics.json."""
    raw_text = _CLINICS_FILE.read_text()

    violations: list[str] = []
    for pattern_name, pattern in _PII_PATTERNS:
        matches = pattern.findall(raw_text)
        if matches:
            violations.append(f"  [{pattern_name}] found: {matches}")

    assert not violations, "PII detected in mock_data/vet_clinics.json:\n" + "\n".join(violations)


def test_synthetic_data_integrity_phone_format() -> None:
    """All phone numbers must use the 555-XXXX synthetic convention."""
    clinics = json.loads(_CLINICS_FILE.read_text())
    synthetic_phone = re.compile(r"^555-\d{4}$")
    for clinic in clinics:
        phone: str = clinic.get("phone", "")
        assert synthetic_phone.match(phone), (
            f"Clinic {clinic['clinic_id']!r} has non-synthetic phone: {phone!r}. "
            "All phone numbers must match 555-XXXX."
        )


def test_synthetic_data_integrity_emergency_clinic_present() -> None:
    """METRO_24_7 clinic must be present — booking agent depends on it."""
    clinics = json.loads(_CLINICS_FILE.read_text())
    ids = {c["clinic_id"] for c in clinics}
    assert "METRO_24_7" in ids, (
        "METRO_24_7 entry is missing from vet_clinics.json. "
        "The booking agent will raise RuntimeError at runtime without it."
    )


def test_synthetic_data_integrity_required_fields() -> None:
    """Every clinic record must have the fields required by BookingResult / routing agent."""
    required = {
        "clinic_id",
        "name",
        "clinic_type",
        "address",
        "phone",
        "species_accepted",
        "available_slots",
        "next_available_slot",
        "distance_miles",
    }
    clinics = json.loads(_CLINICS_FILE.read_text())
    for clinic in clinics:
        missing = required - clinic.keys()
        assert not missing, (
            f"Clinic {clinic.get('clinic_id', '?')!r} is missing required fields: {missing}"
        )


def test_synthetic_data_integrity_no_real_addresses() -> None:
    """Addresses must use obviously synthetic street names, not real geocodable addresses."""
    clinics = json.loads(_CLINICS_FILE.read_text())
    # Real zip codes outside the known synthetic range (90001-90215) are suspicious
    real_zip = re.compile(r"\b(?!9020[0-9]|9021[0-5]|90001)\d{5}\b")
    for clinic in clinics:
        address: str = clinic.get("address", "")
        hits = real_zip.findall(address)
        assert not hits, (
            f"Clinic {clinic['clinic_id']!r} address contains unexpected ZIP code(s) "
            f"{hits!r} outside the synthetic range 90001-90215: {address!r}"
        )
