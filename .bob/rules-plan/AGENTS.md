# AGENTS.md — Plan Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Architectural Constraints

### Safety-critical coupling
- The triage deterministic gate (`CRITICAL_TOXINS`) and the Streamlit `st.stop()` call form a **cross-layer safety contract**. Any architectural change that decouples the API from the Streamlit UI (e.g. adding a message queue) must reproduce the `st.stop()` / block-non-emergency-flows guarantee in the new consumer.

### Stateless agents — required
- All three agent modules (`soap_agent`, `triage_agent`, `routing_agent`) must remain stateless. They are called directly from FastAPI route handlers with no dependency injection. Introducing class instances with state will break the single-worker uvicorn assumptions.

### Routing fallback is forward-only
- Routing fallback logic is not configurable at runtime. Changing the fallback order requires a code change and a new test — not a config value. This is intentional to prevent misconfiguration in a clinical context.

### Mock data is the schema contract
- `mock_data/clinic_capacity.json` field names are the canonical schema for `ClinicMatch`. If fields are added/removed, `backend/schemas/routing.py` and the mock data must change together.

### No shared state between frontends
- MVP 1 (`mvp1_client.py`) and MVP 2 (`mvp2_clinic_console.py`) are independent Streamlit processes. They share no session state and communicate only through the FastAPI backend. Do not introduce shared in-memory state.

### LLM integration boundary
- LLM calls belong exclusively inside `backend/agents/`. Routers and schemas must remain LLM-agnostic. This keeps the OpenAPI contract stable regardless of which model provider is used.

### IBM SkillsBuild lab constraints
- No real PII permitted anywhere — `mock_data/`, test fixtures, and log lines must all use synthetic data.
- `bob_sessions/` screenshots are required lab deliverables — do not `.gitignore` this directory.
- OpenAPI version is pinned to `3.0.3` for IBM API Connect compatibility.
