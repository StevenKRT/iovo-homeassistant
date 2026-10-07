from __future__ import annotations

from typing import Final

DOMAIN: Final = "iovo_doc"
LOADED_VERSION: Final = "0.2.8"

API_BASE_URL: Final = "https://api.iovodoc.de"
CONNECTION_ENDPOINT: Final = "/Data/HomeAssistant"
DEFAULT_ROOMS_ENDPOINT: Final = "/Data/Rooms"
DEFAULT_FLOORS_ENDPOINT: Final = "/Data/Floors"

CONF_API_KEY: Final = "api_key"
CONF_SECRET: Final = "secret"
CONF_RESOURCE: Final = "resource"
CONF_PARENT_ENTRY_ID: Final = "parent_entry_id"
CONF_AUTO_SYNC: Final = "auto_sync"
CONF_SYNC_DIRECTION: Final = "sync_direction"
CONF_SYNC_INTERVAL: Final = "sync_interval"
CONF_CONFLICT_PRIORITY: Final = "conflict_priority"

RESOURCE_ROOMS: Final = "rooms"
RESOURCE_FLOORS: Final = "floors"

DIRECTION_IOVO_TO_HA: Final = "iovo_to_ha"
DIRECTION_HA_TO_IOVO: Final = "ha_to_iovo"
DIRECTION_BIDIRECTIONAL: Final = "bidirectional"

CONFLICT_IOVO: Final = "iovo"
CONFLICT_HA: Final = "home_assistant"

DEFAULT_AUTO_SYNC: Final = False
DEFAULT_SYNC_DIRECTION: Final = DIRECTION_IOVO_TO_HA
DEFAULT_SYNC_INTERVAL: Final = 15
DEFAULT_CONFLICT_PRIORITY: Final = CONFLICT_IOVO

STORAGE_VERSION: Final = 1
STORAGE_KEY_PREFIX: Final = "iovo_doc"

ROOMS_UNIQUE_ID: Final = "iovo_doc_rooms"
ROOMS_ENTRY_TITLE: Final = "Räume"
FLOORS_UNIQUE_ID: Final = "iovo_doc_floors"
FLOORS_ENTRY_TITLE: Final = "Stockwerke"
