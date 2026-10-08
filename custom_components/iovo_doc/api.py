from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import aiohttp
from aiohttp import (
    ClientError,
    ClientResponse,
    ClientSession,
)
from aiohttp.hdrs import ACCEPT, AUTHORIZATION, USER_AGENT

from .const import (
    API_BASE_URL,
    CONNECTION_ENDPOINT,
    DEFAULT_COMMANDS_ENDPOINT,
    DEFAULT_DEVICES_ENDPOINT,
    DEFAULT_FLOORS_ENDPOINT,
    DEFAULT_ROOMS_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


class IovoApiError(Exception):
    pass


class IovoAuthError(IovoApiError):
    pass


class IovoPermissionError(IovoApiError):
    pass


class IovoConnectionError(IovoApiError):
    pass


class IovoUnsupportedError(IovoApiError):
    pass


class IovoApiClient:
    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        secret: str,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._secret = secret
        self._resources: dict[str, dict[str, Any]] = {}

    @property
    def rooms_endpoint(self) -> str:
        rooms = self._resources.get("rooms", {})
        endpoint = rooms.get("endpoint")

        if isinstance(endpoint, str) and endpoint.startswith("/"):
            return endpoint

        return DEFAULT_ROOMS_ENDPOINT

    @property
    def devices_endpoint(self) -> str:
        devices = self._resources.get("devices", {})
        endpoint = devices.get("endpoint")

        if isinstance(endpoint, str) and endpoint.startswith("/"):
            return endpoint

        return DEFAULT_DEVICES_ENDPOINT

    @property
    def floors_endpoint(self) -> str:
        floors = self._resources.get("floors", {})
        endpoint = floors.get("endpoint")

        if isinstance(endpoint, str) and endpoint.startswith("/"):
            return endpoint

        return DEFAULT_FLOORS_ENDPOINT


    @property
    def commands_endpoint(self) -> str:
        commands = self._resources.get("commands", {})
        endpoint = commands.get("endpoint")

        if isinstance(endpoint, str) and endpoint.startswith("/"):
            return endpoint

        return DEFAULT_COMMANDS_ENDPOINT

    @property
    def can_read_commands(self) -> bool:
        commands = self._resources.get("commands", {})
        return bool(
            commands.get("active", False)
            and commands.get("read", False)
        )

    @property
    def can_update_commands(self) -> bool:
        commands = self._resources.get("commands", {})
        return bool(
            commands.get("active", False)
            and commands.get("update", False)
        )

    @property
    def can_create_devices(self) -> bool:
        devices = self._resources.get("devices", {})
        return bool(devices.get("create", False))

    @property
    def can_update_devices(self) -> bool:
        devices = self._resources.get("devices", {})
        return bool(devices.get("update", True))

    @property
    def can_create_floors(self) -> bool:
        floors = self._resources.get("floors", {})
        return bool(floors.get("create", False))

    @property
    def can_update_floors(self) -> bool:
        floors = self._resources.get("floors", {})
        return bool(floors.get("update", True))

    @property
    def can_create_rooms(self) -> bool:
        rooms = self._resources.get("rooms", {})
        return bool(rooms.get("create", False))

    @property
    def can_update_rooms(self) -> bool:
        rooms = self._resources.get("rooms", {})
        return bool(rooms.get("update", True))

    async def async_connect(self) -> dict[str, Any]:
        payload = await self._async_request(
            "GET",
            CONNECTION_ENDPOINT,
        )

        meta = payload.get("meta")
        data = payload.get("data")

        if not isinstance(meta, dict) or meta.get("valid") is not True:
            raise IovoUnsupportedError(
                "Die iovo|doc Schnittstelle hat die Anfrage nicht bestätigt."
            )

        if not isinstance(data, dict):
            raise IovoUnsupportedError(
                "Die iovo|doc Schnittstelle liefert keine Integrationsinformationen."
            )

        if data.get("integration") != "home_assistant":
            raise IovoUnsupportedError(
                "Die iovo|doc Schnittstelle ist nicht für Home Assistant freigegeben."
            )

        resources = data.get("resources", {})

        if not isinstance(resources, dict):
            resources = {}

        self._resources = resources
        return data

    async def async_get_rooms(self) -> list[dict[str, Any]]:
        payload = await self._async_request(
            "GET",
            self.rooms_endpoint,
        )

        data = payload.get("data", [])

        if data is None:
            return []

        if not isinstance(data, list):
            raise IovoApiError(
                "Die Raumdaten von iovo|doc konnten nicht verarbeitet werden."
            )

        rooms: list[dict[str, Any]] = []

        for room in data:
            if not isinstance(room, dict):
                continue

            room_id = room.get("id")
            name = room.get("text")

            if room_id is None:
                continue

            if not isinstance(name, str) or not name.strip():
                continue

            rooms.append(
                {
                    "id": str(room_id),
                    "name": name.strip(),
                    "identifiers": self._clean_string(room.get("identifiers")),
                    "label": self._clean_string(room.get("label")),
                    "shortdescription": self._clean_string(
                        room.get("shortdescription")
                    ),
                    "status": self._clean_string(room.get("status")),
                    "sizem2": self._clean_string(room.get("sizem2")),
                    "handsanitizer_sum": self._clean_string(
                        room.get("handsanitizer_sum")
                    ),
                    "Floors_idFloors": self._clean_string(
                        room.get("Floors_idFloors")
                    ),
                }
            )

        return rooms

    async def async_save_room(
        self,
        area_id: str,
        name: str,
        room_id: str | None = None,
    ) -> dict[str, Any]:
        if room_id is None and not self.can_create_rooms:
            raise IovoUnsupportedError(
                "iovo|doc erlaubt derzeit keine neuen Räume."
            )

        if room_id is not None and not self.can_update_rooms:
            raise IovoUnsupportedError(
                "iovo|doc erlaubt derzeit keine Änderungen an Räumen."
            )

        data: dict[str, Any] = {
            "description": name.strip(),
            "identifiers": area_id,
        }

        if room_id is not None:
            data["roomID"] = int(room_id)

        payload = await self._async_request(
            "POST",
            self.rooms_endpoint,
            json_data=data,
        )
        result = payload.get("data")

        if isinstance(result, dict):
            saved_id = result.get("id", room_id)
            created = bool(result.get("created", room_id is None))
        else:
            saved_id = room_id if room_id is not None else result
            created = room_id is None

        if saved_id is None:
            raise IovoApiError(
                "iovo|doc hat keine Raum-ID zurückgegeben."
            )

        return {
            "id": str(saved_id),
            "created": created,
        }

    async def async_get_floors(self) -> list[dict[str, Any]]:
        payload = await self._async_request(
            "GET",
            self.floors_endpoint,
        )

        data = payload.get("data", [])

        if data is None:
            return []

        if not isinstance(data, list):
            raise IovoApiError(
                "Die Stockwerksdaten von iovo|doc konnten nicht verarbeitet werden."
            )

        floors: list[dict[str, Any]] = []

        for floor in data:
            if not isinstance(floor, dict):
                continue

            floor_id = floor.get("id")
            name = floor.get("text")

            if floor_id is None:
                continue

            if not isinstance(name, str) or not name.strip():
                continue

            level_value = floor.get("level")
            level: int | None = None

            if level_value not in (None, ""):
                try:
                    level = int(level_value)
                except (TypeError, ValueError):
                    level = None

            floors.append(
                {
                    "id": str(floor_id),
                    "name": name.strip(),
                    "identifiers": self._clean_string(floor.get("identifiers")),
                    "level": level,
                }
            )

        return floors

    async def async_save_floor(
        self,
        ha_floor_id: str,
        name: str,
        level: int | None,
        iovo_floor_id: str | None = None,
    ) -> dict[str, Any]:
        if iovo_floor_id is None and not self.can_create_floors:
            raise IovoUnsupportedError(
                "iovo|doc erlaubt derzeit keine neuen Stockwerke."
            )

        if iovo_floor_id is not None and not self.can_update_floors:
            raise IovoUnsupportedError(
                "iovo|doc erlaubt derzeit keine Änderungen an Stockwerken."
            )

        data: dict[str, Any] = {
            "description": name.strip(),
            "identifiers": ha_floor_id,
            "level": level,
        }

        if iovo_floor_id is not None:
            data["floorID"] = int(iovo_floor_id)

        payload = await self._async_request(
            "POST",
            self.floors_endpoint,
            json_data=data,
        )
        result = payload.get("data")

        if isinstance(result, dict):
            saved_id = result.get("id", iovo_floor_id)
            created = bool(result.get("created", iovo_floor_id is None))
        else:
            saved_id = iovo_floor_id if iovo_floor_id is not None else result
            created = iovo_floor_id is None

        if saved_id is None:
            raise IovoApiError(
                "iovo|doc hat keine Stockwerks-ID zurückgegeben."
            )

        return {
            "id": str(saved_id),
            "created": created,
        }

    async def async_set_room_floor(
        self,
        room_id: str,
        iovo_floor_id: str | int | None,
    ) -> None:
        floor_id = 0 if iovo_floor_id in (None, "") else int(iovo_floor_id)

        await self._async_request(
            "POST",
            self.rooms_endpoint,
            json_data={
                "roomID": int(room_id),
                "Floors_idFloors": floor_id,
            },
        )

    async def async_save_device(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._resources:
            await self.async_connect()

        if not self.can_create_devices and not self.can_update_devices:
            raise IovoUnsupportedError(
                "iovo|doc erlaubt derzeit keine Geräteübertragung."
            )

        device_id = self._clean_string(data.get("device_id"))
        if not device_id:
            raise IovoApiError("Für das Gerät fehlt device_id.")

        payload = await self._async_request(
            "POST",
            self.devices_endpoint,
            json_data=data,
        )
        result = payload.get("data")

        if not isinstance(result, dict):
            raise IovoApiError(
                "iovo|doc hat keine gültige Geräteantwort geliefert."
            )

        saved_id = result.get("id")
        if saved_id is None:
            raise IovoApiError(
                "iovo|doc hat keine Geräte-ID zurückgegeben."
            )

        return {
            "id": str(saved_id),
            "created": bool(result.get("created", False)),
        }


    async def async_get_command(
        self,
        wait_seconds: int = 20,
    ) -> dict[str, Any] | None:
        if not self._resources:
            await self.async_connect()

        if not self.can_read_commands:
            return None

        wait_seconds = max(0, min(int(wait_seconds), 20))
        payload = await self._async_request(
            "GET",
            self.commands_endpoint,
            params_data={"wait": wait_seconds},
            timeout_seconds=wait_seconds + 10,
        )
        data = payload.get("data")

        if data is None:
            return None

        if not isinstance(data, dict):
            raise IovoApiError(
                "iovo|doc hat einen ungültigen Steuerbefehl geliefert."
            )

        command_id = data.get("id")
        device_id = self._clean_string(data.get("device_id"))
        action = self._clean_string(data.get("action"))
        command_payload = data.get("payload", {})

        if command_id is None or not device_id or not action:
            raise IovoApiError(
                "iovo|doc hat einen unvollständigen Steuerbefehl geliefert."
            )

        if command_payload is None or command_payload == []:
            command_payload = {}

        if not isinstance(command_payload, dict):
            raise IovoApiError(
                "Die Parameter des Steuerbefehls sind ungültig."
            )

        return {
            "id": int(command_id),
            "device_id": device_id,
            "action": action,
            "payload": command_payload,
        }

    async def async_finish_command(
        self,
        command_id: int,
        status: str,
        error: str = "",
    ) -> None:
        if not self._resources:
            await self.async_connect()

        if not self.can_update_commands:
            return

        data: dict[str, Any] = {
            "id": int(command_id),
            "status": status,
        }

        if error:
            data["error"] = error[:1000]

        await self._async_request(
            "POST",
            self.commands_endpoint,
            json_data=data,
        )

    def _authorization_header(self) -> str:
        encode_basic_auth = getattr(aiohttp, "encode_basic_auth", None)

        if encode_basic_auth is not None:
            return encode_basic_auth(
                self._api_key,
                self._secret,
                encoding="utf-8",
            )

        return aiohttp.BasicAuth(
            login=self._api_key,
            password=self._secret,
            encoding="utf-8",
        ).encode()

    def _request_headers(self) -> dict[str, str]:
        user_agent = self._session.headers.get(USER_AGENT)

        if not user_agent:
            raise IovoConnectionError(
                "Die Home-Assistant-HTTP-Session enthält keinen User-Agent."
            )

        user_agent = re.sub(
            r"\s+Python/[^\s]+$",
            "",
            user_agent,
        )

        return {
            ACCEPT: "application/json",
            AUTHORIZATION: self._authorization_header(),
            USER_AGENT: user_agent,
        }

    async def _async_request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
        params_data: dict[str, Any] | None = None,
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        url = f"{API_BASE_URL}{endpoint}"
        headers = self._request_headers()

        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "allow_redirects": False,
        }

        if json_data is not None:
            request_kwargs["json"] = json_data

        if params_data is not None:
            request_kwargs["params"] = params_data

        _LOGGER.debug(
            "iovo|doc API request %s %s, Basic Auth vorhanden: %s, User-Agent: %s",
            method,
            endpoint,
            AUTHORIZATION in headers,
            headers[USER_AGENT],
        )

        try:
            async with asyncio.timeout(timeout_seconds):
                async with self._session.request(
                    method,
                    url,
                    **request_kwargs,
                ) as response:
                    return await self._async_read_response(
                        response,
                        method,
                        endpoint,
                    )
        except IovoApiError:
            raise
        except (TimeoutError, ClientError) as exception:
            raise IovoConnectionError(
                "iovo|doc ist derzeit nicht erreichbar."
            ) from exception

    async def _async_read_response(
        self,
        response: ClientResponse,
        method: str,
        endpoint: str,
    ) -> dict[str, Any]:
        body = await response.text()

        _LOGGER.debug(
            "iovo|doc API %s %s -> HTTP %s",
            method,
            endpoint,
            response.status,
        )

        sent_headers = response.request_info.headers
        sent_authorization = sent_headers.get(AUTHORIZATION, "")
        sent_user_agent = sent_headers.get(USER_AGENT, "")
        sent_basic_auth = sent_authorization.startswith("Basic ")

        if response.status == 401:
            _LOGGER.warning(
                "iovo|doc API %s %s -> HTTP 401; "
                "Basic Auth tatsächlich gesendet: %s; User-Agent: %s",
                method,
                endpoint,
                sent_basic_auth,
                sent_user_agent,
            )
            raise IovoAuthError(
                "iovo|doc hat die Basic-Auth-Zugangsdaten nicht akzeptiert."
            )

        if response.status == 403:
            _LOGGER.warning(
                "iovo|doc API %s %s -> HTTP 403; "
                "Basic Auth tatsächlich gesendet: %s; User-Agent: %s; "
                "Antwort: %s",
                method,
                endpoint,
                sent_basic_auth,
                sent_user_agent,
                body[:500],
            )

            if sent_basic_auth:
                raise IovoPermissionError(
                    "iovo|doc hat HTTP 403 zurückgegeben, obwohl Basic Auth "
                    "tatsächlich gesendet wurde."
                )

            raise IovoPermissionError(
                "Home Assistant hat den Request ohne wirksame Basic Auth gesendet."
            )

        if 300 <= response.status < 400:
            location = response.headers.get("Location", "")
            _LOGGER.warning(
                "iovo|doc API hat %s %s mit HTTP %s weitergeleitet nach %s.",
                method,
                endpoint,
                response.status,
                location,
            )
            raise IovoApiError(
                "Die iovo|doc API hat die Anfrage unerwartet weitergeleitet."
            )

        payload: dict[str, Any] | None = None

        try:
            decoded = json.loads(body)

            if isinstance(decoded, dict):
                payload = decoded
        except ValueError:
            payload = None

        if response.status >= 400:
            if payload is not None and payload.get("error"):
                raise IovoApiError(str(payload["error"]))

            raise IovoApiError(
                f"iovo|doc hat HTTP {response.status} zurückgegeben."
            )

        if payload is None:
            raise IovoApiError(
                "iovo|doc hat keine gültige JSON-Antwort geliefert."
            )

        if payload.get("error"):
            raise IovoApiError(str(payload["error"]))

        return payload

    @staticmethod
    def _clean_string(value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()
