"""Application settings, read only from environment variables (R-32, design §10).

Business thresholds live here so rules never hard-code them (business-rules.md).
The admin database URL is deliberately absent: only the roles bootstrap reads it.
"""

from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BeforeValidator, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_SESSION_SECRET_LENGTH = 32


def _split_comma_separated(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CommaSeparated = Annotated[list[str], NoDecode, BeforeValidator(_split_comma_separated)]
Probability = Annotated[float, Field(ge=0, le=1)]
PositiveSeconds = Annotated[float, Field(gt=0)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class Settings(BaseSettings):
    # Empty values (e.g. `CORS_ORIGINS=` in .env) mean "use the default".
    # Validation errors must never echo input values: they would print secrets in logs.
    model_config = SettingsConfigDict(env_ignore_empty=True, hide_input_in_errors=True)

    # Fail closed (OWASP A10): a deploy that forgets APP_ENV gets the production checks.
    # Local runs set APP_ENV=local explicitly (.env.example).
    app_env: Literal["local", "production"] = "production"

    database_url_rw: SecretStr
    database_url_ro: SecretStr | None = None
    db_connect_timeout_seconds: PositiveSeconds = 5

    anthropic_api_key: SecretStr | None = None
    anthropic_fast_model: str = "claude-haiku-4-5-20251001"
    anthropic_writer_model: str = "claude-sonnet-5-5"
    anthropic_timeout_seconds: PositiveSeconds = 30
    jev_api_key: SecretStr | None = None
    jev_base_url: str = "https://api.typesafe.ai"
    jev_model: str = "jev-latest"
    jev_timeout_seconds: PositiveSeconds = 10
    run_timeout_seconds: PositiveSeconds = 90

    refund_limit_per_window: Annotated[int, Field(ge=1)] = 3
    refund_window_days: Annotated[int, Field(ge=1)] = 365
    claim_window_days: Annotated[int, Field(ge=1)] = 60
    staff_approval_limit: Money = Decimal("50.00")
    auto_refund_enabled: bool = True
    auto_refund_max_amount: Money = Decimal("35.00")
    auto_min_confidence: Probability = 0.95
    decision_min_confidence: Probability = 0.85
    injection_threshold: Probability = 0.5
    auto_max_injection: Probability = 0.1

    session_secret: SecretStr | None = None

    max_runs_per_case_per_hour: Annotated[int, Field(ge=1)] = 5
    max_message_chars_for_models: Annotated[int, Field(ge=1)] = 2000
    rate_limit_default: str = "60/minute"
    rate_limit_run: str = "10/minute"
    max_request_body_bytes: Annotated[int, Field(ge=1)] = 65536
    cors_origins: CommaSeparated = []

    fault_injection: Literal["", "jev_down", "anthropic_down", "slow"] = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _require_production_secrets(self) -> Self:
        # OWASP A02: never start in production with a missing or weak secret.
        if not self.is_production:
            return self
        required = {
            "DATABASE_URL_RO": self.database_url_ro,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "JEV_API_KEY": self.jev_api_key,
            "SESSION_SECRET": self.session_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required settings in production: {', '.join(missing)}")
        if len(self.session_secret_value) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"SESSION_SECRET must be at least {MIN_SESSION_SECRET_LENGTH} characters"
            )
        return self

    @property
    def session_secret_value(self) -> str:
        return self.session_secret.get_secret_value() if self.session_secret else ""
