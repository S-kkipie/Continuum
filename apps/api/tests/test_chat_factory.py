from continuum_api.agent.factory import build_chat_model
from continuum_api.agent.fake_chat import FakeChatModel


def test_default_chat_model_is_fake():
    assert isinstance(build_chat_model(), FakeChatModel)
