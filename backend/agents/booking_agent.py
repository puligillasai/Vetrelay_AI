"""Archetype 2 — Invisible Coordinator: clinic booking for the /api/route-booking endpoint.

Routing rules
-------------
1. If is_emergency=True  → always assign METRO_24_7, slot = "IMMEDIATE WALK-IN".
2. Otherwise:
   a. Filter vet_clinics.json to clinics that accept the given species AND have available_slots > 0.
   b. Sort by distance_miles ascending.
   c. Return the closest match.
   d. If no species-compatible clinic has capacity, fall back to METRO_24_7 with a note.

Capacity data is read from disk on every call (mock prototype — no DB).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.schemas import BookingResult, PetIntakeInput, TriageResult
from backend.telemetry import get_logger

log: logging.Logger = get_logger("vetrelay.booking")

_CLINICS_FILE = Path(__file__).parents[2] / "mock_data" / "vet_clinics.json"

# Sentinel ID used to locate the mandatory emergency clinic in the fixture file.
_EMERGENCY_CLINIC_ID = "METRO_24_7"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_clinics() -> list[dict[str, Any]]:
    with _CLINICS_FILE.open() as f:
        data: list[dict[str, Any]] = json.load(f)
        return data


def _get_emergency_clinic(clinics: list[dict[str, Any]]) -> dict[str, Any]:
    for c in clinics:
        if c["clinic_id"] == _EMERGENCY_CLINIC_ID:
            return c
    # Should never happen if vet_clinics.json is intact; fail loudly.
    raise RuntimeError(
        f"METRO_24_7 emergency clinic not found in {_CLINICS_FILE}. "
        "Do not remove this entry from mock_data/vet_clinics.json."
    )


def _to_booking(clinic: dict[str, Any], slot_override: str | None = None) -> BookingResult:
    slot = slot_override if slot_override is not None else clinic["next_available_slot"]
    return BookingResult(
        clinic_name=clinic["name"],
        address=clinic["address"],
        scheduled_slot=slot or "IMMEDIATE WALK-IN",
        instructions=(
            f"Please bring your pet's vaccination records. "
            f"Contact the clinic at {clinic['phone']} before arriving. "
            f"{clinic.get('notes', '')}"
        ).strip(),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def route_booking(intake: PetIntakeInput, triage: TriageResult) -> BookingResult:
    """Return a BookingResult for the given intake + triage outcome.

    Emergency fast-path: is_emergency=True bypasses all capacity/species checks.
    """
    clinics = _load_clinics()
    species = intake.species.lower()

    if triage.is_emergency:
        emergency = _get_emergency_clinic(clinics)
        log.warning(
            "event=booking_emergency species=%s severity_score=%d clinic_id=%s",
            species,
            triage.severity_score,
            _EMERGENCY_CLINIC_ID,
        )
        return _to_booking(emergency, slot_override="IMMEDIATE WALK-IN")

    # Species-aware, capacity-filtered candidates sorted by proximity
    candidates = [
        c
        for c in clinics
        if c["clinic_id"] != _EMERGENCY_CLINIC_ID
        and c["available_slots"] > 0
        and species in [s.lower() for s in c.get("species_accepted", [])]
    ]
    candidates.sort(key=lambda c: c["distance_miles"])

    if candidates:
        chosen = candidates[0]
        log.info(
            "event=booking_scheduled species=%s clinic_id=%s triage_level=%s",
            species,
            chosen["clinic_id"],
            triage.triage_level.value,
        )
        return _to_booking(chosen)

    # No species-compatible clinic available — fall back to emergency hospital with advisory note
    emergency = _get_emergency_clinic(clinics)
    log.warning(
        "event=booking_fallback_to_emergency species=%s reason=no_species_compatible_capacity",
        species,
    )
    fallback = _to_booking(emergency, slot_override="IMMEDIATE WALK-IN")
    return BookingResult(
        clinic_name=fallback.clinic_name,
        address=fallback.address,
        scheduled_slot=fallback.scheduled_slot,
        instructions=(
            f"No {species} clinics have capacity right now. "
            f"Routing to 24/7 emergency care as a precaution. "
            f"{fallback.instructions}"
        ),
    )
