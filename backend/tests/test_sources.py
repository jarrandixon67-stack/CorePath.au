from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_source_registry_category_and_verification_flow(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_API_TOKEN", "source-test-token")
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer source-test-token"}

            libraries_response = client.get("/v1/libraries", headers=headers)
            assert libraries_response.status_code == 200
            libraries = libraries_response.json()
            assert len(libraries) == 11

            library_id = libraries[0]["library_id"]
            overview_response = client.get(
                f"/v1/libraries/{library_id}/overview",
                headers=headers,
            )
            assert overview_response.status_code == 200
            overview = overview_response.json()
            assert overview["registered_sources"] == 0
            assert overview["verified_records"] == 0
            assert overview["research_findings"] == 0
            assert overview["categories"]

            category = overview["categories"][0]
            source_response = client.post(
                f"/v1/libraries/{library_id}/sources",
                headers=headers,
                json={
                    "source_type": "book",
                    "title": "CorePath CI source registry test",
                    "authors": ["Automated Test"],
                    "category_id": category["id"],
                },
            )
            assert source_response.status_code == 201
            source = source_response.json()
            assert source["category_id"] == category["id"]
            assert source["verification_status"] == "unverified"

            verify_response = client.patch(
                f"/v1/libraries/{library_id}/sources/{source['id']}/verification",
                headers=headers,
                json={
                    "verification_status": "verified",
                    "verification_notes": "Automated workflow verification test.",
                },
            )
            assert verify_response.status_code == 200
            assert verify_response.json()["verification_status"] == "verified"

            final_overview = client.get(
                f"/v1/libraries/{library_id}/overview",
                headers=headers,
            ).json()
            assert final_overview["registered_sources"] == 1
            assert final_overview["verified_records"] == 1
    finally:
        get_settings.cache_clear()
