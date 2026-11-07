"""Station list helpers (pure Python, no Home Assistant imports)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .board import _tidy


@dataclass(frozen=True)
class Station:
    """A passenger station: its three-letter code and a readable name."""

    crs: str
    name: str

    @property
    def label(self) -> str:
        """Text shown in the picker, e.g. 'Belvedere (BVD)'. Typing either part finds it."""
        return f"{self.name} ({self.crs})"


def parse_stations(raw: Any) -> list[Station]:
    """Turn a /api/tiploc?stations_only=1 response into a sorted station list.

    Accepts ``{"results": [...]}`` (or a bare list) and quietly skips rows without a
    valid three-letter CRS code or a name, and repeated CRS codes, so one odd row
    cannot break the picker.
    """
    if isinstance(raw, dict):
        rows = raw.get("results")
        if rows is None:
            rows = raw.get("stations")
    else:
        rows = raw
    if not isinstance(rows, list):
        return []

    seen: dict[str, Station] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        crs = row.get("crs")
        if not isinstance(crs, str) or len(crs.strip()) != 3 or not crs.strip().isalpha():
            continue
        if row.get("is_passenger_station") is False:
            continue
        name = _tidy(row.get("display_name") or row.get("name") or row.get("description"))
        if not name:
            continue
        crs = crs.strip().upper()
        seen.setdefault(crs, Station(crs, name.strip()))
    return sorted(seen.values(), key=lambda s: (s.name.casefold(), s.crs))


def split_codes(value: Any) -> list[str]:
    """'GNW, lew' -> ['GNW', 'LEW']; accepts a list too. Empty input gives []."""
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace(";", ",").split(",")
    else:
        parts = list(value)
    return [p.strip().upper() for p in parts if str(p).strip()]


def resolve_station(text: Any, stations: list[Station]) -> str:
    """Turn what was typed or picked into a CRS code where we can tell which station it is.

    Understands a CRS code ('bvd'), a picker label ('Belvedere (BVD)') and an exact
    station name ('belvedere'). Anything else is returned stripped, for the caller
    to validate.
    """
    value = str(text or "").strip()
    if not value:
        return ""
    if len(value) == 3 and value.isalpha():
        return value.upper()
    lowered = value.casefold()
    matches = [s for s in stations if lowered in (s.label.casefold(), s.name.casefold())]
    if len(matches) == 1:
        return matches[0].crs
    return value
