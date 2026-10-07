# iovo|doc für Home Assistant

HACS-Custom-Integration zur kontrollierten Synchronisierung zwischen iovo|doc und Home Assistant.

## Installation

1. Repository in HACS als benutzerdefiniertes Repository vom Typ `Integration` hinzufügen.
2. `iovo|doc` über HACS installieren.
3. Home Assistant neu starten.
4. Unter `Einstellungen > Geräte & Dienste` die Integration `iovo|doc` hinzufügen.
5. `API-Schlüssel` und `Geheimer Secret` eingeben.

## Verhalten bei der Einrichtung

Die HACS-Installation führt keinen API-Aufruf aus.

Beim Hinzufügen der Integration wird nach dem Absenden der Zugangsdaten genau der folgende Endpunkt aufgerufen:

`GET https://api.iovodoc.de/Data/HomeAssistant`

Der Aufruf dient ausschließlich zur Prüfung der Verbindung und zum Abruf der von der Schnittstelle angebotenen Funktionen.

Es werden dabei keine Räume gelesen, angelegt, geändert oder synchronisiert.

Nach erfolgreicher Einrichtung ist die automatische Synchronisierung ausgeschaltet.

## Räume

Eine Raumsynchronisierung verwendet den vom Verbindungsendpunkt angegebenen Raum-Endpunkt. In Version 1 ist dies:

`/Data/Rooms`

Manuelle Synchronisierung und automatische Synchronisierung werden unter `Einstellungen > Geräte & Dienste > iovo|doc > Konfigurieren` gesteuert.

## Automatische Synchronisierung

Die automatische Synchronisierung ist standardmäßig ausgeschaltet.

Nach dem Einschalten startet nicht sofort eine Synchronisierung. Der erste Lauf erfolgt erst nach Ablauf des gewählten Intervalls.

## iovo|doc API

Zum Repository gehört unter `iovo-api/HomeAssistant.php` der Verbindungsendpunkt für iovo|doc.

Er wird serverseitig als:

`/Data/HomeAssistant`

bereitgestellt.

Die Authentifizierung erfolgt über die bestehende iovo|doc API-Authentifizierung.

## Aktueller Funktionsumfang

- Verbindung mit API-Schlüssel und Geheimer Secret
- Manuelle Raumsynchronisierung
- iovo|doc nach Home Assistant
- Home Assistant nach iovo|doc für bereits zugeordnete Räume
- Bidirektionale Synchronisierung
- Automatische Synchronisierung optional
- Automatische Synchronisierung standardmäßig aus
- Persistente Raumzuordnungen
- Behandlung gleichnamiger Räume
- Deutsche und englische Oberfläche
- Reauthentifizierung bei geänderten Zugangsdaten
