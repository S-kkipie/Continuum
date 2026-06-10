import uuid

from sqlmodel import Session

from continuum_api.db import engine
from continuum_api.services.conversation import ConversationService


def test_create_append_history_and_title():
    with Session(engine) as session:
        svc = ConversationService(session)
        sid = f"s-{uuid.uuid4().hex[:8]}"
        uid = f"u-{uuid.uuid4().hex[:8]}"
        convo = svc.create(successor_id=sid, user_id=uid)
        svc.append(convo.id, role="user", content="Why do we deploy on Fridays exactly?")
        svc.append(convo.id, role="assistant", content="Because…",
                   citations=[{"title": "doc.txt", "source_document_id": "doc.txt",
                               "snippet": "…", "score": 1.0}])
        session.commit()

        msgs = svc.history(convo.id)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[1].citations and msgs[1].citations[0]["source_document_id"] == "doc.txt"
        refreshed = svc.get(convo.id)
        assert refreshed.title.startswith("Why do we deploy")
