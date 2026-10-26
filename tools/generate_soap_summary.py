"""VetRelay AI — watsonx Orchestrate tool: generateSOAPSummary.

Archetype 1 — Cognitive Load Reducer.
Converts a free-text owner narrative into a structured SOAP clinical note.

Import into watsonx Orchestrate:
    orchestrate tools import -k python -f tools/generate_soap_summary.py
"""

from __future__ import annotations

import os

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool

_API_BASE = os.getenv("VETRELAY_API_URL", "http://localhost:8000")  # set VETRELAY_API_URL in env


@tool
def generate_soap_summary(
    owner_statement: str,
    species: str,
    age_years: float | None = None,
) -> dict:
    """Convert a pet owner's free-text narrative into a structured SOAP clinical note.

    SOAP stands for Subjective, Objective, Assessment, Plan — the standard
    format used by veterinary clinicians to document patient visits. This tool
    reduces cognitive load for clinic staff by automatically structuring the
    owner's description into the four SOAP sections.

    Use this tool when a staff member or owner provides a narrative description
    of their pet's condition and you need to produce a structured clinical note.
    Do NOT invent clinical facts — only use information provided in owner_statement.

    Args:
        owner_statement: Free-text description of the pet's condition from the
            owner's perspective. Must be at least 10 characters. Example:
            "My dog has been vomiting and refusing food for the past two days.
            He also seems very lethargic and is drinking more water than usual."
        species: Species of the pet. Examples: canine, feline, avian, reptile, exotic.
        age_years: Approximate age of the pet in years (e.g. 4.5). Optional.

    Returns:
        A dict containing:
        - soap.subjective (str): Owner-reported symptoms in clinical language
        - soap.objective (str): Physical exam findings (pending until examined)
        - soap.assessment (str): Preliminary clinical assessment
        - soap.plan (str): Recommended next steps
        - confidence_score (float): 0.0–1.0 confidence of the generated summary
        - raw_owner_statement (str): The original owner statement echoed back
    """
    payload: dict = {
        "owner_statement": owner_statement,
        "species": species.lower(),
    }
    if age_years is not None:
        payload["age_years"] = age_years

    response = httpx.post(
        f"{_API_BASE}/soap/summarise",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
