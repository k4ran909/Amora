from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    app_name: str = "Spark"

    telegram_bot_token: str | None = None
    discord_bot_token: str | None = None
    discord_guild_id: int | None = None

    owner_tg_ids: Annotated[list[int], NoDecode] = []
    owner_dc_ids: Annotated[list[int], NoDecode] = []

    tg_vault_channel_id: int | None = None
    tg_admin_chat_id: int | None = None

    database_url: str = "sqlite+aiosqlite:///./data/spark.db"
    redis_url: str | None = None
    fernet_key: str

    models_dir: Path = Path("models")
    data_dir: Path = Path("data")

    # Profile rules
    min_age: int = 18
    min_photos: int = 1
    max_photos: int = 6
    min_interests: int = 3
    max_interests: int = 10

    # Photo / face rules
    min_image_side: int = 400
    max_upload_bytes: int = 10 * 1024 * 1024
    face_min_score: float = 0.8
    face_min_area_main: float = 0.04
    face_min_area_extra: float = 0.01
    face_dominance_ratio: float = 2.0
    face_min_sharpness: float = 35.0
    face_match_threshold: float = 0.363
    phash_max_distance: int = 6

    @field_validator("owner_tg_ids", "owner_dc_ids", mode="before")
    @classmethod
    def _split_ids(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, (int,)):
            return [value]
        if isinstance(value, str):
            return [int(part) for part in value.replace(" ", "").split(",") if part]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
