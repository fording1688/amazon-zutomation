from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8020
    storage_dir: Path = Path("storage/Amazon-Images")
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "IMAGE_FACTORY_OPENAI_API_KEY"),
    )
    image_model_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("IMAGE_MODEL_API_KEY", "IMAGE_FACTORY_IMAGE_MODEL_API_KEY"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="IMAGE_FACTORY_",
        extra="ignore",
    )


settings = Settings()


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def storage_root() -> Path:
    path = settings.storage_dir
    if not path.is_absolute():
        path = project_root() / path
    path.mkdir(parents=True, exist_ok=True)
    return path
