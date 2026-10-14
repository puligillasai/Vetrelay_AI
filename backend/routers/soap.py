"""Archetype 1 — Cognitive Load Reducer: SOAP summarisation endpoint."""

from fastapi import APIRouter

from backend.agents.soap_agent import build_soap_summary
from backend.schemas.soap import SOAPRequest, SOAPResponse

router = APIRouter()


@router.post(
    "/summarise",
    response_model=SOAPResponse,
    summary="Convert owner narrative to SOAP summary",
)
async def summarise(request: SOAPRequest) -> SOAPResponse:
    """Accept a free-text owner statement and return a structured SOAP note.

    No PII is persisted; the payload is processed in-memory only.
    """
    return await build_soap_summary(request)
