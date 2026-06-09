HEADERS = {"X-Service-Token": "dev-shared-service-token"}


def test_internal_hello_requires_service_token(client):
    res = client.get("/internal/hello")
    assert res.status_code == 401


def test_internal_hello_reads_seed_from_db(client):
    res = client.get("/internal/hello", headers=HEADERS)
    assert res.status_code == 200
    body = res.json()
    assert body["from"] == "fastapi"
    assert body["db"] == "continuum"  # the seeded app_info value
