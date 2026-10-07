from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IovoApiClient
from .const import CONF_API_KEY, CONF_SECRET
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
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
