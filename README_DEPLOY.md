# VetRelay AI — Deployment & Submission Guide

IBM SkillsBuild AI Experiential Learning Lab  
Smart Healthcare / Life Sciences Track

---

## What This Project Delivers

VetRelay AI implements three agentic archetypes from the IBM SkillsBuild lab spec,
wired together under a single supervisor agent in IBM watsonx Orchestrate:

| Agent | Archetype | Tool |
| --- | --- | --- |
| `soap_summariser` | Cognitive Load Reducer | `generate_soap_summary` |
| `triage_evaluator` | Human-AI Boundary Manager | `evaluate_pet_triage` |
| `clinic_router` | Invisible Coordinator | `find_available_clinic` |
| `vetrelay_coordinator` | Supervisor (all-in-one) | `assess_pet_triage` + collaborators |

---

## Directory Layout

```text
agents/
  vetrelay_coordinator.agent.yaml   ← Supervisor agent (primary submission artifact)
  soap_agent.agent.yaml             ← Archetype 1 sub-agent
  triage_agent.agent.yaml           ← Archetype 3 sub-agent
  routing_agent.agent.yaml          ← Archetype 2 sub-agent
tools/
  assess_pet_triage.py              ← Primary tool (triage + booking in one call)
  generate_soap_summary.py          ← SOAP note generation tool
  evaluate_triage.py                ← Standalone triage evaluation tool
  find_clinic.py                    ← Clinic routing tool
connections/
  vetrelay_openapi.json             ← Full OpenAPI 3.0.3 spec (for UI import)
backend/                            ← FastAPI backend (the tool runtime)
frontend/                           ← Streamlit UI
```

---

## Phase 0 — Prerequisites

You need:

- [ ] Python 3.11+
- [ ] IBM watsonx Orchestrate account
- [ ] IBM Cloud API key → [cloud.ibm.com/iam/apikeys](https://cloud.ibm.com/iam/apikeys)
- [ ] Your Orchestrate instance URL
  (format: `https://your-instance.orchestrate.cloud.ibm.com`)

---

## Phase 1 — Install & Set Up Locally

```bash
# 1. Install project dependencies
cd /Users/saisumanthpuligilla/Documents/Vetrelay_AI
make install

# 2. Run all tests — must be 35/35 green before continuing
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
cd /Users/saisumanthpuligilla/Documents/Vetrelay_AI
make dev

# Verify it is alive
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}
```

> **Production note**: For a real deployment, publish the backend to a public
> URL and set `export VETRELAY_API_URL=https://your-deployed-backend.com`
> before running the import commands below.

---

## Phase 4 — Import All Tools (Terminal 2)

Import tools in order. Each must succeed before importing agents.

```bash
cd /Users/saisumanthpuligilla/Documents/Vetrelay_AI

# Tool 1 — Primary: triage + booking in one call (used by supervisor)
orchestrate tools import -k python -f tools/assess_pet_triage.py

# Tool 2 — Archetype 1: SOAP note generation
orchestrate tools import -k python -f tools/generate_soap_summary.py

# Tool 3 — Archetype 3: standalone triage evaluation
orchestrate tools import -k python -f tools/evaluate_triage.py

# Tool 4 — Archetype 2: clinic routing
orchestrate tools import -k python -f tools/find_clinic.py

# Verify all 4 tools are registered
orchestrate tools list
# Expected output includes:
#   assess_pet_triage
#   generate_soap_summary
#   evaluate_pet_triage
#   find_available_clinic
```

---

## Phase 5 — Import All Agents

Import sub-agents first, then the supervisor coordinator last.

```bash
cd /Users/saisumanthpuligilla/Documents/Vetrelay_AI

# Sub-agent 1 — Archetype 1: Cognitive Load Reducer
orchestrate agents import -f agents/soap_agent.agent.yaml

# Sub-agent 2 — Archetype 3: Human-AI Boundary Manager
orchestrate agents import -f agents/triage_agent.agent.yaml

# Sub-agent 3 — Archetype 2: Invisible Coordinator
orchestrate agents import -f agents/routing_agent.agent.yaml

# Supervisor — imports last (references the 3 sub-agents as collaborators)
orchestrate agents import -f agents/vetrelay_coordinator.agent.yaml

# Verify all 4 agents are registered
orchestrate agents list
# Expected output includes:
#   soap_summariser
#   triage_evaluator
#   clinic_router
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
3. You should see all 4 agents: `vetrelay_coordinator`, `soap_summariser`,
   `triage_evaluator`, `clinic_router`
4. Click **vetrelay_coordinator** → **Test** to chat with it in the UI
5. Take a screenshot of the agent list and a successful test conversation
   → save to `bob_sessions/` for lab submission evidence

---

## Phase 8 — Run the Streamlit Frontend (Optional Demo)

While the backend is running, open a second terminal:

```bash
# Terminal 2
cd /Users/saisumanthpuligilla/Documents/Vetrelay_AI
make run-frontend
# Opens at http://localhost:8501
```

The Streamlit UI is a standalone demo that calls the FastAPI backend directly.
It is separate from the Orchestrate agent but demonstrates the same triage
and booking logic visually.

---

## Submission Checklist

Before submitting, verify:

- [ ] `make test` → 35/35 passed
- [ ] `make lint` → all checks passed
- [ ] `make typecheck` → no issues
- [ ] All 4 tools imported: `orchestrate tools list`
- [ ] All 4 agents imported: `orchestrate agents list`
- [ ] Emergency test case correctly returns `CRITICAL_EMERGENCY` + Metro 24/7
- [ ] Routine test case returns `ROUTINE` + a dated appointment slot
- [ ] Screenshot of agent list saved to `bob_sessions/`
- [ ] Screenshot of emergency test conversation saved to `bob_sessions/`

---

## Quick-Reference Commands

```bash
# Run tests
make test

# Start backend
make dev

# Start Streamlit UI
make run-frontend

# Import everything (after ADK setup)
orchestrate tools import -k python -f tools/assess_pet_triage.py
orchestrate tools import -k python -f tools/generate_soap_summary.py
orchestrate tools import -k python -f tools/evaluate_triage.py
orchestrate tools import -k python -f tools/find_clinic.py
orchestrate agents import -f agents/soap_agent.agent.yaml
orchestrate agents import -f agents/triage_agent.agent.yaml
orchestrate agents import -f agents/routing_agent.agent.yaml
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
or persisted. The `test_synthetic_data_integrity_no_pii` test enforces this.
