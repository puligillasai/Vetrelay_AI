"""VetRelay AI — Unified Streamlit Frontend.

Sidebar toggle switches between:
  MVP 1 — Pet Owner Intake  (conversational form → /api/assess)
  MVP 2 — Clinic Console    (staff queue with SOAP notes + urgency ranking)

Calls POST /api/assess for MVP 1 (single round-trip: triage + booking).
MVP 2 simulates a live queue using session_state to accumulate submitted cases
so the console reflects every assessment made in the current browser session.

Voice-to-text (STT):
  Uses audio_recorder_streamlit to capture browser mic audio, then transcribes
  via IBM Watson Speech-to-Text.  Falls back gracefully if Watson is not configured.

Voice synthesis (TTS):
  After triage, speaks the urgency level + booking instructions aloud via
  IBM Watson Text-to-Speech.  Falls back silently if TTS is not configured.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Optional IBM Watson STT import (graceful degradation if not installed/configured)
# ---------------------------------------------------------------------------

try:
    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator as _IAMAuthenticator
    from ibm_watson import SpeechToTextV1

    _WATSON_APIKEY = os.getenv("WATSON_STT_APIKEY", "")
    _WATSON_URL = os.getenv("WATSON_STT_URL", "")
    _WATSON_AVAILABLE = bool(_WATSON_APIKEY and _WATSON_URL)
except ImportError:
    _WATSON_AVAILABLE = False

try:
    from audio_recorder_streamlit import audio_recorder as _audio_recorder

    _AUDIO_RECORDER_AVAILABLE = True
except ImportError:
    _AUDIO_RECORDER_AVAILABLE = False

# ---------------------------------------------------------------------------
# Optional Watson TTS — speak triage/booking results aloud
# ---------------------------------------------------------------------------

try:
    from backend.services.watson_tts import booking_speech as _booking_speech
    from backend.services.watson_tts import triage_speech as _triage_speech

    _TTS_AVAILABLE = True
except Exception:
    _TTS_AVAILABLE = False


def _play_audio(audio_bytes: bytes | None) -> None:
    """Embed WAV bytes as an autoplay audio element in Streamlit."""
    if not audio_bytes:
        return
    import base64

    b64 = base64.b64encode(audio_bytes).decode()
    st.markdown(
        f'<audio autoplay style="display:none">'
        f'<source src="data:audio/wav;base64,{b64}" type="audio/wav"></audio>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = os.getenv("VETRELAY_API_URL", "http://localhost:8000")
SPECIES_OPTIONS = ["canine", "feline", "avian", "reptile", "exotic", "other"]

TRIAGE_COLOURS = {
    "CRITICAL_EMERGENCY": "#b91c1c",  # red-700
    "URGENT": "#d97706",  # amber-600
    "ROUTINE": "#15803d",  # green-700
}

TRIAGE_ICONS = {
    "CRITICAL_EMERGENCY": "🚨",
    "URGENT": "⚠️",
    "ROUTINE": "✅",
}

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="VetRelay AI",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS — minimal, clean, responsive
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* Main card wrapper */
    .vr-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
    }
    /* Emergency banner */
    .vr-emergency {
        background: #fef2f2;
        border: 2px solid #b91c1c;
        border-radius: 10px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        color: #7f1d1d;
    }
    .vr-emergency h2 { color: #b91c1c; margin-top: 0; }
    /* Urgency badge */
    .vr-badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        color: #fff;
    }
    .badge-critical { background: #b91c1c; }
    .badge-urgent   { background: #d97706; }
    .badge-routine  { background: #15803d; }
    /* SOAP section */
    .soap-block {
        font-family: "SF Mono", "Fira Code", monospace;
        font-size: 0.82rem;
        background: #1e293b;
        color: #e2e8f0;
        border-radius: 8px;
        padding: 0.9rem 1rem;
        white-space: pre-wrap;
        line-height: 1.6;
    }
    /* Queue row */
    .queue-row {
        border-left: 4px solid #94a3b8;
        padding-left: 0.9rem;
        margin-bottom: 0.75rem;
    }
    .queue-row-critical { border-color: #b91c1c; }
    .queue-row-urgent   { border-color: #d97706; }
    .queue-row-routine  { border-color: #15803d; }
    /* Scheduling progress stepper */
    .vr-stepper {
        display: flex;
        align-items: flex-start;
        gap: 0;
        margin: 1rem 0 1.5rem;
        padding: 1rem 1.25rem;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
    }
    .vr-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 1;
        position: relative;
    }
    .vr-step:not(:last-child)::after {
        content: "";
        position: absolute;
        top: 14px;
        left: 50%;
        width: 100%;
        height: 2px;
        background: #e2e8f0;
        z-index: 0;
    }
    .vr-step.done::after  { background: #15803d; }
    .vr-step.active::after { background: #3b82d4; }
    .vr-step-circle {
        width: 28px; height: 28px;
        border-radius: 50%;
        background: #e2e8f0;
        color: #94a3b8;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.78rem; font-weight: 700;
        position: relative; z-index: 1;
    }
    .vr-step.done  .vr-step-circle { background: #15803d; color: #fff; }
    .vr-step.active .vr-step-circle { background: #3b82d4; color: #fff; }
    .vr-step-label {
        font-size: 0.7rem;
        color: #94a3b8;
        margin-top: 0.3rem;
        text-align: center;
        max-width: 80px;
        line-height: 1.3;
    }
    .vr-step.done  .vr-step-label { color: #15803d; }
    .vr-step.active .vr-step-label { color: #3b82d4; font-weight: 600; }
    /* Voice recorder hint */
    .vr-voice-hint {
        font-size: 0.78rem;
        color: #57606a;
        margin-bottom: 0.4rem;
    }
    /* Footer */
    .vr-footer {
        text-align: center;
        color: #94a3b8;
        font-size: 0.75rem;
        padding: 1.5rem 0 0.5rem;
        border-top: 1px solid #e2e8f0;
        margin-top: 2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

if "case_queue" not in st.session_state:
    # List[dict] — each entry is {"intake": {...}, "triage": {...}, "booking": {...}}
    st.session_state.case_queue: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _transcribe_audio(audio_bytes: bytes) -> str | None:
    """Transcribe audio bytes via IBM Watson Speech-to-Text.

    Returns the transcript string, or None if transcription failed.
    Only called when _WATSON_AVAILABLE is True.
    """
    try:
        authenticator = _IAMAuthenticator(_WATSON_APIKEY)
        stt = SpeechToTextV1(authenticator=authenticator)
        stt.set_service_url(_WATSON_URL)
        result = stt.recognize(
            audio=audio_bytes,
            content_type="audio/wav",
            model="en-US_BroadbandModel",
        ).get_result()
        alternatives = result.get("results", [{}])[0].get("alternatives", [{}])
        if alternatives:
            return alternatives[0].get("transcript", "").strip()
    except Exception as exc:
        st.warning(f"Voice transcription failed: {exc}")
    return None


def _post_assess(payload: dict) -> dict | None:
    """Call POST /api/assess and return the parsed response, or None on error."""
    try:
        resp = httpx.post(f"{API_BASE}/api/assess", json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except httpx.ConnectError:
        st.error(
            "⚠️ Cannot reach the VetRelay API at `http://localhost:8000`. "
            "Run `make dev` in a separate terminal first."
        )
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        st.error(f"API returned {exc.response.status_code}: {json.dumps(detail, indent=2)}")
    return None


def _format_slot(slot: str) -> str:
    if slot == "IMMEDIATE WALK-IN":
        return slot
    try:
        dt = datetime.fromisoformat(slot)
        return dt.strftime("%A, %d %b %Y at %I:%M %p")
    except ValueError:
        return slot


def _badge_class(level: str) -> str:
    return {
        "CRITICAL_EMERGENCY": "badge-critical",
        "URGENT": "badge-urgent",
        "ROUTINE": "badge-routine",
    }.get(level, "badge-routine")


def _row_class(level: str) -> str:
    return {
        "CRITICAL_EMERGENCY": "queue-row queue-row-critical",
        "URGENT": "queue-row queue-row-urgent",
        "ROUTINE": "queue-row queue-row-routine",
    }.get(level, "queue-row")


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/5/51/IBM_logo.svg",
        width=72,
    )
    st.title("VetRelay AI")
    st.caption("Smart Healthcare · Veterinary Clinical Ops")
    st.divider()

    view = st.radio(
        "Select view",
        options=["🐾  Pet Owner Intake", "🏥  Clinic Console"],
        index=0,
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Built with **IBM Bob IDE** & **watsonx Orchestrate**")

# ---------------------------------------------------------------------------
# MVP 1 — Pet Owner Intake
# ---------------------------------------------------------------------------

if view == "🐾  Pet Owner Intake":
    st.title("🐾 Pet Intake & Triage")
    st.markdown(
        "Tell us about your pet's condition and we'll assess urgency, "
        "generate a clinical summary, and find the right clinic for you."
    )
    st.divider()

    # ── Scheduling progress stepper (Step 1 active until form submitted) ────
    _result_ready = bool(st.session_state.get("last_result"))

    def _step_cls(step_n: int, active: int) -> str:  # noqa: E306
        if step_n < active:
            return "vr-step done"
        if step_n == active:
            return "vr-step active"
        return "vr-step"

    _active_step = 3 if _result_ready else 1
    st.markdown(
        f"""
        <div class="vr-stepper">
          <div class="{_step_cls(1, _active_step)}">
            <div class="vr-step-circle">{"✓" if _active_step > 1 else "1"}</div>
            <div class="vr-step-label">Intake &amp; Symptoms</div>
          </div>
          <div class="{_step_cls(2, _active_step)}">
            <div class="vr-step-circle">{"✓" if _active_step > 2 else "2"}</div>
            <div class="vr-step-label">Triage Assessment</div>
          </div>
          <div class="{_step_cls(3, _active_step)}">
            <div class="vr-step-circle">{"✓" if _active_step > 3 else "3"}</div>
            <div class="vr-step-label">Clinic Routing</div>
          </div>
          <div class="{_step_cls(4, _active_step)}">
            <div class="vr-step-circle">4</div>
            <div class="vr-step-label">Front-Desk Handoff</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Voice-to-text recorder (outside form — must be outside st.form) ─────
    _voice_transcript: str = st.session_state.get("voice_transcript", "")
    if _AUDIO_RECORDER_AVAILABLE:
        st.markdown(
            '<p class="vr-voice-hint">🎙️ <strong>Voice input:</strong> '
            "Click the mic to record your pet's symptoms — transcript will "
            "auto-fill the symptoms box below.</p>",
            unsafe_allow_html=True,
        )
        _audio_bytes = _audio_recorder(
            text="",
            recording_color="#b91c1c",
            neutral_color="#3b82d4",
            icon_size="2x",
            key="voice_recorder",
        )
        if _audio_bytes and len(_audio_bytes) > 1000:
            if _WATSON_AVAILABLE:
                with st.spinner("Transcribing audio via IBM Watson STT…"):
                    _transcript = _transcribe_audio(_audio_bytes)
                if _transcript:
                    st.session_state["voice_transcript"] = _transcript
                    st.success(f"Transcript: *{_transcript}*")
                    _voice_transcript = _transcript
            else:
                st.info(
                    "Watson STT not configured — set `WATSON_STT_APIKEY` and "
                    "`WATSON_STT_URL` in your `.env` to enable transcription. "
                    "You can still type symptoms manually below."
                )
    else:
        st.caption(
            "💡 Install `audio-recorder-streamlit` to enable voice input: "
            "`pip install audio-recorder-streamlit`"
        )

    with st.form("intake_form", clear_on_submit=False):
        col_a, col_b = st.columns(2)

        with col_a:
            owner_name = st.text_input(
                "Your name",
                placeholder="e.g. Jane Smith",
                help="Used only for appointment labelling.",
            )
            pet_name = st.text_input("Pet's name", placeholder="e.g. Buddy")
            species = st.selectbox("Species", SPECIES_OPTIONS)

        with col_b:
            age_years = st.number_input(
                "Approximate age (years)",
                min_value=0.0,
                max_value=40.0,
                step=0.5,
                value=None,
                placeholder="Optional",
            )
            duration_hours = st.number_input(
                "How long have symptoms been present? (hours)",
                min_value=0.0,
                step=0.5,
                value=None,
                placeholder="Optional",
            )
            suspected_toxicity = st.toggle(
                "⚠️ Possible toxic ingestion",
                value=False,
                help=(
                    "Turn on if your pet may have eaten something toxic "
                    "(e.g. chocolate, xylitol, household chemicals)."
                ),
            )

        symptoms_raw = st.text_area(
            "Describe the symptoms",
            value=_voice_transcript,
            placeholder=(
                "e.g. vomiting since this morning, not eating, trembling, pale gums…\n"
                "Separate multiple symptoms with commas or new lines."
            ),
            height=110,
        )

        submitted = st.form_submit_button("🔍 Assess & Find Clinic", width="stretch")

    # ── Form submission ──────────────────────────────────────────────────────

    if submitted:
        # Clear any prior voice transcript so it doesn't persist unexpectedly
        st.session_state.pop("voice_transcript", None)

        # Validation
        errors: list[str] = []
        if not owner_name.strip():
            errors.append("Please enter your name.")
        if not pet_name.strip():
            errors.append("Please enter your pet's name.")
        if not symptoms_raw.strip():
            errors.append("Please describe the symptoms.")

        if errors:
            for e in errors:
                st.error(e)
            st.stop()

        # Normalise symptoms: split on commas + newlines, strip whitespace, drop blanks
        import re

        tokens = [s.strip() for s in re.split(r"[,\n]+", symptoms_raw) if s.strip()]

        payload: dict[str, Any] = {
            "owner_name": owner_name.strip(),
            "pet_name": pet_name.strip(),
            "species": species,
            "age_years": float(age_years) if age_years is not None else None,
            "duration_hours": float(duration_hours) if duration_hours is not None else None,
            "reported_symptoms": tokens,
            "suspected_toxicity": suspected_toxicity,
        }

        # Steps 2 + 3: triage assessment → clinic routing
        step_status = st.status("Running triage assessment…", expanded=True)
        with step_status:
            st.write("Step 2 — Evaluating symptoms and triage level…")
            result = _post_assess(payload)
            if result is None:
                step_status.update(label="Assessment failed", state="error")
                st.stop()
            st.write("Step 3 — Routing to nearest compatible clinic…")
            step_status.update(label="Assessment complete — clinic assigned ✓", state="complete")

        st.session_state["last_result"] = result

        triage = result["triage"]
        booking = result["booking"]
        level: str = triage["triage_level"]
        icon = TRIAGE_ICONS.get(level, "")

        # ── Emergency path ───────────────────────────────────────────────────
        if triage["is_emergency"]:
            st.markdown(
                f"""
                <div class="vr-emergency">
                    <h2>{icon} EMERGENCY — Immediate Veterinary Care Required</h2>
                    <p style="font-size:1.05rem;">
                        <strong>{pet_name.strip()}</strong> requires urgent evaluation.
                        Do <strong>not</strong> wait for an appointment.
                    </p>
                    <hr style="border-color:#fca5a5; margin:0.75rem 0;">
                    <p style="margin:0;">
                        🏥 <strong>{booking["clinic_name"]}</strong><br>
                        📍 {booking["address"]}<br>
                        🕐 <strong>{booking["scheduled_slot"]}</strong>
                    </p>
                    <p style="margin:0.75rem 0 0;">{booking["instructions"]}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Recommended action:** {triage['action_required']}",
            )
            # TTS — speak emergency direction aloud
            if _TTS_AVAILABLE:
                _play_audio(_triage_speech(pet_name.strip(), level, triage["action_required"]))
                _play_audio(
                    _booking_speech(
                        pet_name.strip(),
                        booking["clinic_name"],
                        booking["scheduled_slot"],
                        booking["instructions"],
                    )
                )
            # Step 4: front-desk handoff (Cloudant persistence already done in /api/assess)
            st.success(
                "Step 4 — Clinical record sent to front-desk queue ✓",
                icon="🏥",
            )
            st.session_state.case_queue.insert(
                0,
                {
                    "pet_name": pet_name.strip(),
                    "species": species,
                    "intake": payload,
                    "triage": triage,
                    "booking": booking,
                    "submitted_at": datetime.now().strftime("%H:%M:%S"),
                },
            )
            st.markdown(
                '<div class="vr-footer">Built with IBM Bob IDE &amp; watsonx Orchestrate</div>',
                unsafe_allow_html=True,
            )
            st.stop()

        # ── Non-emergency path ───────────────────────────────────────────────
        badge_cls = _badge_class(level)
        st.markdown(
            f"""
            <div class="vr-card">
                <span class="vr-badge {badge_cls}">{icon} {level.replace("_", " ")}</span>
                &nbsp; Severity score: <strong>{triage["severity_score"]} / 5</strong>
                &nbsp;·&nbsp; Pet: <strong>{pet_name.strip()}</strong>
                ({species}, {f"{age_years} yr" if age_years else "age unknown"})
            </div>
            """,
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns([3, 2])

        with col1:
            st.subheader("📋 Clinical Summary (SOAP)")
            # Parse SOAP sections for structured display
            soap_raw: str = triage["soap_summary"]
            for label, key in [
                ("Subjective", "S:"),
                ("Objective", "O:"),
                ("Assessment", "A:"),
                ("Plan", "P:"),
            ]:
                if key in soap_raw:
                    start = soap_raw.index(key) + len(key)
                    # Find next section marker or end of string
                    next_markers = [
                        soap_raw.index(m)
                        for m in ["S:", "O:", "A:", "P:"]
                        if m != key and m in soap_raw and soap_raw.index(m) > start
                    ]
                    end = min(next_markers) if next_markers else len(soap_raw)
                    section_text = soap_raw[start:end].strip().strip(".")
                    with st.expander(f"**{label}**", expanded=True):
                        st.write(section_text)

        with col2:
            st.subheader("📅 Appointment")
            slot_display = _format_slot(booking["scheduled_slot"])
            st.markdown(
                f"""
                <div class="vr-card">
                    <p style="margin:0 0 0.4rem;">
                        🏥 <strong>{booking["clinic_name"]}</strong>
                    </p>
                    <p style="margin:0 0 0.4rem;">
                        📍 {booking["address"]}
                    </p>
                    <p style="margin:0 0 0.4rem;">
                        🕐 <strong>{slot_display}</strong>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.info(booking["instructions"])
            st.markdown(
                f"**Recommended action:** {triage['action_required']}",
            )
            # TTS — speak booking confirmation aloud
            if _TTS_AVAILABLE:
                _play_audio(_triage_speech(pet_name.strip(), level, triage["action_required"]))
                _play_audio(
                    _booking_speech(
                        pet_name.strip(),
                        booking["clinic_name"],
                        booking["scheduled_slot"],
                        booking["instructions"],
                    )
                )

        # Step 4: front-desk handoff confirmation
        st.success(
            "Step 4 — Clinical record sent to front-desk queue ✓",
            icon="🏥",
        )

        # Persist to queue
        st.session_state.case_queue.insert(
            0,
            {
                "pet_name": pet_name.strip(),
                "species": species,
                "intake": payload,
                "triage": triage,
                "booking": booking,
                "submitted_at": datetime.now().strftime("%H:%M:%S"),
            },
        )

    st.markdown(
        '<div class="vr-footer">Built with IBM Bob IDE &amp; watsonx Orchestrate</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# MVP 2 — Clinic Console
# ---------------------------------------------------------------------------

else:
    st.title("🏥 Clinic Console")
    st.markdown(
        "Live triage queue for clinic staff and nurses. "
        "Cases are sorted by urgency score (most critical first). "
        "Submit cases via the **Pet Owner Intake** view to populate the queue."
    )
    st.divider()

    # ── Real-time Cloudant sync ──────────────────────────────────────────────
    # Merge any records persisted to Cloudant (e.g. from a different browser
    # session or the watsonx Orchestrate agent) into the local session queue.
    try:
        from backend.services.cloudant_db import get_recent_records as _get_recent

        _cloudant_rows = _get_recent(limit=20)
        _existing_ids = {
            c.get("intake", {}).get("pet_name", "") + c.get("submitted_at", "")
            for c in st.session_state.case_queue
        }
        for _row in _cloudant_rows:
            _key = _row.get("pet_name", "") + _row.get("created_at", "")
            if _key not in _existing_ids and _row.get("triage_level"):
                # Reshape Cloudant flat record into the queue dict shape
                st.session_state.case_queue.append(
                    {
                        "pet_name": _row.get("pet_name", "Unknown"),
                        "species": _row.get("species", "unknown"),
                        "intake": {
                            "reported_symptoms": _row.get("reported_symptoms", []),
                            "species": _row.get("species", "unknown"),
                        },
                        "triage": {
                            "triage_level": _row.get("triage_level", "ROUTINE"),
                            "is_emergency": _row.get("is_emergency", False),
                            "severity_score": _row.get("severity_score", 5),
                            "soap_summary": _row.get("soap_brief", ""),
                            "action_required": _row.get("action_required", ""),
                        },
                        "booking": {
                            "clinic_name": _row.get("assigned_clinic", ""),
                            "address": _row.get("clinic_address", ""),
                            "scheduled_slot": _row.get("scheduled_slot", ""),
                            "instructions": _row.get("instructions", ""),
                        },
                        "submitted_at": _row.get("created_at", "")[:19],
                    }
                )
    except Exception:
        pass  # Cloudant unavailable — session queue still works

    queue: list[dict[str, Any]] = st.session_state.case_queue

    if not queue:
        st.info(
            "No active cases in this session. "
            "Switch to **Pet Owner Intake** and submit an assessment to see it here."
        )
    else:
        # Sort: CRITICAL_EMERGENCY first, then URGENT, then ROUTINE, then by severity_score asc
        _level_order = {"CRITICAL_EMERGENCY": 0, "URGENT": 1, "ROUTINE": 2}
        sorted_queue = sorted(
            queue,
            key=lambda c: (
                _level_order.get(c["triage"]["triage_level"], 9),
                c["triage"]["severity_score"],
            ),
        )

        # Summary metrics row
        n_critical = sum(1 for c in queue if c["triage"]["triage_level"] == "CRITICAL_EMERGENCY")
        n_urgent = sum(1 for c in queue if c["triage"]["triage_level"] == "URGENT")
        n_routine = sum(1 for c in queue if c["triage"]["triage_level"] == "ROUTINE")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Cases", len(queue))
        m2.metric("🚨 Critical", n_critical, delta_color="off")
        m3.metric("⚠️ Urgent", n_urgent, delta_color="off")
        m4.metric("✅ Routine", n_routine, delta_color="off")

        st.divider()

        # Optional filter
        filter_level = st.selectbox(
            "Filter by urgency",
            options=["All", "CRITICAL_EMERGENCY", "URGENT", "ROUTINE"],
            index=0,
        )
        if filter_level != "All":
            sorted_queue = [c for c in sorted_queue if c["triage"]["triage_level"] == filter_level]

        for idx, case in enumerate(sorted_queue):
            t = case["triage"]
            b = case["booking"]
            level = t["triage_level"]
            icon = TRIAGE_ICONS.get(level, "")
            badge_cls = _badge_class(level)
            row_cls = _row_class(level)
            slot_display = _format_slot(b["scheduled_slot"])

            with st.expander(
                f"{icon} [{case['submitted_at']}]  "
                f"{case['pet_name']} ({case['species']})  —  "
                f"{level.replace('_', ' ')}  "
                f"· Score {t['severity_score']}/5  "
                f"→ {b['clinic_name']}",
                expanded=(level == "CRITICAL_EMERGENCY"),
            ):
                col_left, col_right = st.columns([3, 2])

                with col_left:
                    st.markdown("**SOAP Brief**")
                    st.markdown(
                        f'<div class="soap-block">{t["soap_summary"]}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"**Action required:** {t['action_required']}",
                    )

                with col_right:
                    st.markdown("**Routing**")
                    st.markdown(
                        f"""
                        <div class="vr-card" style="padding:0.9rem 1rem;">
                            <p style="margin:0 0 0.3rem;">
                                <span class="vr-badge {badge_cls}">
                                    {icon} {level.replace("_", " ")}
                                </span>
                            </p>
                            <p style="margin:0.5rem 0 0.3rem;">
                                🏥 <strong>{b["clinic_name"]}</strong>
                            </p>
                            <p style="margin:0 0 0.3rem; font-size:0.85rem; color:#64748b;">
                                📍 {b["address"]}
                            </p>
                            <p style="margin:0; font-size:0.85rem;">
                                🕐 <strong>{slot_display}</strong>
                            </p>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(f"**Symptoms:** {', '.join(case['intake']['reported_symptoms'])}")
                    if case["intake"].get("suspected_toxicity"):
                        st.warning("⚠️ Toxic ingestion suspected")

            # Thin divider between rows (not after last)
            if idx < len(sorted_queue) - 1:
                st.markdown(
                    "<hr style='border:none; border-top:1px solid #e2e8f0; margin:0.2rem 0'>",
                    unsafe_allow_html=True,
                )

    st.markdown(
        '<div class="vr-footer">Built with IBM Bob IDE &amp; watsonx Orchestrate</div>',
        unsafe_allow_html=True,
    )
