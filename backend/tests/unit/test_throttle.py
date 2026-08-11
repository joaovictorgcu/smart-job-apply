"""Guardrails: daily cap, working-hours window and randomized delays.

`Throttle` is the designed stop. A `ThrottleLimitError` is never something to work
around, so these tests pin down that it fires exactly at the boundary.

No test here waits on real time: `asyncio.sleep` is recorded by `sleep_spy` and
`random.uniform` is pinned when the value itself matters.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.errors import AutomationError, ThrottleLimitError
from app.automation.throttle import Throttle
from app.database.base import utcnow
from app.models import ApplicationStatus, UserSettings
from tests.fixtures.factories import create_application, create_job, create_user, days_ago


def settings_row(**overrides: Any) -> UserSettings:
    """A detached `UserSettings` — the throttle needs no database to be built."""
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


def at(hour: int) -> datetime:
    """A naive local datetime: the window models a person's day, not UTC."""
    return datetime(2026, 8, 11, hour, 30)


class TestErrorContract:
    def test_a_throttle_limit_is_an_automation_error_and_never_recoverable(self) -> None:
        error = ThrottleLimitError("Daily cap reached.")
        assert isinstance(error, AutomationError)
        assert error.recoverable is False


class TestConfiguration:
    def test_reads_the_ranges_from_the_users_settings(self) -> None:
        throttle = Throttle(settings_row())
        assert throttle.action_delay == (2.5, 7.0)
        assert throttle.apply_delay == (45.0, 120.0)
        assert throttle.working_hours == (8, 20)
        assert throttle.daily_cap == 15

    def test_falls_back_to_the_conservative_defaults(self) -> None:
        throttle = Throttle(None)
        assert throttle.daily_cap == 15
        assert throttle.action_delay[0] > 0

    def test_a_swapped_range_is_normalized_instead_of_breaking_random(self) -> None:
        throttle = Throttle(settings_row(action_delay_min=9.0, action_delay_max=1.0))
        assert throttle.action_delay == (1.0, 9.0)

    def test_a_negative_delay_is_clamped_to_zero(self) -> None:
        throttle = Throttle(settings_row(action_delay_min=-5.0, action_delay_max=2.0))
        assert throttle.action_delay[0] == 0.0


class TestWorkingHours:
    @pytest.mark.parametrize("hour", [8, 12, 19])
    def test_allows_an_hour_inside_the_window(self, hour: int) -> None:
        throttle = Throttle(settings_row(working_hour_start=8, working_hour_end=20))
        assert throttle.within_working_hours(at(hour)) is True
        throttle.assert_within_working_hours(at(hour))

    @pytest.mark.parametrize("hour", [0, 7, 20, 23])
    def test_blocks_an_hour_outside_the_window(self, hour: int) -> None:
        throttle = Throttle(settings_row(working_hour_start=8, working_hour_end=20))
        assert throttle.within_working_hours(at(hour)) is False
        with pytest.raises(ThrottleLimitError, match="working hours"):
            throttle.assert_within_working_hours(at(hour))

    def test_the_start_is_inclusive_and_the_end_is_exclusive(self) -> None:
        throttle = Throttle(settings_row(working_hour_start=8, working_hour_end=20))
        assert throttle.within_working_hours(datetime(2026, 8, 11, 8, 0)) is True
        assert throttle.within_working_hours(datetime(2026, 8, 11, 20, 0)) is False

    def test_a_window_crossing_midnight_wraps(self) -> None:
        throttle = Throttle(settings_row(working_hour_start=22, working_hour_end=6))
        assert throttle.within_working_hours(at(23)) is True
        assert throttle.within_working_hours(at(2)) is True
        assert throttle.within_working_hours(at(12)) is False

    def test_an_empty_window_means_no_restriction(self) -> None:
        throttle = Throttle(settings_row(working_hour_start=0, working_hour_end=0))
        for hour in (0, 6, 13, 23):
            assert throttle.within_working_hours(at(hour)) is True


class TestDailyCap:
    async def test_no_applications_yet_leaves_the_whole_cap(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="cap0@example.com")
        throttle = Throttle(settings_row(daily_cap=3))

        assert await throttle.submitted_today(session, user.id) == 0
        assert await throttle.remaining_today(session, user.id) == 3
        assert await throttle.assert_daily_cap(session, user.id) == 0

    async def test_counts_only_applications_submitted_today(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="cap1@example.com")
        today = await create_job(session, user)
        yesterday = await create_job(session, user)
        await create_application(
            session, user, today, status=ApplicationStatus.SUBMITTED, submitted_at=utcnow()
        )
        await create_application(
            session,
            user,
            yesterday,
            status=ApplicationStatus.SUBMITTED,
            submitted_at=days_ago(2),
        )
        throttle = Throttle(settings_row(daily_cap=5))

        assert await throttle.submitted_today(session, user.id) == 1
        assert await throttle.remaining_today(session, user.id) == 4

    async def test_a_draft_awaiting_review_does_not_consume_the_cap(
        self, session: AsyncSession
    ) -> None:
        """The cap counts what was actually sent, not what is queued up."""
        user = await create_user(session, email="cap2@example.com")
        job = await create_job(session, user)
        await create_application(
            session, user, job, status=ApplicationStatus.AWAITING_REVIEW, submitted_at=None
        )
        throttle = Throttle(settings_row(daily_cap=1))

        assert await throttle.submitted_today(session, user.id) == 0
        await throttle.assert_daily_cap(session, user.id)

    async def test_blocks_once_the_cap_is_reached(self, session: AsyncSession) -> None:
        user = await create_user(session, email="cap3@example.com")
        for _ in range(2):
            job = await create_job(session, user)
            await create_application(
                session, user, job, status=ApplicationStatus.SUBMITTED, submitted_at=utcnow()
            )
        throttle = Throttle(settings_row(daily_cap=2))

        assert await throttle.remaining_today(session, user.id) == 0
        with pytest.raises(ThrottleLimitError, match="Daily cap"):
            await throttle.assert_daily_cap(session, user.id)

    async def test_remaining_never_goes_negative(self, session: AsyncSession) -> None:
        user = await create_user(session, email="cap4@example.com")
        for _ in range(3):
            job = await create_job(session, user)
            await create_application(
                session, user, job, status=ApplicationStatus.SUBMITTED, submitted_at=utcnow()
            )
        throttle = Throttle(settings_row(daily_cap=1))

        assert await throttle.remaining_today(session, user.id) == 0

    async def test_another_users_submissions_do_not_consume_the_cap(
        self, session: AsyncSession
    ) -> None:
        user = await create_user(session, email="cap5a@example.com")
        stranger = await create_user(session, email="cap5b@example.com")
        job = await create_job(session, stranger)
        await create_application(
            session, stranger, job, status=ApplicationStatus.SUBMITTED, submitted_at=utcnow()
        )
        throttle = Throttle(settings_row(daily_cap=1))

        assert await throttle.submitted_today(session, user.id) == 0
        await throttle.assert_daily_cap(session, user.id)


class TestDelays:
    async def test_the_action_delay_stays_inside_the_configured_range(
        self, sleep_spy: list[float]
    ) -> None:
        throttle = Throttle(settings_row(action_delay_min=2.5, action_delay_max=7.0))

        delay = await throttle.wait_action()

        assert 2.5 <= delay <= 7.0
        assert sleep_spy == [delay]

    async def test_the_apply_delay_stays_inside_the_configured_range(
        self, sleep_spy: list[float]
    ) -> None:
        throttle = Throttle(settings_row(apply_delay_min=45.0, apply_delay_max=120.0))

        delay = await throttle.wait_between_applications()

        assert 45.0 <= delay <= 120.0
        assert sleep_spy == [delay]

    async def test_the_gap_between_applications_is_much_longer_than_between_actions(
        self, sleep_spy: list[float]
    ) -> None:
        throttle = Throttle(settings_row())

        action = await throttle.wait_action()
        apply = await throttle.wait_between_applications()

        assert apply > action

    async def test_the_delay_is_drawn_from_the_range_not_fixed(
        self, monkeypatch: pytest.MonkeyPatch, sleep_spy: list[float]
    ) -> None:
        """A constant sleep is itself a fingerprint, so the bounds must reach random."""
        seen: list[tuple[float, float]] = []

        def _record(low: float, high: float) -> float:
            seen.append((low, high))
            return low

        monkeypatch.setattr(random, "uniform", _record)
        throttle = Throttle(settings_row(action_delay_min=2.5, action_delay_max=7.0))

        await throttle.wait_action()

        assert (2.5, 7.0) in seen

    async def test_successive_delays_differ(self, sleep_spy: list[float]) -> None:
        throttle = Throttle(settings_row(action_delay_min=1.0, action_delay_max=9.0))

        delays = [await throttle.wait_action() for _ in range(8)]

        assert len(set(delays)) > 1

    async def test_backoff_grows_with_the_attempt_and_stays_capped(
        self, sleep_spy: list[float]
    ) -> None:
        throttle = Throttle(settings_row(action_delay_min=1.0, action_delay_max=2.0))

        first = await throttle.backoff(0)
        later = await throttle.backoff(5)
        extreme = await throttle.backoff(50)

        assert later > first
        assert extreme <= 60.0
