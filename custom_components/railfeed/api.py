"""Minimal async client for the RailFeed API."""
from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_BASE, REQUEST_TIMEOUT


class RailFeedError(Exception):
    """Base error for RailFeed API problems."""


class RailFeedAuthError(RailFeedError):
    """The API key is missing, invalid or lacks scope."""


class RailFeedNotFoundError(RailFeedError):
    """The requested station does not exist."""


class RailFeedRateLimitError(RailFeedError):
    """The API rate limit was exceeded."""


class RailFeedConnectionError(RailFeedError):
    """The API could not be reached."""


class RailFeedClient:
    """Thin wrapper around the RailFeed JSON API."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def async_get_live_board(self, crs: str, hours: int = 2) -> dict[str, Any]:
        """Return the live departure board for a station (CRS code)."""
        return await self._get(
            "live_board", {"crs": crs, "hours": hours, "type": "departures"}
        )

    async def async_get_services(
        self, from_crs: str, to_crs: str, day: str | None = None
    ) -> dict[str, Any]:
        """Return scheduled direct services calling at both stations, in that order."""
        params: dict[str, Any] = {"from": from_crs, "to": to_crs}
        if day:
            params["date"] = day
        return await self._get("services", params)

    async def async_get_stations(self) -> dict[str, Any]:
        """Return every passenger station (CRS code and name) in one request."""
        return await self._get("tiploc", {"stations_only": 1})

    async def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json"}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(
                    f"{API_BASE}/{endpoint}", params=params, headers=headers
                ) as resp:
                    status = resp.status
                    try:
                        body = await resp.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError):
                        body = None
        except (TimeoutError, aiohttp.ClientError) as err:
            raise RailFeedConnectionError(f"Cannot reach RailFeed: {err}") from err

        if status == 200 and isinstance(body, dict):
            return body

        message = body.get("error") if isinstance(body, dict) else None
        message = message or f"HTTP {status}"

        if status in (401, 403):
            raise RailFeedAuthError(message)
        if status == 404:
            raise RailFeedNotFoundError(message)
        if status == 429:
            raise RailFeedRateLimitError(message)
        raise RailFeedError(message)
