"""Archetype 3 — Human-AI Boundary Manager: legacy escalation endpoint.

This router is retained for backward-compatibility with /triage/evaluate callers.
New integrations should use POST /api/triage (PetIntakeInput schema).
"""

from fastapi import APIRouter

from backend.schemas.triage import SeverityLevel, TriageRequest, TriageResponse

router = APIRouter()

# Toxins that always force escalation — subset kept here for the legacy TriageRequest schema.
_LEGACY_CRITICAL_TOXINS: frozenset[str] = frozenset(
    {"xylitol", "ibuprofen", "acetaminophen", "grapes", "raisins", "chocolate", "metaldehyde"}
)


@router.post(
    "/evaluate",
    response_model=TriageResponse,
    summary="Evaluate symptom severity and escalate if critical",
)
async def evaluate(request: TriageRequest) -> TriageResponse:
    """Assess toxicity/critical symptoms; force emergency flag when threshold exceeded.

    The escalation_required field must ALWAYS be acted on by the UI — never suppressed.
    """
    toxin_critical = (
        request.possible_toxin is not None
        and request.possible_toxin.lower() in _LEGACY_CRITICAL_TOXINS
    )

    if toxin_critical:
        return TriageResponse(
            severity=SeverityLevel.CRITICAL,
            escalation_required=True,
            reasoning=f"Known critical toxin detected: {request.possible_toxin}.",
            recommended_action="Proceed immediately to nearest 24/7 emergency animal hospital.",
        )

    return TriageResponse(
        severity=SeverityLevel.MODERATE,
        escalation_required=False,
        reasoning="No critical toxin identified. Symptoms require veterinary evaluation.",
        recommended_action="Schedule same-day appointment at community or mobile clinic.",
    )
