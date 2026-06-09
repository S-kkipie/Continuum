from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# settings.py -> continuum_api -> src -> api -> apps -> repo root
_ROOT_ENV = Path(__file__).parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT_ENV), extra="ignore")

    database_url: str = "postgresql://continuum:continuum@localhost:5432/continuum"
    api_service_token: str


settings = Settings()
