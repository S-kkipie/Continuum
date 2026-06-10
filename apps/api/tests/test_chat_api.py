import json
import uuid


def _h():
    from continuum_api.settings import settings
    return {
        "X-Service-Token": settings.api_service_token,
        "X-Org-Id": "o-chat",
        "X-User-Id": "u-chat",
    }


def _ready_successor(client, h):
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    client.post("/internal/roles", json={"id": role_id, "title": "Ops"}, headers=h)
    sid = client.post(f"/internal/roles/{role_id}/successor", headers=h).json()["id"]
    client.post(f"/internal/successors/{sid}/documents",
                files=[("files", ("p.txt", b"We deploy on Fridays to reduce risk.",
                                   "text/plain"))], headers=h)
    client.post(f"/internal/successors/{sid}/ingest", headers=h)
    assert client.get(f"/internal/successors/{sid}", headers=h).json()["status"] == "ready"
    return sid


def _parse_sse(raw: str) -> list[tuple[str, str]]:
    events = []
    for block in raw.strip().split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = line[len("data:"):].strip()
        if ev:
            events.append((ev, data or ""))
    return events


def test_chat_streams_grounded_answer_with_citations(client):
    h = _h()
    sid = _ready_successor(client, h)
    convo = client.post(f"/internal/successors/{sid}/conversations", headers=h)
    assert convo.status_code == 201
    cid = convo.json()["id"]

    r = client.post(f"/internal/conversations/{cid}/messages",
                    json={"content": "why do we deploy on fridays?"}, headers=h)
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert "delta" in kinds
    assert "citations" in kinds
    assert kinds[-1] == "done"
    cite_data = next(d for e, d in events if e == "citations")
    cites = json.loads(cite_data)
    assert cites and cites[0]["source_document_id"] == "p.txt"

    history = client.get(f"/internal/conversations/{cid}", headers=h).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["messages"][1]["citations"]


def test_conversation_create_requires_ready_successor(client):
    h = _h()
    role_id = f"r-{uuid.uuid4().hex[:8]}"
    client.post("/internal/roles", json={"id": role_id, "title": "X"}, headers=h)
    sid = client.post(f"/internal/roles/{role_id}/successor", headers=h).json()["id"]
    r = client.post(f"/internal/successors/{sid}/conversations", headers=h)
    assert r.status_code == 409


def test_cross_org_conversation_is_404(client):
    a = _h()
    b = {"X-Service-Token": a["X-Service-Token"], "X-Org-Id": "other-org"}
    sid = _ready_successor(client, a)
    cid = client.post(f"/internal/successors/{sid}/conversations", headers=a).json()["id"]
    assert client.get(f"/internal/conversations/{cid}", headers=b).status_code == 404
    assert client.post(f"/internal/conversations/{cid}/messages",
                       json={"content": "hi"}, headers=b).status_code == 404


def test_send_message_requires_ready_successor(client):
    from sqlmodel import Session

    from continuum_api.db import engine
    from continuum_api.models import Successor
    h = _h()
    sid = _ready_successor(client, h)
    cid = client.post(f"/internal/successors/{sid}/conversations", headers=h).json()["id"]
    with Session(engine) as s:
        succ = s.get(Successor, sid)
        succ.status = "failed"
        s.add(succ)
        s.commit()
    r = client.post(f"/internal/conversations/{cid}/messages",
                    json={"content": "hi"}, headers=h)
    assert r.status_code == 409


def test_get_unknown_conversation_is_404(client):
    assert client.get("/internal/conversations/nope", headers=_h()).status_code == 404


def test_empty_message_content_rejected(client):
    h = _h()
    sid = _ready_successor(client, h)
    cid = client.post(f"/internal/successors/{sid}/conversations", headers=h).json()["id"]
    r = client.post(f"/internal/conversations/{cid}/messages",
                    json={"content": ""}, headers=h)
    assert r.status_code == 422


def test_conversation_records_user_id_from_header(client):
    from sqlmodel import Session

    from continuum_api.db import engine
    from continuum_api.models import Conversation
    h = _h()
    sid = _ready_successor(client, h)
    cid = client.post(f"/internal/successors/{sid}/conversations", headers=h).json()["id"]
    with Session(engine) as s:
        convo = s.get(Conversation, cid)
        assert convo.user_id == "u-chat"
