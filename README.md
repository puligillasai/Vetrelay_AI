# VetRelay AI — Deployment & Submission Guide

IBM SkillsBuild AI Experiential Learning Lab  
Smart Healthcare / Life Sciences Track

---

## What This Project Delivers

VetRelay AI implements three agentic archetypes from the IBM SkillsBuild lab spec,
wired together under a supervisor agent in IBM watsonx Orchestrate:

| Agent | Archetype | Primary Tool |
| --- | --- | --- |
| `soap_summariser` | Cognitive Load Reducer | `generate_soap_summary` |
| `triage_evaluator` | Human-AI Boundary Manager | `evaluate_pet_triage` |
| `clinic_router` | Invisible Coordinator | `find_available_clinic` |
| `front_desk_agent` | Invisible Coordinator (handoff) | `handoff_to_front_desk` |
| `vetrelay_coordinator` | Supervisor (all-in-one) | `assess_pet_triage` + collaborators |

---

## Directory Layout

```text
agents/
  vetrelay_coordinator.agent.yaml   ← Supervisor agent (primary submission artifact)
  soap_agent.agent.yaml             ← Archetype 1 sub-agent
  triage_agent.agent.yaml           ← Archetype 3 sub-agent
  routing_agent.agent.yaml          ← Archetype 2 sub-agent
  front_desk_agent.agent.yaml       ← Archetype 2 sub-agent (handoff + queue)
tools/
  assess_pet_triage.py              ← Primary tool (triage + booking in one call)
  generate_soap_summary.py          ← SOAP note generation tool
  evaluate_triage.py                ← Standalone triage evaluation tool
  find_clinic.py                    ← Clinic routing tool
  handoff_to_front_desk.py          ← Front-desk queue persistence tool
connections/
  vetrelay_openapi.json             ← Full OpenAPI 3.0.3 spec (for UI import)
backend/
  main.py                           ← FastAPI app; /api/* + legacy routers
  agents/                           ← Triage, booking, SOAP agent logic
  services/
    cloudant_db.py                  ← IBM Cloudant persistence service
    watsonx_ai.py                   ← IBM watsonx.ai Granite inference service
    watson_tts.py                   ← IBM Watson Text-to-Speech service
  schemas/                          ← Pydantic v2 models
  routers/                          ← Legacy sub-routers (backward-compat)
  telemetry.py                      ← JSON structured logging (IBM Cloud Logs)
frontend/
  app.py                            ← Unified Streamlit UI (MVP 1 + MVP 2 toggle)
mock_data/
  vet_clinics.json                  ← Synthetic clinic fixtures (6 records)
  clinic_capacity.json              ← Legacy capacity fixtures
tests/                              ← 45 tests across 6 test files
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your credentials before running:

```bash
cp .env.example .env
```

| Variable | Required | Description |
| --- | --- | --- |
| `WATSONX_API_KEY` | For LLM | IBM Cloud IAM API key for watsonx.ai |
| `WATSONX_URL` | For LLM | Regional endpoint, e.g. `https://us-south.ml.cloud.ibm.com` |
| `WATSONX_PROJECT_ID` | For LLM | watsonx.ai project GUID |
| `CLOUDANT_APIKEY` | For persistence | IBM Cloud IAM API key for Cloudant |
| `CLOUDANT_URL` | For persistence | e.g. `https://<instance>.cloudantnosqldb.appdomain.cloud` |
| `CLOUDANT_DB_NAME` | Optional | Database name (default: `vetrelay_intakes`) |
| `WATSON_STT_APIKEY` | For voice intake | IBM Watson Speech-to-Text API key |
| `WATSON_STT_URL` | For voice intake | Watson STT regional endpoint |
| `WATSON_TTS_APIKEY` | For voice output | IBM Watson Text-to-Speech API key |
| `WATSON_TTS_URL` | For voice output | Watson TTS regional endpoint |
| `VETRELAY_API_URL` | For tools | Backend URL (default: `http://localhost:8000`) |

> All IBM credentials are optional for local development — the app and tools fall
> back gracefully when any credential is absent.

---

## Phase 0 — Prerequisites

- [ ] Python 3.11+
- [ ] IBM watsonx Orchestrate account
- [ ] IBM Cloud API key → [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys)
- [ ] Your Orchestrate instance URL
  (format: `https://your-instance.orchestrate.cloud.ibm.com`)

---

## Phase 1 — Install & Set Up Locally

```bash
# 1. Install project dependencies
make install

# 2. Run all tests — must be 45/45 green before continuing
make test

# 3. Install the watsonx Orchestrate ADK
pip install ibm-watsonx-orchestrate

# 4. Verify ADK installed
orchestrate --version
```

---

## Phase 2 — Connect the ADK to Your Orchestrate Instance

```bash
# Add and activate your environment (run once)
orchestrate env add \
  --name vetrelay-env \
  --url https://YOUR_INSTANCE.orchestrate.cloud.ibm.com \
  --api-key YOUR_IBM_CLOUD_API_KEY

orchestrate env activate vetrelay-env

# Confirm the connection works
orchestrate tools list
```

---

## Phase 3 — Start the Backend

The tools call your FastAPI backend. Start it in a **separate terminal** and
leave it running for all import steps:

```bash
# Terminal 1 — keep this running
make dev

# Verify it is alive
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}

# Verify the full API surface is live
curl http://localhost:8000/docs
```

> **Production note**: For a real deployment, publish the backend to a public
> URL and set `export VETRELAY_API_URL=https://your-deployed-backend.com`
> before running the import commands below.

---

## Phase 4 — Import All Tools (Terminal 2)

Import tools in order. Each must succeed before importing agents.

```bash
# Tool 1 — Primary: triage + booking in one call (used by supervisor)
orchestrate tools import -k python -f tools/assess_pet_triage.py

# Tool 2 — Archetype 1: SOAP note generation
orchestrate tools import -k python -f tools/generate_soap_summary.py

# Tool 3 — Archetype 3: standalone triage evaluation
orchestrate tools import -k python -f tools/evaluate_triage.py

# Tool 4 — Archetype 2: clinic routing
orchestrate tools import -k python -f tools/find_clinic.py

# Tool 5 — Archetype 2: front-desk handoff (persist completed encounter)
orchestrate tools import -k python -f tools/handoff_to_front_desk.py

# Verify all 5 tools are registered
orchestrate tools list
# Expected output includes:
#   assess_pet_triage
#   generate_soap_summary
#   evaluate_pet_triage
#   find_available_clinic
#   handoff_to_front_desk
```

---

## Phase 5 — Import All Agents

Import sub-agents first, then the supervisor coordinator last.

```bash
# Sub-agent 1 — Archetype 1: Cognitive Load Reducer
orchestrate agents import -f agents/soap_agent.agent.yaml

# Sub-agent 2 — Archetype 3: Human-AI Boundary Manager
orchestrate agents import -f agents/triage_agent.agent.yaml

# Sub-agent 3 — Archetype 2: Invisible Coordinator (routing)
orchestrate agents import -f agents/routing_agent.agent.yaml

# Sub-agent 4 — Archetype 2: Invisible Coordinator (front-desk handoff)
orchestrate agents import -f agents/front_desk_agent.agent.yaml

# Supervisor — imports last (references the sub-agents as collaborators)
orchestrate agents import -f agents/vetrelay_coordinator.agent.yaml

# Verify all 5 agents are registered
orchestrate agents list
# Expected output includes:
#   soap_summariser
#   triage_evaluator
#   clinic_router
#   front_desk_agent
#   vetrelay_coordinator
```

---

## Phase 6 — Test in Chat

```bash
orchestrate chat start
# Select: vetrelay_coordinator
```

### Test Case 1 — Emergency (must route to Metro 24/7)

```
Hi, my dog Buddy is a 2-year-old male canine. He ate dark chocolate about
an hour ago. I'm John Smith. He seems hyperactive and is panting heavily.
```

**Expected response:**
- `triage_level: CRITICAL_EMERGENCY`
- `is_emergency: true`
- Emergency alert directing to Metro 24/7 Veterinary Emergency Hospital
- Slot: `IMMEDIATE WALK-IN`
- Disclaimer appended: *Triage recommendations are AI-assisted estimates…*

### Test Case 2 — Urgent (must route to nearest available clinic)

```
My cat Luna is 4 years old, feline. She has been vomiting and not eating
for about 12 hours. I'm Jane Doe. No known toxin exposure.
```

**Expected response:**
- `triage_level: URGENT`
- `is_emergency: false`
- Appointment at a nearby species-compatible clinic with a date/time slot

### Test Case 3 — Routine checkup

```
My rabbit Pepper is 3 years old, exotic species. He seems fine but is due
for a wellness check. Owner is Alex Kim. Duration about 0 hours, no symptoms.
```

**Expected response:**
- `triage_level: ROUTINE`
- `is_emergency: false`
- Appointment at All Species Veterinary Centre or similar

---

## Phase 7 — View in the Orchestrate UI

1. Log in to your Orchestrate instance in the browser
2. Click **AI Agents** in the left nav
3. You should see all 5 agents: `vetrelay_coordinator`, `soap_summariser`,
   `triage_evaluator`, `clinic_router`, `front_desk_agent`
4. Click **vetrelay_coordinator** → **Test** to chat with it in the UI
5. Take a screenshot of the agent list and a successful test conversation
   → save to `bob_sessions/` for lab submission evidence

---

## Phase 8 — Run the Streamlit Frontend (Optional Demo)

While the backend is running (`make dev`), open a second terminal:

```bash
# Unified UI — MVP 1 (owner intake) + MVP 2 (clinic console) with sidebar toggle
make run-frontend
# Opens at http://localhost:8501
```

Features:
- **MVP 1 — Pet Owner Intake**: submit symptoms, run triage + booking, hear the
  result spoken aloud via IBM Watson TTS (if configured)
- **MVP 2 — Clinic Front-Desk Console**: live queue of recent encounters pulled
  from Cloudant, sortable by triage level

> Legacy single-view apps are still available:
> `make run-frontend-mvp1` (port 8502) and `make run-frontend-mvp2` (port 8503)

---

## Submission Checklist

Before submitting, verify:

- [ ] `make test` → 45/45 passed
- [ ] `make lint` → all checks passed
- [ ] `make typecheck` → no issues
- [ ] All 5 tools imported: `orchestrate tools list`
- [ ] All 5 agents imported: `orchestrate agents list`
- [ ] Emergency test case correctly returns `CRITICAL_EMERGENCY` + Metro 24/7
- [ ] Routine test case returns `ROUTINE` + a dated appointment slot
- [ ] Screenshot of agent list saved to `bob_sessions/`
- [ ] Screenshot of emergency test conversation saved to `bob_sessions/`

---

## Quick-Reference Commands

```bash
# Run tests
make test

# Run a single test by substring
make test-one T=test_critical_toxin

# Lint and format
make lint
make lint-fix

# Type check
make typecheck

# Start backend
make dev

# Start Streamlit UI
make run-frontend

# Import everything (after ADK setup)
orchestrate tools import -k python -f tools/assess_pet_triage.py
orchestrate tools import -k python -f tools/generate_soap_summary.py
orchestrate tools import -k python -f tools/evaluate_triage.py
orchestrate tools import -k python -f tools/find_clinic.py
orchestrate tools import -k python -f tools/handoff_to_front_desk.py
orchestrate agents import -f agents/soap_agent.agent.yaml
orchestrate agents import -f agents/triage_agent.agent.yaml
orchestrate agents import -f agents/routing_agent.agent.yaml
orchestrate agents import -f agents/front_desk_agent.agent.yaml
orchestrate agents import -f agents/vetrelay_coordinator.agent.yaml

# Chat
orchestrate chat start

# Check what is registered
orchestrate tools list
orchestrate agents list
```

---

## No-PII Contract

This project uses only synthetic data. Phone numbers match `^555-\d{4}$`.
Owner names and pet names are processed in-memory only and never logged
or persisted. The `test_synthetic_data_integrity_no_pii` test enforces this
on every commit.
