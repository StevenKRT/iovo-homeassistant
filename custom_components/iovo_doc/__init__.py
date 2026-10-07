from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IovoApiClient
from .const import CONF_API_KEY, CONF_SECRET, ENTRY_TITLE, UNIQUE_ID
from .sync import IovoRoomSync


@dataclass(slots=True)
class IovoRuntimeData:
    client: IovoApiClient
    sync: IovoRoomSync


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

    entry.runtime_data = IovoRuntimeData(
        client=client,
        sync=sync,
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
    await runtime.sync.async_shutdown()
    return True


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
