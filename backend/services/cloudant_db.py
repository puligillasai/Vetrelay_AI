import os
from typing import Any
from ibmcloudant.cloudant_v1 import CloudantV1, Document
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator


def get_cloudant_client() -> CloudantV1:
    apikey = os.getenv("CLOUDANT_APIKEY", "")
    url = os.getenv("CLOUDANT_URL", "")

    if not apikey or not url:
        raise ValueError("CLOUDANT_APIKEY and CLOUDANT_URL must be configured.")

    authenticator = IAMAuthenticator(apikey=apikey)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(service_url=url)
    return client


def save_triage_record(record_data: dict[str, Any]) -> dict[str, Any]:
    """Saves an intake, triage result, and booking record to IBM Cloudant."""
    db_name = os.getenv("CLOUDANT_DB_NAME", "vetrelay_intakes")
    client = get_cloudant_client()

    doc = Document._from_dict(record_data)
    response = client.post_document(
        db=db_name,
        document=doc,
    ).get_result()

    return response if isinstance(response, dict) else {}