from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientResponseError, ClientSession

from .const import API_BASE_URL, CONNECTION_ENDPOINT, DEFAULT_ROOMS_ENDPOINT

_LOGGER = logging.getLogger(__name__)


class IovoApiError(Exception):
    pass


class IovoAuthError(IovoApiError):
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
        self._api_key = api_key.strip()
        self._secret = secret.strip()
        self._resources: dict[str, dict[str, Any]] = {}

    @property
    def rooms_endpoint(self) -> str:
        rooms = self._resources.get("rooms", {})
        endpoint = rooms.get("endpoint")

        if isinstance(endpoint, str) and endpoint.startswith("/"):
            return endpoint

        return DEFAULT_ROOMS_ENDPOINT

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
                }
            )

        return rooms

    async def async_update_room(
        self,
        room_id: str,
        name: str,
    ) -> None:
        if not self.can_update_rooms:
            raise IovoUnsupportedError(
                "iovo|doc erlaubt derzeit keine Änderungen an Räumen."
            )

        await self._async_request(
            "POST",
            self.rooms_endpoint,
            json={
                "roomID": int(room_id),
                "description": name.strip(),
            },
        )

    async def _async_request(
        self,
        method: str,
        endpoint: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{API_BASE_URL}{endpoint}"
        credentials = f"{self._api_key}:{self._secret}".encode("utf-8")
        authorization = base64.b64encode(credentials).decode("ascii")

        headers = {
            "Authorization": f"Basic {authorization}",
            "Accept": "*/*",
        }

        try:
            async with asyncio.timeout(20):
                async with self._session.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    ssl=False,
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

        if response.status == 401:
            raise IovoAuthError(
                "Die Zugangsdaten wurden von iovo|doc nicht akzeptiert."
            )

        if response.status == 403:
            raise IovoAuthError(
                "Der API-Zugang ist für diese Funktion nicht freigegeben."
            )

        try:
            response.raise_for_status()
        except ClientResponseError as exception:
            raise IovoApiError(
                f"iovo|doc hat HTTP {response.status} zurückgegeben."
            ) from exception

        try:
            payload = json_module_loads(body)
        except ValueError as exception:
            raise IovoApiError(
                "iovo|doc hat keine gültige JSON-Antwort geliefert."
            ) from exception

        if not isinstance(payload, dict):
            raise IovoApiError(
                "iovo|doc hat eine unerwartete Antwort geliefert."
            )

        if payload.get("error"):
            raise IovoApiError(str(payload["error"]))

        return payload

    @staticmethod
    def _clean_string(value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()


def json_module_loads(value: str) -> Any:
    import json

    return json.loads(value)
