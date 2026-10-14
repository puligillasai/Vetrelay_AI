"""Archetype 2 — Invisible Coordinator: clinic routing endpoint."""

from fastapi import APIRouter

from backend.agents.routing_agent import find_available_clinic
from backend.schemas.routing import RoutingRequest, RoutingResponse

router = APIRouter()


@router.post(
    "/find-clinic",
    response_model=RoutingResponse,
    summary="Route pet intake to available clinic",
)
async def find_clinic(request: RoutingRequest) -> RoutingResponse:
    """Return the best-matched clinic (community, mobile, or 24/7 hospital).

    Capacity data is sourced exclusively from mock_data/clinic_capacity.json — never from a live DB.
    """
    return await find_available_clinic(request)
