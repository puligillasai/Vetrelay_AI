"""IBM Cloudant persistence service.

Provides:
  - get_cloudant_client()   — authenticated CloudantV1 client
  - ensure_database()       — auto-create DB if it does not exist (prevents 404 on first run)
  - save_triage_record()    — insert a triage/booking encounter document
  - get_recent_records()    — fetch the N most recent records for front-desk queue sync

Auto-initialisation:
  On the first call to save_triage_record() the database is provisioned
  automatically if it does not exist, so a cold deployment never crashes
  with a 404 Not Found from Cloudant.

Environment variables:
    CLOUDANT_APIKEY    — IBM Cloud IAM API key
    CLOUDANT_URL       — e.g. https://<instance>.cloudantnosqldb.appdomain.cloud
    CLOUDANT_DB_NAME   — database name (default: vetrelay_intakes)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from ibm_cloud_sdk_core import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
from ibmcloudant.cloudant_v1 import CloudantV1, Document

_log = logging.getLogger("vetrelay.cloudant")

# Module-level flag so we only call ensure_database() once per process.
_DB_VERIFIED: bool = False


def get_cloudant_client() -> CloudantV1:
    """Return an authenticated CloudantV1 client.

    Raises ValueError when credentials are absent (caught by callers).
    """
    apikey = os.getenv("CLOUDANT_APIKEY", "")
    url = os.getenv("CLOUDANT_URL", "")

    if not apikey or not url:
        raise ValueError("CLOUDANT_APIKEY and CLOUDANT_URL must be configured.")

    authenticator = IAMAuthenticator(apikey=apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(service_url=url)
    return client


def ensure_database(client: CloudantV1, db_name: str) -> None:
    """Create *db_name* if it does not already exist.

    Swallows the 412 Precondition Failed that Cloudant returns when the DB
    already exists, and raises for any other error.
    """
    try:
        client.put_database(db=db_name).get_result()
        _log.info("event=cloudant_db_created db=%s", db_name)
    except ApiException as exc:
        if exc.code == 412:
            # Database already exists — this is the normal case after first run.
            _log.debug("event=cloudant_db_exists db=%s", db_name)
        else:
            _log.warning("event=cloudant_db_create_failed db=%s status=%d", db_name, exc.code)
            raise


def save_triage_record(record_data: dict[str, Any]) -> dict[str, Any]:
    """Insert a triage/booking encounter into Cloudant.

    Auto-provisions the database on the first call so a fresh deployment
    never hits a 404.

    Args:
        record_data: Dict containing the encounter fields (see main.py).

    Returns:
        Cloudant response dict with ``id`` and ``rev``, or empty dict on error.
    """
    global _DB_VERIFIED  # noqa: PLW0603

    db_name = os.getenv("CLOUDANT_DB_NAME", "vetrelay_intakes")
    client = get_cloudant_client()

    if not _DB_VERIFIED:
        ensure_database(client, db_name)
        _DB_VERIFIED = True

    doc = Document._from_dict(record_data)
    response = client.post_document(
        db=db_name,
        document=doc,
    ).get_result()

    return response if isinstance(response, dict) else {}


def get_recent_records(limit: int = 20) -> list[dict[str, Any]]:
    """Fetch the *limit* most recently saved encounter records.

    Used by the Clinic Console (MVP 2) to synchronise the front-desk queue
    across browser sessions.

    Returns an empty list when Cloudant is unavailable or credentials are missing.
    """
    db_name = os.getenv("CLOUDANT_DB_NAME", "vetrelay_intakes")
    try:
        client = get_cloudant_client()
        raw = client.post_all_docs(
            db=db_name,
            include_docs=True,
            limit=limit,
            descending=True,  # newest first
        ).get_result()
        if not isinstance(raw, dict):
            return []
        rows: list[dict[str, Any]] = raw.get("rows", [])
        return [r["doc"] for r in rows if "doc" in r]
    except Exception as exc:
        _log.warning("event=cloudant_fetch_failed error=%s", str(exc))
        return []
