"""Stub agent — Archetype 2: Invisible Coordinator."""

import json
from pathlib import Path
from typing import Any

from backend.schemas.routing import ClinicMatch, ClinicType, RoutingRequest, RoutingResponse

_CAPACITY_FILE = Path(__file__).parents[2] / "mock_data" / "clinic_capacity.json"


def _load_capacity() -> list[dict[str, Any]]:
    with _CAPACITY_FILE.open() as f:
        data: list[dict[str, Any]] = json.load(f)
        return data


async def find_available_clinic(request: RoutingRequest) -> RoutingResponse:
    """Route pet intake using synthetic capacity fixtures from mock_data/.

    Capacity data is NEVER sourced from a live database in this prototype.
    Fallback order: preferred_type → emergency_24_7 → any available slot.
    """
    clinics = _load_capacity()

    def _to_match(c: dict[str, Any]) -> ClinicMatch:
        return ClinicMatch(**c)

    preferred_type = request.preferred_clinic_type or (
        ClinicType.EMERGENCY_24_7 if request.urgent else ClinicType.COMMUNITY
    )
    candidates = [_to_match(c) for c in clinics if c["available_slots"] > 0]
    preferred = [c for c in candidates if c.clinic_type == preferred_type]

    if preferred:
        return RoutingResponse(matches=candidates, routed_to=preferred[0], fallback_used=False)

    # Fallback to any available slot
    if candidates:
        return RoutingResponse(matches=candidates, routed_to=candidates[0], fallback_used=True)

    return RoutingResponse(matches=[], routed_to=None, fallback_used=True)
