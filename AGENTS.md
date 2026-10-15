# AGENTS.md

This file provides guidance to agents when working with code in this repository.

---

## Project

**VetRelay AI** — IBM SkillsBuild AI Experiential Learning Lab, Smart Healthcare / Life Sciences track.  
Veterinary clinical operations prototype built on FastAPI (Python 3.11), Pydantic v2, and Streamlit.  
No real PII or proprietary clinic data is used anywhere in this repository.

---

## VetRelay Coordinator — Agent Persona & Operating Directives

This section defines the system-level behaviour of the **VetRelay Coordinator**, the
IBM watsonx Orchestrate agent that consumes the `/api/*` endpoints.
Any LLM or coding agent implementing or extending the orchestrator must follow these rules exactly.

### Identity

> You are the **VetRelay Coordinator**, an enterprise agentic assistant designed to streamline
> veterinary intake and clinical appointment scheduling.  
> You adhere strictly to two guiding archetypes:
> **The Cognitive Load Reducer** and **The Human-AI Boundary Manager**.

### Step 1 — Intake Collection

Collect the following attributes before invoking any tool.  
If any required field is missing, ask **one focused clarifying question** — never a multi-part question.

| Field | Type | Required |
| --- | --- | --- |
| `owner_name` | string | ✅ |
| `pet_name` | string | ✅ |
| `species` | string (canine / feline / avian / reptile / exotic) | ✅ |
| `age_years` | float | ✅ |
| `reported_symptoms` | list[string] | ✅ |
| `duration_hours` | float | ✅ |
| `suspected_toxicity` | bool — True if owner reports chocolate, grapes, chemicals, plants, etc. | ✅ |

### Step 2 — Tool: `assessPetTriage` → `POST /api/assess`

Invoke `assessPetTriage` (operation ID: `assessAndBook`) with the full `PetIntakeInput` payload.  
Capture from the response:

- `triage.is_emergency` (bool)
- `triage.triage_level` (`CRITICAL_EMERGENCY` | `URGENT` | `ROUTINE`)
- `triage.severity_score` (int 1–5, 1 = most critical)
- `triage.soap_summary` (string — four SOAP sections)
- `booking.clinic_name`, `booking.address`, `booking.scheduled_slot`, `booking.instructions`

### Step 3 — Emergency Guardrails (Human-AI Boundary Manager)

**IF `triage.is_emergency` is `true`:**

1. **DO NOT** attempt routine scheduling, suggest waiting, or offer home-care advice.
2. Output the following emergency directive immediately — verbatim structure, filled with real values:

```text
EMERGENCY ALERT: [pet_name]'s symptoms require immediate veterinary attention.
Please transport them directly to [booking.clinic_name] at [booking.address].
[booking.instructions]
```

3. Then append the standard disclaimer (see § Ethics below).
4. Stop — do not invoke any further tools or offer additional advice.

The `booking.scheduled_slot` for emergencies will always be `"IMMEDIATE WALK-IN"`.  
The clinic will always be **Metro 24/7 Veterinary Emergency Hospital**.  
This routing is deterministic and cannot be changed by the LLM.

### Step 4 — Routine Care Routing (Invisible Coordinator)

**IF `triage.is_emergency` is `false`:**

Present the following to the user:

```text
📅 Appointment confirmed for [pet_name]:
   Clinic:       [booking.clinic_name]
   Address:      [booking.address]
   Scheduled:    [booking.scheduled_slot]
   Instructions: [booking.instructions]

📋 Clinical Summary (SOAP):
   [triage.soap_summary]
```

Then append the standard disclaimer.

### Step 5 — Ethics & Hard Boundaries

- You are a **triage and routing coordinator**, not a veterinarian.
- **Never** provide definitive diagnoses, drug dosages, or home-treatment instructions.
- **Never** lower an `is_emergency=true` result — the deterministic gate in
  [`backend/agents/triage_agent.py`](backend/agents/triage_agent.py) cannot be overridden.
- Always append this disclaimer to every response:

> *Triage recommendations are AI-assisted estimates.  
> If your pet deteriorates, seek immediate emergency veterinary care.*

---

## Agentic Archetypes (Implementation)

| # | Name | File | Contract |
| --- | --- | --- | --- |
| 1 | **Cognitive Load Reducer** | [`backend/agents/soap_agent.py`](backend/agents/soap_agent.py) | Converts owner narratives → structured SOAP sections. Never invent clinical facts. |
| 2 | **Invisible Coordinator** | [`backend/agents/booking_agent.py`](backend/agents/booking_agent.py) | Routes intake to community / mobile / 24-7 clinics. Emergency always routes to `METRO_24_7`. Capacity read from `mock_data/vet_clinics.json` per-request. |
| 3 | **Human-AI Boundary Manager** | [`backend/agents/triage_agent.py`](backend/agents/triage_agent.py) | Deterministic red-flag gate (toxins + critical symptoms). `is_emergency=True` blocks all non-emergency flows. Gate fires before any LLM call and cannot be overridden. |

---

## API Endpoints (watsonx Orchestrate tool surface)

| Operation ID | Method + Path | Purpose |
| --- | --- | --- |
| `assessAndBook` | `POST /api/assess` | **Primary tool** — single round-trip: triage + booking |
| `triagePetIntake` | `POST /api/triage` | Triage only (returns `TriageResult`) |
| `routeBooking` | `POST /api/route-booking` | Booking only (requires pre-computed `TriageResult`) |

All endpoints accept `PetIntakeInput` (defined in [`backend/schemas_api.py`](backend/schemas_api.py))
and return OpenAPI 3.0.3-compliant JSON.

---

## Commands

```bash
make install              # pip install -e ".[dev]"
make dev                  # uvicorn backend.main:app --reload --port 8000
make lint                 # ruff check + ruff format --check
make lint-fix             # ruff check --fix + ruff format
make typecheck            # mypy backend/
make test                 # pytest tests/ -v  (35 tests)
make test-one T=<name>    # single test by name substring
make run-frontend         # streamlit run frontend/app.py --server.port 8501  ← primary UI
make run-frontend-mvp1    # legacy owner intake only, port 8502
make run-frontend-mvp2    # legacy clinic console only, port 8503
```

---

## Directory Layout

```text
backend/
  main.py                 # FastAPI app factory; /api/* + legacy /soap|triage|routing routers
  schemas_api.py          # Canonical /api/* models: PetIntakeInput, TriageResult, BookingResult
  schemas/                # Legacy per-archetype Pydantic models (re-exported via __init__.py)
  agents/
    triage_agent.py       # Archetype 3 — deterministic gate + SOAP brief generation
    booking_agent.py      # Archetype 2 — emergency fast-path + species-aware routing
    soap_agent.py         # Archetype 1 — SOAP stub (replace body with LLM call)
    routing_agent.py      # Legacy routing agent (clinic_capacity.json)
  routers/                # Legacy routers retained for backward-compat tests
  telemetry.py            # JSON formatter + HTTP trace middleware (IBM Cloud Logs compatible)
frontend/
  app.py                  # Unified Streamlit UI — sidebar toggle MVP1/MVP2  ← primary entry
  mvp1_client.py          # Legacy owner intake Streamlit app
  mvp2_clinic_console.py  # Legacy clinic console Streamlit app
mock_data/
  vet_clinics.json        # Synthetic clinic fixtures (6 records incl. METRO_24_7 anchor)
  clinic_capacity.json    # Legacy capacity fixtures (used by routing_agent.py)
bob_sessions/             # Bob IDE task screenshots for lab submission evidence
tests/
  test_vetrelay.py        # Comprehensive agentic behaviour tests (13 tests — primary suite)
  test_api_triage.py      # /api/triage endpoint tests
  test_api_booking.py     # /api/route-booking + /api/assess endpoint tests
  test_soap.py            # Legacy /soap/summarise tests
  test_triage.py          # Legacy /triage/evaluate tests
  test_routing.py         # Legacy /routing/find-clinic tests
```

---

## Critical Non-Obvious Rules

1. **Escalation gate is deterministic — LLM cannot lower it.**  
   `_CRITICAL_TOXINS` and `_CRITICAL_SYMPTOMS` frozensets in
   [`backend/agents/triage_agent.py`](backend/agents/triage_agent.py) use
   case-insensitive substring matching. A symptom string of `"ate dark chocolate bar"`
   matches `"chocolate"` and always produces `is_emergency=True`, `severity_score=1`.

2. **`/api/assess` is the canonical single-call tool for watsonx Orchestrate.**  
   `/api/route-booking` requires a nested `{"intake": ..., "triage": ...}` body shape
   (two Pydantic models). Frontends and orchestrators should use `/api/assess` instead.

3. **Routing reads `vet_clinics.json` from disk on every call — intentional.**  
   [`backend/agents/booking_agent.py`](backend/agents/booking_agent.py) calls
   `json.load()` per request. Do not add caching — capacity edits take effect without restart.

4. **`METRO_24_7` entry must never be removed from `mock_data/vet_clinics.json`.**  
   The booking agent raises `RuntimeError` at runtime if the `METRO_24_7` clinic ID is absent.

5. **`schemas_api.py` vs `schemas/` package — import via `backend.schemas`.**  
   `backend/schemas/__init__.py` re-exports all models (including those from `schemas_api.py`)
   so `from backend.schemas import PetIntakeInput` always resolves. Never import directly
   from `backend.schemas_api` in new code.

6. **Frontend uses `st.stop()` on `is_emergency=True`.**  
   [`frontend/app.py`](frontend/app.py) calls `st.stop()` immediately after rendering
   the emergency banner — this hard-blocks all further Streamlit rendering for that run.

7. **`pytest-asyncio` in `auto` mode — no event-loop fixtures needed.**  
   `asyncio_mode = "auto"` in `pyproject.toml`. All async tests need only `@pytest.mark.asyncio`.

8. **All log lines must use `event=<name> key=val` structured pairs — no PII in values.**  
   The JSON formatter in [`backend/telemetry.py`](backend/telemetry.py) emits IBM Cloud
   Logs-compatible NDJSON. Never log `owner_name`, `pet_name`, or symptom text.

---

## Code Style (enforced by `ruff`)

- Line length: **100** · Target: `python 3.11`
- Import order: stdlib → third-party → `backend` (first-party, declared in `pyproject.toml`)
- Rules: `E, F, I, UP, B, SIM, ARG` · `mypy --strict` on `backend/`
- Pydantic v2: use `float | None` (not `Optional[float]`); `StrEnum` for all categoricals

---

## No-PII Contract

- `mock_data/` contains only synthetic fixtures. Phone numbers must match `^555-\d{4}$`.
- Owner name and pet name are processed in-memory only — never logged or persisted.
- All log lines use structured `key=val` pairs; symptom text and owner fields are excluded.
- `test_synthetic_data_integrity_no_pii` in
  [`tests/test_vetrelay.py`](tests/test_vetrelay.py) enforces this with regex checks on
  every commit.
