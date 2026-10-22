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
from typing import Any

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agents.booking_agent import route_booking
from backend.agents.triage_agent import evaluate_triage
from backend.routers import routing, soap
from backend.routers import triage as triage_router
from backend.schemas import BookingResult, PetIntakeInput, TriageResult
from backend.services.cloudant_db import get_recent_records, save_triage_record
from backend.services.watson_tts import booking_speech, triage_speech
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
    docs_url="/docs",
    redoc_url="/redoc",
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["openapi"] = "3.0.3"
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

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
# /api/intakes — Cloudant record retrieval (front-desk queue sync)
# ---------------------------------------------------------------------------


@app.get(
    "/api/intakes",
    tags=["VetRelay API"],
    summary="Retrieve recent triage/booking intake records from Cloudant",
    operation_id="listIntakes",
)
async def api_intakes(limit: int = 20) -> list[dict[str, Any]]:
    """Return the *limit* most recent encounter records persisted in Cloudant.

    Used by the clinic front-desk console (MVP 2) to synchronise the queue
    across sessions and by integration tests to verify Cloudant persistence.
    Returns an empty list when Cloudant is unavailable or credentials are missing.
    """
    records = get_recent_records(limit=limit)
    log.info("event=api_intakes_fetched count=%d", len(records))
    return records


# ---------------------------------------------------------------------------
# /api/tts — Watson TTS audio synthesis
# ---------------------------------------------------------------------------


class _TTSRequest(BaseModel):
    text: str = ""
    pet_name: str = ""
    triage_level: str = ""
    action: str = ""
    clinic_name: str = ""
    scheduled_slot: str = ""
    instructions: str = ""
    mode: str = "text"  # "text" | "triage" | "booking"


@app.post(
    "/api/tts",
    tags=["VetRelay API"],
    summary="Synthesise triage or booking text to WAV audio via IBM Watson TTS",
    operation_id="synthesiseTTS",
)
async def api_tts(body: _TTSRequest) -> Response:
    """Convert triage or booking text to spoken audio using IBM Watson TTS.

    Modes:
    - ``text``: Synthesise ``body.text`` directly.
    - ``triage``: Build a triage direction for ``pet_name`` from ``triage_level``
      and ``action``, then synthesise.
    - ``booking``: Build a booking confirmation for ``pet_name`` from
      ``clinic_name``, ``scheduled_slot``, and ``instructions``, then synthesise.

    Returns WAV audio bytes (``Content-Type: audio/wav``) when TTS is available,
    or a 200 JSON ``{"status": "tts_unavailable"}`` when credentials are missing.
    """
    audio: bytes | None = None

    if body.mode == "triage":
        audio = triage_speech(body.pet_name, body.triage_level, body.action)
    elif body.mode == "booking":
        audio = booking_speech(
            body.pet_name, body.clinic_name, body.scheduled_slot, body.instructions
        )
    else:
        from backend.services.watson_tts import speak

        audio = speak(body.text or body.action or "")

    if audio:
        log.info("event=api_tts_synthesised bytes=%d", len(audio))
        return Response(content=audio, media_type="audio/wav")

    log.info("event=api_tts_unavailable reason=no_audio")
    from fastapi.responses import JSONResponse

    return JSONResponse({"status": "tts_unavailable"})


# ---------------------------------------------------------------------------
# /api/handoff — front-desk record persistence (called by handoff tool)
# ---------------------------------------------------------------------------


class _HandoffRequest(BaseModel):
    owner_name: str
    pet_name: str
    species: str
    age_years: float
    owner_zip: str = "75038"
    triage_level: str
    is_emergency: bool
    severity_score: int
    soap_summary: str
    clinic_name: str
    clinic_address: str
    scheduled_slot: str
    booking_instructions: str


@app.post(
    "/api/handoff",
    tags=["VetRelay API"],
    summary="Persist a completed intake encounter to the front-desk queue in Cloudant",
    operation_id="handoffToFrontDesk",
)
async def api_handoff(body: _HandoffRequest) -> dict[str, Any]:
    """Save the completed encounter to Cloudant and return a record ID.

    Called by the ``handoff_to_front_desk`` watsonx Orchestrate tool at the
    end of the intake pipeline.  Non-blocking — returns ``status=skipped``
    if Cloudant is unavailable rather than raising.
    """
    record: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(),
        "record_type": "handoff",
        "owner_name": body.owner_name,
        "pet_name": body.pet_name,
        "species": body.species,
        "age_years": body.age_years,
        "owner_zip": body.owner_zip,
        "triage_level": body.triage_level,
        "is_emergency": body.is_emergency,
        "severity_score": body.severity_score,
        "soap_brief": body.soap_summary,
        "assigned_clinic": body.clinic_name,
        "clinic_address": body.clinic_address,
        "scheduled_slot": body.scheduled_slot,
        "instructions": body.booking_instructions,
    }
    try:
        result = save_triage_record(record)
        record_id = result.get("id") if isinstance(result, dict) else None
        log.info("event=api_handoff_saved pet_name=%r record_id=%r", body.pet_name, record_id)
        return {"status": "saved", "record_id": record_id, "message": "Encounter record saved."}
    except Exception as exc:
        log.warning("event=api_handoff_failed error=%s", str(exc))
        return {
            "status": "skipped",
            "record_id": None,
            "message": f"Front-desk handoff unavailable: {exc}",
        }


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
