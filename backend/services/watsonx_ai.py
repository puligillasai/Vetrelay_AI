"""IBM watsonx.ai Foundation Model service — Granite inference helper.

Wraps ibm-watsonx-ai ModelInference so any agent can call _generate()
without knowing SDK details.  Falls back gracefully when credentials are
absent (e.g. CI/unit tests).

Environment variables required:
    WATSONX_API_KEY      — IBM Cloud IAM API key
    WATSONX_URL          — Regional endpoint, e.g. https://us-south.ml.cloud.ibm.com
    WATSONX_PROJECT_ID   — watsonx.ai project GUID
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from backend.telemetry import get_logger

if TYPE_CHECKING:
    from ibm_watsonx_ai import Credentials  # type: ignore[import]
    from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore[import]
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as _P  # type: ignore[import]

log: logging.Logger = get_logger("vetrelay.watsonx_ai")

# Lazily imported so the rest of the app starts even if ibm-watsonx-ai is absent.
try:
    from ibm_watsonx_ai import Credentials  # type: ignore[import]
    from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore[import]
    from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as _P  # type: ignore[import]

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SDK_AVAILABLE = False
    Credentials = None  # type: ignore[assignment]
    ModelInference = None  # type: ignore[assignment]
    _P = None  # type: ignore[assignment]
    log.warning("event=watsonx_ai_sdk_missing install ibm-watsonx-ai to enable Granite inference")

# ---------------------------------------------------------------------------
# Default generation parameters
# ---------------------------------------------------------------------------

# These string keys are the actual MetaNames values used by the SDK.
# When the SDK IS available the params dict is rebuilt with _P.* constants
# (which resolve to the same strings) so they are always correct.
_DEFAULT_PARAMS: dict[str, object] = {
    "max_new_tokens": 512,
    "min_new_tokens": 10,
    "decoding_method": "greedy",
    "repetition_penalty": 1.1,
}

_MODEL_ID = "ibm/granite-3-8b-instruct"


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def generate(prompt: str, max_new_tokens: int = 512) -> str | None:
    """Send *prompt* to the Granite model and return the generated text.

    Returns ``None`` if credentials are missing or the SDK is unavailable,
    allowing callers to fall back to rule-based stubs.

    Args:
        prompt: The full prompt string to send to the model.
        max_new_tokens: Maximum tokens to generate (default 512).

    Returns:
        Generated text string, or None on any failure.
    """
    if not _SDK_AVAILABLE:
        log.debug("event=watsonx_ai_skipped reason=sdk_unavailable")
        return None

    api_key = os.getenv("WATSONX_API_KEY", "")
    url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    project_id = os.getenv("WATSONX_PROJECT_ID", "")

    if not api_key or not project_id:
        log.debug("event=watsonx_ai_skipped reason=missing_credentials")
        return None

    try:
        credentials = Credentials(api_key=api_key, url=url)  # type: ignore[union-attr]
        # Build params using SDK MetaNames so keys are always correct,
        # then override max_new_tokens with the caller-supplied value.
        params: dict[str, object] = {
            _P.MAX_NEW_TOKENS: max_new_tokens,  # type: ignore[union-attr]
            _P.MIN_NEW_TOKENS: _DEFAULT_PARAMS["min_new_tokens"],  # type: ignore[union-attr]
            _P.DECODING_METHOD: _DEFAULT_PARAMS["decoding_method"],  # type: ignore[union-attr]
            _P.REPETITION_PENALTY: _DEFAULT_PARAMS["repetition_penalty"],  # type: ignore[union-attr]
        }
        model = ModelInference(  # type: ignore[union-attr]
            model_id=_MODEL_ID,
            credentials=credentials,
            project_id=project_id,
            params=params,
        )
        raw = model.generate_text(prompt=prompt)
        result = raw if isinstance(raw, str) else None
        log.info("event=watsonx_ai_generate_ok model=%s tokens=%d", _MODEL_ID, max_new_tokens)
        return result.strip() if result else None
    except Exception as exc:
        log.warning("event=watsonx_ai_generate_failed error=%s", str(exc))
        return None
