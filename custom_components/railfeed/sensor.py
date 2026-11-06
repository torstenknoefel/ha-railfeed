"""Sensors for RailFeed."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .board import BoardData
from .const import ATTRIBUTION, DOMAIN
from .coordinator import RailFeedConfigEntry, RailFeedCoordinator


@dataclass(frozen=True, kw_only=True)
class RailFeedSensorDescription(SensorEntityDescription):
    """Describes a RailFeed sensor."""

    value_fn: Callable[[BoardData], StateType | datetime]
    attrs_fn: Callable[[BoardData], dict[str, Any]] | None = None


def _next_attr(board: BoardData, getter: Callable[[Any], Any]) -> Any:
    service = board.next_service
    return getter(service) if service else None


def _next_departure_attrs(board: BoardData) -> dict[str, Any]:
    attrs: dict[str, Any] = {"station": board.station}
    if board.calling_at:
        attrs["calling_at"] = board.calling_at
    service = board.next_service
    if service:
        attrs.update(service.as_dict())
    attrs["departures"] = [s.as_dict() for s in board.services]
    return attrs


SENSORS: tuple[RailFeedSensorDescription, ...] = (
    RailFeedSensorDescription(
        key="next_departure",
        translation_key="next_departure",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda b: _next_attr(b, lambda s: s.expected),
        attrs_fn=_next_departure_attrs,
    ),
    RailFeedSensorDescription(
        key="next_destination",
        translation_key="next_destination",
        value_fn=lambda b: _next_attr(b, lambda s: s.destination_label),
    ),
    RailFeedSensorDescription(
        key="next_platform",
        translation_key="next_platform",
        value_fn=lambda b: _next_attr(b, lambda s: s.platform),
    ),
    RailFeedSensorDescription(
        key="next_delay",
        translation_key="next_delay",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: _next_attr(b, lambda s: s.delay_minutes),
    ),
    RailFeedSensorDescription(
        key="next_status",
        translation_key="next_status",
        value_fn=lambda b: _next_attr(b, lambda s: s.status),
    ),
    RailFeedSensorDescription(
        key="delayed_services",
        translation_key="delayed_services",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: b.delayed_count,
    ),
    RailFeedSensorDescription(
        key="cancelled_services",
        translation_key="cancelled_services",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda b: b.cancelled_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RailFeedConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up RailFeed sensors."""
    coordinator = entry.runtime_data
    async_add_entities(RailFeedSensor(coordinator, desc) for desc in SENSORS)


class RailFeedSensor(CoordinatorEntity[RailFeedCoordinator], SensorEntity):
    """A sensor derived from the station's departure board."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    # The full departures list is large and changes every poll; keep it out of the DB.
    _unrecorded_attributes = frozenset({"departures"})

    entity_description: RailFeedSensorDescription

    def __init__(
        self, coordinator: RailFeedCoordinator, description: RailFeedSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry_key.lower()}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_key)},
            name=coordinator.config_entry.title or coordinator.data.station,
            manufacturer="RailFeed",
            model="Live departure board",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://railfeed.co.uk/timetables/{coordinator.crs}",
        )

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
