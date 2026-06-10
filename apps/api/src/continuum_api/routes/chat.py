import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from continuum_api.agent.factory import build_chat_model
from continuum_api.agent.mentor import MentorAgent
from continuum_api.agent.types import Citations, MentorDone, RetrievalStarted, TextDelta
from continuum_api.db import get_session
from continuum_api.knowledge.factory import build_blob_store, build_knowledge
from continuum_api.routes.capture import _org
from continuum_api.routes.internal import require_service_token
from continuum_api.services.conversation import ConversationService
from continuum_api.services.ingestion import IngestionService
from continuum_api.settings import settings

router = APIRouter(prefix="/internal", dependencies=[Depends(require_service_token)])


def _capture(session: Session) -> IngestionService:
    blob = build_blob_store()
    return IngestionService(session, blob, build_knowledge(blob))


def _user(x_user_id: str | None = Header(default=None), org: str = Depends(_org)) -> str:
    return x_user_id or org


class SendMessage(BaseModel):
    content: str = Field(min_length=1, max_length=10_000)


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/successors/{successor_id}/conversations", status_code=201)
def create_conversation(
    successor_id: str,
    org: str = Depends(_org),
    user: str = Depends(_user),
    session: Session = Depends(get_session),
) -> dict:
    capture = _capture(session)
    if not capture.successor_in_org(successor_id, org):
        raise HTTPException(status_code=404, detail="not found")
    successor = capture.get_successor(successor_id)
    if successor is None:
        raise HTTPException(status_code=404, detail="not found")
    if successor.status != "ready":
        raise HTTPException(status_code=409, detail="successor still learning this role")
    convo = ConversationService(session).create(successor_id=successor_id, user_id=user)
    session.commit()
    return {"id": convo.id}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> dict:
    convos = ConversationService(session)
    convo = convos.get(conversation_id)
    capture = _capture(session)
    if convo is None or not capture.successor_in_org(convo.successor_id, org):
        raise HTTPException(status_code=404, detail="not found")
    msgs = convos.history(conversation_id)
    return {
        "id": convo.id,
        "title": convo.title,
        "messages": [
            {"role": m.role, "content": m.content, "citations": m.citations} for m in msgs
        ],
    }


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessage,
    org: str = Depends(_org),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    convos = ConversationService(session)
    convo = convos.get(conversation_id)
    blob = build_blob_store()
    knowledge = build_knowledge(blob)
    capture = IngestionService(session, blob, knowledge)
    if convo is None or not capture.successor_in_org(convo.successor_id, org):
        raise HTTPException(status_code=404, detail="not found")
    successor = capture.get_successor(convo.successor_id)
    if successor is None:
        raise HTTPException(status_code=404, detail="not found")
    if successor.status != "ready":
        raise HTTPException(status_code=409, detail="successor still learning this role")
    role = capture.roles.get(successor.role_id)
    if role is None:
        raise HTTPException(status_code=500, detail="role data missing")

    history = convos.history(conversation_id)
    agent = MentorAgent(
        build_chat_model(), knowledge, role, successor,
        retrieve_top=settings.mentor_retrieve_top,
        max_iterations=settings.mentor_max_iterations,
    )

    async def gen() -> AsyncIterator[str]:
        answer = ""
        citations: list[dict] = []
        finish = "stop"
        try:
            async for ev in agent.stream(history, body.content):
                if isinstance(ev, TextDelta):
                    answer += ev.text
                    yield _sse("delta", json.dumps({"text": ev.text}))
                elif isinstance(ev, RetrievalStarted):
                    yield _sse("retrieval", json.dumps({"query": ev.query}))
                elif isinstance(ev, Citations):
                    citations = [
                        {
                            "title": c.title,
                            "source_document_id": c.source_document_id,
                            "snippet": c.snippet,
                            "score": c.score,
                        }
                        for c in ev.items
                    ]
                    yield _sse("citations", json.dumps(citations))
                elif isinstance(ev, MentorDone):
                    finish = ev.finish_reason
            convos.append(conversation_id, role="user", content=body.content)
            convos.append(
                conversation_id,
                role="assistant",
                content=answer,
                citations=citations or None,
            )
            session.commit()
            yield _sse("done", json.dumps({"finish_reason": finish}))
        except Exception as exc:  # noqa: BLE001 — surface a typed SSE error, then close
            session.rollback()
            yield _sse("error", json.dumps({"detail": str(exc)}))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
