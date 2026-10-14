"""Pydantic schemas for clinic routing (Archetype 2)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class ClinicType(StrEnum):
    COMMUNITY = "community"
    MOBILE = "mobile"
    EMERGENCY_24_7 = "emergency_24_7"


class RoutingRequest(BaseModel):
    zip_code: str = Field(..., pattern=r"^\d{5}$")
    preferred_clinic_type: ClinicType | None = None
    urgent: bool = False


class ClinicMatch(BaseModel):
    clinic_id: str
    name: str
    clinic_type: ClinicType
    distance_miles: float
    available_slots: int
    phone: str  # synthetic only — sourced from mock_data/


class RoutingResponse(BaseModel):
    matches: list[ClinicMatch]
    routed_to: ClinicMatch | None = None
    fallback_used: bool = Field(
        False,
        description=(
            "True when the preferred clinic type had no capacity "
            "and routing fell back to next best."
        ),
    )
