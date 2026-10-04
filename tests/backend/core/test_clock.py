"""LocalClock: the credit union's wall clock, whatever the server's timezone."""

from datetime import UTC, datetime, timedelta

from app.core.clock import LocalClock


def test_now_is_the_naive_local_time_of_the_configured_timezone() -> None:
    clock = LocalClock("America/Bogota")  # UTC-5 all year

    now = clock.now()

    expected = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=5)
    assert now.tzinfo is None
    assert abs(now - expected) < timedelta(seconds=5)


def test_today_follows_the_local_date() -> None:
    clock = LocalClock("Pacific/Kiritimati")  # UTC+14: often already tomorrow

    assert clock.today() == (datetime.now(UTC) + timedelta(hours=14)).date()
