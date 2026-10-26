"""Archetype 1 — Cognitive Load Reducer.

Converts a free-text owner narrative into a structured SOAP clinical note.

LLM integration:
    Calls IBM watsonx.ai Granite-3-8b-instruct via backend.services.watsonx_ai.
    Falls back to the deterministic rule-based stub when:
      - ibm-watsonx-ai is not installed
      - WATSONX_API_KEY / WATSONX_PROJECT_ID env vars are absent
      - The model call fails for any reason

Design constraints:
    - The LLM prompt explicitly forbids inventing clinical facts.
    - No owner PII is included in log lines.
    - confidence_score is 0.9 for LLM-generated output, 0.0 for stub.
"""

from __future__ import annotations

import logging

from backend.schemas.soap import SOAPRequest, SOAPResponse, SOAPSections
from backend.services.watsonx_ai import generate as _wx_generate
from backend.telemetry import get_logger

log: logging.Logger = get_logger("vetrelay.soap")

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SOAP_PROMPT = """\
You are a veterinary clinical assistant. Convert the pet owner's statement below into a \
structured SOAP note. Use ONLY information explicitly stated by the owner — do NOT invent \
symptoms, diagnoses, medications, or treatments.

Pet details:
  Species: {species}
  Age: {age}

Owner's statement:
"{statement}"

Respond with exactly four labelled sections and nothing else:

S (Subjective): <owner-reported symptoms and history in clinical language>
O (Objective): <physical exam findings — write "Pending physical examination" if not provided>
A (Assessment): <preliminary differential or clinical impression based only on stated symptoms>
P (Plan): <recommended next steps based only on the triage level and stated symptoms>
"""


def _build_prompt(request: SOAPRequest) -> str:
    age = f"{request.age_years} years" if request.age_years is not None else "unknown"
    return _SOAP_PROMPT.format(
        species=request.species.capitalize(),
        age=age,
        statement=request.owner_statement,
    )


def _parse_sections(raw: str) -> SOAPSections | None:
    """Extract S/O/A/P sections from the model's free-text reply.

    Returns None if any section is missing so the caller can fall back.
    """
    markers = {
        "S (Subjective):": "subjective",
        "O (Objective):": "objective",
        "A (Assessment):": "assessment",
        "P (Plan):": "plan",
    }
    sections: dict[str, str] = {}
    lines = raw.splitlines()
    current_key: str | None = None
    buffer: list[str] = []

    for line in lines:
        matched = False
        for marker, key in markers.items():
            if line.strip().startswith(marker):
                if current_key:
                    sections[current_key] = " ".join(buffer).strip()
                current_key = key
                buffer = [line.strip()[len(marker) :].strip()]
                matched = True
                break
        if not matched and current_key:
            buffer.append(line.strip())

    if current_key:
        sections[current_key] = " ".join(buffer).strip()

    if len(sections) < 4 or not all(
        sections.get(k) for k in ("subjective", "objective", "assessment", "plan")
    ):
        return None

    return SOAPSections(**sections)


def _stub_sections(request: SOAPRequest) -> SOAPSections:
    """Rule-based fallback — never invents clinical facts."""
    return SOAPSections(
        subjective=(
            f"{request.species.capitalize()} patient, "
            f"{f'{request.age_years} yr' if request.age_years else 'age unknown'}. "
            f"Owner reports: {request.owner_statement}"
        ),
        objective="Pending physical examination — vitals not yet assessed.",
        assessment="Preliminary assessment pending veterinarian evaluation.",
        plan="Schedule veterinary appointment. Monitor for symptom progression.",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def build_soap_summary(request: SOAPRequest) -> SOAPResponse:
    """Generate a structured SOAP note from the owner narrative.

    Attempts Granite inference first; falls back to the deterministic stub.
    """
    prompt = _build_prompt(request)
    raw = _wx_generate(prompt, max_new_tokens=400)

    if raw:
        sections = _parse_sections(raw)
        if sections:
            log.info(
                "event=soap_llm_generated species=%s confidence=0.9",
                request.species,
            )
            return SOAPResponse(
                soap=sections,
                confidence_score=0.9,
                raw_owner_statement=request.owner_statement,
            )
        log.warning("event=soap_parse_failed fallback=stub raw_length=%d", len(raw))
    else:
        log.info("event=soap_stub_used reason=llm_unavailable species=%s", request.species)

    return SOAPResponse(
        soap=_stub_sections(request),
        confidence_score=0.0,
        raw_owner_statement=request.owner_statement,
    )
