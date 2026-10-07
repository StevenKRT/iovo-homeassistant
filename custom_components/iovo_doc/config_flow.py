from __future__ import annotations

from typing import Any

import probatio

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    IovoApiClient,
    IovoApiError,
    IovoAuthError,
    IovoConnectionError,
    IovoPermissionError,
    IovoUnsupportedError,
)
from .const import (
    CONF_API_KEY,
    CONF_AUTO_SYNC,
    CONF_CONFLICT_PRIORITY,
    CONF_SECRET,
    CONF_SYNC_DIRECTION,
    CONF_SYNC_INTERVAL,
    CONFLICT_HA,
    CONFLICT_IOVO,
    DEFAULT_AUTO_SYNC,
    DEFAULT_CONFLICT_PRIORITY,
    DEFAULT_SYNC_DIRECTION,
    DEFAULT_SYNC_INTERVAL,
    DIRECTION_BIDIRECTIONAL,
    DIRECTION_HA_TO_IOVO,
    DIRECTION_IOVO_TO_HA,
    DOMAIN,
    UNIQUE_ID,
)


def _credentials_schema(
    values: dict[str, Any] | None = None,
) -> probatio.Schema:
    values = values or {}

    return probatio.Schema(
        {
            probatio.Required(
                CONF_API_KEY,
                description={
                    "suggested_value": values.get(CONF_API_KEY)
                },
            ): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.TEXT,
                    autocomplete="username",
                )
            ),
            probatio.Required(
                CONF_SECRET,
            ): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                )
            ),
        }
    )


async def _async_validate_credentials(
    hass,
    api_key: str,
    secret: str,
) -> None:
    client = IovoApiClient(
        async_get_clientsession(hass),
        api_key,
        secret,
    )
    await client.async_connect()


class IovoConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        await self.async_set_unique_id(UNIQUE_ID)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            api_key = str(user_input[CONF_API_KEY]).strip()
            secret = str(user_input[CONF_SECRET]).strip()

            try:
                await _async_validate_credentials(
                    self.hass,
                    api_key,
                    secret,
                )
            except IovoAuthError:
                errors["base"] = "invalid_auth"
            except IovoPermissionError:
                errors["base"] = "forbidden"
            except IovoConnectionError:
                errors["base"] = "cannot_connect"
            except IovoUnsupportedError:
                errors["base"] = "unsupported"
            except IovoApiError:
                errors["base"] = "api_error"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="iovo|doc",
                    data={
                        CONF_API_KEY: api_key,
                        CONF_SECRET: secret,
                    },
                    options={
                        CONF_AUTO_SYNC: DEFAULT_AUTO_SYNC,
                        CONF_SYNC_DIRECTION: DEFAULT_SYNC_DIRECTION,
                        CONF_SYNC_INTERVAL: DEFAULT_SYNC_INTERVAL,
                        CONF_CONFLICT_PRIORITY: DEFAULT_CONFLICT_PRIORITY,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            api_key = str(user_input[CONF_API_KEY]).strip()
            secret = str(user_input[CONF_SECRET]).strip()

            try:
                await _async_validate_credentials(
                    self.hass,
                    api_key,
                    secret,
                )
            except IovoAuthError:
                errors["base"] = "invalid_auth"
            except IovoPermissionError:
                errors["base"] = "forbidden"
            except IovoConnectionError:
                errors["base"] = "cannot_connect"
            except IovoUnsupportedError:
                errors["base"] = "unsupported"
            except IovoApiError:
                errors["base"] = "api_error"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_API_KEY: api_key,
                        CONF_SECRET: secret,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_credentials_schema(
                {
                    CONF_API_KEY: entry.data.get(
                        CONF_API_KEY,
                        "",
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return IovoOptionsFlow()


class IovoOptionsFlow(
    config_entries.OptionsFlow,
):
    def __init__(self) -> None:
        self._sync_result = ""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "sync",
                "automatic",
            ],
        )

    async def async_step_sync(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            direction = user_input[CONF_SYNC_DIRECTION]
            runtime = self.config_entry.runtime_data

            try:
                result = await runtime.sync.async_sync(direction)
            except IovoAuthError:
                errors["base"] = "invalid_auth"
            except IovoPermissionError:
                errors["base"] = "forbidden"
            except IovoConnectionError:
                errors["base"] = "cannot_connect"
            except IovoApiError:
                errors["base"] = "api_error"
            except Exception:
                errors["base"] = "unknown"
            else:
                self._sync_result = self._format_sync_result(result)
                return await self.async_step_sync_done()

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_SYNC_DIRECTION,
                    default=DEFAULT_SYNC_DIRECTION,
                ): probatio.In(
                    {
                        DIRECTION_IOVO_TO_HA: "iovo|doc → Home Assistant",
                        DIRECTION_HA_TO_IOVO: "Home Assistant → iovo|doc",
                        DIRECTION_BIDIRECTIONAL: "Beide Richtungen",
                    }
                )
            }
        )

        return self.async_show_form(
            step_id="sync",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_sync_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self.async_step_init()

        return self.async_show_form(
            step_id="sync_done",
            data_schema=probatio.Schema({}),
            description_placeholders={
                "result": self._sync_result,
            },
        )

    async def async_step_automatic(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        options = dict(self.config_entry.options)

        if user_input is not None:
            options.update(user_input)
            return self.async_create_entry(
                data=options,
            )

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_AUTO_SYNC,
                    default=bool(
                        options.get(
                            CONF_AUTO_SYNC,
                            DEFAULT_AUTO_SYNC,
                        )
                    ),
                ): bool,
                probatio.Required(
                    CONF_SYNC_DIRECTION,
                    default=options.get(
                        CONF_SYNC_DIRECTION,
                        DEFAULT_SYNC_DIRECTION,
                    ),
                ): probatio.In(
                    {
                        DIRECTION_IOVO_TO_HA: "iovo|doc → Home Assistant",
                        DIRECTION_HA_TO_IOVO: "Home Assistant → iovo|doc",
                        DIRECTION_BIDIRECTIONAL: "Beide Richtungen",
                    }
                ),
                probatio.Required(
                    CONF_SYNC_INTERVAL,
                    default=int(
                        options.get(
                            CONF_SYNC_INTERVAL,
                            DEFAULT_SYNC_INTERVAL,
                        )
                    ),
                ): probatio.All(
                    probatio.Coerce(int),
                    probatio.Range(
                        min=1,
                        max=1440,
                    ),
                ),
                probatio.Required(
                    CONF_CONFLICT_PRIORITY,
                    default=options.get(
                        CONF_CONFLICT_PRIORITY,
                        DEFAULT_CONFLICT_PRIORITY,
                    ),
                ): probatio.In(
                    {
                        CONFLICT_IOVO: "iovo|doc",
                        CONFLICT_HA: "Home Assistant",
                    }
                ),
            }
        )

        return self.async_show_form(
            step_id="automatic",
            data_schema=schema,
        )

    @staticmethod
    def _format_sync_result(
        result: dict[str, Any],
    ) -> str:
        parts = [
            f"{int(result.get('created', 0))} angelegt",
            f"{int(result.get('updated', 0))} aktualisiert",
            f"{int(result.get('linked', 0))} zugeordnet",
        ]

        skipped = int(result.get("skipped", 0))
        conflicts = int(result.get("conflicts", 0))

        if skipped:
            parts.append(f"{skipped} nicht übertragen")

        if conflicts:
            parts.append(f"{conflicts} Konflikte aufgelöst")

        return ", ".join(parts) + "."
