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
    ClientResponseError,
    ClientSession,
)
from aiohttp.hdrs import ACCEPT, AUTHORIZATION, USER_AGENT

from .const import API_BASE_URL, CONNECTION_ENDPOINT, DEFAULT_ROOMS_ENDPOINT

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
            json_data={
                "roomID": int(room_id),
                "description": name.strip(),
            },
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
    ) -> dict[str, Any]:
        url = f"{API_BASE_URL}{endpoint}"
        headers = self._request_headers()

        request_kwargs: dict[str, Any] = {
            "headers": headers,
            "allow_redirects": False,
        }

        if json_data is not None:
            request_kwargs["json"] = json_data

        _LOGGER.debug(
            "iovo|doc API request %s %s, Basic Auth vorhanden: %s, User-Agent: %s",
            method,
            endpoint,
            AUTHORIZATION in headers,
            headers[USER_AGENT],
        )

        try:
            async with asyncio.timeout(20):
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

        try:
            response.raise_for_status()
        except ClientResponseError as exception:
            raise IovoApiError(
                f"iovo|doc hat HTTP {response.status} zurückgegeben."
            ) from exception

        try:
            payload = json.loads(body)
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
