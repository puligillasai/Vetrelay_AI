"""Archetype 3 — Human-AI Boundary Manager + Archetype 1 — Cognitive Load Reducer.

Triage evaluation for the unified /api/triage endpoint.

Design constraints
------------------
- The deterministic red-flag gate fires BEFORE any LLM call.
- `is_emergency=True` can never be lowered by downstream logic once set here.
- SOAP brief is generated inline (rule-based stub; replace the _build_soap() call with
  an async LLM call to watsonx.ai when integrating a language model).
- No owner PII is included in log lines.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.schemas import PetIntakeInput, TriageLevel, TriageResult
from backend.telemetry import get_logger

log: logging.Logger = get_logger("vetrelay.triage")

# ---------------------------------------------------------------------------
# Deterministic red-flag catalogue
# ---------------------------------------------------------------------------

# Toxin/substance keywords that always force CRITICAL_EMERGENCY regardless of
# any other signal.  Comparison is case-insensitive substring match.
_CRITICAL_TOXINS: frozenset[str] = frozenset(
    {
        "xylitol",
        "ibuprofen",
        "acetaminophen",
        "paracetamol",
        "grapes",
        "raisins",
        "chocolate",
        "cocoa",
        "theobromine",
        "rat poison",
        "rodenticide",
        "metaldehyde",
        "antifreeze",
        "ethylene glycol",
        "permethrin",
        "organophosphate",
    }
)

# Symptom keywords that always force CRITICAL_EMERGENCY.
_CRITICAL_SYMPTOMS: frozenset[str] = frozenset(
    {
        "seizure",
        "convulsion",
        "collapse",
        "unresponsive",
        "unconscious",
        "not breathing",
        "dyspnea",
        "difficulty breathing",
        "laboured breathing",
        "bloat",
        "gvd",
        "gastric dilatation",
        "pale gums",
        "white gums",
        "blue gums",
        "grey gums",
        "hemorrhage",
        "severe bleeding",
        "trauma",
        "hit by car",
        "broken bone",
        "paralysis",
        "paresis",
        "suspected toxin",
        "ingested poison",
    }
)

# Symptom keywords that indicate URGENT (score 2-3).
_URGENT_SYMPTOMS: frozenset[str] = frozenset(
    {
        "vomiting",
        "diarrhea",
        "blood in stool",
        "blood in urine",
        "haematuria",
        "lethargy",
        "not eating",
        "anorexia",
        "excessive thirst",
        "rapid breathing",
        "tachycardia",
        "limping",
        "eye discharge",
        "swollen",
        "abscess",
        "wound",
        "scratch",
        "straining to urinate",
        "painful abdomen",
        "crying in pain",
        "fever",
        "high temperature",
    }
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise(text: str) -> str:
    return text.lower().strip()


def _matches_any(token: str, catalogue: frozenset[str]) -> bool:
    n = _normalise(token)
    return any(kw in n for kw in catalogue)


def _symptom_tokens(symptoms: list[str]) -> list[str]:
    """Flatten and normalise symptom list."""
    return [_normalise(s) for s in symptoms]


def _is_critical_toxin(intake: PetIntakeInput) -> bool:
    if intake.suspected_toxicity:
        return True
    # Check reported_symptoms for embedded toxin references
    tokens = _symptom_tokens(intake.reported_symptoms)
    return any(_matches_any(t, _CRITICAL_TOXINS) for t in tokens)


def _is_critical_symptom(intake: PetIntakeInput) -> bool:
    tokens = _symptom_tokens(intake.reported_symptoms)
    return any(_matches_any(t, _CRITICAL_SYMPTOMS) for t in tokens)


def _count_urgent(intake: PetIntakeInput) -> int:
    tokens = _symptom_tokens(intake.reported_symptoms)
    return sum(1 for t in tokens if _matches_any(t, _URGENT_SYMPTOMS))


def _build_soap(intake: PetIntakeInput, triage_level: TriageLevel) -> str:
    """Rule-based SOAP brief (Cognitive Load Reducer stub).

    Replace the body of this function with an async LLM call to watsonx.ai.
    The LLM prompt must instruct the model NOT to invent clinical facts and
    must receive triage_level as a context hint.
    """
    symptoms_str = "; ".join(intake.reported_symptoms)
    duration = (
        f"{intake.duration_hours}h" if intake.duration_hours is not None else "unknown duration"
    )
    age = f"{intake.age_years}yr" if intake.age_years is not None else "age unknown"
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    return (
        f"[SOAP Brief — {ts}] "
        f"S: {intake.species.capitalize()} patient, {age}. "
        f"Owner reports: {symptoms_str} (onset {duration}). "
        f"O: Physical exam pending — vitals not yet assessed. "
        f"A: Triage level {triage_level.value} based on reported presentation. "
        f"P: {_action_for_level(triage_level)}"
    )


def _action_for_level(level: TriageLevel) -> str:
    if level == TriageLevel.CRITICAL_EMERGENCY:
        return (
            "Immediate transfer to 24/7 emergency hospital. "
            "Do not delay for further history-taking."
        )
    if level == TriageLevel.URGENT:
        return "Same-day veterinary evaluation required. Monitor vitals during transport."
    return "Schedule routine appointment within 48–72 hours. Monitor for symptom progression."


def _score_for_level(level: TriageLevel, urgent_count: int) -> int:
    if level == TriageLevel.CRITICAL_EMERGENCY:
        return 1
    if level == TriageLevel.URGENT:
        return 2 if urgent_count >= 3 else 3
    return 4 if urgent_count >= 1 else 5


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def evaluate_triage(intake: PetIntakeInput) -> TriageResult:
    """Evaluate intake and return a TriageResult.

    Gate order (deterministic, cannot be overridden):
    1. suspected_toxicity flag or critical-toxin keyword → CRITICAL_EMERGENCY
    2. critical-symptom keyword → CRITICAL_EMERGENCY
    3. urgent-symptom count → URGENT
    4. Default → ROUTINE
    """
    critical_toxin = _is_critical_toxin(intake)
    critical_symptom = _is_critical_symptom(intake)
    urgent_count = _count_urgent(intake)

    if critical_toxin or critical_symptom:
        level = TriageLevel.CRITICAL_EMERGENCY
        is_emergency = True
        trigger = "toxin_flag" if critical_toxin else "critical_symptom"
        log.warning(
            "event=triage_critical species=%s trigger=%s severity_score=1",
            intake.species,
            trigger,
        )
    elif urgent_count > 0:
        level = TriageLevel.URGENT
        is_emergency = False
        log.info(
            "event=triage_urgent species=%s urgent_symptom_count=%d",
            intake.species,
            urgent_count,
        )
    else:
        level = TriageLevel.ROUTINE
        is_emergency = False
        log.info("event=triage_routine species=%s", intake.species)

    score = _score_for_level(level, urgent_count)
    soap = _build_soap(intake, level)
    action = _action_for_level(level)

    return TriageResult(
        is_emergency=is_emergency,
        triage_level=level,
        severity_score=score,
        soap_summary=soap,
        action_required=action,
    )
