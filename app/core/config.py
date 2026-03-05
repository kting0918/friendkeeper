from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""  # 逗號分隔的 chat_id

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/friendkeeper"

    # OpenAI
    openai_api_key: str = ""

    # Face Recognition
    face_similarity_threshold: float = 0.6

    # Storage
    upload_dir: str = "./uploads"

    # App
    app_env: str = "production"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    @property
    def allowed_chat_ids(self) -> List[int]:
        if not self.telegram_allowed_chat_ids:
            return []
        return [int(x.strip()) for x in self.telegram_allowed_chat_ids.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
