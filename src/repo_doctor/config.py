from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field



class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    deepseek_api_key: str = Field(default="", validation_alias="DeepSeek_API_TRAE_study_KEY")
    model: str = "deepseek-chat"
    max_steps: int = 15
    max_context_tokens: int = 60_000
    workspace_dir: str = "./workspace"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None


settings = Settings()