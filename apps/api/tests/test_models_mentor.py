from continuum_api.models import Conversation, Message


def test_mentor_models_have_expected_tablenames():
    assert Conversation.__tablename__ == "conversation"
    assert Message.__tablename__ == "message"


def test_message_role_and_citations_default():
    m = Message(conversation_id="c1", role="user", content="hi")
    assert m.role == "user"
    assert m.citations is None
