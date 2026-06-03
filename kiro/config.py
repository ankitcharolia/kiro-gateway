# -*- coding: utf-8 -*-
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROXY_API_KEY: str = "change-me"
    KIRO_CLI_COMMAND: str = "kiro"
    ACP_ENABLED: bool = True
    OPENAI_SHIM_ENABLED: bool = True
    ANTHROPIC_SHIM_ENABLED: bool = True
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
