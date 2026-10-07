from __future__ import annotations

from typing import Any


import voluptuous as vol

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
    CONF_SECRET,
    CONF_AUTO_SYNC,
    CONF_CONFLICT_PRIORITY,
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
    ENTRY_TITLE,
    UNIQUE_ID,
)


def _credentials_schema(
    values: dict[str, Any] | None = None,
) -> vol.Schema:
    values = values or {}

    return vol.Schema(
        {
            vol.Required(
                CONF_API_KEY,
                description={
                    "suggested_value": values.get(CONF_API_KEY)
                },
            ): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.TEXT,
                )
            ),
            vol.Required(
                CONF_SECRET,
            ): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD,
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
    VERSION = 4
    MINOR_VERSION = 0

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
                errors["base"] = "access_denied"
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
                    title=ENTRY_TITLE,
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
                errors["base"] = "access_denied"
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
                errors["base"] = "access_denied"
            except IovoConnectionError:
                errors["base"] = "cannot_connect"
            except IovoApiError:
                errors["base"] = "api_error"
            except Exception:
                errors["base"] = "unknown"
            else:
                self._sync_result = self._format_sync_result(result)
                return await self.async_step_sync_done()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SYNC_DIRECTION,
                    default=DEFAULT_SYNC_DIRECTION,
                ): vol.In(
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
            data_schema=vol.Schema({}),
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

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AUTO_SYNC,
                    default=bool(
                        options.get(
                            CONF_AUTO_SYNC,
                            DEFAULT_AUTO_SYNC,
                        )
                    ),
                ): bool,
                vol.Required(
                    CONF_SYNC_DIRECTION,
                    default=options.get(
                        CONF_SYNC_DIRECTION,
                        DEFAULT_SYNC_DIRECTION,
                    ),
                ): vol.In(
                    {
                        DIRECTION_IOVO_TO_HA: "iovo|doc → Home Assistant",
                        DIRECTION_HA_TO_IOVO: "Home Assistant → iovo|doc",
                        DIRECTION_BIDIRECTIONAL: "Beide Richtungen",
                    }
                ),
                vol.Required(
                    CONF_SYNC_INTERVAL,
                    default=int(
                        options.get(
                            CONF_SYNC_INTERVAL,
                            DEFAULT_SYNC_INTERVAL,
                        )
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=1,
                        max=1440,
                    ),
                ),
                vol.Required(
                    CONF_CONFLICT_PRIORITY,
                    default=options.get(
                        CONF_CONFLICT_PRIORITY,
                        DEFAULT_CONFLICT_PRIORITY,
                    ),
                ): vol.In(
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
        created = int(result.get("created", 0))
        updated = int(result.get("updated", 0))
        linked = int(result.get("linked", 0))
        unchanged = int(result.get("unchanged", 0))
        skipped = int(result.get("skipped", 0))
        conflicts = int(result.get("conflicts", 0))

        parts: list[str] = []

        if created:
            parts.append(f"{created} Räume angelegt")

        if updated:
            parts.append(f"{updated} Räume aktualisiert")

        if linked:
            parts.append(f"{linked} Räume zugeordnet")

        if unchanged:
            parts.append(f"{unchanged} unverändert")

        if conflicts:
            parts.append(f"{conflicts} Konflikte aufgelöst")

        if skipped:
            parts.append(f"{skipped} nicht verarbeitet")

        if not parts:
            return "Keine Änderungen notwendig."

        text = ", ".join(parts) + "."
        errors = [
            str(error).strip()
            for error in result.get("errors", [])
            if str(error).strip()
        ]
        unique_errors = list(dict.fromkeys(errors))

        if unique_errors:
            reason = "; ".join(unique_errors[:3])

            if len(unique_errors) > 3:
                reason += f"; {len(unique_errors) - 3} weitere Fehler"

            text += f" Grund: {reason}."

        return text
