from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# settings.py -> continuum_api -> src -> api -> apps -> repo root
_ROOT_ENV = Path(__file__).parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), extra="ignore")

    database_url: str = "postgresql://continuum:continuum@localhost:5432/continuum"
    api_service_token: str

    # Capture backends — default to local/fake so the loop runs without Azure.
    blob_backend: Literal["local", "azure"] = "local"
    knowledge_backend: Literal["fake", "foundry"] = "fake"
    blob_local_root: str = ".data/blobs"

    # Azure (only used when the backends above are azure/foundry)
    azure_storage_account_url: str = ""
    azure_search_endpoint: str = ""

    # Retrieval tuning
    retrieve_top: int = 5

    # Mentor chat backend — default fake so the loop runs without Azure OpenAI.
    chat_backend: Literal["fake", "azure_openai"] = "fake"

    # Azure OpenAI (only when chat_backend == "azure_openai"; auth via DefaultAzureCredential)
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # Mentor tuning
    mentor_retrieve_top: int = 5
    mentor_max_iterations: int = 4


settings = Settings()
