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

Der sichtbare Konfigurationseintrag heißt `Räume`. Weitere Ressourcenarten können später als eigene Einträge ergänzt werden.

## Räume

Mapping zwischen Home Assistant und iovo|doc:

- Home-Assistant-Bereich `name` -> iovo|doc `description`
- Home-Assistant-Bereich `id` -> iovo|doc `identifiers`

`idRooms` bleibt eine interne iovo|doc-ID und wird beim Anlegen von iovo|doc selbst erzeugt.

Bei Home Assistant -> iovo|doc sucht der Server zuerst nach `identifiers = area.id`. Wird ein Raum gefunden, wird er aktualisiert. Wird keiner gefunden, wird ein neuer Raum angelegt.

Bei bestehenden iovo|doc-Räumen ohne `identifiers` kann die Integration einen eindeutig gleichnamigen Home-Assistant-Bereich einmalig zuordnen und anschließend dessen `area.id` in `identifiers` hinterlegen.

## API

Zum Repository gehören:

- `iovo-api/HomeAssistant.php`
- `iovo-api/Rooms.php`

`/Data/HomeAssistant` meldet für Räume Lesen, Ändern und Anlegen als unterstützt.

`POST /Data/Rooms` unterstützt Update und Insert. Die Zuordnung erfolgt über `identifiers`.

## Automatik

Die automatische Synchronisierung ist standardmäßig ausgeschaltet und kann in den Optionen des Eintrags `Räume` aktiviert werden.
