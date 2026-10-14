"""Stub agent — Archetype 1: Cognitive Load Reducer."""

from backend.schemas.soap import SOAPRequest, SOAPResponse, SOAPSections


async def build_soap_summary(request: SOAPRequest) -> SOAPResponse:
    """Placeholder: replace with LLM call to watsonx.ai / OpenAI.

    The LLM prompt must instruct the model to extract SOAP sections
    without inventing clinical facts.
    """
    # TODO: integrate LLM provider
    return SOAPResponse(
        soap=SOAPSections(
            subjective=request.owner_statement,
            objective="[Pending physical exam]",
            assessment="[Pending veterinarian assessment]",
            plan="[Pending treatment plan]",
        ),
        confidence_score=0.0,
        raw_owner_statement=request.owner_statement,
    )
