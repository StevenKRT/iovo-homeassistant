# iovo|doc für Home Assistant

Home-Assistant-Integration für die kontrollierte Synchronisierung zwischen iovo|doc und Home Assistant.

## Installation über HACS

[![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=StevenKRT&repository=iovo-homeassistant&category=integration)

Nach dem Öffnen:

1. Repository zu HACS hinzufügen.
2. `iovo|doc` herunterladen.
3. Home Assistant neu starten.
4. Unter `Einstellungen > Geräte & Dienste` die Integration `iovo|doc` hinzufügen.
5. `API-Schlüssel` und `Geheimer Secret` aus iovo|doc eingeben.

## Verhalten bei der Installation

Die Installation über HACS führt keinen API-Aufruf aus.

Es werden keine Räume gelesen, angelegt, geändert oder synchronisiert.

## Verhalten beim ersten Einrichten

Beim Hinzufügen der Integration werden ausschließlich folgende Zugangsdaten abgefragt:

- API-Schlüssel
- Geheimer Secret

Die Authentifizierung erfolgt technisch über HTTP Basic Auth:

- API-Schlüssel = Benutzername
- Geheimer Secret = Passwort

Nach dem Bestätigen der Zugangsdaten wird genau dieser Endpunkt aufgerufen:

`GET https://api.iovodoc.de/Data/HomeAssistant`

Dieser Aufruf:

- prüft die Zugangsdaten
- bestätigt die Home-Assistant-Unterstützung
- liefert die verfügbaren Funktionen und Endpunkte
- liest keine Räume
- verändert keine Daten
- startet keine Synchronisierung

Nach erfolgreicher Einrichtung bleibt die automatische Synchronisierung ausgeschaltet.

## Räume

Die Raumsynchronisierung verwendet den vom Verbindungsendpunkt bereitgestellten Raum-Endpunkt.

Aktuell:

`/Data/Rooms`

Eine Synchronisierung erfolgt ausschließlich:

- manuell durch den Anwender
- oder nach ausdrücklichem Aktivieren der automatischen Synchronisierung

## Manuelle Synchronisierung

Unter:

`Einstellungen > Geräte & Dienste > iovo|doc > Konfigurieren`

stehen folgende Richtungen zur Verfügung:

- iovo|doc → Home Assistant
- Home Assistant → iovo|doc
- Beide Richtungen

Die Synchronisierung beginnt erst nach ausdrücklicher Bestätigung.

## Automatische Synchronisierung

Die automatische Synchronisierung ist standardmäßig ausgeschaltet.

Konfigurierbar sind:

- Aktivierung
- Richtung
- Intervall
- Vorrang bei gleichzeitigen Änderungen

Nach dem Aktivieren wird nicht sofort synchronisiert. Der erste automatische Lauf erfolgt nach Ablauf des gewählten Intervalls.

## iovo|doc API

Der Verbindungsendpunkt befindet sich unter:

`/Data/HomeAssistant`

Die Authentifizierung erfolgt über die bestehende iovo|doc API-Authentifizierung mit HTTP Basic Auth.

Der Endpunkt liefert die für Home Assistant verfügbaren Funktionen und deren API-Endpunkte.

## Aktueller Funktionsumfang

- Verbindung über API-Schlüssel und Geheimer Secret
- HTTP Basic Auth
- Discovery über `/Data/HomeAssistant`
- Manuelle Raumsynchronisierung
- iovo|doc → Home Assistant
- Home Assistant → iovo|doc für bereits zugeordnete Räume
- Bidirektionale Synchronisierung
- Optionale automatische Synchronisierung
- Automatische Synchronisierung standardmäßig ausgeschaltet
- Persistente Raumzuordnungen
- Behandlung gleichnamiger Räume
- Deutsche und englische Oberfläche
- Reauthentifizierung bei geänderten Zugangsdaten
