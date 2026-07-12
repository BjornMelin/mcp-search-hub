"""Provider configuration and lifecycle registry."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable
from functools import partial
from typing import Protocol

from ..config import AppSettings, resolve_env_references
from ..models import ProviderHealth
from .sessions import MCPProviderSession, ProviderDefinition, ProviderSession

logger = logging.getLogger(__name__)
# Cooperative cleanup gets a brief grace; resistant tasks continue detached.
_RECOVERY_SHUTDOWN_GRACE_SECONDS = 0.1
_STARTUP_COMPLETION_GRACE_SECONDS = 0.1


class ProviderRegistryProtocol(Protocol):
    """Lifecycle and lookup surface required by the hub."""

    async def startup(self) -> None: ...

    async def ensure_started(self, required_identifiers: set[str] | None = None) -> None: ...

    def active_sessions(self) -> list[ProviderSession]: ...

    def definitions(self) -> list[ProviderDefinition]: ...

    def recovering_identifiers(self) -> set[str]: ...

    def health(self) -> dict[str, ProviderHealth]: ...

    async def close(self) -> None: ...


class ProviderRegistry:
    """Own all configured downstream provider sessions."""

    def __init__(self, definitions: Iterable[ProviderDefinition]) -> None:
        self._definitions = {
            definition.identifier: definition
            for definition in sorted(definitions, key=lambda item: item.identifier)
        }
        self._sessions: dict[str, ProviderSession] = {}
        self._recovery_tasks: dict[str, asyncio.Task[None]] = {}
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()
        self._closed = False

    @classmethod
    def from_settings(cls, settings: AppSettings) -> ProviderRegistry:
        definitions: list[ProviderDefinition] = []
        for identifier, provider in sorted(settings.providers.items()):
            if not provider.enabled:
                continue
            definitions.append(
                ProviderDefinition(
                    identifier=identifier,
                    transport=provider.resolved_transport(identifier),
                    tool=provider.tool,
                    tags=frozenset(provider.tags),
                    weight=provider.weight,
                    timeout_seconds=provider.timeout_seconds,
                    estimated_cost_usd=provider.estimated_cost_usd,
                    query_argument=provider.query_argument,
                    max_results_argument=provider.max_results_argument,
                    raw_content_argument=provider.raw_content_argument,
                    static_arguments=resolve_env_references(provider.static_arguments),
                    result_path=tuple(provider.result_path),
                    field_aliases={
                        name: tuple(aliases) for name, aliases in provider.field_aliases.items()
                    },
                )
            )
        return cls(definitions)

    async def startup(self) -> None:
        """Warm all providers concurrently within the longest configured timeout."""

        tasks = await self._schedule_recoveries()
        if tasks:
            _, pending = await asyncio.wait(
                tasks,
                timeout=max(definition.timeout_seconds for definition in self._definitions.values())
                + _STARTUP_COMPLETION_GRACE_SECONDS,
            )
            for task in pending:
                task.cancel()

    async def ensure_started(self, required_identifiers: set[str] | None = None) -> None:
        """Recover unavailable providers without delaying usable automatic routes."""

        tasks = await self._schedule_recoveries()
        if required_identifiers:
            if self._has_ready_session(required_identifiers):
                return
            required_tasks = tuple(
                task
                for identifier, task in self._recovery_tasks.items()
                if identifier in required_identifiers
            )
            await self._wait_until_ready(required_tasks, required_identifiers)
            return
        if not self._has_ready_session():
            await self._wait_until_ready(tasks)

    async def _schedule_recoveries(self) -> tuple[asyncio.Task[None], ...]:
        async with self._lock:
            if self._closed:
                return ()
            if not self._sessions:
                self._sessions = {
                    identifier: MCPProviderSession(definition)
                    for identifier, definition in self._definitions.items()
                }
            for identifier, session in self._sessions.items():
                if session.ready or identifier in self._recovery_tasks:
                    continue
                task = asyncio.create_task(
                    session.start(),
                    name=f"search-hub-recover-{identifier}",
                )
                self._recovery_tasks[identifier] = task
                task.add_done_callback(partial(self._recovery_finished, identifier))
            return tuple(self._recovery_tasks.values())

    async def _wait_until_ready(
        self,
        tasks: tuple[asyncio.Task[None], ...],
        required_identifiers: set[str] | None = None,
    ) -> None:
        waiters = {asyncio.shield(task) for task in tasks}
        try:
            while waiters and not self._has_ready_session(required_identifiers):
                done, waiters = await asyncio.wait(
                    waiters,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for completed in done:
                    if not completed.cancelled():
                        completed.exception()
        finally:
            for waiter in waiters:
                waiter.cancel()

    def _has_ready_session(self, identifiers: set[str] | None = None) -> bool:
        return any(
            session.ready and (identifiers is None or identifier in identifiers)
            for identifier, session in self._sessions.items()
        )

    def _recovery_finished(self, identifier: str, task: asyncio.Task[None]) -> None:
        if self._recovery_tasks.get(identifier) is task:
            self._recovery_tasks.pop(identifier, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.warning("Provider %s did not start: %s", identifier, type(error).__name__)

    def active_sessions(self) -> list[ProviderSession]:
        return [session for session in self._sessions.values() if session.ready]

    def definitions(self) -> list[ProviderDefinition]:
        return list(self._definitions.values())

    def recovering_identifiers(self) -> set[str]:
        """Return providers whose registry-owned recovery is still pending."""

        return {identifier for identifier, task in self._recovery_tasks.items() if not task.done()}

    def health(self) -> dict[str, ProviderHealth]:
        return {identifier: session.health() for identifier, session in self._sessions.items()}

    async def close(self) -> None:
        """Close every provider even when another provider cleanup fails."""

        async with self._lock:
            recovery_tasks = dict(self._recovery_tasks)
            sessions = dict(self._sessions)
            self._closed = True
            self._recovery_tasks = {}
            self._sessions = {}

        callback_owned = {
            identifier: task for identifier, task in recovery_tasks.items() if not task.done()
        }
        for identifier, task in callback_owned.items():
            task.add_done_callback(
                partial(self._close_session_after_recovery, sessions[identifier])
            )

        direct_close_tasks = {
            identifier: asyncio.create_task(
                session.close(),
                name=f"search-hub-close-{identifier}",
            )
            for identifier, session in sessions.items()
            if identifier not in callback_owned
        }
        for identifier, task in direct_close_tasks.items():
            self._track_cleanup(identifier, task)

        for task in recovery_tasks.values():
            task.cancel()
        pending: set[asyncio.Task[None]] = set()
        if recovery_tasks:
            _, pending = await asyncio.wait(
                recovery_tasks.values(),
                timeout=_RECOVERY_SHUTDOWN_GRACE_SECONDS,
            )

        for identifier in sorted(
            identifier for identifier, task in recovery_tasks.items() if task in pending
        ):
            logger.warning(
                "Provider %s recovery resisted shutdown; cleanup deferred",
                identifier,
            )

        await asyncio.sleep(0)
        cleanup_tasks = set(self._cleanup_tasks)
        if cleanup_tasks:
            _, pending_closes = await asyncio.wait(
                cleanup_tasks,
                timeout=_RECOVERY_SHUTDOWN_GRACE_SECONDS,
            )
            for task in pending_closes:
                logger.warning("Provider cleanup resisted shutdown: %s", task.get_name())
                task.cancel()

    def _close_session_after_recovery(
        self,
        session: ProviderSession,
        recovery_task: asyncio.Task[None],
    ) -> None:
        """Close a detached session once its recovery releases the lifecycle lock."""

        cleanup_task = recovery_task.get_loop().create_task(
            session.close(),
            name=f"search-hub-close-{session.identifier}",
        )
        self._track_cleanup(session.identifier, cleanup_task)

    def _track_cleanup(self, identifier: str, task: asyncio.Task[None]) -> None:
        self._cleanup_tasks.add(task)
        task.add_done_callback(partial(self._cleanup_finished, identifier))

    def _cleanup_finished(self, identifier: str, task: asyncio.Task[None]) -> None:
        self._cleanup_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.warning("Provider %s cleanup failed: %s", identifier, type(error).__name__)


__all__ = [
    "ProviderDefinition",
    "ProviderRegistry",
    "ProviderRegistryProtocol",
    "ProviderSession",
]
