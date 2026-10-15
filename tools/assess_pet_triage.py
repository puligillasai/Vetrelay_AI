"""VetRelay AI — watsonx Orchestrate tool: assessPetTriage.

This file is the ADK Python tool that the VetRelay Coordinator agent calls.
It wraps the FastAPI /api/assess endpoint so watsonx Orchestrate can invoke
triage + booking in a single round-trip.

Import into watsonx Orchestrate:
    orchestrate tools import -k python -f tools/assess_pet_triage.py

The tool calls the VetRelay FastAPI backend at VETRELAY_API_URL (default:
http://localhost:8000).  Set the environment variable to your deployed URL
before importing into a production Orchestrate environment.
"""

from __future__ import annotations

import os

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_API_BASE = os.getenv("VETRELAY_API_URL", "http://localhost:8000")


@tool
def assess_pet_triage(
    owner_name: str,
    pet_name: str,
    species: str,
    age_years: float,
    reported_symptoms: str,
    duration_hours: float,
    suspected_toxicity: bool = False,
) -> dict:
    """Assess a pet's triage level and book the most appropriate clinic in a single call.

    Collects the pet owner's intake information, runs a deterministic triage
    evaluation (checking for critical toxins, emergency symptoms, and urgency
    indicators), generates a structured SOAP clinical summary, and routes the
    case to the nearest available compatible clinic.

    CRITICAL SAFETY RULE: If the response contains is_emergency=true, you MUST
    immediately output an emergency alert directing the owner to transport their
    pet to the clinic right away. Do NOT suggest waiting, home care, or routine
    scheduling when is_emergency is true.

    Args:
        owner_name: Full name of the pet owner (used for appointment labelling only).
        pet_name: Name of the pet (e.g. "Buddy").
        species: Species of the pet. One of: canine, feline, avian, reptile, exotic.
        age_years: Approximate age of the pet in years (e.g. 3.5).
        reported_symptoms: Comma-separated list of symptoms reported by the owner
            (e.g. "vomiting, lethargy, pale gums"). Be as descriptive as possible.
        duration_hours: How many hours the symptoms have been present (e.g. 6.0).
        suspected_toxicity: Set to True if the owner believes the pet ingested a
            toxic substance such as chocolate, grapes, xylitol, rat poison,
            antifreeze, medications, or any household chemical. Defaults to False.

    Returns:
        A dict containing:
        - triage.is_emergency (bool): True means IMMEDIATE emergency care required.
        - triage.triage_level (str): CRITICAL_EMERGENCY | URGENT | ROUTINE
        - triage.severity_score (int): 1 (most critical) to 5 (routine)
        - triage.soap_summary (str): Structured SOAP clinical brief
        - triage.action_required (str): Plain-language instruction for the owner
        - booking.clinic_name (str): Name of the assigned clinic
        - booking.address (str): Address of the assigned clinic
        - booking.scheduled_slot (str): ISO datetime or "IMMEDIATE WALK-IN"
        - booking.instructions (str): What the owner should bring and expect
    """
    symptoms_list = [s.strip() for s in reported_symptoms.split(",") if s.strip()]

    payload = {
        "owner_name": owner_name,
        "pet_name": pet_name,
        "species": species.lower(),
        "age_years": age_years,
        "reported_symptoms": symptoms_list,
        "duration_hours": duration_hours,
        "suspected_toxicity": suspected_toxicity,
    }

    response = httpx.post(
        f"{_API_BASE}/api/assess",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
