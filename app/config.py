from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379/0"

    # Generator timing (seconds)
    spend_interval_min_sec: float = Field(default=4.0, ge=0.1)
    spend_interval_max_sec: float = Field(default=10.0, ge=0.1)
    revenue_delay_min_sec: float = Field(default=10.0, ge=0.0)
    revenue_delay_max_sec: float = Field(default=180.0, ge=0.0)
    revenue_amount_min_factor: float = Field(default=0.85, ge=0.0)
    revenue_amount_max_factor: float = Field(default=1.05, ge=0.0)

    # Matching thresholds
    match_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    ambiguity_margin: float = Field(default=0.15, ge=0.0, le=1.0)
    amount_tolerance_pct: float = Field(default=0.15, ge=0.0, le=1.0)
    amount_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    time_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    lookback_sec: float = Field(default=600.0, ge=0.0)

    # Stale / trust window
    stale_after_sec: float = Field(default=240.0, ge=0.0)
    stale_check_interval_sec: float = Field(default=1.0, ge=0.1)

    # Demo / API
    events_log_max_len: int = Field(default=100, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
