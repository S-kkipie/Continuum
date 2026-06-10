import os

import pytest

_REASON = (
    "set RUN_AZURE_INTEGRATION=1 + AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_DEPLOYMENT + az login"
)
pytestmark = pytest.mark.skipif(os.getenv("RUN_AZURE_INTEGRATION") != "1", reason=_REASON)


@pytest.mark.asyncio
async def test_azure_openai_streams_text():
    from continuum_api.agent.azure_openai import AzureOpenAIChatModel
    from continuum_api.agent.types import ChatMessage, TextDelta

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    if not endpoint or not deployment:
        pytest.skip("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT not set")

    model = AzureOpenAIChatModel(endpoint, deployment, "2024-10-21")
    msgs = [ChatMessage(role="user", content="Say the single word: ping")]
    text = ""
    async for ev in model.stream_turn(msgs, []):
        if isinstance(ev, TextDelta):
            text += ev.text
    assert text.strip()
