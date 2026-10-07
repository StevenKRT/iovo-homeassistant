from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import floor_registry as fr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .api import IovoApiClient
from .const import (
    CONF_AUTO_SYNC,
    CONF_CONFLICT_PRIORITY,
    CONF_SYNC_DIRECTION,
    CONF_SYNC_INTERVAL,
    CONFLICT_HA,
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


class IovoFloorSync:
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
        self._data.setdefault("assignments", {})
        self._data.setdefault("last_sync", None)
        self._data.setdefault("last_result", None)
        self._schedule_auto_sync()

    async def async_shutdown(self) -> None:
        if self._cancel_auto is not None:
            self._cancel_auto()
            self._cancel_auto = None

    async def async_sync(self, direction: str) -> dict[str, Any]:
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
            await self._store.async_save(self._data)
            return result

    def _schedule_auto_sync(self) -> None:
        if self._cancel_auto is not None:
            self._cancel_auto()
            self._cancel_auto = None

        if not bool(self.options.get(CONF_AUTO_SYNC, DEFAULT_AUTO_SYNC)):
            return

        interval_minutes = int(
            self.options.get(CONF_SYNC_INTERVAL, DEFAULT_SYNC_INTERVAL)
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
        iovo_floors = await self.client.async_get_floors()
        registry = fr.async_get(self.hass)
        names = self._build_floor_names(iovo_floors)

        created = 0
        updated = 0
        linked = 0
        unchanged = 0
        skipped = 0
        errors: list[str] = []
        claimed_ha_floor_ids: set[str] = set()
        iovo_to_ha: dict[str, str] = {}

        for item in iovo_floors:
            iovo_floor_id = item["id"]
            identifier = item.get("identifiers", "")
            floor = registry.async_get_floor(identifier) if identifier else None
            target_name = names[iovo_floor_id]

            if floor is None:
                exact = registry.async_get_floor_by_name(target_name)

                if exact is not None and exact.floor_id not in claimed_ha_floor_ids:
                    floor = exact
                else:
                    try:
                        floor = registry.async_create(
                            target_name,
                            level=item.get("level"),
                        )
                        created += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

            claimed_ha_floor_ids.add(floor.floor_id)
            changed = False

            if floor.name != target_name or floor.level != item.get("level"):
                try:
                    floor = registry.async_update(
                        floor.floor_id,
                        name=target_name,
                        level=item.get("level"),
                    )
                    updated += 1
                    changed = True
                except ValueError as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            if identifier != floor.floor_id:
                try:
                    await self.client.async_save_floor(
                        ha_floor_id=floor.floor_id,
                        name=item["name"],
                        level=item.get("level"),
                        iovo_floor_id=iovo_floor_id,
                    )
                    item["identifiers"] = floor.floor_id
                    linked += 1
                    changed = True
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            if not changed:
                unchanged += 1

            iovo_to_ha[iovo_floor_id] = floor.floor_id
            self._remember_floor_state(
                floor.floor_id,
                iovo_floor_id,
                item["name"],
                floor.name,
                item.get("level"),
                floor.level,
            )

        assignment_result = await self._async_apply_iovo_assignments_to_ha(
            iovo_to_ha
        )
        skipped += assignment_result["skipped"]
        errors.extend(assignment_result["errors"])

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "assigned": assignment_result["assigned"],
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": 0,
            "errors": errors,
        }

    async def _async_ha_to_iovo(self) -> dict[str, Any]:
        iovo_floors = await self.client.async_get_floors()
        registry = fr.async_get(self.hass)
        ha_floors = list(registry.async_list_floors())

        by_identifier = {
            item["identifiers"]: item
            for item in iovo_floors
            if item.get("identifiers")
        }
        unnamed_by_name = self._floors_without_identifier_by_name(iovo_floors)
        claimed_iovo_floor_ids: set[str] = set()
        ha_to_iovo: dict[str, str] = {}

        created = 0
        updated = 0
        linked = 0
        unchanged = 0
        skipped = 0
        errors: list[str] = []

        for floor in ha_floors:
            item = by_identifier.get(floor.floor_id)

            if item is None:
                candidates = [
                    candidate
                    for candidate in unnamed_by_name.get(floor.name, [])
                    if candidate["id"] not in claimed_iovo_floor_ids
                ]
                if len(candidates) == 1:
                    item = candidates[0]

            if item is None:
                try:
                    saved = await self.client.async_save_floor(
                        ha_floor_id=floor.floor_id,
                        name=floor.name,
                        level=floor.level,
                    )
                    if saved["created"]:
                        created += 1
                    else:
                        updated += 1
                    iovo_floor_id = saved["id"]
                    ha_to_iovo[floor.floor_id] = iovo_floor_id
                    self._remember_floor_state(
                        floor.floor_id,
                        iovo_floor_id,
                        floor.name,
                        floor.name,
                        floor.level,
                        floor.level,
                    )
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                continue

            claimed_iovo_floor_ids.add(item["id"])
            needs_update = (
                item["name"] != floor.name
                or item.get("identifiers", "") != floor.floor_id
                or item.get("level") != floor.level
            )

            if needs_update:
                try:
                    await self.client.async_save_floor(
                        ha_floor_id=floor.floor_id,
                        name=floor.name,
                        level=floor.level,
                        iovo_floor_id=item["id"],
                    )
                    updated += 1
                    if item.get("identifiers", "") != floor.floor_id:
                        linked += 1
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue
            else:
                unchanged += 1

            ha_to_iovo[floor.floor_id] = item["id"]
            self._remember_floor_state(
                floor.floor_id,
                item["id"],
                floor.name,
                floor.name,
                floor.level,
                floor.level,
            )

        assignment_result = await self._async_apply_ha_assignments_to_iovo(
            ha_to_iovo
        )
        skipped += assignment_result["skipped"]
        errors.extend(assignment_result["errors"])

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "assigned": assignment_result["assigned"],
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": 0,
            "errors": errors,
        }

    async def _async_bidirectional(self) -> dict[str, Any]:
        iovo_floors = await self.client.async_get_floors()
        registry = fr.async_get(self.hass)
        names = self._build_floor_names(iovo_floors)
        floor_states = self._data["states"]

        created = 0
        updated = 0
        linked = 0
        unchanged = 0
        skipped = 0
        conflicts = 0
        errors: list[str] = []
        claimed_ha_floor_ids: set[str] = set()
        iovo_to_ha: dict[str, str] = {}
        ha_to_iovo: dict[str, str] = {}

        for item in iovo_floors:
            iovo_floor_id = item["id"]
            identifier = item.get("identifiers", "")
            floor = registry.async_get_floor(identifier) if identifier else None

            if floor is None:
                target_name = names[iovo_floor_id]
                exact = registry.async_get_floor_by_name(target_name)

                if exact is not None and exact.floor_id not in claimed_ha_floor_ids:
                    floor = exact
                else:
                    try:
                        floor = registry.async_create(
                            target_name,
                            level=item.get("level"),
                        )
                        created += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

                try:
                    await self.client.async_save_floor(
                        ha_floor_id=floor.floor_id,
                        name=item["name"],
                        level=item.get("level"),
                        iovo_floor_id=iovo_floor_id,
                    )
                    linked += 1
                    item["identifiers"] = floor.floor_id
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            claimed_ha_floor_ids.add(floor.floor_id)
            iovo_to_ha[iovo_floor_id] = floor.floor_id
            ha_to_iovo[floor.floor_id] = iovo_floor_id

            state = floor_states.get(floor.floor_id, {})
            current_iovo_name = item["name"]
            current_ha_name = floor.name
            current_iovo_level = item.get("level")
            current_ha_level = floor.level
            last_iovo_name = state.get("last_iovo_name")
            last_ha_name = state.get("last_ha_name")
            last_iovo_level = state.get("last_iovo_level")
            last_ha_level = state.get("last_ha_level")

            if last_iovo_name is None or last_ha_name is None:
                iovo_changed = (
                    current_iovo_name != current_ha_name
                    or current_iovo_level != current_ha_level
                )
                ha_changed = iovo_changed
            else:
                iovo_changed = (
                    current_iovo_name != last_iovo_name
                    or current_iovo_level != last_iovo_level
                )
                ha_changed = (
                    current_ha_name != last_ha_name
                    or current_ha_level != last_ha_level
                )

            if not iovo_changed and not ha_changed:
                unchanged += 1
            elif iovo_changed and not ha_changed:
                try:
                    floor = registry.async_update(
                        floor.floor_id,
                        name=names.get(iovo_floor_id, current_iovo_name),
                        level=current_iovo_level,
                    )
                    current_ha_name = floor.name
                    current_ha_level = floor.level
                    updated += 1
                except ValueError as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue
            elif ha_changed and not iovo_changed:
                try:
                    await self.client.async_save_floor(
                        ha_floor_id=floor.floor_id,
                        name=current_ha_name,
                        level=current_ha_level,
                        iovo_floor_id=iovo_floor_id,
                    )
                    current_iovo_name = current_ha_name
                    current_iovo_level = current_ha_level
                    updated += 1
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue
            else:
                conflicts += 1
                if self.options.get(
                    CONF_CONFLICT_PRIORITY,
                    DEFAULT_CONFLICT_PRIORITY,
                ) == CONFLICT_HA:
                    try:
                        await self.client.async_save_floor(
                            ha_floor_id=floor.floor_id,
                            name=current_ha_name,
                            level=current_ha_level,
                            iovo_floor_id=iovo_floor_id,
                        )
                        current_iovo_name = current_ha_name
                        current_iovo_level = current_ha_level
                        updated += 1
                    except Exception as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue
                else:
                    try:
                        floor = registry.async_update(
                            floor.floor_id,
                            name=names.get(iovo_floor_id, current_iovo_name),
                            level=current_iovo_level,
                        )
                        current_ha_name = floor.name
                        current_ha_level = floor.level
                        updated += 1
                    except ValueError as exception:
                        errors.append(str(exception))
                        skipped += 1
                        continue

            self._remember_floor_state(
                floor.floor_id,
                iovo_floor_id,
                current_iovo_name,
                current_ha_name,
                current_iovo_level,
                current_ha_level,
            )

        for floor in list(registry.async_list_floors()):
            if floor.floor_id in claimed_ha_floor_ids:
                continue

            try:
                saved = await self.client.async_save_floor(
                    ha_floor_id=floor.floor_id,
                    name=floor.name,
                    level=floor.level,
                )
                if saved["created"]:
                    created += 1
                else:
                    updated += 1
                iovo_to_ha[saved["id"]] = floor.floor_id
                ha_to_iovo[floor.floor_id] = saved["id"]
                self._remember_floor_state(
                    floor.floor_id,
                    saved["id"],
                    floor.name,
                    floor.name,
                    floor.level,
                    floor.level,
                )
            except Exception as exception:
                errors.append(str(exception))
                skipped += 1

        assignment_result = await self._async_bidirectional_assignments(
            iovo_to_ha,
            ha_to_iovo,
        )
        skipped += assignment_result["skipped"]
        conflicts += assignment_result["conflicts"]
        errors.extend(assignment_result["errors"])

        return {
            "success": not errors,
            "created": created,
            "updated": updated,
            "linked": linked,
            "assigned": assignment_result["assigned"],
            "unchanged": unchanged,
            "skipped": skipped,
            "conflicts": conflicts,
            "errors": errors,
        }

    async def _async_apply_ha_assignments_to_iovo(
        self,
        ha_to_iovo: dict[str, str],
    ) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        areas = ar.async_get(self.hass)
        assigned = 0
        skipped = 0
        errors: list[str] = []

        for room in rooms:
            area_id = room.get("identifiers", "")
            if not area_id:
                continue

            area = areas.async_get_area(area_id)
            if area is None:
                continue

            desired_iovo_floor_id = "0"
            if area.floor_id:
                mapped = ha_to_iovo.get(area.floor_id)
                if mapped is None:
                    skipped += 1
                    errors.append(
                        f"Stockwerk für Bereich '{area.name}' konnte nicht zugeordnet werden."
                    )
                    continue
                desired_iovo_floor_id = mapped

            current_iovo_floor_id = str(room.get("Floors_idFloors") or "0")
            if current_iovo_floor_id != desired_iovo_floor_id:
                try:
                    await self.client.async_set_room_floor(
                        room["id"],
                        desired_iovo_floor_id,
                    )
                    assigned += 1
                except Exception as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            self._remember_assignment(
                area.id,
                area.floor_id or "",
                area.floor_id or "",
            )

        return {
            "assigned": assigned,
            "skipped": skipped,
            "errors": errors,
        }

    async def _async_apply_iovo_assignments_to_ha(
        self,
        iovo_to_ha: dict[str, str],
    ) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        areas = ar.async_get(self.hass)
        assigned = 0
        skipped = 0
        errors: list[str] = []

        for room in rooms:
            area_id = room.get("identifiers", "")
            if not area_id:
                continue

            area = areas.async_get_area(area_id)
            if area is None:
                continue

            iovo_floor_id = str(room.get("Floors_idFloors") or "0")
            desired_ha_floor_id = ""

            if iovo_floor_id != "0":
                mapped = iovo_to_ha.get(iovo_floor_id)
                if mapped is None:
                    skipped += 1
                    errors.append(
                        f"Stockwerk für Raum '{room['name']}' konnte nicht zugeordnet werden."
                    )
                    continue
                desired_ha_floor_id = mapped

            if (area.floor_id or "") != desired_ha_floor_id:
                try:
                    area = areas.async_update(
                        area.id,
                        floor_id=desired_ha_floor_id or None,
                    )
                    assigned += 1
                except (KeyError, ValueError) as exception:
                    errors.append(str(exception))
                    skipped += 1
                    continue

            self._remember_assignment(
                area.id,
                desired_ha_floor_id,
                desired_ha_floor_id,
            )

        return {
            "assigned": assigned,
            "skipped": skipped,
            "errors": errors,
        }

    async def _async_bidirectional_assignments(
        self,
        iovo_to_ha: dict[str, str],
        ha_to_iovo: dict[str, str],
    ) -> dict[str, Any]:
        rooms = await self.client.async_get_rooms()
        areas = ar.async_get(self.hass)
        assignment_states = self._data["assignments"]
        assigned = 0
        skipped = 0
        conflicts = 0
        errors: list[str] = []

        for room in rooms:
            area_id = room.get("identifiers", "")
            if not area_id:
                continue

            area = areas.async_get_area(area_id)
            if area is None:
                continue

            current_iovo_id = str(room.get("Floors_idFloors") or "0")
            current_iovo_ha_id = ""
            if current_iovo_id != "0":
                current_iovo_ha_id = iovo_to_ha.get(current_iovo_id, "")

            current_ha_id = area.floor_id or ""
            state = assignment_states.get(area.id, {})
            last_iovo_ha_id = state.get("last_iovo_floor_id")
            last_ha_id = state.get("last_ha_floor_id")

            if last_iovo_ha_id is None or last_ha_id is None:
                iovo_changed = current_iovo_ha_id != current_ha_id
                ha_changed = iovo_changed
            else:
                iovo_changed = current_iovo_ha_id != last_iovo_ha_id
                ha_changed = current_ha_id != last_ha_id

            if current_iovo_ha_id == current_ha_id:
                self._remember_assignment(
                    area.id,
                    current_iovo_ha_id,
                    current_ha_id,
                )
                continue

            try:
                if iovo_changed and not ha_changed:
                    area = areas.async_update(
                        area.id,
                        floor_id=current_iovo_ha_id or None,
                    )
                    current_ha_id = area.floor_id or ""
                    assigned += 1
                elif ha_changed and not iovo_changed:
                    target_iovo_id = (
                        ha_to_iovo.get(current_ha_id, "0")
                        if current_ha_id
                        else "0"
                    )
                    await self.client.async_set_room_floor(
                        room["id"],
                        target_iovo_id,
                    )
                    current_iovo_ha_id = current_ha_id
                    assigned += 1
                else:
                    conflicts += 1
                    if self.options.get(
                        CONF_CONFLICT_PRIORITY,
                        DEFAULT_CONFLICT_PRIORITY,
                    ) == CONFLICT_HA:
                        target_iovo_id = (
                            ha_to_iovo.get(current_ha_id, "0")
                            if current_ha_id
                            else "0"
                        )
                        await self.client.async_set_room_floor(
                            room["id"],
                            target_iovo_id,
                        )
                        current_iovo_ha_id = current_ha_id
                    else:
                        area = areas.async_update(
                            area.id,
                            floor_id=current_iovo_ha_id or None,
                        )
                        current_ha_id = area.floor_id or ""
                    assigned += 1
            except Exception as exception:
                errors.append(str(exception))
                skipped += 1
                continue

            self._remember_assignment(
                area.id,
                current_iovo_ha_id,
                current_ha_id,
            )

        return {
            "assigned": assigned,
            "skipped": skipped,
            "conflicts": conflicts,
            "errors": errors,
        }

    def _floors_without_identifier_by_name(
        self,
        floors: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for floor in floors:
            if not floor.get("identifiers"):
                result[floor["name"]].append(floor)
        return result

    def _build_floor_names(
        self,
        floors: list[dict[str, Any]],
    ) -> dict[str, str]:
        name_counts = Counter(floor["name"].casefold() for floor in floors)
        used: set[str] = set()
        result: dict[str, str] = {}

        for floor in floors:
            base = floor["name"]
            if name_counts[base.casefold()] > 1:
                qualifier = floor.get("identifiers") or floor["id"]
                candidate = f"{base} ({qualifier})"
            else:
                candidate = base

            original = candidate
            counter = 2
            while candidate.casefold() in used:
                candidate = f"{original} {counter}"
                counter += 1

            used.add(candidate.casefold())
            result[floor["id"]] = candidate

        return result

    def _remember_floor_state(
        self,
        ha_floor_id: str,
        iovo_floor_id: str,
        iovo_name: str,
        ha_name: str,
        iovo_level: int | None,
        ha_level: int | None,
    ) -> None:
        self._data["states"][ha_floor_id] = {
            "iovo_floor_id": str(iovo_floor_id),
            "last_iovo_name": iovo_name,
            "last_ha_name": ha_name,
            "last_iovo_level": iovo_level,
            "last_ha_level": ha_level,
        }

    def _remember_assignment(
        self,
        area_id: str,
        iovo_floor_id: str,
        ha_floor_id: str,
    ) -> None:
        self._data["assignments"][area_id] = {
            "last_iovo_floor_id": iovo_floor_id,
            "last_ha_floor_id": ha_floor_id,
        }
