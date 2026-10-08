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

Die Ressourcen werden als getrennte Konfigurationseinträge geführt. Aktuell sind `Räume`, `Stockwerke` und `Geräte` vorgesehen. `Stockwerke` und `Geräte` verwenden dieselben Zugangsdaten wie der Eintrag `Räume`.

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

## Geräte

Geräte werden ausschließlich von Home Assistant nach iovo|doc übertragen. Ein iovo|doc-Geräteeintrag entspricht dabei einer Home-Assistant-Entität und wird über `device_id = entity_id` wiedererkannt.

In den Optionen des Eintrags `Geräte` kann gewählt werden:

- alle unterstützten Entitäten
- bestimmte automatisch erkannte Gerätearten
- einzelne Entitäten
- Arten und einzelne Entitäten kombiniert
- einzelne Entitäten ausdrücklich ausschließen
- Zustandsänderungen automatisch an iovo|doc übertragen

Die Typzuordnung erfolgt nur bei eindeutigen Home-Assistant-Domains oder Geräteklassen. Generische Schalter bleiben `switch`, generische Sensoren bleiben `sensor`. Eine manuelle Umklassifizierung einzelner Entitäten ist für einen späteren Schritt vorgesehen.

## Automatik

Die automatische regelmäßige Synchronisierung von Räumen und Stockwerken ist standardmäßig ausgeschaltet und kann je Konfigurationseintrag separat aktiviert werden. Geräte werden manuell übertragen; zusätzlich kann für ausgewählte Geräte eine laufende Zustandsübertragung aktiviert werden.


## 0.3.0

- iovo|doc kann ausgewählte Home-Assistant-Geräte über einen sicheren Command-Kanal steuern.
- Home Assistant baut die Verbindung ausschließlich ausgehend zu iovo|doc auf.
- Befehle werden per Long Polling über `/Data/HomeAssistantCommands` abgeholt.
- Nur im Geräte-Sync ausgewählte Entitäten können gesteuert werden.
- Erlaubte Aktionen und Parameter sind je Home-Assistant-Domain fest eingeschränkt.
- Nach Befehlen wird der tatsächliche Zustand wieder an iovo|doc übertragen.
