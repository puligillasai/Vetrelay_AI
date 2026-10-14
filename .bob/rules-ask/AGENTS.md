# AGENTS.md — Ask Mode

This file provides guidance to agents when working with code in this repository.

## Non-Obvious Documentation Context

- **`backend/agents/`** contains stubs, not finished LLM agents. All three files have `# TODO` markers — the logic is intentionally incomplete for lab extension.
- **`backend/telemetry.py`** is a logging stub. The name implies OpenTelemetry but it only sets up stdlib `logging` — replace with `opentelemetry-sdk` before production.
- **`frontend/mvp2_clinic_console.py`** has a non-functional `httpx.get` call (routing endpoint doesn't support GET) — MVP 2 is a placeholder shell, not a working dashboard.
- **`mock_data/clinic_capacity.json`** is the sole source of truth for routing in this prototype. There is no database.
- **`bob_sessions/`** is for IBM Bob IDE screenshots submitted as lab evidence — it is not a generated artifact directory.
- **Two Streamlit apps run on different ports**: MVP 1 on `:8501`, MVP 2 on `:8502`.
- **`CRITICAL_TOXINS`** in the triage agent is the canonical list of always-escalate substances — it is not configured externally and is not in `mock_data/`.
- The OpenAPI schema version is `3.0.3` (set in `FastAPI(openapi_version=...)`), not the default `3.1.0` — this matters for IBM API Connect compatibility.
