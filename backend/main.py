"""VetRelay AI — FastAPI application entry point.

Exposes two API surfaces:
  /api/*     — unified endpoints consumed by IBM watsonx Orchestrate (OpenAPI 3.0 / MCP)
  /soap/*    — legacy SOAP-summarisation router (Archetype 1 standalone)
  /triage/*  — legacy triage router (Archetype 3 standalone)
  /routing/* — legacy routing router (Archetype 2 standalone)

The /api/* routes are the canonical integration surface; the /soap|triage|routing
sub-routers are retained for backward compatibility with existing tests.
"""

# Load environment variables before any module that reads them.
# dotenv is optional — if not installed (CI/CD), os.environ is used directly.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agents.booking_agent import route_booking
from backend.agents.triage_agent import evaluate_triage
from backend.routers import routing, soap
from backend.routers import triage as triage_router
from backend.schemas import BookingResult, PetIntakeInput, TriageResult
from backend.services.cloudant_db import save_triage_record
from backend.telemetry import get_logger, setup_telemetry

log = get_logger("vetrelay.api")

app = FastAPI(
    title="VetRelay AI",
    description=(
        "Veterinary clinical operations AI — "
        "SOAP summarisation, emergency triage, and clinic routing. "
        "Designed for consumption by IBM watsonx Orchestrate via OpenAPI 3.0 and MCP."
    ),
    version="0.2.0",
    openapi_version="3.0.3",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_telemetry(app)

# ---------------------------------------------------------------------------
# /api/* — canonical watsonx Orchestrate integration surface
# ---------------------------------------------------------------------------


@app.post(
    "/api/triage",
    response_model=TriageResult,
    tags=["VetRelay API"],
    summary="Evaluate pet intake and return triage result + SOAP brief",
    operation_id="triagePetIntake",
)
async def api_triage(intake: PetIntakeInput) -> TriageResult:
    """Human-AI Boundary Manager + Cognitive Load Reducer.

    Applies a deterministic red-flag gate (toxins, critical symptoms) before
    generating a structured SOAP brief.  `is_emergency=True` must never be
    suppressed by the calling client.

    **Deterministic escalation triggers (always CRITICAL_EMERGENCY, score=1):**
    - `suspected_toxicity=true`
    - Symptom tokens matching known toxins (xylitol, chocolate, rat poison, antifreeze, …)
    - Symptom tokens matching critical presentations
      (seizure, pale gums, bloat, dyspnea, collapse, …)
    """
    result = await evaluate_triage(intake)
    log.info(
        "event=api_triage_complete triage_level=%s is_emergency=%s severity_score=%d",
        result.triage_level.value,
        result.is_emergency,
        result.severity_score,
    )
    return result


class _RouteBookingRequest(BaseModel):
    intake: PetIntakeInput
    triage: TriageResult


@app.post(
    "/api/route-booking",
    response_model=BookingResult,
    tags=["VetRelay API"],
    summary="Route pet intake to the most appropriate available clinic",
    operation_id="routeBooking",
)
async def api_route_booking(body: _RouteBookingRequest) -> BookingResult:
    """Invisible Coordinator.

    - `is_emergency=True` → always assigns Metro 24/7 Veterinary Emergency Hospital,
      slot = `IMMEDIATE WALK-IN`.
    - Otherwise, selects the nearest species-compatible clinic with available capacity
      from `mock_data/vet_clinics.json`.
    - Falls back to Metro 24/7 if no species-compatible clinic has capacity.

    Body shape: `{"intake": <PetIntakeInput>, "triage": <TriageResult>}`
    """
    result = await route_booking(body.intake, body.triage)
    log.info(
        "event=api_booking_complete clinic=%r slot=%r",
        result.clinic_name,
        result.scheduled_slot,
    )

    # Persist booking record to Cloudant so every booking path is captured,
    # not just those that go through /api/assess.
    try:
        record = {
            "created_at": datetime.now(UTC).isoformat(),
            "record_type": "booking",
            "owner_name": body.intake.owner_name,
            "pet_name": body.intake.pet_name,
            "species": body.intake.species,
            "age_years": body.intake.age_years,
            "reported_symptoms": body.intake.reported_symptoms,
            "duration_hours": body.intake.duration_hours,
            "triage_level": body.triage.triage_level.value,
            "is_emergency": body.triage.is_emergency,
            "severity_score": body.triage.severity_score,
            "soap_brief": body.triage.soap_summary,
            "assigned_clinic": result.clinic_name,
            "clinic_address": result.address,
            "scheduled_slot": result.scheduled_slot,
            "instructions": result.instructions,
        }
        save_triage_record(record)
        log.info("event=cloudant_booking_saved pet_name=%r", body.intake.pet_name)
    except Exception as exc:
        log.warning("event=cloudant_booking_save_failed error=%s", str(exc))

    return result


# ---------------------------------------------------------------------------
# /api/assess — convenience composite: triage + booking in one call
# ---------------------------------------------------------------------------


class _AssessResponse(BaseModel):
    triage: TriageResult
    booking: BookingResult


@app.post(
    "/api/assess",
    tags=["VetRelay API"],
    summary="Full assessment: triage + booking in a single round-trip",
    operation_id="assessAndBook",
    response_model=_AssessResponse,
)
async def api_assess(intake: PetIntakeInput) -> _AssessResponse:
    """Runs triage then booking sequentially and returns both results.

    Useful for watsonx Orchestrate flows that need a single tool call.
    """
    triage_result = await evaluate_triage(intake)
    booking_result = await route_booking(intake, triage_result)
    log.info(
        "event=api_assess_complete triage_level=%s clinic=%r",
        triage_result.triage_level.value,
        booking_result.clinic_name,
    )

    # Persist full encounter record (triage + booking) to Cloudant
    try:
        record = {
            "created_at": datetime.now(UTC).isoformat(),
            "record_type": "assess",
            "owner_name": intake.owner_name,
            "pet_name": intake.pet_name,
            "species": intake.species,
            "age_years": intake.age_years,
            "owner_zip": getattr(intake, "owner_zip", None),
            "reported_symptoms": intake.reported_symptoms,
            "duration_hours": intake.duration_hours,
            "triage_level": triage_result.triage_level.value,
            "is_emergency": triage_result.is_emergency,
            "severity_score": triage_result.severity_score,
            "soap_brief": triage_result.soap_summary,
            "action_required": triage_result.action_required,
            "assigned_clinic": booking_result.clinic_name,
            "clinic_address": booking_result.address,
            "scheduled_slot": booking_result.scheduled_slot,
            "instructions": booking_result.instructions,
        }
        save_triage_record(record)
        log.info("event=cloudant_record_saved pet_name=%r", intake.pet_name)
    except Exception as exc:
        log.warning("event=cloudant_save_failed error=%s", str(exc))

    return _AssessResponse(triage=triage_result, booking=booking_result)


# ---------------------------------------------------------------------------
# Legacy sub-routers (backward-compatible)
# ---------------------------------------------------------------------------

app.include_router(soap.router, prefix="/soap", tags=["SOAP Summarisation (legacy)"])
app.include_router(triage_router.router, prefix="/triage", tags=["Triage (legacy)"])
app.include_router(routing.router, prefix="/routing", tags=["Routing (legacy)"])


@app.get("/", tags=["Meta"])
async def root() -> dict[str, str]:
    return {
        "service": "VetRelay AI",
        "status": "online",
        "docs": "/docs",
        "health": "/healthz",
    }


@app.get("/healthz", tags=["Meta"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
