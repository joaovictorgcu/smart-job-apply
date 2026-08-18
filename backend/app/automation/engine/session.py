"""Browser session lifecycle and the `LinkedInAccount` row behind it.

Opening a window, restoring the encrypted cookies, waiting for a manual login,
and persisting the session state back on the way out. Nothing here decides
*what* to do with the browser; it only guarantees the rest of the engine gets a
started, configured, signed-in service.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.crypto import DecryptionError, decrypt_json, encrypt_json
from app.automation.contracts import SessionState
from app.automation.engine.base import EngineBase
from app.automation.errors import AutomationError, SecurityCheckpointError
from app.database.base import utcnow
from app.database.session import session_scope
from app.models import LinkedInAccount
from app.observability import get_logger

if TYPE_CHECKING:
    from app.automation.linkedin.service import LinkedInBrowserService

logger = get_logger(__name__)


def _new_browser_service(user_id: int) -> LinkedInBrowserService:
    """Build the browser service through the package namespace.

    `app.automation.engine.LinkedInBrowserService` is the seam the test suite
    swaps by name; importing the class into this module would bind the real one
    before the swap and make the fake unreachable.
    """
    from app.automation import engine as engine_package

    return engine_package.LinkedInBrowserService(user_id)


class SessionMixin(EngineBase):
    """Owns the browser window: open it, sign in, persist it, close it."""

    async def start_session(self, user_id: int) -> SessionState:
        """Open the browser and report whether a manual login is still needed."""
        async with self._exclusive(user_id):
            service = self._service(user_id)
            await self._configure_service(user_id, service)
            try:
                state = await service.start()
                if not state.logged_in and await self._restore_cookies(user_id, service):
                    state = await service.start()
                await self._persist_account(user_id, service, state)
            except SecurityCheckpointError as exc:
                await self._handle_checkpoint(user_id, None, exc)
                return SessionState(
                    browser_open=False, logged_in=False, blocked=True, blocked_reason=exc.reason
                )
            await self._publish_session(user_id, state)
            return state

    async def wait_for_manual_login(self, user_id: int, timeout_seconds: int = 300) -> SessionState:
        """Block until the user finishes signing in inside the visible window."""
        async with self._exclusive(user_id):
            service = self._service(user_id)
            state = await service.wait_for_login(timeout_seconds)
            await self._persist_account(user_id, service, state)
            await self._publish_session(user_id, state)
            return state

    async def stop_session(self, user_id: int) -> SessionState:
        """Persist the encrypted session state, then close the browser."""
        service = self._services.pop(user_id, None)
        if service is None:
            state = SessionState()
            await self._publish_session(user_id, state)
            return state

        async with self._exclusive(user_id):
            try:
                storage = await service.export_storage_state()
            except AutomationError as exc:
                storage = None
                logger.warning(
                    "Could not export the LinkedIn session state.",
                    extra={"action": "engine.stop_session", "user_id": user_id, "error": str(exc)},
                )
            if storage is not None:
                async with session_scope() as session:
                    account = await self._account(session, user_id, create=True)
                    account.encrypted_storage_state = encrypt_json(storage)
                    account.is_connected = True
                    account.last_verified_at = utcnow()
            await service.stop()

        state = SessionState()
        await self._publish_session(user_id, state)
        return state

    async def get_session_state(self, user_id: int) -> SessionState:
        service = self._services.get(user_id)
        if service is not None:
            return await service.get_state()
        async with session_scope() as session:
            account = await self._account(session, user_id)
            display_name = account.display_name if account else None
        return SessionState(browser_open=False, logged_in=False, display_name=display_name)

    def _service(self, user_id: int) -> LinkedInBrowserService:
        service = self._services.get(user_id)
        if service is None:
            service = _new_browser_service(user_id)
            self._services[user_id] = service
        return service

    async def _ready_service(self, user_id: int) -> LinkedInBrowserService:
        """A started, signed-in service with fresh throttle and resume settings."""
        service = self._service(user_id)
        await self._configure_service(user_id, service)
        if not service.browser.is_open:
            state = await service.start()
            if not state.logged_in and await self._restore_cookies(user_id, service):
                await service.start()
        return service

    async def _configure_service(self, user_id: int, service: LinkedInBrowserService) -> None:
        throttle = await self._throttle(user_id)
        service.configure(throttle=throttle, resume_path=await self._resume_path(user_id))

    async def _restore_cookies(self, user_id: int, service: LinkedInBrowserService) -> bool:
        async with session_scope() as session:
            account = await self._account(session, user_id)
            token = account.encrypted_storage_state if account else None
        if not token:
            return False
        try:
            state = decrypt_json(token)
        except DecryptionError as exc:
            logger.warning(
                "Stored LinkedIn cookies could not be decrypted; a manual login is required.",
                extra={"action": "engine.restore_cookies", "user_id": user_id, "error": str(exc)},
            )
            return False
        if not isinstance(state, dict):
            return False
        await service.import_storage_state(state)
        return True

    async def _persist_account(
        self, user_id: int, service: LinkedInBrowserService, state: SessionState
    ) -> None:
        async with session_scope() as session:
            account = await self._account(session, user_id, create=True)
            account.browser_profile_dir = str(service.browser.profile_dir)
            account.is_connected = state.logged_in
            if state.display_name:
                account.display_name = state.display_name
            if state.logged_in:
                account.last_verified_at = utcnow()
                # If the export fails the persistent profile on disk still holds
                # the session, so this is not worth failing the connection over.
                with suppress(AutomationError):
                    account.encrypted_storage_state = encrypt_json(
                        await service.export_storage_state()
                    )

    @staticmethod
    async def _account(
        session: AsyncSession, user_id: int, *, create: bool = False
    ) -> LinkedInAccount | None:
        account = await session.scalar(
            select(LinkedInAccount).where(LinkedInAccount.user_id == user_id)
        )
        if account is None and create:
            account = LinkedInAccount(user_id=user_id)
            session.add(account)
            await session.flush()
        return account
