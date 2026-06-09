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


settings = Settings()
