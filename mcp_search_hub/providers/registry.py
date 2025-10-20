"""Provider registry orchestration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from ..config.settings import AppSettings
from ..models import ProviderHealth
from .sessions import MCPProviderSession, ProviderDefinition, ProviderSession

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Manage lifecycle of provider sessions defined in configuration."""

    def __init__(self, definitions: Iterable[ProviderDefinition]):
        self._definitions: dict[str, ProviderDefinition] = {
            definition.identifier: definition for definition in definitions
        }
        self._sessions: dict[str, ProviderSession] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: AppSettings) -> ProviderRegistry:
        """Construct the registry from application settings."""

        definitions: list[ProviderDefinition] = []
        for identifier, provider in settings.iter_provider_settings().items():
            definition = provider.build_definition(identifier)
            if definition is None:
                logger.info("Skipping provider %s: no transport configured", identifier)
                continue
            definitions.append(definition)
        return cls(definitions)

    async def startup(self) -> None:
        """Instantiate provider sessions and establish connections."""

        async with self._lock:
            if self._sessions:
                return
            for definition in self._definitions.values():
                session = MCPProviderSession(definition)
                await session.start()
                self._sessions[definition.identifier] = session
                logger.info("Registered provider session: %s", definition.identifier)

    async def ensure_started(self) -> None:
        """Ensure provider sessions have been started."""

        if not self._sessions:
            await self.startup()

    def active_sessions(self) -> list[ProviderSession]:
        """Return the active provider sessions."""

        return list(self._sessions.values())

    def definitions(self) -> list[ProviderDefinition]:
        """Return configured provider definitions."""

        return list(self._definitions.values())

    def get_session(self, identifier: str) -> ProviderSession:
        """Return a provider session by identifier."""

        try:
            return self._sessions[identifier]
        except KeyError as exc:  # noqa: B904 - raise contextual error
            raise KeyError(f"Unknown provider session: {identifier}") from exc

    def health(self) -> dict[str, ProviderHealth]:
        """Return provider health metrics."""

        return {
            identifier: session.health()
            for identifier, session in self._sessions.items()
        }

    async def close(self) -> None:
        """Shutdown provider sessions and release resources."""

        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        if not sessions:
            return

        results = await asyncio.gather(
            *(session.close() for session in sessions),
            return_exceptions=True,
        )
        for session, result in zip(sessions, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "Error closing provider %s: %s",
                    session.identifier,
                    result,
                    exc_info=result if logger.isEnabledFor(logging.DEBUG) else None,
                )
            elif isinstance(result, BaseException):
                raise result


__all__ = ["ProviderRegistry", "ProviderDefinition", "ProviderSession"]
