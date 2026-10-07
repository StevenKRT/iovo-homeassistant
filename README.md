# iovo|doc für Home Assistant

HACS-Custom-Integration für die Verbindung von iovo|doc mit Home Assistant.

## Installation

[![In HACS öffnen](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=StevenKRT&repository=iovo-homeassistant&category=integration)

1. Repository in HACS als benutzerdefiniertes Repository vom Typ `Integration` hinzufügen.
2. `iovo|doc` über HACS installieren.
3. Home Assistant neu starten.
4. Unter `Einstellungen > Geräte & Dienste` die Integration `iovo|doc` hinzufügen.
5. `API-Schlüssel` und `Geheimer Secret` eingeben.

## Einrichtung

Beim Hinzufügen der Integration wird nach dem Absenden der Zugangsdaten ausschließlich folgender Endpunkt aufgerufen:

`GET https://api.iovodoc.de/Data/HomeAssistant`

Die Ressourcen werden als getrennte Konfigurationseinträge geführt. Aktuell sind `Räume` und `Stockwerke` vorgesehen. `Stockwerke` verwendet dieselben Zugangsdaten wie der Eintrag `Räume`.

## Räume

Mapping zwischen Home Assistant und iovo|doc:

- Home-Assistant-Bereich `name` -> iovo|doc `description`
- Home-Assistant-Bereich `id` -> iovo|doc `identifiers`

`idRooms` bleibt eine interne iovo|doc-ID.

## Stockwerke

Mapping zwischen Home Assistant und iovo|doc:

- Home-Assistant-Stockwerk `floor_id` -> iovo|doc `identifiers`
- Home-Assistant-Stockwerk `name` -> iovo|doc `description`
- Home-Assistant-Stockwerk `level` -> iovo|doc `level`
- Home-Assistant-Bereich `floor_id` -> iovo|doc `Rooms.Floors_idFloors` über die bereits synchronisierten Kennungen

Die Stockwerkssynchronisierung legt keine Räume an. Sie ordnet nur bereits über `area.id` und `Rooms.identifiers` verbundene Räume einem Stockwerk zu.

## Automatik

Die automatische Synchronisierung ist standardmäßig ausgeschaltet und kann je Konfigurationseintrag separat aktiviert werden.
