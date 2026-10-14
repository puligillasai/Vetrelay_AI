# AGENTS.md — Agent (Coding) Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Coding Rules

### Archetype contracts (must not be violated)
- `escalation_required=True` from `/triage/evaluate` **must** trigger `st.stop()` in any Streamlit consumer — see [`frontend/mvp1_client.py`](../../frontend/mvp1_client.py). Never add a bypass.
- `CRITICAL_TOXINS` in [`backend/agents/triage_agent.py`](../../backend/agents/triage_agent.py) is the deterministic safety gate. LLM calls added later must not be able to return `escalation_required=False` when the gate fires.
- Routing fallback order (`preferred → emergency_24_7 → any`) in [`backend/agents/routing_agent.py`](../../backend/agents/routing_agent.py) is clinically intentional — do not reorder.

### LLM integration points
- All three agent stubs have `# TODO: integrate LLM provider` comments. Replace the stub return with an LLM call but **keep the deterministic triage gate above the LLM call**.
- Use `httpx.AsyncClient` (already a dependency) for async LLM HTTP calls — do not add `aiohttp`.

### Adding a new archetype
1. Create `backend/agents/<name>_agent.py` + `backend/schemas/<name>.py` + `backend/routers/<name>.py`.
2. Mount the router in [`backend/main.py`](../../backend/main.py) with a prefix and tag.
3. Add a corresponding `tests/test_<name>.py` using `AsyncClient(transport=ASGITransport(app=app))`.

### Test pattern
- Tests use `httpx.AsyncClient` with `ASGITransport` — no running server needed.
- Single test: `make test-one T=<substring>` (e.g. `make test-one T=test_critical_toxin`).
- `asyncio_mode = "auto"` is set; do not add `@pytest.fixture(scope="session")` event loop fixtures.

### Pydantic v2 specifics
- Use `float | None` not `Optional[float]`.
- `StrEnum` for all categorical fields (e.g. `SeverityLevel`, `ClinicType`).
- `Field(description=...)` is required on any field with clinical safety implications.

### Mock data
- `mock_data/clinic_capacity.json` is loaded per-request by design. Editing it changes routing behaviour immediately without restart.
- Never replace `mock_data/` reads with a live database connection in this prototype.

### Logging
- All log lines: `logger.info("event=<name> key=val")` — structured key=value, no f-strings with variable data.
