"""VetRelay AI — watsonx Orchestrate tool: assessPetTriage.

ADK Python tool that wraps the FastAPI /api/assess endpoint.
Handles robust type casting so natural conversational phrasing
(e.g., "1 hour ago", omitted age) never causes tool execution crashes.
"""

from __future__ import annotations

import os
import re
from typing import Any
import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_API_BASE = "https://surreal-traps-bubbly.ngrok-free.dev"


def _parse_float(val: Any, default: float = 1.0) -> float:
    """Extract first float or integer from any input (e.g. '1.5 hours' -> 1.5)."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    match = re.search(r"(\d+(?:\.\d+)?)", str(val))
    return float(match.group(1)) if match else default


@tool
def assess_pet_triage(
    owner_name: str = "Anonymous",
    pet_name: str = "Unknown",
    species: str = "canine",
    age_years: Any = 3.0,
    reported_symptoms: str = "general malaise",
    duration_hours: Any = 2.0,
    suspected_toxicity: bool = False,
    owner_zip: str = "75038",
) -> dict[str, Any]:
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
        owner_name: Full name of the pet owner.
        pet_name: Name of the pet.
        species: Species of the pet (canine, feline, etc.). Defaults to canine.
        age_years: Age of the pet in years (e.g., 4 or '4 years'). Defaults to 3.0.
        reported_symptoms: Symptoms described by the owner (e.g. 'vomiting, chocolate').
        duration_hours: Time elapsed in hours (e.g., 1.5 or 'about an hour'). Defaults to 2.0.
        suspected_toxicity: True if toxin ingestion is suspected. Defaults to False.
        owner_zip: 5-digit zip code for local clinic routing. Defaults to '75038'.

    Returns:
        A dict containing triage results, emergency flags, clinic details, and SOAP note.
    """
    # Safe symptom extraction
    if isinstance(reported_symptoms, list):
        symptoms_list = [str(s).strip() for s in reported_symptoms if str(s).strip()]
    else:
        symptoms_list = [s.strip() for s in str(reported_symptoms).split(",") if s.strip()]

    if not symptoms_list:
        symptoms_list = ["unspecified symptoms"]

    # Safe numeric conversion
    safe_age = _parse_float(age_years, default=3.0)
    safe_duration = _parse_float(duration_hours, default=2.0)

    # Detect toxicity from symptom text if flag was omitted by LLM
    text_check = " ".join(symptoms_list).lower()
    toxin_keywords = ["chocolate", "xylitol", "poison", "antifreeze", "grapes", "raisins", "rat"]
    detected_toxicity = bool(suspected_toxicity) or any(t in text_check for t in toxin_keywords)

    payload = {
        "owner_name": str(owner_name or "Anonymous"),
        "pet_name": str(pet_name or "Unknown"),
        "species": str(species or "canine").lower(),
        "age_years": safe_age,
        "reported_symptoms": symptoms_list,
        "duration_hours": safe_duration,
        "suspected_toxicity": detected_toxicity,
        "owner_zip": str(owner_zip or "75038"),
    }

    try:
        response = httpx.post(
            f"{_API_BASE}/api/assess",
            json=payload,
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {
            "error": str(exc),
            "is_emergency": detected_toxicity,
            "triage_level": "CRITICAL_EMERGENCY" if detected_toxicity else "URGENT",
            "action_required": "Please proceed directly to the nearest emergency veterinary facility.",
        }