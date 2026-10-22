"""IBM Cloudant persistence service for VetRelay AI."""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("vetrelay.cloudant")

try:
    from ibm_cloud_sdk_core import ApiException
    from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
    from ibmcloudant.cloudant_v1 import CloudantV1, Document

    _CLOUDANT_SDK_AVAILABLE = True
except ImportError:
    _CLOUDANT_SDK_AVAILABLE = False
    ApiException = Exception

# In-memory store fallback so the app works even if Cloudant is unreachable
_MEMORY_RECORDS: list[dict[str, Any]] = []


def is_cloudant_configured() -> bool:
    """Check if Cloudant credentials are configured in the environment."""
    return bool(os.getenv("CLOUDANT_APIKEY") and os.getenv("CLOUDANT_URL"))


def get_cloudant_client() -> Any:
    """Initialize and return an authenticated CloudantV1 client."""
    if not _CLOUDANT_SDK_AVAILABLE:
        raise ImportError("ibmcloudant package is not installed.")

    apikey = os.getenv("CLOUDANT_APIKEY", "")
    url = os.getenv("CLOUDANT_URL", "")

    if not apikey or not url:
        raise ValueError("CLOUDANT_APIKEY and CLOUDANT_URL must be configured.")

    authenticator = IAMAuthenticator(apikey=apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(service_url=url)
    return client


def ensure_database_exists(client: Any, db_name: str) -> None:
    """Ensure the target Cloudant database exists, creating it if necessary."""
    try:
        client.get_database_information(db=db_name).get_result()
    except ApiException as exc:
        if getattr(exc, "code", None) == 404:
            client.put_database(db=db_name).get_result()
        else:
            raise


def save_triage_record(record_data: dict[str, Any]) -> dict[str, Any]:
    """Save an intake, triage result, and booking record to Cloudant and memory."""
    snapshot = dict(record_data)
    _MEMORY_RECORDS.insert(0, snapshot)

    if not is_cloudant_configured() or not _CLOUDANT_SDK_AVAILABLE:
        return {"id": snapshot.get("pet_name", "local-mem"), "status": "saved_in_memory"}

    db_name = os.getenv("CLOUDANT_DB_NAME", "vetrelay_intakes")
    try:
        client = get_cloudant_client()
        ensure_database_exists(client, db_name)
        doc = Document._from_dict(record_data)
        response = client.post_document(db=db_name, document=doc).get_result()
        return response if isinstance(response, dict) else {}
    except Exception as exc:
        log.warning("Failed to save record to Cloudant: %s", exc)
        return {"status": "saved_in_memory", "error": str(exc)}


def get_recent_records(limit: int = 50) -> list[dict[str, Any]]:
    """Retrieve recent intake and triage records from Cloudant or memory."""
    if not is_cloudant_configured() or not _CLOUDANT_SDK_AVAILABLE:
        return _MEMORY_RECORDS[:limit]

    db_name = os.getenv("CLOUDANT_DB_NAME", "vetrelay_intakes")
    try:
        client = get_cloudant_client()
        result = client.post_all_docs(
            db=db_name,
            include_docs=True,
            limit=limit,
            descending=True,
        ).get_result()

        rows = result.get("rows", [])
        docs = [row["doc"] for row in rows if row.get("doc") and not row["doc"].get("_id", "").startswith("_design/")]
        return docs if docs else _MEMORY_RECORDS[:limit]
    except Exception as exc:
        log.warning("Failed to fetch records from Cloudant: %s", exc)
        return _MEMORY_RECORDS[:limit]


# Alias for backward compatibility
get_recent_intakes = get_recent_records