from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
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

        self._data.setdefault("states", {})
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
        names = self._build_area_names(rooms)

        created = 0
        updated = 0
        linked = 0
        skipped = 0
        unchanged = 0
        errors: list[str] = []
        claimed_area_ids: set[str] = set()

        for room in rooms:
            room_id = room["id"]
            target_name = names[room_id]
            identifier = room.get("identifiers", "")
            area = registry.async_get_area(identifier) if identifier else None

            if area is not None and area.id in claimed_area_ids:
                area = None

            if area is None:
                exact = registry.async_get_area_by_name(target_name)

                if exact is not None and exact.id not in claimed_area_ids:
                    area = exact
                else:
                    try:
                        area = registry.async_create(target_name)
                        created += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

            claimed_area_ids.add(area.id)
            changed = False

            if area.name != target_name:
                try:
                    area = registry.async_update(
                        area.id,
                        name=target_name,
                    )
                    updated += 1
                    changed = True
                except ValueError as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            if identifier != area.id:
                try:
                    await self.client.async_save_room(
                        area_id=area.id,
                        name=room["name"],
                        room_id=room_id,
                    )
                    room["identifiers"] = area.id
                    linked += 1
                    changed = True
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            if not changed and area.name == target_name:
                unchanged += 1

            self._remember_state(
                area.id,
                room_id,
                room["name"],
                area.name,
            )

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": 0,
            "errors": errors,
        }

    async def _async_ha_to_iovo(self) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        registry = ar.async_get(self.hass)
        areas = list(registry.async_list_areas())

        rooms_by_identifier = {
            room["identifiers"]: room
            for room in rooms
            if room.get("identifiers")
        }
        unnamed_by_name = self._rooms_without_identifier_by_name(rooms)
        claimed_room_ids: set[str] = set()

        created = 0
        updated = 0
        linked = 0
        unchanged = 0
        skipped = 0
        errors: list[str] = []

        for area in areas:
            room = rooms_by_identifier.get(area.id)

            if room is None:
                candidates = [
                    candidate
                    for candidate in unnamed_by_name.get(area.name, [])
                    if candidate["id"] not in claimed_room_ids
                ]

                if len(candidates) == 1:
                    room = candidates[0]

            if room is None:
                if not self.client.can_create_rooms:
                    skipped += 1
                    errors.append(
                        f"Raum '{area.name}' kann in iovo|doc nicht angelegt werden."
                    )
                    continue

                try:
                    saved = await self.client.async_save_room(
                        area_id=area.id,
                        name=area.name,
                    )

                    if saved["created"]:
                        created += 1
                    else:
                        updated += 1

                    room_id = saved["id"]
                    self._remember_state(
                        area.id,
                        room_id,
                        area.name,
                        area.name,
                    )
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1

                continue

            claimed_room_ids.add(room["id"])
            needs_name_update = room["name"] != area.name
            needs_identifier_update = room.get("identifiers", "") != area.id

            if needs_name_update or needs_identifier_update:
                try:
                    await self.client.async_save_room(
                        area_id=area.id,
                        name=area.name,
                        room_id=room["id"],
                    )
                    updated += 1

                    if needs_identifier_update:
                        linked += 1
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue
            else:
                unchanged += 1

            self._remember_state(
                area.id,
                room["id"],
                area.name,
                area.name,
            )

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": 0,
            "errors": errors,
        }

    async def _async_bidirectional(self) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        registry = ar.async_get(self.hass)
        names = self._build_area_names(rooms)
        states = self._data["states"]

        created = 0
        updated = 0
        linked = 0
        unchanged = 0
        skipped = 0
        conflicts = 0
        errors: list[str] = []
        claimed_area_ids: set[str] = set()

        for room in rooms:
            room_id = room["id"]
            identifier = room.get("identifiers", "")
            area = registry.async_get_area(identifier) if identifier else None

            if area is None:
                target_name = names[room_id]
                exact = registry.async_get_area_by_name(target_name)

                if exact is not None and exact.id not in claimed_area_ids:
                    area = exact
                else:
                    try:
                        area = registry.async_create(target_name)
                        created += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

                try:
                    await self.client.async_save_room(
                        area_id=area.id,
                        name=room["name"],
                        room_id=room_id,
                    )
                    room["identifiers"] = area.id
                    linked += 1
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            claimed_area_ids.add(area.id)
            state = states.get(area.id, {})
            current_iovo = room["name"]
            current_ha = area.name
            last_iovo = state.get("last_iovo_name")
            last_ha = state.get("last_ha_name")

            if last_iovo is None or last_ha is None:
                iovo_changed = current_iovo != current_ha
                ha_changed = current_iovo != current_ha
            else:
                iovo_changed = current_iovo != last_iovo
                ha_changed = current_ha != last_ha

            if not iovo_changed and not ha_changed:
                unchanged += 1
            elif iovo_changed and not ha_changed:
                try:
                    area = registry.async_update(
                        area.id,
                        name=names.get(room_id, current_iovo),
                    )
                    current_ha = area.name
                    updated += 1
                except ValueError as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue
            elif ha_changed and not iovo_changed:
                try:
                    await self.client.async_save_room(
                        area_id=area.id,
                        name=current_ha,
                        room_id=room_id,
                    )
                    current_iovo = current_ha
                    updated += 1
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
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
                        await self.client.async_save_room(
                            area_id=area.id,
                            name=current_ha,
                            room_id=room_id,
                        )
                        current_iovo = current_ha
                        updated += 1
                    except Exception as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue
                else:
                    try:
                        area = registry.async_update(
                            area.id,
                            name=names.get(room_id, current_iovo),
                        )
                        current_ha = area.name
                        updated += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

            self._remember_state(
                area.id,
                room_id,
                current_iovo,
                current_ha,
            )

        areas = list(registry.async_list_areas())
        room_identifiers = {
            room.get("identifiers", "")
            for room in rooms
            if room.get("identifiers")
        }
        unnamed_by_name = self._rooms_without_identifier_by_name(rooms)
        claimed_room_ids = {
            room["id"]
            for room in rooms
            if room.get("identifiers") in claimed_area_ids
        }

        for area in areas:
            if area.id in room_identifiers:
                continue

            candidates = [
                candidate
                for candidate in unnamed_by_name.get(area.name, [])
                if candidate["id"] not in claimed_room_ids
            ]
            room = candidates[0] if len(candidates) == 1 else None

            try:
                if room is not None:
                    saved = await self.client.async_save_room(
                        area_id=area.id,
                        name=area.name,
                        room_id=room["id"],
                    )
                    linked += 1
                    updated += 1
                else:
                    saved = await self.client.async_save_room(
                        area_id=area.id,
                        name=area.name,
                    )

                    if saved["created"]:
                        created += 1
                    else:
                        updated += 1

                self._remember_state(
                    area.id,
                    saved["id"],
                    area.name,
                    area.name,
                )
            except Exception as exception:
                errors.append(str(exception))
                skipped += 1

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": conflicts,
            "errors": errors,
        }

    def _rooms_without_identifier_by_name(
        self,
        rooms: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for room in rooms:
            if not room.get("identifiers"):
                result[room["name"]].append(room)

        return result

    def _remember_state(
        self,
        area_id: str,
        room_id: str,
        iovo_name: str,
        ha_name: str,
    ) -> None:
        self._data["states"][area_id] = {
            "room_id": str(room_id),
            "last_iovo_name": iovo_name,
            "last_ha_name": ha_name,
        }

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
                    or room.get("label")
                    or room.get("identifiers")
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
