from collections.abc import AsyncIterator
from typing import Any

from continuum_api.agent.types import (
    ChatMessage,
    ChatModelEvent,
    TextDelta,
    ToolCallRequested,
    TurnDone,
)


def _to_openai(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc.get("arguments", "{}"),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class AzureOpenAIChatModel:
    """Real ChatModel over Azure OpenAI tool-calling (managed identity).

    NOTE: the streaming tool-call delta shape targets the GA openai SDK
    (verified against the installed v2.x); the auth/token-provider wiring is
    confirmed by the gated integration test. This is the only file to change
    if the SDK surface differs — the ChatModel Protocol is stable.
    """

    def __init__(self, endpoint: str, deployment: str, api_version: str) -> None:
        self._endpoint = endpoint
        self._deployment = deployment
        self._api_version = api_version

    def _client(self):
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AsyncAzureOpenAI

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://cognitiveservices.azure.com/.default",
        )
        return AsyncAzureOpenAI(
            azure_endpoint=self._endpoint,
            api_version=self._api_version,
            azure_ad_token_provider=token_provider,
        )

    async def stream_turn(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> AsyncIterator[ChatModelEvent]:
        async with self._client() as client:
            stream = await client.chat.completions.create(
                model=self._deployment,
                messages=_to_openai(messages),
                tools=tools or None,
                tool_choice="auto" if tools else "none",
                stream=True,
            )
            calls: dict[int, dict[str, str]] = {}
            finish = "stop"
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta and delta.content:
                    yield TextDelta(text=delta.content)
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        slot = calls.setdefault(tc.index, {"id": "", "name": "", "args": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function and tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            slot["args"] += tc.function.arguments
                if choice.finish_reason:
                    finish = choice.finish_reason
        for idx, slot in calls.items():
            if slot["name"]:
                yield ToolCallRequested(
                    id=slot["id"] or f"call-{idx}",
                    name=slot["name"],
                    arguments_json=slot["args"] or "{}",
                )
        yield TurnDone(finish_reason=finish)
