"""VetRelay AI — watsonx Orchestrate tool: findAvailableClinic.

Archetype 2 — Invisible Coordinator.
Routes a pet intake case to the most appropriate available clinic based on
species compatibility, urgency, and proximity.

Import into watsonx Orchestrate:
    orchestrate tools import -k python -f tools/find_clinic.py
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_API_BASE = os.getenv("VETRELAY_API_URL", "https://surreal-traps-bubbly.ngrok-free.dev")
_MAX_RETRIES = 3
_RETRY_DELAY_SECONDS = 1.0
_TIMEOUT_SECONDS = 30.0


def _post_with_retry(url: str, json: dict[str, Any]) -> dict[str, Any]:
    """POST with exponential backoff retry logic."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = httpx.post(url, json=json, timeout=_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_SECONDS * (2**attempt))
                continue
            raise
        except (httpx.RequestError, httpx.TimeoutException) as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY_SECONDS * (2**attempt))
                continue
            raise
    raise last_error or RuntimeError("Unexpected retry exhaustion")


@tool
def find_available_clinic(
    owner_name: str,
    pet_name: str,
    species: str,
    age_years: float,
    reported_symptoms: str,
    duration_hours: float,
    is_emergency: bool,
    triage_level: str,
    severity_score: int,
    soap_summary: str,
    action_required: str,
    suspected_toxicity: bool = False,
) -> dict:
    """Route a pet intake case to the most appropriate available clinic.

    The Invisible Coordinator applies three routing rules:
    1. If is_emergency is True → always assigns Metro 24/7 Veterinary Emergency
       Hospital with slot "IMMEDIATE WALK-IN". No other clinic is considered.
    2. Otherwise → selects the nearest species-compatible clinic with available
       slots from the clinic registry, sorted by distance.
    3. If no compatible clinic has capacity → falls back to Metro 24/7 with a note.

    This tool requires a completed triage result (from evaluate_pet_triage).
    For a single round-trip combining triage + booking, use assess_pet_triage.

    Args:
        owner_name: Full name of the pet owner.
        pet_name: Name of the pet.
        species: Species of the pet. One of: canine, feline, avian, reptile, exotic.
        age_years: Approximate age of the pet in years.
        reported_symptoms: Comma-separated symptoms string.
        duration_hours: How long symptoms have been present in hours.
        is_emergency: Whether triage determined this is an emergency (from evaluate_pet_triage).
        triage_level: Triage level string: CRITICAL_EMERGENCY | URGENT | ROUTINE.
        severity_score: Severity score 1–5 from triage (1 = most critical).
        soap_summary: SOAP brief from triage result.
        action_required: Action instruction from triage result.
        suspected_toxicity: Whether the owner suspected toxin ingestion.

    Returns:
        A dict containing:
        - clinic_name (str): Name of the assigned clinic
        - address (str): Address of the assigned clinic
        - scheduled_slot (str): ISO datetime or "IMMEDIATE WALK-IN"
        - instructions (str): What the owner should bring and expect on arrival
    """
    symptoms_list = [s.strip() for s in reported_symptoms.split(",") if s.strip()]

    triage_payload = {
        "is_emergency": is_emergency,
        "triage_level": triage_level,
        "severity_score": severity_score,
        "soap_summary": soap_summary,
        "action_required": action_required,
    }
    intake_payload = {
        "owner_name": owner_name,
        "pet_name": pet_name,
        "species": species.lower(),
        "age_years": age_years,
        "reported_symptoms": symptoms_list,
        "duration_hours": duration_hours,
        "suspected_toxicity": suspected_toxicity,
    }

    response = httpx.post(
        f"{_API_BASE}/api/route-booking",
        json={"intake": intake_payload, "triage": triage_payload},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
