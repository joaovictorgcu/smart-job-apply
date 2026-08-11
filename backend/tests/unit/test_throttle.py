"""Guardrails: daily cap, working-hours window and randomized delays.

Expected surface (`app/automation/throttle.py`), resolved leniently so a rename of
the module or of a method shows up as a precise xfail rather than a cryptic error:

    class Throttle:
        def __init__(self, settings: UserSettings) -> None: ...
        def check_working_hours(self, now: datetime | None = None) -> None
        def check_daily_cap(self, applications_today: int) -> None
        async def action_delay(self) -> float
        async def apply_delay(self) -> float

Both checks raise `ThrottleLimitError`. No test here waits on real time:
`asyncio.sleep` is recorded by `sleep_spy` and `random.uniform` is pinned.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

import pytest

from app.automation.errors import AutomationError, ThrottleLimitError
from app.models import UserSettings
from tests import call_maybe_async, construct, find_attr, first_method, missing

THROTTLE_MODULES = (
    "app.automation.throttle",
    "app.automation.guardrails",
    "app.automation.limits",
    "app.services.throttle",
)

Throttle = find_attr(
    ("Throttle", "Throttler", "ThrottleGuard", "Guardrails", "RateGuard"), *THROTTLE_MODULES
)

pytestmark = pytest.mark.xfail(
    Throttle is None, reason=missing("Throttle", *THROTTLE_MODULES)
)


def settings_row(**overrides: Any) -> UserSettings:
    """A detached `UserSettings` — the throttle should not need a database."""
    values: dict[str, Any] = {
        "user_id": 1,
        "daily_cap": 15,
        "min_score": 70,
        "action_delay_min": 2.5,
        "action_delay_max": 7.0,
        "apply_delay_min": 45.0,
        "apply_delay_max": 120.0,
        "working_hour_start": 8,
        "working_hour_end": 20,
        "require_manual_approval": True,
        "dry_run": True,
    }
    values.update(overrides)
    return UserSettings(**values)


def make_throttle(**overrides: Any) -> Any:
    return construct(Throttle, settings_row(**overrides), settings=settings_row(**overrides))


def cap_check(throttle: Any) -> Any:
    return first_method(
        throttle,
        "check_daily_cap",
        "ensure_daily_cap",
        "assert_daily_cap",
        "check_cap",
        "ensure_capacity",
    )


def hours_check(throttle: Any) -> Any:
    return first_method(
        throttle,
        "check_working_hours",
        "ensure_working_hours",
        "assert_working_hours",
        "check_hours",
        "ensure_within_working_hours",
    )


class TestErrorType:
    def test_throttle_limit_is_an_automation_error_and_not_recoverable(self) -> None:
        error = ThrottleLimitError("Daily cap reached.")
        assert isinstance(error, AutomationError)
        assert error.recoverable is False


class TestDailyCap:
    async def test_allows_an_application_below_the_cap(self) -> None:
        throttle = make_throttle(daily_cap=15)
        await call_maybe_async(cap_check(throttle), 14)

    async def test_blocks_once_the_cap_is_reached(self) -> None:
        throttle = make_throttle(daily_cap=15)
        with pytest.raises(ThrottleLimitError):
            await call_maybe_async(cap_check(throttle), 15)

    async def test_blocks_past_the_cap(self) -> None:
        throttle = make_throttle(daily_cap=3)
        with pytest.raises(ThrottleLimitError):
            await call_maybe_async(cap_check(throttle), 9)

    async def test_a_cap_of_one_blocks_the_second_application(self) -> None:
        throttle = make_throttle(daily_cap=1)
        await call_maybe_async(cap_check(throttle), 0)
        with pytest.raises(ThrottleLimitError):
            await call_maybe_async(cap_check(throttle), 1)


class TestWorkingHours:
    async def test_allows_an_hour_inside_the_window(self) -> None:
        throttle = make_throttle(working_hour_start=8, working_hour_end=20)
        await call_maybe_async(
            hours_check(throttle), datetime(2026, 8, 11, 13, 0, tzinfo=UTC)
        )

    @pytest.mark.parametrize("hour", [0, 7, 20, 23])
    async def test_blocks_an_hour_outside_the_window(self, hour: int) -> None:
        throttle = make_throttle(working_hour_start=8, working_hour_end=20)
        with pytest.raises(ThrottleLimitError):
            await call_maybe_async(
                hours_check(throttle), datetime(2026, 8, 11, hour, 0, tzinfo=UTC)
            )

    async def test_the_window_start_is_inclusive(self) -> None:
        throttle = make_throttle(working_hour_start=8, working_hour_end=20)
        await call_maybe_async(hours_check(throttle), datetime(2026, 8, 11, 8, 0, tzinfo=UTC))

    async def test_a_full_day_window_never_blocks(self) -> None:
        throttle = make_throttle(working_hour_start=0, working_hour_end=24)
        for hour in (0, 6, 12, 23):
            await call_maybe_async(
                hours_check(throttle), datetime(2026, 8, 11, hour, 0, tzinfo=UTC)
            )


class TestDelays:
    async def test_the_action_delay_stays_inside_the_configured_range(
        self, monkeypatch: pytest.MonkeyPatch, sleep_spy: list[float]
    ) -> None:
        monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)
        throttle = make_throttle(action_delay_min=2.5, action_delay_max=7.0)
        await call_maybe_async(
            first_method(throttle, "action_delay", "wait_between_actions", "delay_action")
        )
        assert sleep_spy, "the action delay must actually await asyncio.sleep"
        assert all(2.5 <= delay <= 7.0 for delay in sleep_spy), sleep_spy

    async def test_the_apply_delay_stays_inside_the_configured_range(
        self, monkeypatch: pytest.MonkeyPatch, sleep_spy: list[float]
    ) -> None:
        monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)
        throttle = make_throttle(apply_delay_min=45.0, apply_delay_max=120.0)
        await call_maybe_async(
            first_method(throttle, "apply_delay", "wait_between_applications", "delay_apply")
        )
        assert sleep_spy, "the apply delay must actually await asyncio.sleep"
        assert all(45.0 <= delay <= 120.0 for delay in sleep_spy), sleep_spy

    async def test_the_delay_is_randomized_between_the_bounds(
        self, monkeypatch: pytest.MonkeyPatch, sleep_spy: list[float]
    ) -> None:
        """A fixed delay is a fingerprint; the bounds have to reach `random.uniform`."""
        seen: list[tuple[float, float]] = []

        def _record(low: float, high: float) -> float:
            seen.append((low, high))
            return low

        monkeypatch.setattr(random, "uniform", _record)
        throttle = make_throttle(action_delay_min=2.5, action_delay_max=7.0)
        await call_maybe_async(
            first_method(throttle, "action_delay", "wait_between_actions", "delay_action")
        )
        assert (2.5, 7.0) in seen, seen
