from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import IovoApiClient
from .const import (
    CONF_API_KEY,
    CONF_PARENT_ENTRY_ID,
    CONF_RESOURCE,
    CONF_SECRET,
    DEVICES_ENTRY_TITLE,
    DEVICES_UNIQUE_ID,
    DOMAIN,
    FLOORS_ENTRY_TITLE,
    FLOORS_UNIQUE_ID,
    LOADED_VERSION,
    RESOURCE_DEVICES,
    RESOURCE_FLOORS,
    RESOURCE_ROOMS,
    ROOMS_ENTRY_TITLE,
    ROOMS_UNIQUE_ID,
)
from .device_sync import IovoDeviceSync
from .floor_sync import IovoFloorSync
from .sync import IovoRoomSync

RESTART_ISSUE_ID = "restart_required"
VERSION_CHECK_INTERVAL = timedelta(minutes=1)


@dataclass(slots=True)
class IovoRuntimeData:
    client: IovoApiClient
    sync: IovoRoomSync | IovoFloorSync | IovoDeviceSync
    cancel_version_check: Callable[[], None] | None = None


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    return True


def _resource_for_entry(entry: ConfigEntry) -> str:
    return str(entry.data.get(CONF_RESOURCE, RESOURCE_ROOMS))


def _find_entry(hass: HomeAssistant, entry_id: str) -> ConfigEntry | None:
    for candidate in hass.config_entries.async_entries(DOMAIN):
        if candidate.entry_id == entry_id:
            return candidate
    return None


def _credentials_for_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> tuple[str, str]:
    resource = _resource_for_entry(entry)

    if resource == RESOURCE_ROOMS:
        return (
            str(entry.data[CONF_API_KEY]),
            str(entry.data[CONF_SECRET]),
        )

    parent_entry_id = str(entry.data.get(CONF_PARENT_ENTRY_ID, ""))
    parent = _find_entry(hass, parent_entry_id)

    if parent is None:
        raise ValueError("Der zugehörige Räume-Eintrag wurde nicht gefunden.")

    return (
        str(parent.data[CONF_API_KEY]),
        str(parent.data[CONF_SECRET]),
    )


def _entry_identity(resource: str) -> tuple[str, str]:
    if resource == RESOURCE_FLOORS:
        return FLOORS_ENTRY_TITLE, FLOORS_UNIQUE_ID

    if resource == RESOURCE_DEVICES:
        return DEVICES_ENTRY_TITLE, DEVICES_UNIQUE_ID

    return ROOMS_ENTRY_TITLE, ROOMS_UNIQUE_ID


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    data = dict(entry.data)

    if "username" in data and CONF_API_KEY not in data:
        data[CONF_API_KEY] = data.pop("username")

    if "password" in data and CONF_SECRET not in data:
        data[CONF_SECRET] = data.pop("password")

    resource = str(data.get(CONF_RESOURCE, RESOURCE_ROOMS))
    data[CONF_RESOURCE] = resource
    title, unique_id = _entry_identity(resource)

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        title=title,
        unique_id=unique_id,
        version=6,
        minor_version=0,
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    resource = _resource_for_entry(entry)
    expected_title, expected_unique_id = _entry_identity(resource)

    if entry.title != expected_title or entry.unique_id != expected_unique_id:
        hass.config_entries.async_update_entry(
            entry,
            title=expected_title,
            unique_id=expected_unique_id,
        )

    api_key, secret = _credentials_for_entry(hass, entry)
    client = IovoApiClient(
        async_get_clientsession(hass),
        api_key,
        secret,
    )

    if resource == RESOURCE_FLOORS:
        sync: IovoRoomSync | IovoFloorSync | IovoDeviceSync = IovoFloorSync(
            hass,
            entry.entry_id,
            client,
            dict(entry.options),
        )
    elif resource == RESOURCE_DEVICES:
        sync = IovoDeviceSync(
            hass,
            entry.entry_id,
            client,
            dict(entry.options),
        )
    else:
        sync = IovoRoomSync(
            hass,
            entry.entry_id,
            client,
            dict(entry.options),
        )

    await sync.async_initialize()

    cancel_version_check: Callable[[], None] | None = None

    if resource == RESOURCE_ROOMS:
        await _async_check_restart_required(hass)

        async def _check_version(_: datetime) -> None:
            await _async_check_restart_required(hass)

        cancel_version_check = async_track_time_interval(
            hass,
            _check_version,
            VERSION_CHECK_INTERVAL,
        )

    entry.runtime_data = IovoRuntimeData(
        client=client,
        sync=sync,
        cancel_version_check=cancel_version_check,
    )

    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    if resource == RESOURCE_ROOMS:
        await _async_ensure_child_entry(
            hass,
            entry,
            RESOURCE_FLOORS,
            FLOORS_UNIQUE_ID,
        )
        await _async_ensure_child_entry(
            hass,
            entry,
            RESOURCE_DEVICES,
            DEVICES_UNIQUE_ID,
        )

    return True


async def _async_ensure_child_entry(
    hass: HomeAssistant,
    rooms_entry: ConfigEntry,
    resource: str,
    unique_id: str,
) -> None:
    for candidate in hass.config_entries.async_entries(DOMAIN):
        if candidate.unique_id == unique_id:
            return
        if _resource_for_entry(candidate) == resource:
            return

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={
            CONF_RESOURCE: resource,
            CONF_PARENT_ENTRY_ID: rooms_entry.entry_id,
        },
    )


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    runtime = entry.runtime_data

    if runtime.cancel_version_check is not None:
        runtime.cancel_version_check()

    await runtime.sync.async_shutdown()
    return True


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

    if _resource_for_entry(entry) != RESOURCE_ROOMS:
        return

    for candidate in hass.config_entries.async_entries(DOMAIN):
        if candidate.entry_id == entry.entry_id:
            continue

        if _resource_for_entry(candidate) in {
            RESOURCE_FLOORS,
            RESOURCE_DEVICES,
        }:
            await hass.config_entries.async_reload(candidate.entry_id)


async def _async_check_restart_required(
    hass: HomeAssistant,
) -> None:
    installed_version = await hass.async_add_executor_job(
        _read_installed_version
    )

    if installed_version and installed_version != LOADED_VERSION:
        ir.async_create_issue(
            hass,
            DOMAIN,
            RESTART_ISSUE_ID,
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="restart_required",
            translation_placeholders={
                "loaded_version": LOADED_VERSION,
                "installed_version": installed_version,
            },
        )
        return

    ir.async_delete_issue(
        hass,
        DOMAIN,
        RESTART_ISSUE_ID,
    )


def _read_installed_version() -> str:
    manifest_path = Path(__file__).with_name("manifest.json")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""

    version = manifest.get("version", "")
    return str(version).strip()
