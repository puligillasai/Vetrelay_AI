"""Pydantic schemas for SOAP summarisation (Archetype 1)."""

from pydantic import BaseModel, Field


class SOAPRequest(BaseModel):
    owner_statement: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Free-text narrative from the pet owner — no PII required.",
        examples=["My dog has been vomiting and not eating for the past two days."],
    )
    species: str = Field(..., description="e.g. canine, feline, avian")
    age_years: float | None = Field(None, ge=0, description="Approximate age in years")


class SOAPSections(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str


class SOAPResponse(BaseModel):
    soap: SOAPSections
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    raw_owner_statement: str  # echoed back; never persisted
