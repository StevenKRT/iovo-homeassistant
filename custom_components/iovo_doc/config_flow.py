from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
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
    AUTO_DEVICE_TYPES,
    CONF_API_KEY,
    CONF_AUTO_SYNC,
    CONF_CONFLICT_PRIORITY,
    CONF_DEVICE_ENTITIES,
    CONF_DEVICE_EXCLUDED_ENTITIES,
    CONF_DEVICE_SELECTION_MODE,
    CONF_DEVICE_STATE_SYNC,
    CONF_DEVICE_TYPES,
    CONF_PARENT_ENTRY_ID,
    CONF_RESOURCE,
    CONF_SECRET,
    CONF_SYNC_DIRECTION,
    CONF_SYNC_INTERVAL,
    CONFLICT_HA,
    CONFLICT_IOVO,
    DEFAULT_AUTO_SYNC,
    DEFAULT_CONFLICT_PRIORITY,
    DEFAULT_DEVICE_SELECTION_MODE,
    DEFAULT_DEVICE_STATE_SYNC,
    DEFAULT_SYNC_DIRECTION,
    DEFAULT_SYNC_INTERVAL,
    DEVICE_SELECTION_ALL,
    DEVICE_SELECTION_ENTITIES,
    DEVICE_SELECTION_TYPES,
    DEVICE_SELECTION_TYPES_AND_ENTITIES,
    DEVICE_TYPE_LABELS,
    DEVICES_ENTRY_TITLE,
    DEVICES_UNIQUE_ID,
    DIRECTION_BIDIRECTIONAL,
    DIRECTION_HA_TO_IOVO,
    DIRECTION_IOVO_TO_HA,
    DOMAIN,
    FLOORS_ENTRY_TITLE,
    FLOORS_UNIQUE_ID,
    RESOURCE_DEVICES,
    RESOURCE_FLOORS,
    RESOURCE_ROOMS,
    ROOMS_ENTRY_TITLE,
    ROOMS_UNIQUE_ID,
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
    VERSION = 6
    MINOR_VERSION = 0

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        await self.async_set_unique_id(ROOMS_UNIQUE_ID)
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
                    title=ROOMS_ENTRY_TITLE,
                    data={
                        CONF_API_KEY: api_key,
                        CONF_SECRET: secret,
                        CONF_RESOURCE: RESOURCE_ROOMS,
                    },
                    options=self._default_options(RESOURCE_ROOMS),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_credentials_schema(user_input),
            errors=errors,
        )

    async def async_step_import(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        data = user_input or {}
        resource = str(data.get(CONF_RESOURCE, ""))

        if resource not in {RESOURCE_FLOORS, RESOURCE_DEVICES}:
            return self.async_abort(reason="unsupported")

        parent_entry_id = str(data.get(CONF_PARENT_ENTRY_ID, "")).strip()
        if not parent_entry_id:
            return self.async_abort(reason="unsupported")

        if resource == RESOURCE_FLOORS:
            unique_id = FLOORS_UNIQUE_ID
            title = FLOORS_ENTRY_TITLE
        else:
            unique_id = DEVICES_UNIQUE_ID
            title = DEVICES_ENTRY_TITLE

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=title,
            data={
                CONF_RESOURCE: resource,
                CONF_PARENT_ENTRY_ID: parent_entry_id,
            },
            options=self._default_options(resource),
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

        if entry.data.get(CONF_RESOURCE, RESOURCE_ROOMS) != RESOURCE_ROOMS:
            return self.async_abort(reason="unsupported")

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
    def _default_options(resource: str) -> dict[str, Any]:
        if resource == RESOURCE_DEVICES:
            return {
                CONF_DEVICE_SELECTION_MODE: DEFAULT_DEVICE_SELECTION_MODE,
                CONF_DEVICE_TYPES: [],
                CONF_DEVICE_ENTITIES: [],
                CONF_DEVICE_EXCLUDED_ENTITIES: [],
                CONF_DEVICE_STATE_SYNC: DEFAULT_DEVICE_STATE_SYNC,
            }

        return {
            CONF_AUTO_SYNC: DEFAULT_AUTO_SYNC,
            CONF_SYNC_DIRECTION: DEFAULT_SYNC_DIRECTION,
            CONF_SYNC_INTERVAL: DEFAULT_SYNC_INTERVAL,
            CONF_CONFLICT_PRIORITY: DEFAULT_CONFLICT_PRIORITY,
        }

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
        resource = self.config_entry.data.get(
            CONF_RESOURCE,
            RESOURCE_ROOMS,
        )

        if resource == RESOURCE_DEVICES:
            return self.async_show_menu(
                step_id="init",
                menu_options=[
                    "device_selection",
                    "sync",
                    "device_states",
                ],
            )

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "sync",
                "automatic",
            ],
        )

    async def async_step_device_selection(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        options = dict(self.config_entry.options)

        if user_input is not None:
            options.update(user_input)
            return self.async_create_entry(data=options)

        mode_options = [
            SelectOptionDict(label="Alle unterstützten Entitäten", value=DEVICE_SELECTION_ALL),
            SelectOptionDict(label="Nach Arten auswählen", value=DEVICE_SELECTION_TYPES),
            SelectOptionDict(label="Einzelne Entitäten auswählen", value=DEVICE_SELECTION_ENTITIES),
            SelectOptionDict(
                label="Arten und einzelne Entitäten kombinieren",
                value=DEVICE_SELECTION_TYPES_AND_ENTITIES,
            ),
        ]
        type_options = [
            SelectOptionDict(
                label=DEVICE_TYPE_LABELS.get(device_type, device_type),
                value=device_type,
            )
            for device_type in AUTO_DEVICE_TYPES
        ]

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_SELECTION_MODE,
                    default=options.get(
                        CONF_DEVICE_SELECTION_MODE,
                        DEFAULT_DEVICE_SELECTION_MODE,
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(options=mode_options)
                ),
                vol.Optional(
                    CONF_DEVICE_TYPES,
                    default=list(options.get(CONF_DEVICE_TYPES, [])),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=type_options,
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_DEVICE_ENTITIES,
                    default=list(options.get(CONF_DEVICE_ENTITIES, [])),
                ): EntitySelector(
                    EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(
                    CONF_DEVICE_EXCLUDED_ENTITIES,
                    default=list(
                        options.get(
                            CONF_DEVICE_EXCLUDED_ENTITIES,
                            [],
                        )
                    ),
                ): EntitySelector(
                    EntitySelectorConfig(multiple=True)
                ),
            }
        )

        return self.async_show_form(
            step_id="device_selection",
            data_schema=schema,
        )

    async def async_step_device_states(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        options = dict(self.config_entry.options)

        if user_input is not None:
            options.update(user_input)
            return self.async_create_entry(data=options)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DEVICE_STATE_SYNC,
                    default=bool(
                        options.get(
                            CONF_DEVICE_STATE_SYNC,
                            DEFAULT_DEVICE_STATE_SYNC,
                        )
                    ),
                ): bool,
            }
        )

        return self.async_show_form(
            step_id="device_states",
            data_schema=schema,
        )

    async def async_step_sync(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        resource = self.config_entry.data.get(
            CONF_RESOURCE,
            RESOURCE_ROOMS,
        )

        if resource == RESOURCE_DEVICES:
            if user_input is not None:
                runtime = self.config_entry.runtime_data

                try:
                    result = await runtime.sync.async_sync(
                        DIRECTION_HA_TO_IOVO
                    )
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
                    self._sync_result = self._format_sync_result(
                        result,
                        RESOURCE_DEVICES,
                    )
                    return await self.async_step_sync_done()

            return self.async_show_form(
                step_id="sync",
                data_schema=vol.Schema({}),
                errors=errors,
            )

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
                self._sync_result = self._format_sync_result(
                    result,
                    str(resource),
                )
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
        resource: str,
    ) -> str:
        if resource == RESOURCE_DEVICES and result.get("empty_selection"):
            return "Keine Geräte ausgewählt."

        created = int(result.get("created", 0))
        updated = int(result.get("updated", 0))
        linked = int(result.get("linked", 0))
        assigned = int(result.get("assigned", 0))
        unchanged = int(result.get("unchanged", 0))
        skipped = int(result.get("skipped", 0))
        conflicts = int(result.get("conflicts", 0))

        if resource == RESOURCE_FLOORS:
            singular = "Stockwerk"
            plural = "Stockwerke"
        elif resource == RESOURCE_DEVICES:
            singular = "Gerät"
            plural = "Geräte"
        else:
            singular = "Raum"
            plural = "Räume"

        def count_text(count: int, singular_text: str, plural_text: str) -> str:
            return f"{count} {singular_text if count == 1 else plural_text}"

        parts: list[str] = []

        if created:
            parts.append(f"{count_text(created, singular, plural)} angelegt")

        if updated:
            parts.append(f"{count_text(updated, singular, plural)} aktualisiert")

        if linked:
            parts.append(f"{count_text(linked, singular, plural)} zugeordnet")

        if assigned:
            parts.append(
                f"{count_text(assigned, 'Raumzuordnung', 'Raumzuordnungen')} aktualisiert"
            )

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
