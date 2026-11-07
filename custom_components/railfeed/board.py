"""Pure-Python parsing of RailFeed live_board responses.

Deliberately has no Home Assistant imports so it can be unit tested on its own.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
import string
from typing import Any

# A train running at least this many minutes late is reported as "delayed".
DELAY_THRESHOLD_MINS = 1

STATUS_ON_TIME = "on_time"
STATUS_DELAYED = "delayed"
STATUS_CANCELLED = "cancelled"


def _tidy(name: str | None) -> str | None:
    """RailFeed stores some names in capitals; make them readable."""
    if not name:
        return None
    return string.capwords(name) if name.isupper() else name


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        parts = [int(p) for p in value.split(":")]
        return time(parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return None


def _parse_uk_datetime(value: str | None, tz: tzinfo) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    except ValueError:
        return None


@dataclass(frozen=True)
class CallingInfo:
    """What we know about a train's call at the configured 'calling at' station."""

    arrival: str | None  # advertised arrival, "HH:MM"
    journey_mins: int | None


@dataclass(frozen=True)
class ViaStation:
    """A station used to tell routes apart ("via Greenwich") and the trains calling there."""

    crs: str
    name: str
    calling: Mapping[str, CallingInfo]


def join_names(names: Sequence[str]) -> str:
    """'A', 'A and B', 'A, B and C'."""
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def parse_calling_services(raw: dict[str, Any]) -> dict[str, CallingInfo]:
    """Turn a /api/services response into {schedule uid: CallingInfo}.

    Only trains that genuinely stop at both stations count: a train that merely
    passes the destination, or has an operational-only stop there, does not serve it.
    """
    result: dict[str, CallingInfo] = {}
    for item in raw.get("services") or []:
        uid = item.get("uid")
        if not uid or item.get("to_is_pass") or item.get("from_is_pass"):
            continue
        public = item.get("to_public_arrival")
        if public is None and "to_public_arrival" in item:
            continue  # no public call at the destination
        stamp = public or item.get("to_arrival")
        journey = item.get("journey_mins")
        result[uid] = CallingInfo(
            arrival=stamp[:5] if stamp else None,
            journey_mins=int(journey) if isinstance(journey, (int, float)) else None,
        )
    return result


def base_date_of(raw: dict[str, Any], now: datetime, tz: tzinfo) -> date:
    """The service date a live_board response is for."""
    try:
        return date.fromisoformat(raw["date"])
    except (KeyError, TypeError, ValueError):
        return now.astimezone(tz).date()


def service_dates(base: date, now: datetime, tz: tzinfo, hours: int) -> list[date]:
    """Schedule dates whose trains can appear on the board.

    A train's schedule belongs to the day it started, so just after midnight the
    board holds trains from yesterday's schedule, and a window reaching past
    midnight holds trains from tomorrow's.
    """
    local_now = now.astimezone(tz)
    dates = {base}
    if local_now.hour < 6:
        dates.add(base - timedelta(days=1))
    if (local_now + timedelta(hours=hours)).date() > local_now.date():
        dates.add(base + timedelta(days=1))
    return sorted(dates)


@dataclass(frozen=True)
class Service:
    """One departure from the station."""

    uid: str | None
    headcode: str | None
    operator: str | None
    origin: str | None
    destination: str | None
    destination_crs: str | None
    scheduled: datetime
    expected: datetime
    platform: str | None
    platform_confirmed: bool
    platform_changed: bool
    status: str
    delay_minutes: int
    cancel_reason: str | None
    late_reason: str | None
    coaches: int | None
    calling_at_arrival: str | None = None
    journey_minutes: int | None = None
    via: tuple[str, ...] = ()

    @property
    def destination_label(self) -> str | None:
        """Destination, with the route appended when known: 'London Cannon Street via Greenwich'."""
        if self.destination and self.via:
            return f"{self.destination} via {join_names(self.via)}"
        return self.destination

    @property
    def cancelled(self) -> bool:
        return self.status == STATUS_CANCELLED

    def as_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination_label,
            "destination_name": self.destination,
            "via": list(self.via),
            "destination_crs": self.destination_crs,
            "origin": self.origin,
            "operator": self.operator,
            "headcode": self.headcode,
            "scheduled_time": self.scheduled.strftime("%H:%M"),
            "expected_time": self.expected.strftime("%H:%M"),
            "scheduled": self.scheduled.isoformat(),
            "expected": self.expected.isoformat(),
            "platform": self.platform,
            "platform_confirmed": self.platform_confirmed,
            "platform_changed": self.platform_changed,
            "status": self.status,
            "delay_minutes": self.delay_minutes,
            "cancel_reason": self.cancel_reason,
            "late_reason": self.late_reason,
            "coaches": self.coaches,
            "calling_at_arrival": self.calling_at_arrival,
            "journey_minutes": self.journey_minutes,
            "service_uid": self.uid,
        }


@dataclass(frozen=True)
class BoardData:
    """Processed departure board for one station."""

    station: str
    services: list[Service]
    calling_at: str | None = None

    @property
    def next_service(self) -> Service | None:
        """First departure that is actually running."""
        return next((s for s in self.services if not s.cancelled), None)

    @property
    def delayed_count(self) -> int:
        return sum(1 for s in self.services if s.status == STATUS_DELAYED)

    @property
    def cancelled_count(self) -> int:
        return sum(1 for s in self.services if s.cancelled)


def _parse_service(
    item: dict[str, Any],
    *,
    base_date: date,
    tz: tzinfo,
    now: datetime,
    passenger_only: bool,
    destinations: frozenset[str],
    calling: Mapping[str, CallingInfo] | None = None,
    via: Sequence[ViaStation] = (),
) -> Service | None:
    # Things that never belong on a departure board.
    if item.get("is_pass") or item.get("stale") or item.get("reached_destination"):
        return None
    if item.get("status") == "passed":
        return None
    if item.get("cancel_type") == "ON CALL":  # runs-as-required path, never ran
        return None

    headcode = item.get("headcode") or ""
    if passenger_only:
        if item.get("toc_type") not in ("PASSENGER", None):
            return None
        # The first character of a headcode is the train class. Drop the classes that
        # are never passengers: 0 light engine, 3 parcels, 4/6/7 freight, 5 empty
        # stock, 8 departmental. Classes 1, 2 and 9 stay: 9 is used by passenger
        # operators too (Thameslink, Eurostar), so it can't be treated as non-passenger.
        if headcode[:1] in ("0", "3", "4", "5", "6", "7", "8"):
            return None

    destination_crs = item.get("destination_crs")
    if destinations and destination_crs not in destinations:
        return None

    calling_info: CallingInfo | None = None
    if calling is not None:
        calling_info = calling.get(item.get("uid"))
        if calling_info is None:  # train doesn't call at the configured station
            return None

    # Route labels: every configured via station this train calls at (after the
    # board's station), in route order. A train that ends at a via station is not
    # "via" it, and a train that merely runs through one is not labelled.
    hits = [
        (v.calling[item.get("uid")].journey_mins, v.name)
        for v in via
        if v.crs != destination_crs and item.get("uid") in v.calling
    ]
    hits.sort(key=lambda h: (h[0] is None, h[0] or 0))
    via_names = tuple(name for _, name in hits)

    sched_t = _parse_time(item.get("public_departure")) or _parse_time(
        item.get("scheduled_departure")
    )
    if sched_t is None:
        return None

    scheduled = datetime.combine(base_date, sched_t, tzinfo=tz)
    if scheduled < now.astimezone(tz) - timedelta(hours=6):
        scheduled += timedelta(days=1)  # board has rolled past midnight

    cancelled = item.get("status") == "cancelled"

    raw_delay = item.get("projected_delay_mins")
    if raw_delay is None:
        raw_delay = item.get("delay_mins")
    delay = 0 if cancelled else max(0, int(raw_delay or 0))

    expected = scheduled
    if not cancelled:
        actual = _parse_uk_datetime(item.get("actual_departure_uk"), tz)
        projected_t = _parse_time(item.get("projected_departure"))
        if actual:
            expected = actual
        elif projected_t:
            expected = datetime.combine(scheduled.date(), projected_t, tzinfo=tz)
            if expected < scheduled - timedelta(hours=12):
                expected += timedelta(days=1)
        elif delay:
            expected = scheduled + timedelta(minutes=delay)

    if cancelled:
        status = STATUS_CANCELLED
    elif delay >= DELAY_THRESHOLD_MINS:
        status = STATUS_DELAYED
    else:
        status = STATUS_ON_TIME

    # Platform: honour the operator's request to keep a platform off public screens.
    live_platform = item.get("live_platform")
    booked_platform = item.get("platform")
    if item.get("live_platform_suppressed"):
        platform = None
    else:
        platform = live_platform or item.get("actual_platform") or booked_platform
    platform_changed = bool(
        live_platform
        and booked_platform
        and not item.get("live_platform_suppressed")
        and live_platform != booked_platform
    )

    formation = item.get("formation") or {}
    coaches = formation.get("total_coaches") if isinstance(formation, dict) else None

    return Service(
        uid=item.get("uid"),
        headcode=headcode or None,
        operator=item.get("toc_name"),
        origin=_tidy(item.get("origin")),
        destination=_tidy(item.get("destination")),
        destination_crs=destination_crs,
        scheduled=scheduled,
        expected=expected,
        platform=str(platform) if platform else None,
        platform_confirmed=bool(item.get("live_platform_confirmed")),
        platform_changed=platform_changed,
        status=status,
        delay_minutes=delay,
        cancel_reason=item.get("cancel_reason") if cancelled else None,
        # "Check the delay before showing it": reasons linger on recovered trains.
        late_reason=item.get("late_reason") if delay >= DELAY_THRESHOLD_MINS else None,
        coaches=coaches,
        calling_at_arrival=calling_info.arrival if calling_info else None,
        journey_minutes=calling_info.journey_mins if calling_info else None,
        via=via_names,
    )


def parse_board(
    raw: dict[str, Any],
    *,
    tz: tzinfo,
    now: datetime,
    max_departures: int,
    passenger_only: bool,
    destinations: frozenset[str],
    calling: Mapping[str, CallingInfo] | None = None,
    calling_at: str | None = None,
    via: Sequence[ViaStation] = (),
) -> BoardData:
    """Turn a raw live_board response into a BoardData.

    With ``calling`` set, only trains whose schedule uid is in it are kept.
    """
    station = _tidy(raw.get("station")) or "Station"
    base_date = base_date_of(raw, now, tz)

    services: list[Service] = []
    for item in raw.get("services") or []:
        service = _parse_service(
            item,
            base_date=base_date,
            tz=tz,
            now=now,
            passenger_only=passenger_only,
            destinations=destinations,
            calling=calling,
            via=via,
        )
        if service is None:
            continue
        services.append(service)
        if len(services) >= max_departures:
            break

    return BoardData(station=station, services=services, calling_at=calling_at)
