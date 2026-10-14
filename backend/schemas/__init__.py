"""backend.schemas — re-exports the unified public API schemas.

The canonical models used by /api/* endpoints live in backend/schemas.py (top-level module).
This __init__.py re-exports them so that ``from backend.schemas import PetIntakeInput`` resolves
correctly regardless of whether callers import via the package or the top-level module.
"""

from backend.schemas.routing import ClinicMatch, ClinicType, RoutingRequest, RoutingResponse
from backend.schemas.soap import SOAPRequest, SOAPResponse, SOAPSections
from backend.schemas.triage import SeverityLevel, TriageRequest, TriageResponse

# Unified /api/* models — defined in backend/schemas_api.py to avoid circular import
# with the schemas/ sub-package.
from backend.schemas_api import BookingResult, PetIntakeInput, TriageLevel, TriageResult

__all__ = [
    # routing
    "ClinicMatch",
    "ClinicType",
    "RoutingRequest",
    "RoutingResponse",
    # soap
    "SOAPRequest",
    "SOAPResponse",
    "SOAPSections",
    # triage (legacy)
    "SeverityLevel",
    "TriageRequest",
    "TriageResponse",
    # unified /api/* models
    "BookingResult",
    "PetIntakeInput",
    "TriageLevel",
    "TriageResult",
]
