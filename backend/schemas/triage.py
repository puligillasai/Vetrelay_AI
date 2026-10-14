"""Pydantic schemas for emergency triage (Archetype 3)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class SeverityLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class TriageRequest(BaseModel):
    symptoms: list[str] = Field(..., min_length=1, description="List of reported symptoms")
    possible_toxin: str | None = Field(None, description="Suspected toxin or substance if known")
    species: str
    weight_kg: float | None = Field(None, ge=0)


class TriageResponse(BaseModel):
    severity: SeverityLevel
    escalation_required: bool = Field(
        ...,
        description=(
            "When True the UI MUST display an emergency alert and block all non-emergency flows."
        ),
    )
    reasoning: str
    recommended_action: str
