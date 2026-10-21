import os
from datetime import UTC, datetime

from dotenv import load_dotenv

from backend.services.cloudant_db import get_cloudant_client, save_triage_record

load_dotenv()


def test_connection():
    print("Testing IBM Cloudant connection...")

    # 1. Test Client Initialization & Server Ping
    try:
        client = get_cloudant_client()
        server_info = client.get_server_information().get_result()
        version = getattr(server_info, "version", "unknown")
        print(f" Connected to Cloudant! Server version: {version}")
    except Exception as e:
        print(f" Failed to connect to Cloudant: {e}")
        return

    # 2. Test Inserting a Document
    db_name = os.getenv("CLOUDANT_DB_NAME", "vetrelay_intakes")
    print(f"Writing test intake document to database '{db_name}'...")

    test_payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "owner_name": "Test User",
        "pet_name": "Max",
        "species": "canine",
        "age_years": 3.0,
        "reported_symptoms": ["vomiting", "tremors"],
        "is_emergency": True,
        "assigned_clinic": "Metro 24/7 Veterinary Emergency Hospital",
        "status": "CONNECTION_TEST_OK",
    }

    try:
        result = save_triage_record(test_payload)
        doc_id = result.get("id")
        doc_rev = result.get("rev")
        print(" Document successfully inserted!")
        print(f"   Document ID:  {doc_id}")
        print(f"   Revision:     {doc_rev}")
    except Exception as e:
        print(f" Failed to write document: {e}")


if __name__ == "__main__":
    test_connection()
