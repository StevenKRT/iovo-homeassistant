from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .api import IovoApiClient
from .const import (
    CONFLICT_HA,
    CONF_AUTO_SYNC,
    CONF_CONFLICT_PRIORITY,
    CONF_SYNC_DIRECTION,
    CONF_SYNC_INTERVAL,
    DEFAULT_AUTO_SYNC,
    DEFAULT_CONFLICT_PRIORITY,
    DEFAULT_SYNC_DIRECTION,
    DEFAULT_SYNC_INTERVAL,
    DIRECTION_BIDIRECTIONAL,
    DIRECTION_HA_TO_IOVO,
    DIRECTION_IOVO_TO_HA,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
)


class IovoRoomSync:
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
        self._cancel_auto: Callable[[], None] | None = None

    async def async_initialize(self) -> None:
        stored = await self._store.async_load()

        if isinstance(stored, dict):
            self._data = stored
        else:
            self._data = {}

        self._data.setdefault("mappings", {})
        self._data.setdefault("last_sync", None)
        self._data.setdefault("last_result", None)

        self._schedule_auto_sync()

    async def async_shutdown(self) -> None:
        if self._cancel_auto is not None:
            self._cancel_auto()
            self._cancel_auto = None

    async def async_sync(
        self,
        direction: str,
    ) -> dict[str, Any]:
        async with self._lock:
            await self.client.async_connect()

            if direction == DIRECTION_IOVO_TO_HA:
                result = await self._async_iovo_to_ha()
            elif direction == DIRECTION_HA_TO_IOVO:
                result = await self._async_ha_to_iovo()
            elif direction == DIRECTION_BIDIRECTIONAL:
                result = await self._async_bidirectional()
            else:
                raise ValueError("Ungültige Synchronisationsrichtung.")

            now = datetime.now(timezone.utc).isoformat()
            result["direction"] = direction
            result["finished_at"] = now

            self._data["last_sync"] = now
            self._data["last_result"] = result

            await self._async_save()

            return result

    def _schedule_auto_sync(self) -> None:
        if self._cancel_auto is not None:
            self._cancel_auto()
            self._cancel_auto = None

        enabled = bool(
            self.options.get(
                CONF_AUTO_SYNC,
                DEFAULT_AUTO_SYNC,
            )
        )

        if not enabled:
            return

        interval_minutes = int(
            self.options.get(
                CONF_SYNC_INTERVAL,
                DEFAULT_SYNC_INTERVAL,
            )
        )
        interval_minutes = min(max(interval_minutes, 1), 1440)

        direction = self.options.get(
            CONF_SYNC_DIRECTION,
            DEFAULT_SYNC_DIRECTION,
        )

        async def _run(_: datetime) -> None:
            try:
                await self.async_sync(direction)
            except Exception:
                return

        self._cancel_auto = async_track_time_interval(
            self.hass,
            _run,
            timedelta(minutes=interval_minutes),
        )

    async def _async_iovo_to_ha(self) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        registry = ar.async_get(self.hass)
        mappings = self._data["mappings"]
        names = self._build_area_names(rooms)

        created = 0
        updated = 0
        linked = 0
        skipped = 0
        errors: list[str] = []

        claimed_area_ids = {
            mapping.get("area_id")
            for mapping in mappings.values()
            if isinstance(mapping, dict)
        }

        for room in rooms:
            room_id = room["id"]
            area_name = names[room_id]
            mapping = mappings.get(room_id)
            area = None

            if isinstance(mapping, dict):
                area_id = mapping.get("area_id")

                if isinstance(area_id, str):
                    area = registry.async_get_area(area_id)

            if area is None:
                exact = registry.async_get_area_by_name(area_name)

                if exact is not None and exact.id not in claimed_area_ids:
                    area = exact
                    linked += 1
                else:
                    try:
                        area = registry.async_create(area_name)
                        created += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

                claimed_area_ids.add(area.id)

            if area.name != area_name:
                try:
                    area = registry.async_update(
                        area.id,
                        name=area_name,
                    )
                    updated += 1
                except ValueError as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            mappings[room_id] = {
                "area_id": area.id,
                "last_iovo_name": room["name"],
                "last_ha_name": area.name,
            }

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "skipped": skipped,
            "conflicts": 0,
            "errors": errors,
        }

    async def _async_ha_to_iovo(self) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        registry = ar.async_get(self.hass)
        areas = list(registry.async_list_areas())
        mappings = self._data["mappings"]
        names = self._build_area_names(rooms)

        self._link_exact_matches(
            rooms,
            areas,
            names,
        )

        rooms_by_id = {
            room["id"]: room
            for room in rooms
        }
        areas_by_id = {
            area.id: area
            for area in areas
        }

        updated = 0
        skipped = 0
        errors: list[str] = []
        mapped_area_ids: set[str] = set()

        for room_id, mapping in list(mappings.items()):
            if not isinstance(mapping, dict):
                continue

            area_id = mapping.get("area_id")

            if not isinstance(area_id, str):
                continue

            mapped_area_ids.add(area_id)
            room = rooms_by_id.get(room_id)
            area = areas_by_id.get(area_id)

            if room is None or area is None:
                continue

            if area.name != names.get(room_id, room["name"]):
                try:
                    await self.client.async_update_room(
                        room_id,
                        area.name,
                    )
                    updated += 1
                except Exception as exception:
                    errors.append(str(exception))
                    continue

            mapping["last_iovo_name"] = area.name
            mapping["last_ha_name"] = area.name

        for area in areas:
            if area.id not in mapped_area_ids:
                skipped += 1

        return {
            "success": not errors,
            "created": 0,
            "updated": updated,
            "linked": 0,
            "skipped": skipped,
            "conflicts": 0,
            "errors": errors,
            "create_supported": self.client.can_create_rooms,
        }

    async def _async_bidirectional(self) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        registry = ar.async_get(self.hass)
        areas = list(registry.async_list_areas())
        mappings = self._data["mappings"]
        names = self._build_area_names(rooms)

        self._link_exact_matches(
            rooms,
            areas,
            names,
        )

        claimed_area_ids = {
            mapping.get("area_id")
            for mapping in mappings.values()
            if isinstance(mapping, dict)
        }

        created = 0
        linked = 0
        updated = 0
        skipped = 0
        conflicts = 0
        errors: list[str] = []

        for room in rooms:
            room_id = room["id"]

            if room_id in mappings:
                continue

            area_name = names[room_id]
            exact = registry.async_get_area_by_name(area_name)

            if exact is not None and exact.id not in claimed_area_ids:
                area = exact
                linked += 1
            else:
                try:
                    area = registry.async_create(area_name)
                    created += 1
                except ValueError as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            claimed_area_ids.add(area.id)
            mappings[room_id] = {
                "area_id": area.id,
                "last_iovo_name": room["name"],
                "last_ha_name": area.name,
            }

        areas = list(registry.async_list_areas())
        rooms_by_id = {
            room["id"]: room
            for room in rooms
        }
        areas_by_id = {
            area.id: area
            for area in areas
        }
        mapped_area_ids: set[str] = set()

        for room_id, mapping in list(mappings.items()):
            if not isinstance(mapping, dict):
                continue

            area_id = mapping.get("area_id")

            if not isinstance(area_id, str):
                continue

            mapped_area_ids.add(area_id)
            room = rooms_by_id.get(room_id)
            area = areas_by_id.get(area_id)

            if room is None or area is None:
                continue

            current_iovo = room["name"]
            current_ha = area.name
            last_iovo = mapping.get("last_iovo_name", current_iovo)
            last_ha = mapping.get("last_ha_name", current_ha)

            iovo_changed = current_iovo != last_iovo
            ha_changed = current_ha != last_ha

            if not iovo_changed and not ha_changed:
                continue

            if iovo_changed and not ha_changed:
                target = names.get(room_id, current_iovo)

                if current_ha != target:
                    try:
                        area = registry.async_update(
                            area.id,
                            name=target,
                        )
                        current_ha = area.name
                        updated += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        continue
            elif ha_changed and not iovo_changed:
                try:
                    await self.client.async_update_room(
                        room_id,
                        current_ha,
                    )
                    current_iovo = current_ha
                    updated += 1
                except Exception as exception:
                    errors.append(str(exception))
                    continue
            else:
                conflicts += 1

                if (
                    self.options.get(
                        CONF_CONFLICT_PRIORITY,
                        DEFAULT_CONFLICT_PRIORITY,
                    )
                    == CONFLICT_HA
                ):
                    try:
                        await self.client.async_update_room(
                            room_id,
                            current_ha,
                        )
                        current_iovo = current_ha
                        updated += 1
                    except Exception as exception:
                        errors.append(str(exception))
                        continue
                else:
                    target = names.get(room_id, current_iovo)

                    try:
                        area = registry.async_update(
                            area.id,
                            name=target,
                        )
                        current_ha = area.name
                        updated += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        continue

            mapping["last_iovo_name"] = current_iovo
            mapping["last_ha_name"] = current_ha

        for area in areas:
            if area.id not in mapped_area_ids:
                skipped += 1

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "skipped": skipped,
            "conflicts": conflicts,
            "errors": errors,
            "create_supported": self.client.can_create_rooms,
        }

    def _link_exact_matches(
        self,
        rooms: list[dict[str, Any]],
        areas: list[Any],
        names: dict[str, str],
    ) -> None:
        mappings = self._data["mappings"]
        mapped_area_ids = {
            mapping.get("area_id")
            for mapping in mappings.values()
            if isinstance(mapping, dict)
        }

        available_by_name = {
            area.name: area
            for area in areas
            if area.id not in mapped_area_ids
        }

        for room in rooms:
            room_id = room["id"]

            if room_id in mappings:
                continue

            area = available_by_name.get(names[room_id])

            if area is None:
                continue

            mappings[room_id] = {
                "area_id": area.id,
                "last_iovo_name": room["name"],
                "last_ha_name": area.name,
            }
            mapped_area_ids.add(area.id)

    def _build_area_names(
        self,
        rooms: list[dict[str, Any]],
    ) -> dict[str, str]:
        name_counts = Counter(
            room["name"].casefold()
            for room in rooms
        )
        used: set[str] = set()
        result: dict[str, str] = {}

        for room in rooms:
            base = room["name"]

            if name_counts[base.casefold()] > 1:
                qualifier = (
                    room.get("shortdescription")
                    or room.get("identifiers")
                    or room.get("label")
                )

                if qualifier:
                    candidate = f"{base} ({qualifier})"
                else:
                    candidate = base
            else:
                candidate = base

            original = candidate
            counter = 2

            while candidate.casefold() in used:
                candidate = f"{original} {counter}"
                counter += 1

            used.add(candidate.casefold())
            result[room["id"]] = candidate

        return result

    async def _async_save(self) -> None:
        await self._store.async_save(self._data)
