"""VetRelay AI — watsonx Orchestrate tool: handoffToFrontDesk.

Archetype 2 — Invisible Coordinator (handoff step).
Persists a completed triage + booking encounter to the front-desk queue
so clinic staff can action the case without re-entering data.

Import into watsonx Orchestrate:
    orchestrate tools import -k python -f tools/handoff_to_front_desk.py
"""

from __future__ import annotations

import os

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_API_BASE = os.getenv("VETRELAY_API_URL", "http://localhost:8000")  # set VETRELAY_API_URL in env


@tool
def handoff_to_front_desk(
    owner_name: str,
    pet_name: str,
    species: str,
    age_years: float,
    triage_level: str,
    is_emergency: bool,
    severity_score: int,
    soap_summary: str,
    clinic_name: str,
    clinic_address: str,
    scheduled_slot: str,
    booking_instructions: str,
    owner_zip: str = "75038",
) -> dict:
    """Persist a completed triage and booking record to the VetRelay front-desk queue.

    This tool performs the final handoff step in the VetRelay intake pipeline,
    saving the full encounter record (triage result + clinic booking) to the
    Cloudant database where clinic front-desk staff can review and action it.

    CRITICAL SAFETY RULE: For emergency cases (is_emergency=True), this tool
    must only be called AFTER the emergency directive has been issued to the
    owner. Never delay the emergency directive to call this tool first.

    Use this tool AFTER assess_pet_triage has returned a result and the
    appropriate triage response has been delivered to the owner.

    Args:
        owner_name: Full name of the pet owner.
        pet_name: Name of the pet.
        species: Species of the pet (canine, feline, avian, reptile, exotic).
        age_years: Approximate age of the pet in years.
        triage_level: Triage classification: CRITICAL_EMERGENCY | URGENT | ROUTINE.
        is_emergency: True if this case requires immediate emergency care.
        severity_score: Severity score 1–5 from triage (1 = most critical).
        soap_summary: Structured SOAP clinical brief from triage result.
        clinic_name: Name of the assigned clinic from booking result.
        clinic_address: Address of the assigned clinic.
        scheduled_slot: Appointment slot or "IMMEDIATE WALK-IN" for emergencies.
        booking_instructions: What the owner should bring and expect on arrival.
        owner_zip: Owner's 5-digit ZIP code for location reference.

    Returns:
        A dict containing:
        - status (str): "saved" if the record was persisted, "skipped" if
          Cloudant is unavailable (non-blocking — does not fail the intake flow).
        - record_id (str | None): Cloudant document ID if successfully saved.
        - message (str): Human-readable confirmation or error description.
    """
    payload = {
        "owner_name": owner_name,
        "pet_name": pet_name,
        "species": species.lower(),
        "age_years": age_years,
        "owner_zip": owner_zip,
        "triage_level": triage_level,
        "is_emergency": is_emergency,
        "severity_score": severity_score,
        "soap_summary": soap_summary,
        "clinic_name": clinic_name,
        "clinic_address": clinic_address,
        "scheduled_slot": scheduled_slot,
        "booking_instructions": booking_instructions,
    }

    try:
        response = httpx.post(
            f"{_API_BASE}/api/handoff",
            json=payload,
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        # Non-blocking — a handoff failure must never interrupt the intake flow.
        return {
            "status": "skipped",
            "record_id": None,
            "message": f"Front-desk handoff unavailable: {exc}",
        }
