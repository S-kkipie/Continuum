import uuid


def _headers():
    from continuum_api.settings import settings

    return {"X-Service-Token": settings.api_service_token, "X-Org-Id": "o-api"}


def test_capture_flow_via_api(client):
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    h = _headers()
    # create role (org comes from the X-Org-Id header, not the path)
    r = client.post("/internal/roles", json={"id": role_id, "title": "Ops"}, headers=h)
    assert r.status_code == 201
    # create successor
    r = client.post(f"/internal/roles/{role_id}/successor", headers=h)
    assert r.status_code == 201
    sid = r.json()["id"]
    # upload a document
    r = client.post(
        f"/internal/successors/{sid}/documents",
        files=[("files", ("p.txt", b"Deploys happen on Fridays.", "text/plain"))],
        headers=h,
    )
    assert r.status_code == 201
    # ingest
    r = client.post(f"/internal/successors/{sid}/ingest", headers=h)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    # poll
    r = client.get(f"/internal/successors/{sid}/ingest/{job_id}", headers=h)
    assert r.json()["status"] == "succeeded"
    # successor ready
    assert client.get(f"/internal/successors/{sid}", headers=h).json()["status"] == "ready"
    # smoke retrieval
    r = client.post(
        f"/internal/successors/{sid}/query",
        json={"query": "when do we deploy"},
        headers=h,
    )
    hits = r.json()["snippets"]
    assert hits and "Fridays" in hits[0]["content"]


def test_service_token_required(client):
    assert client.get("/internal/successors/whatever").status_code == 401


def test_query_unknown_successor_404(client):
    r = client.post("/internal/successors/nope/query",
                    json={"query": "x"}, headers=_headers())
    assert r.status_code == 404


def test_job_status_unknown_job_404(client):
    r = client.get("/internal/successors/nope/ingest/nope", headers=_headers())
    assert r.status_code == 404
