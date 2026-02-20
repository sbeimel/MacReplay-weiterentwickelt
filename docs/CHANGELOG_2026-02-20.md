# Changelog - 20. Februar 2026

## Neue Features & Verbesserungen

### 1. Playback Limit Caching
**Status**: ✅ Implementiert

Jede MAC-Adresse speichert nun ihr `playback_limit` (maximale Anzahl gleichzeitiger Verbindungen) in der Datenbank.

**Änderungen**:
- Neues DB-Format: `MAC:limit:success:fail:last_ts`
- Limit wird bei Portal Add, Portal Edit (Retest), Genre Selection und Cache Refresh aktualisiert
- API-Aufruf `getProfile()` liefert `max_connections` für jede MAC
- Limit bleibt auch nach "Clear Cache" im Portal-Config erhalten

**Betroffene Dateien**:
- `app-docker.py`: Portal Add, Portal Edit, Genre Selection, Refresh Cache

**Nutzen**:
- Bessere Auslastungsverteilung
- Transparenz über MAC-Kapazitäten
- Grundlage für intelligente Sortierung

---

### 2. MAC Scoring System (0-100 Punkte)
**Status**: ✅ Implementiert

Jede MAC erhält einen Reliability Score basierend auf Erfolgsrate, Aktualität und Zuverlässigkeit.

**Score-Komponenten**:
1. **Success Rate** (0-50 Punkte): Verhältnis erfolgreiche/fehlgeschlagene Streams
2. **Recency** (0-30 Punkte): Wie aktuell war der letzte Erfolg?
   - <1h: 30 Punkte
   - <24h: 20 Punkte
   - <1 Woche: 10 Punkte
   - >1 Woche: 5 Punkte
3. **Reliability Bonus** (0-20 Punkte): Gesamtzahl erfolgreicher Streams
   - ≥10: 20 Punkte
   - ≥5: 10 Punkte
   - <5: 0 Punkte

**Score-Updates**:
- ✅ Mit Stream-Testing: Bei ffprobe/playlist-Tests
- ✅ Ohne Stream-Testing: Bei Stream-Ende basierend auf Dauer (≥5s = Erfolg)
- ✅ Kein Link: `fail += 2` (härtere Strafe)

**Sortierung**:
- Nur nach Score (höchster zuerst)
- Zuverlässigkeit schlägt Kapazität
- Beispiel: MAC mit limit:2 + score:85 kommt VOR MAC mit limit:5 + score:30

**Betroffene Dateien**:
- `app-docker.py`: Score-Berechnung, Sortierung, Updates
- `templates/settings.html`: Beschreibung im WebUI

**Nutzen**:
- Selbstlernendes System
- Schnellere Stream-Starts durch intelligente MAC-Auswahl
- Weniger Fehler durch Priorisierung zuverlässiger MACs

---

### 3. Score-Anzeige im Portal WebUI
**Status**: ✅ Implementiert

Scores werden für jede MAC im Portal-Dialog angezeigt.

**Features**:
- Neuer API-Endpoint: `/portal/mac-scores`
- Farb-kodierte Badges:
  - Grün (≥75): Exzellent
  - Blau (≥50): Gut
  - Gelb (≥25): Mittel
  - Rot (<25): Schlecht
- Tooltip zeigt Success/Fail-Counts
- Asynchrones Laden (keine Verzögerung beim Portal-Öffnen)

**Betroffene Dateien**:
- `app-docker.py`: `/portal/mac-scores` Endpoint
- `templates/portals.html`: Score-Anzeige

**Nutzen**:
- Transparenz über MAC-Qualität
- User sieht auf einen Blick, welche MACs zuverlässig sind

---

### 8. MAC-Sortierung im Portal WebUI
**Status**: ✅ Implementiert

MACs werden im Portal-Dialog automatisch nach Score sortiert (höchster zuerst).

**Implementierung**:
- Score wird als `data-score` Attribut in jeder Tabellenzeile gespeichert
- Nach dem Laden der Scores werden die Zeilen sortiert
- DOM-Elemente werden neu angeordnet
- Sortierung erfolgt client-seitig (keine zusätzlichen Server-Requests)

**Betroffene Dateien**:
- `templates/portals.html`: Sortier-Logik nach Score-Laden

**Nutzen**:
- Konsistente Sortierung mit Backend-Logik
- Beste MACs stehen oben
- Visuell sofort erkennbar, welche MACs bevorzugt werden

---

### 4. DE-Content Detection Optimierung
**Status**: ✅ Implementiert

DE-Erkennung wird nicht mehr bei jedem Portal-Öffnen durchgeführt, sondern gecacht.

**Änderungen**:
- DE-Erkennung nur bei Portal Add und "Retest all MACs"
- Ergebnisse werden im Portal-Config gespeichert: `mac_has_de`
- `/portal/mac-regions` Endpoint liest aus Cache statt API-Calls
- Grüner Haken (✓) im WebUI wenn DE-Content gefunden

**Betroffene Dateien**:
- `app-docker.py`: Portal Add, Portal Edit, `/portal/mac-regions`
- `templates/portals.html`: DE-Anzeige

**Nutzen**:
- Deutlich schnelleres Portal-Öffnen
- Weniger API-Requests
- Ergebnisse bleiben konsistent bis zum nächsten Retest

---

### 5. Scoring immer aktiv
**Status**: ✅ Implementiert

Das Scoring-System ist nun IMMER aktiv, unabhängig von den Settings.

**Änderungen**:
- Entfernung der Abhängigkeit von `skip_busy_macs` Setting
- Scoring läuft kontinuierlich im Hintergrund
- Settings beeinflussen nur WANN/WIE getestet wird, nicht das Scoring selbst

**Rationale**:
- System lernt kontinuierlich
- Bessere Datengrundlage für Entscheidungen
- Konsistente Sortierung unabhängig von Settings

**Betroffene Dateien**:
- `app-docker.py`: Scoring-Logik

**Nutzen**:
- Selbstlernendes System ohne Konfiguration
- Immer optimale MAC-Auswahl
- Keine Verwirrung durch Settings

---

### 6. Score-Updates ohne Stream-Testing
**Status**: ✅ Implementiert

Scores werden auch aktualisiert, wenn Stream-Testing deaktiviert ist.

**Implementierung**:
- In `unoccupy()` Funktion
- Basierend auf Stream-Dauer:
  - ≥5 Sekunden: `success += 1`, `last_ts = now`
  - <5 Sekunden: `fail += 1`
- Funktioniert für Direct Streaming
- HLS ohne auto-retry: Kein automatisches Scoring (zu komplex)

**Betroffene Dateien**:
- `app-docker.py`: `unoccupy()` Funktion

**Nutzen**:
- System lernt auch ohne Testing
- Scores bleiben aktuell
- Funktioniert für alle Streaming-Modi

---

### 7. Bug Fixes & Robustheit

**SQLite Timeout erhöht**:
- Von 5s auf 30s
- Bessere Handhabung von Race Conditions bei vielen gleichzeitigen Streams

**Sicherheitschecks**:
- Prüfung auf `startTime` Existenz vor Score-Update
- Graceful Handling wenn MAC nicht in `mac_stats`
- Alle Exceptions werden geloggt

**Betroffene Dateien**:
- `app-docker.py`: Diverse Funktionen

---

## Technische Details

### Datenbank-Schema

**Vorher**:
```
available_macs: "MAC_A,MAC_B,MAC_C"
```

**Nachher**:
```
available_macs: "MAC_A:5:12:3:1708456789,MAC_B:2:8:1:1708450000"
```

Format: `MAC:limit:success:fail:last_ts`

### API-Änderungen

**Neue Endpoints**:
- `POST /portal/mac-scores`: Liefert Scores für alle MACs eines Portals

**Geänderte Endpoints**:
- `POST /portal/mac-regions`: Liest aus Cache statt API

### Performance-Verbesserungen

1. **Weniger API-Requests**:
   - DE-Erkennung gecacht
   - Playback Limit gecacht

2. **Schnellere Stream-Starts**:
   - Intelligente MAC-Sortierung
   - Zuverlässige MACs werden zuerst probiert

3. **Asynchrones Laden**:
   - Scores im WebUI
   - Keine Blockierung beim Portal-Öffnen

---

## Migration

**Keine Migration erforderlich!**

Das System ist abwärtskompatibel:
- Alte DB-Einträge werden beim nächsten Cache-Refresh aktualisiert
- Fehlende Scores werden mit 25 (neutral) initialisiert
- Fehlende Limits werden mit 1 (Standard) initialisiert

---

## Bekannte Einschränkungen

1. **HLS ohne Auto-Retry**: Kein automatisches Scoring (akzeptabel, da selten verwendet)
2. **Score-Reifung**: Neue MACs brauchen 5-10 Streams zum "Lernen"
3. **Race Conditions**: Theoretisch möglich bei sehr vielen gleichzeitigen Streams (SQLite Locking + Timeout sollte ausreichen)

---

## Testing

**Getestet**:
- ✅ Portal Add mit mehreren MACs
- ✅ Portal Edit mit "Retest all MACs"
- ✅ Genre Selection
- ✅ Stream-Start mit Testing
- ✅ Stream-Start ohne Testing
- ✅ Score-Updates bei Erfolg/Fehler
- ✅ Sortierung nach Score im Backend
- ✅ WebUI Score-Anzeige
- ✅ WebUI MAC-Sortierung nach Score
- ✅ DE-Content Caching
- ✅ Clear Cache (Scores werden gelöscht)
- ✅ Refresh Cache (Limits werden aktualisiert)

---

## Dokumentation

**Neue Dokumente**:
- `docs/PLAYBACK_LIMIT_AND_SCORING_SYSTEM.md`: Vollständige Dokumentation des Systems
- `docs/CHANGELOG_2026-02-20.md`: Dieses Dokument

**Aktualisierte Dokumente**:
- `templates/settings.html`: Beschreibung des Scoring-Systems

---

## Zusammenfassung

Heute wurden 8 Features implementiert, die zusammen die Stream-Zuverlässigkeit und Performance deutlich verbessern:

1. **Playback Limit Caching**: Wissen über MAC-Kapazitäten
2. **MAC Scoring System**: Intelligente Bewertung (0-100 Punkte)
3. **Score-Anzeige im WebUI**: Transparenz über MAC-Qualität
4. **DE-Content Detection Optimierung**: Caching statt wiederholter API-Calls
5. **Scoring immer aktiv**: Unabhängig von Settings
6. **Score-Updates ohne Testing**: Lernt auch bei deaktiviertem Stream-Testing
7. **Bug Fixes & Robustheit**: SQLite Timeout, Sicherheitschecks
8. **MAC-Sortierung im WebUI**: Konsistente Sortierung mit Backend

Das System ist:
- ✅ Selbstlernend
- ✅ Immer aktiv
- ✅ Transparent (Scores im WebUI)
- ✅ Robust (Fehlerbehandlung, Timeouts)
- ✅ Performant (Caching, asynchrones Laden)

**Hauptvorteil**: Zuverlässige MACs werden bevorzugt, was zu schnelleren Stream-Starts und weniger Fehlern führt.
