"""VetRelay AI — watsonx Orchestrate tool: evaluatePetTriage.

Archetype 3 — Human-AI Boundary Manager.
Runs deterministic triage evaluation: checks for critical toxins and
emergency symptoms, then returns severity + SOAP brief.

Import into watsonx Orchestrate:
    orchestrate tools import -k python -f tools/evaluate_triage.py
"""

from __future__ import annotations

import os

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_API_BASE = os.getenv("VETRELAY_API_URL", "http://localhost:8000")


@tool
def evaluate_pet_triage(
    owner_name: str,
    pet_name: str,
    species: str,
    age_years: float,
    reported_symptoms: str,
    duration_hours: float,
    suspected_toxicity: bool = False,
) -> dict:
    """Evaluate the triage level for a pet based on reported symptoms.

    Applies a deterministic safety gate that checks for critical toxins
    (chocolate, xylitol, rat poison, antifreeze, grapes, ibuprofen, etc.)
    and critical symptom presentations (seizure, collapse, pale gums, bloat,
    difficulty breathing, etc.) BEFORE any AI reasoning.

    CRITICAL SAFETY RULE: If is_emergency is True in the response, you MUST
    immediately escalate to emergency care. You MUST NOT attempt to lower the
    triage level, suggest home care, or delay action. The triage gate is
    deterministic and cannot be overridden.

    Use this tool when you need triage evaluation only (without booking).
    For a combined triage + booking in one call, use assess_pet_triage instead.

    Args:
        owner_name: Full name of the pet owner.
        pet_name: Name of the pet (e.g. "Max").
        species: Species of the pet. One of: canine, feline, avian, reptile, exotic.
        age_years: Approximate age of the pet in years (e.g. 3.0).
        reported_symptoms: Comma-separated symptoms (e.g. "seizure, pale gums, collapse").
        duration_hours: How long symptoms have been present in hours (e.g. 2.0).
        suspected_toxicity: True if owner suspects the pet ingested a toxic substance.

    Returns:
        A dict containing:
        - is_emergency (bool): True means IMMEDIATE emergency care is required.
        - triage_level (str): CRITICAL_EMERGENCY | URGENT | ROUTINE
        - severity_score (int): 1 (most critical) to 5 (routine)
        - soap_summary (str): Structured SOAP clinical brief
        - action_required (str): Plain-language instruction for the owner
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
        f"{_API_BASE}/api/triage",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
