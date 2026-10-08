from __future__ import annotations

from typing import Final

DOMAIN: Final = "iovo_doc"
LOADED_VERSION: Final = "0.3.0"

API_BASE_URL: Final = "https://api.iovodoc.de"
CONNECTION_ENDPOINT: Final = "/Data/HomeAssistant"
DEFAULT_ROOMS_ENDPOINT: Final = "/Data/Rooms"
DEFAULT_FLOORS_ENDPOINT: Final = "/Data/Floors"
DEFAULT_DEVICES_ENDPOINT: Final = "/Data/Devices"
DEFAULT_COMMANDS_ENDPOINT: Final = "/Data/HomeAssistantCommands"

CONF_API_KEY: Final = "api_key"
CONF_SECRET: Final = "secret"
CONF_RESOURCE: Final = "resource"
CONF_PARENT_ENTRY_ID: Final = "parent_entry_id"
CONF_AUTO_SYNC: Final = "auto_sync"
CONF_SYNC_DIRECTION: Final = "sync_direction"
CONF_SYNC_INTERVAL: Final = "sync_interval"
CONF_CONFLICT_PRIORITY: Final = "conflict_priority"
CONF_DEVICE_SELECTION_MODE: Final = "device_selection_mode"
CONF_DEVICE_TYPES: Final = "device_types"
CONF_DEVICE_ENTITIES: Final = "device_entities"
CONF_DEVICE_EXCLUDED_ENTITIES: Final = "device_excluded_entities"
CONF_DEVICE_STATE_SYNC: Final = "device_state_sync"

RESOURCE_ROOMS: Final = "rooms"
RESOURCE_FLOORS: Final = "floors"
RESOURCE_DEVICES: Final = "devices"

DIRECTION_IOVO_TO_HA: Final = "iovo_to_ha"
DIRECTION_HA_TO_IOVO: Final = "ha_to_iovo"
DIRECTION_BIDIRECTIONAL: Final = "bidirectional"

CONFLICT_IOVO: Final = "iovo"
CONFLICT_HA: Final = "home_assistant"

DEFAULT_AUTO_SYNC: Final = False
DEFAULT_SYNC_DIRECTION: Final = DIRECTION_IOVO_TO_HA
DEFAULT_SYNC_INTERVAL: Final = 15
DEFAULT_CONFLICT_PRIORITY: Final = CONFLICT_IOVO
DEFAULT_DEVICE_SELECTION_MODE: Final = "types"
DEFAULT_DEVICE_STATE_SYNC: Final = False

DEVICE_SELECTION_ALL: Final = "all"
DEVICE_SELECTION_TYPES: Final = "types"
DEVICE_SELECTION_ENTITIES: Final = "entities"
DEVICE_SELECTION_TYPES_AND_ENTITIES: Final = "types_and_entities"

STORAGE_VERSION: Final = 1
STORAGE_KEY_PREFIX: Final = "iovo_doc"

ROOMS_UNIQUE_ID: Final = "iovo_doc_rooms"
ROOMS_ENTRY_TITLE: Final = "Räume"
FLOORS_UNIQUE_ID: Final = "iovo_doc_floors"
FLOORS_ENTRY_TITLE: Final = "Stockwerke"
DEVICES_UNIQUE_ID: Final = "iovo_doc_devices"
DEVICES_ENTRY_TITLE: Final = "Geräte"

ROOMPLANNER_DEVICE_TYPES: Final = (
    "access",
    "aed",
    "air_purifier",
    "alarm",
    "bed",
    "call",
    "camera",
    "charger",
    "climate",
    "cover",
    "dehumidifier",
    "disinfectant_dispenser",
    "display",
    "fan",
    "fire_extinguisher",
    "fire_hydrant",
    "first_aid",
    "gas",
    "humidifier",
    "intercom",
    "lawn_mower",
    "light",
    "media",
    "network",
    "power",
    "sensor",
    "soap_dispenser",
    "switch",
    "towel_dispenser",
    "vacuum",
    "valve",
    "water_heater",
)

AUTO_DEVICE_TYPES: Final = (
    "access",
    "alarm",
    "camera",
    "climate",
    "cover",
    "dehumidifier",
    "fan",
    "gas",
    "humidifier",
    "humidity",
    "lawn_mower",
    "light",
    "media",
    "motiondetect",
    "network",
    "power",
    "sensor",
    "smokedetector",
    "switch",
    "temp",
    "vacuum",
    "valve",
    "water_heater",
    "watersensor",
    "weather",
)

DEVICE_TYPE_LABELS: Final = {
    "access": "Zugang",
    "alarm": "Alarm",
    "camera": "Kamera",
    "climate": "Thermostat",
    "cover": "Abdeckung",
    "dehumidifier": "Luftentfeuchter",
    "fan": "Ventilator",
    "gas": "Gas",
    "humidifier": "Luftbefeuchter",
    "humidity": "Luftfeuchtigkeit",
    "lawn_mower": "Mähroboter",
    "light": "Licht",
    "media": "Mediengerät",
    "motiondetect": "Bewegungsmelder",
    "network": "Netzwerk",
    "power": "Strom/Energie",
    "sensor": "Sensor",
    "smokedetector": "Rauchmelder",
    "switch": "Schalter",
    "temp": "Temperatur",
    "vacuum": "Saugroboter",
    "valve": "Ventil",
    "water_heater": "Warmwassergerät",
    "watersensor": "Feuchtigkeitssensor",
    "weather": "Wetter",
}
