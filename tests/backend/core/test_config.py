"""Settings come only from the environment and fail fast when misconfigured (R-32, OWASP A02)."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import Settings

RW_URL = "postgresql+asyncpg://app_rw:pw@db:5432/refunds"
PRODUCTION_SECRETS = {
    "database_url_ro": "postgresql+asyncpg://agent_ro:pw@db:5432/refunds",
    "anthropic_api_key": "key",
    "jev_api_key": "key",
    "session_secret": "s" * 48,
}


@pytest.mark.parametrize("missing", sorted(PRODUCTION_SECRETS))
def test_production_refuses_to_start_without_each_secret(missing: str) -> None:
    secrets = {name: value for name, value in PRODUCTION_SECRETS.items() if name != missing}

    with pytest.raises(ValidationError, match=missing.upper()):
        Settings(app_env="production", database_url_rw=RW_URL, **secrets)


def test_production_rejects_a_short_session_secret() -> None:
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        Settings(
            app_env="production",
            database_url_rw=RW_URL,
            **{**PRODUCTION_SECRETS, "session_secret": "too-short"},
        )


def test_production_error_never_echoes_secret_values() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            app_env="production",
            database_url_rw=RW_URL,
            **{**PRODUCTION_SECRETS, "session_secret": "visible-but-too-short"},
        )

    assert "visible-but-too-short" not in str(error.value)


def test_a_missing_app_env_means_production_so_it_fails_closed() -> None:
    # A deploy that forgets APP_ENV must not run with docs on, no HSTS and no secret checks.
    with pytest.raises(ValidationError, match="Missing required settings in production"):
        Settings(database_url_rw=RW_URL)


def test_local_runs_without_model_keys_or_session_secret() -> None:
    settings = Settings(app_env="local", database_url_rw=RW_URL)

    assert settings.anthropic_api_key is None
    assert settings.session_secret is None


def test_cors_origins_are_read_as_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://127.0.0.1:5173")

    settings = Settings(app_env="local", database_url_rw=RW_URL)

    assert settings.cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_empty_env_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "")
    monkeypatch.setenv("STAFF_APPROVAL_LIMIT", "")

    settings = Settings(app_env="local", database_url_rw=RW_URL)

    assert settings.cors_origins == []
    assert settings.staff_approval_limit == Decimal("50.00")


def test_money_thresholds_are_decimals_not_floats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_REFUND_MAX_AMOUNT", "35.10")

    settings = Settings(app_env="local", database_url_rw=RW_URL)

    assert settings.auto_refund_max_amount == Decimal("35.10")


def test_an_unknown_fault_injection_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULT_INJECTION", "everything_down")

    with pytest.raises(ValidationError):
        Settings(app_env="local", database_url_rw=RW_URL)
