"""IBM Watson Text-to-Speech service — speak triage/booking output aloud.

Provides a single public function ``speak()`` that returns raw WAV audio bytes
for a given text string.  Callers (Streamlit frontend) embed the bytes into an
HTML <audio> element for immediate autoplay.

Falls back silently (returns None) when:
  - ibm-watson is not installed
  - WATSON_TTS_APIKEY / WATSON_TTS_URL env vars are absent
  - The TTS call fails for any reason

Environment variables:
    WATSON_TTS_APIKEY   — IBM Cloud IAM API key for Watson TTS
    WATSON_TTS_URL      — Regional endpoint,
                          e.g. https://api.us-south.text-to-speech.watson.cloud.ibm.com
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.telemetry import get_logger

log: logging.Logger = get_logger("vetrelay.watson_tts")

try:
    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator as _IAMAuthenticator
    from ibm_watson import TextToSpeechV1 as _TextToSpeechV1

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    log.warning("event=watson_tts_sdk_missing ibm-watson package not installed")

# Watson TTS voice — en-US Allison Neural gives clear, natural speech.
_VOICE = "en-US_AllisonV3Voice"
_ACCEPT = "audio/wav"


def _get_client() -> Any:
    """Return an authenticated TextToSpeechV1 client or None."""
    if not _SDK_AVAILABLE:
        return None
    apikey = os.getenv("WATSON_TTS_APIKEY", "")
    url = os.getenv("WATSON_TTS_URL", "")
    if not apikey or not url:
        log.debug("event=watson_tts_skipped reason=missing_credentials")
        return None
    try:
        auth = _IAMAuthenticator(apikey)
        client = _TextToSpeechV1(authenticator=auth)
        client.set_service_url(url)
        return client
    except Exception as exc:
        log.warning("event=watson_tts_client_failed error=%s", str(exc))
        return None


def speak(text: str) -> bytes | None:
    """Convert *text* to WAV audio bytes via IBM Watson TTS.

    Args:
        text: The text to synthesise.  Keep under ~500 characters for
              low-latency response.

    Returns:
        Raw WAV bytes ready to embed in an HTML <audio> element, or
        None if TTS is unavailable or fails.
    """
    if not text or not text.strip():
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        response = client.synthesize(
            text=text[:1000],  # hard cap to avoid runaway payloads
            voice=_VOICE,
            accept=_ACCEPT,
        ).get_result()
        audio: bytes = response.content
        log.info("event=watson_tts_synthesised chars=%d bytes=%d", len(text), len(audio))
        return audio
    except Exception as exc:
        log.warning("event=watson_tts_synthesise_failed error=%s", str(exc))
        return None


def triage_speech(pet_name: str, triage_level: str, action: str) -> bytes | None:
    """Build and synthesise an urgent triage direction for *pet_name*.

    Args:
        pet_name:      The pet's name.
        triage_level:  e.g. CRITICAL_EMERGENCY, URGENT, ROUTINE.
        action:        The action_required string from TriageResult.

    Returns:
        WAV bytes or None.
    """
    level_phrase = {
        "CRITICAL_EMERGENCY": "This is a critical emergency.",
        "URGENT": "This case is urgent.",
        "ROUTINE": "This is a routine case.",
    }.get(triage_level, "")
    text = f"Triage result for {pet_name}. {level_phrase} {action}"
    return speak(text)


def booking_speech(pet_name: str, clinic_name: str, slot: str, instructions: str) -> bytes | None:
    """Build and synthesise the booking confirmation for *pet_name*.

    Args:
        pet_name:     The pet's name.
        clinic_name:  Assigned clinic name.
        slot:         Scheduled slot string (e.g. "IMMEDIATE WALK-IN").
        instructions: Booking instructions text.

    Returns:
        WAV bytes or None.
    """
    if slot == "IMMEDIATE WALK-IN":
        text = (
            f"Emergency booking for {pet_name}. "
            f"Please proceed immediately to {clinic_name}. "
            f"{instructions}"
        )
    else:
        text = (
            f"Appointment confirmed for {pet_name} at {clinic_name}, "
            f"scheduled for {slot}. {instructions}"
        )
    return speak(text[:600])
