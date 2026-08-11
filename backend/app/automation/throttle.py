"""Pacing guard rails for browser automation.

These delays, caps and working-hour windows exist to keep the tool's behaviour
close to a human's and to bound the damage of a bug (a loop that would otherwise
fire hundreds of applications in a minute). They are risk *reduction*, NOT a
guarantee against detection: LinkedIn's automation defences look at far more than
timing, and no delay makes automated use of the site safe or sanctioned. Treat a
`ThrottleLimitError` as a designed stop, never as something to work around.

Every interval is randomized. A fixed sleep is itself a fingerprint.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.errors import ThrottleLimitError
from app.config import get_settings
from app.models import Application, ApplicationStatus
from app.observability import get_logger

if TYPE_CHECKING:
    from app.models import UserSettings

logger = get_logger(__name__)

# Upper bound for `backoff`, so a retry loop can never sleep for minutes.
_MAX_BACKOFF_SECONDS = 60.0


class Throttle:
    """Timing and volume guard rails derived from a user's settings."""

    __slots__ = (
        "action_delay",
        "apply_delay",
        "daily_cap",
        "working_hours",
    )

    def __init__(self, settings: UserSettings | None = None) -> None:
        defaults = get_settings()
        if settings is None:
            self.action_delay = tuple(defaults.default_action_delay_range)
            self.apply_delay = tuple(defaults.default_apply_delay_range)
            self.working_hours = tuple(defaults.default_working_hours)
            self.daily_cap = defaults.default_daily_cap
        else:
            self.action_delay = (
                float(settings.action_delay_min),
                float(settings.action_delay_max),
            )
            self.apply_delay = (
                float(settings.apply_delay_min),
                float(settings.apply_delay_max),
            )
            self.working_hours = (
                int(settings.working_hour_start),
                int(settings.working_hour_end),
            )
            self.daily_cap = int(settings.daily_cap)

        self.action_delay = _ordered(self.action_delay)
        self.apply_delay = _ordered(self.apply_delay)

    # --- Delays -----------------------------------------------------------

    async def wait_action(self) -> float:
        """Pause between two interactions on the same page."""
        return await self._sleep_uniform(*self.action_delay)

    async def wait_between_applications(self) -> float:
        """Pause between two applications. Deliberately much longer."""
        return await self._sleep_uniform(*self.apply_delay)

    async def backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter, capped, for recoverable failures."""
        exponent = max(0, min(attempt, 8))
        base = min(self.action_delay[0] * (2**exponent), _MAX_BACKOFF_SECONDS)
        delay = min(base * random.uniform(0.7, 1.3), _MAX_BACKOFF_SECONDS)
        logger.info(
            "Backing off before retry.",
            extra={"action": "throttle.backoff", "attempt": attempt, "delay": round(delay, 2)},
        )
        await asyncio.sleep(delay)
        return delay

    @staticmethod
    async def _sleep_uniform(low: float, high: float) -> float:
        delay = random.uniform(low, high)
        await asyncio.sleep(delay)
        return delay

    # --- Working hours ----------------------------------------------------

    def within_working_hours(self, now: datetime | None = None) -> bool:
        """True when the local hour is inside the user's configured window.

        The window is evaluated in the machine's local time because it models
        "when a person would plausibly be job hunting", not a UTC schedule.
        """
        start, end = self.working_hours
        current = (now or datetime.now()).hour
        if start == end:
            return True
        if start < end:
            return start <= current < end
        # Window crossing midnight, e.g. 22 -> 6.
        return current >= start or current < end

    def assert_within_working_hours(self, now: datetime | None = None) -> None:
        if not self.within_working_hours(now):
            start, end = self.working_hours
            raise ThrottleLimitError(
                f"Outside the configured working hours ({start:02d}:00-{end:02d}:00). "
                "Adjust the window in settings or try again later."
            )

    # --- Daily cap --------------------------------------------------------

    async def submitted_today(self, session: AsyncSession, user_id: int) -> int:
        """Applications actually submitted during the current UTC day."""
        start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count())
            .select_from(Application)
            .where(
                Application.user_id == user_id,
                Application.status == ApplicationStatus.SUBMITTED,
                Application.submitted_at.is_not(None),
                Application.submitted_at >= start_of_day,
            )
        )
        return int((await session.execute(stmt)).scalar_one())

    async def remaining_today(self, session: AsyncSession, user_id: int) -> int:
        return max(0, self.daily_cap - await self.submitted_today(session, user_id))

    async def assert_daily_cap(self, session: AsyncSession, user_id: int) -> int:
        """Raise when the user already hit the daily cap; return the count used."""
        used = await self.submitted_today(session, user_id)
        if used >= self.daily_cap:
            raise ThrottleLimitError(
                f"Daily cap reached: {used}/{self.daily_cap} applications submitted today."
            )
        return used

    # --- Interaction shaping ---------------------------------------------

    async def human_pause(self, page: Any) -> None:
        """Small randomized mouse move / scroll between meaningful actions.

        Purely cosmetic jitter so interactions are not perfectly mechanical. Any
        failure here is irrelevant to the task, so it is swallowed (the page may
        be navigating or already closed).
        """
        try:
            viewport = page.viewport_size or {"width": 1440, "height": 900}
            await page.mouse.move(
                random.uniform(0.15, 0.85) * viewport["width"],
                random.uniform(0.15, 0.85) * viewport["height"],
                steps=random.randint(4, 14),
            )
            await asyncio.sleep(random.uniform(0.2, 0.9))
            if random.random() < 0.5:
                await page.mouse.wheel(0, random.randint(-220, 420))
                await asyncio.sleep(random.uniform(0.2, 0.8))
        except Exception as exc:  # cosmetic only — never fail a run over this
            logger.debug(
                "Skipped human pause.",
                extra={"action": "throttle.human_pause", "status": "skipped", "error": str(exc)},
            )


def _ordered(pair: tuple[float, ...]) -> tuple[float, float]:
    """Normalize a (min, max) pair so a swapped configuration cannot break random.uniform."""
    low, high = float(pair[0]), float(pair[1])
    if low > high:
        low, high = high, low
    return (max(0.0, low), max(0.0, high))
