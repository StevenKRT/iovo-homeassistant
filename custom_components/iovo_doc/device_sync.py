from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .api import IovoApiClient
from .const import (
    CONF_DEVICE_ENTITIES,
    CONF_DEVICE_EXCLUDED_ENTITIES,
    CONF_DEVICE_SELECTION_MODE,
    CONF_DEVICE_STATE_SYNC,
    CONF_DEVICE_TYPES,
    DEFAULT_DEVICE_SELECTION_MODE,
    DEFAULT_DEVICE_STATE_SYNC,
    DEVICE_SELECTION_ALL,
    DEVICE_SELECTION_ENTITIES,
    DEVICE_SELECTION_TYPES,
    DEVICE_SELECTION_TYPES_AND_ENTITIES,
    DIRECTION_HA_TO_IOVO,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)


class IovoDeviceSync:
    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        client: IovoApiClient,
        options: dict[str, Any],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.client = client
        self.options = options
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY_PREFIX}.{entry_id}",
        )
        self._data: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._cancel_state_listener: Callable[[], None] | None = None
        self._room_map: dict[str, str] = {}
        self._room_map_loaded_at: datetime | None = None

    async def async_initialize(self) -> None:
        stored = await self._store.async_load()
        self._data = stored if isinstance(stored, dict) else {}
        self._data.setdefault("last_sync", None)
        self._data.setdefault("last_result", None)
        self._refresh_state_listener()

    async def async_shutdown(self) -> None:
        if self._cancel_state_listener is not None:
            self._cancel_state_listener()
            self._cancel_state_listener = None

    async def async_sync(
        self,
        direction: str = DIRECTION_HA_TO_IOVO,
    ) -> dict[str, Any]:
        if direction != DIRECTION_HA_TO_IOVO:
            raise ValueError("Geräte werden nur von Home Assistant nach iovo|doc übertragen.")

        async with self._lock:
            await self.client.async_connect()
            await self._async_refresh_room_map(force=True)

            selected = self._selected_entity_ids()
            if not selected:
                result = {
                    "success": True,
                    "created": 0,
                    "updated": 0,
                    "skipped": 0,
                    "errors": [],
                    "empty_selection": True,
                }
            else:
                created = 0
                updated = 0
                skipped = 0
                errors: list[str] = []

                for entity_id in selected:
                    state = self.hass.states.get(entity_id)
                    if state is None:
                        skipped += 1
                        errors.append(f"{entity_id}: Entität ist nicht verfügbar.")
                        continue

                    try:
                        payload = await self._async_build_payload(state)
                        if payload is None:
                            skipped += 1
                            errors.append(
                                f"{entity_id}: keine automatische Geräteart verfügbar."
                            )
                            continue

                        saved = await self.client.async_save_device(payload)
                        if saved["created"]:
                            created += 1
                        else:
                            updated += 1
                    except Exception as exception:
                        skipped += 1
                        errors.append(f"{entity_id}: {exception}")

                result = {
                    "success": not errors,
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "errors": errors,
                }

            now = datetime.now(timezone.utc).isoformat()
            result["direction"] = DIRECTION_HA_TO_IOVO
            result["finished_at"] = now
            self._data["last_sync"] = now
            self._data["last_result"] = result
            await self._store.async_save(self._data)
            return result

    def _refresh_state_listener(self) -> None:
        if self._cancel_state_listener is not None:
            self._cancel_state_listener()
            self._cancel_state_listener = None

        if not bool(
            self.options.get(
                CONF_DEVICE_STATE_SYNC,
                DEFAULT_DEVICE_STATE_SYNC,
            )
        ):
            return

        entity_ids = self._selected_entity_ids()
        if not entity_ids:
            return

        self._cancel_state_listener = async_track_state_change_event(
            self.hass,
            entity_ids,
            self._async_state_changed,
        )

    @callback
    def _async_state_changed(self, event: Event) -> None:
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        if not isinstance(new_state, State):
            return

        if isinstance(old_state, State):
            old_type = self._detect_type(old_state)
            new_type = self._detect_type(new_state)
            if old_type == new_type:
                old_data = self._state_payload(old_state, old_type)
                new_data = self._state_payload(new_state, new_type)
                if old_data == new_data:
                    return

        self.hass.async_create_task(
            self._async_push_state_change(new_state)
        )

    async def _async_push_state_change(self, state: State) -> None:
        try:
            await self._async_refresh_room_map()
            payload = await self._async_build_payload(state)
            if payload is None:
                return
            await self.client.async_save_device(payload)
        except Exception:
            return

    def _selected_entity_ids(self) -> list[str]:
        mode = str(
            self.options.get(
                CONF_DEVICE_SELECTION_MODE,
                DEFAULT_DEVICE_SELECTION_MODE,
            )
        )
        selected_types = {
            str(item)
            for item in self.options.get(CONF_DEVICE_TYPES, [])
            if str(item)
        }
        selected_entities = {
            str(item)
            for item in self.options.get(CONF_DEVICE_ENTITIES, [])
            if str(item)
        }
        excluded = {
            str(item)
            for item in self.options.get(CONF_DEVICE_EXCLUDED_ENTITIES, [])
            if str(item)
        }

        result: set[str] = set()

        if mode == DEVICE_SELECTION_ALL:
            for state in self.hass.states.async_all():
                if self._detect_type(state) is not None:
                    result.add(state.entity_id)
        elif mode == DEVICE_SELECTION_TYPES:
            if selected_types:
                for state in self.hass.states.async_all():
                    if self._detect_type(state) in selected_types:
                        result.add(state.entity_id)
        elif mode == DEVICE_SELECTION_ENTITIES:
            result.update(selected_entities)
        elif mode == DEVICE_SELECTION_TYPES_AND_ENTITIES:
            result.update(selected_entities)
            if selected_types:
                for state in self.hass.states.async_all():
                    if self._detect_type(state) in selected_types:
                        result.add(state.entity_id)

        result.difference_update(excluded)
        return sorted(result)

    async def _async_refresh_room_map(self, force: bool = False) -> None:
        now = datetime.now(timezone.utc)
        if (
            not force
            and self._room_map_loaded_at is not None
            and now - self._room_map_loaded_at < timedelta(minutes=5)
        ):
            return

        rooms = await self.client.async_get_rooms()
        self._room_map = {
            str(room["identifiers"]): str(room["id"])
            for room in rooms
            if room.get("identifiers")
        }
        self._room_map_loaded_at = now

    async def _async_build_payload(self, state: State) -> dict[str, Any] | None:
        device_type = self._detect_type(state)
        if device_type is None:
            return None

        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        entity = entity_registry.async_get(state.entity_id)
        device = None
        metadata_device = None
        area_id = None

        if entity is not None:
            area_id = entity.area_id

            if entity.device_id:
                device = device_registry.async_get(entity.device_id)

        if device is not None:
            if area_id is None:
                area_id = dr.async_get_effective_area_id(self.hass, device)

            metadata_device = device
            parent_device_id = getattr(device, "parent_device_id", None)
            if parent_device_id:
                parent = device_registry.async_get(parent_device_id)
                if parent is not None:
                    metadata_device = parent

        device_class = self._device_class(state, entity)
        domain = state.entity_id.split(".", 1)[0]
        payload: dict[str, Any] = {
            "device_id": state.entity_id,
            "designation": state.name,
            "type": device_type,
            "platform": self._platform_for_domain(domain),
            "state": state.state,
        }

        if device_class:
            payload["device_class"] = device_class

        if area_id is None:
            payload["Rooms_idRooms"] = 0
        elif area_id in self._room_map:
            payload["Rooms_idRooms"] = int(self._room_map[area_id])

        if metadata_device is not None:
            self._copy_device_metadata(payload, metadata_device)

        xdata = self._state_payload(state, device_type)
        if entity is not None and entity.platform:
            xdata["ha_integration"] = entity.platform

        hw_version = getattr(metadata_device, "hw_version", None)
        if hw_version not in (None, ""):
            xdata["hw_version"] = str(hw_version)

        if xdata:
            payload["xdata"] = xdata

        return payload

    @staticmethod
    def _copy_device_metadata(payload: dict[str, Any], device: Any) -> None:
        mapping = {
            "manufacturer": "manufacturer",
            "model": "modelnumber",
            "serial_number": "serialnumber",
            "sw_version": "sotwareversion",
        }

        for source, target in mapping.items():
            value = getattr(device, source, None)
            if value not in (None, ""):
                payload[target] = str(value)

    def _detect_type(self, state: State) -> str | None:
        domain = state.entity_id.split(".", 1)[0]
        device_class = str(state.attributes.get("device_class") or "").lower()

        direct = {
            "alarm_control_panel": "alarm",
            "camera": "camera",
            "climate": "climate",
            "cover": "cover",
            "fan": "fan",
            "lawn_mower": "lawn_mower",
            "light": "light",
            "lock": "access",
            "media_player": "media",
            "siren": "alarm",
            "switch": "switch",
            "vacuum": "vacuum",
            "valve": "valve",
            "water_heater": "water_heater",
            "weather": "weather",
        }

        if domain in direct:
            return direct[domain]

        if domain == "humidifier":
            if device_class == "dehumidifier":
                return "dehumidifier"
            return "humidifier"

        if domain == "sensor":
            sensor_classes = {
                "temperature": "temp",
                "humidity": "humidity",
                "moisture": "watersensor",
                "gas": "gas",
                "power": "power",
                "current": "power",
                "voltage": "power",
                "energy": "power",
            }
            return sensor_classes.get(device_class, "sensor")

        if domain == "binary_sensor":
            binary_classes = {
                "moisture": "watersensor",
                "motion": "motiondetect",
                "occupancy": "motiondetect",
                "presence": "motiondetect",
                "smoke": "smokedetector",
                "gas": "gas",
                "connectivity": "network",
            }
            return binary_classes.get(device_class, "sensor")

        if domain in {"device_tracker", "air_quality"}:
            return "sensor"

        return None

    @staticmethod
    def _device_class(state: State, entity: Any) -> str:
        value = state.attributes.get("device_class")
        if value not in (None, ""):
            return str(value)

        if entity is not None:
            for attribute in ("device_class", "original_device_class"):
                value = getattr(entity, attribute, None)
                if value not in (None, ""):
                    return str(value)

        return ""

    @staticmethod
    def _platform_for_domain(domain: str) -> str:
        if domain in {
            "air_quality",
            "binary_sensor",
            "camera",
            "device_tracker",
            "sensor",
            "weather",
        }:
            return "sensor"

        return "device"

    @staticmethod
    def _state_payload(state: State, device_type: str | None) -> dict[str, Any]:
        if device_type is None:
            return {}

        attributes = state.attributes
        keys: set[str] = set()

        if device_type in {
            "sensor",
            "temp",
            "humidity",
            "watersensor",
            "gas",
            "power",
        }:
            keys.update({"unit_of_measurement", "state_class"})

        if device_type == "light":
            keys.update({"brightness", "color_temp_kelvin", "rgb_color", "effect"})
        elif device_type == "media":
            keys.update(
                {
                    "volume_level",
                    "is_volume_muted",
                    "media_title",
                    "media_artist",
                    "source",
                }
            )
        elif device_type == "climate":
            keys.update(
                {
                    "current_temperature",
                    "temperature",
                    "hvac_action",
                    "preset_mode",
                    "fan_mode",
                    "humidity",
                }
            )
        elif device_type == "cover":
            keys.update({"current_position", "current_tilt_position"})
        elif device_type == "fan":
            keys.update({"percentage", "preset_mode"})
        elif device_type in {"humidifier", "dehumidifier"}:
            keys.update({"humidity", "current_humidity", "mode"})
        elif device_type == "vacuum":
            keys.update({"battery_level", "fan_speed", "status"})
        elif device_type == "lawn_mower":
            keys.update({"battery_level"})
        elif device_type == "valve":
            keys.update({"current_position"})
        elif device_type == "water_heater":
            keys.update({"current_temperature", "temperature", "operation_mode"})
        elif device_type == "weather":
            keys.update(
                {
                    "temperature",
                    "humidity",
                    "pressure",
                    "wind_speed",
                    "wind_bearing",
                    "visibility",
                    "pressure_unit",
                    "wind_speed_unit",
                    "temperature_unit",
                    "precipitation_unit",
                }
            )

        return {
            key: attributes[key]
            for key in keys
            if key in attributes and attributes[key] is not None
        }
