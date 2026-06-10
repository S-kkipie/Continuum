from continuum_api.agent.chat_model import ChatModel
from continuum_api.settings import settings


def build_chat_model() -> ChatModel:
    if settings.chat_backend == "azure_openai":
        from continuum_api.agent.azure_openai import AzureOpenAIChatModel

        return AzureOpenAIChatModel(
            endpoint=settings.azure_openai_endpoint,
            deployment=settings.azure_openai_deployment,
            api_version=settings.azure_openai_api_version,
        )
    from continuum_api.agent.fake_chat import FakeChatModel

    return FakeChatModel()
