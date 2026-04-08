from functools import lru_cache
from typing import List, Union

from pydantic import BaseSettings, Field, validator


class Settings(BaseSettings):
    app_name: str = "SMT Backend Service"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = True

    cors_allow_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    llm_provider: str = "openai_compatible"
    llm_api_key: str = ""
    llm_api_base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3"
    llm_model: str = "doubao-seed-2.0-code"
    llm_timeout_seconds: int = Field(default=60, ge=1)

    workflow_max_attempts: int = Field(default=4, ge=1)
    workflow_accept_unknown: bool = False
    z3_cli_path: str = "z3"
    z3_timeout_seconds: int = Field(default=15, ge=1)

    optimizer_max_depth: int = Field(default=8, ge=1)
    optimizer_max_iterations: int = Field(default=24, ge=1)
    optimizer_max_children: int = Field(default=8, ge=1)
    optimizer_exploration_weight: float = Field(default=0.3, ge=0.0)
    optimizer_enable_llm_postpass: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @validator("cors_allow_origins", pre=True)
    def split_cors_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
