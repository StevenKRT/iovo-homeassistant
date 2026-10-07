from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import IovoApiClient
from .const import (
    CONF_API_KEY,
    CONF_SECRET,
    DOMAIN,
    ENTRY_TITLE,
    LOADED_VERSION,
    UNIQUE_ID,
)
from .sync import IovoRoomSync

RESTART_ISSUE_ID = "restart_required"
VERSION_CHECK_INTERVAL = timedelta(minutes=1)


@dataclass(slots=True)
class IovoRuntimeData:
    client: IovoApiClient
    sync: IovoRoomSync
    cancel_version_check: Callable[[], None] | None = None


async def async_setup(
    hass: HomeAssistant,
    config: dict,
) -> bool:
    return True


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    data = dict(entry.data)

    if "username" in data and CONF_API_KEY not in data:
        data[CONF_API_KEY] = data.pop("username")

    if "password" in data and CONF_SECRET not in data:
        data[CONF_SECRET] = data.pop("password")

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        title=ENTRY_TITLE,
        unique_id=UNIQUE_ID,
        version=4,
        minor_version=0,
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    if entry.title != ENTRY_TITLE or entry.unique_id != UNIQUE_ID:
        hass.config_entries.async_update_entry(
            entry,
            title=ENTRY_TITLE,
            unique_id=UNIQUE_ID,
        )

    client = IovoApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_KEY],
        entry.data[CONF_SECRET],
    )

    sync = IovoRoomSync(
        hass,
        entry.entry_id,
        client,
        dict(entry.options),
    )
    await sync.async_initialize()

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

    return True


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
