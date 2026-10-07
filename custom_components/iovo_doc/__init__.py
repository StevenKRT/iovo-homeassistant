from __future__ import annotations

from dataclasses import dataclass


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import IovoApiClient
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
    if entry.version == 1:
        data = dict(entry.data)

        if "api_key" in data and CONF_USERNAME not in data:
            data[CONF_USERNAME] = data.pop("api_key")

        if "secret" in data and CONF_PASSWORD not in data:
            data[CONF_PASSWORD] = data.pop("secret")

        hass.config_entries.async_update_entry(
            entry,
            data=data,
            version=2,
            minor_version=0,
        )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    client = IovoApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
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
