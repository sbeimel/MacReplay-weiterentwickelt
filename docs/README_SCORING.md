# MAC Scoring System - Dokumentation

## Übersicht

Das MAC Scoring System ist ein selbstlernendes Feature, das die Zuverlässigkeit jeder MAC-Adresse bewertet und automatisch die beste MAC für Streams auswählt.

## Dokumentations-Struktur

### 📘 Hauptdokumentation
**[PLAYBACK_LIMIT_AND_SCORING_SYSTEM.md](PLAYBACK_LIMIT_AND_SCORING_SYSTEM.md)**
- Vollständige technische Dokumentation
- Detaillierte Erklärung aller Komponenten
- Code-Beispiele und Implementierungsdetails
- Workflow-Beispiele
- Performance-Überlegungen
- Bekannte Einschränkungen

**Für wen**: Entwickler, die das System verstehen oder erweitern möchten

---

### 📋 Quick Reference
**[QUICK_REFERENCE_SCORING.md](QUICK_REFERENCE_SCORING.md)**
- Kompakte Übersicht
- Score-Berechnung mit Beispielen
- Tabellen und Faustregel
- API-Referenz
- Häufige Fragen

**Für wen**: Alle, die schnell nachschlagen möchten

---

### 📝 Changelog
**[CHANGELOG_2026-02-20.md](CHANGELOG_2026-02-20.md)**
- Alle Features vom 20. Februar 2026
- Detaillierte Änderungen
- Betroffene Dateien
- Testing-Status
- Migration-Hinweise

**Für wen**: Alle, die wissen möchten, was sich geändert hat

---

## Features im Überblick

### 1. Playback Limit Caching
Speichert die maximale Anzahl gleichzeitiger Verbindungen pro MAC.

**Format**: `MAC:limit:success:fail:last_ts`

**Aktualisierung**: Bei Portal Add, Edit (Retest), Genre Selection, Cache Refresh

---

### 2. MAC Scoring (0-100 Punkte)
Bewertet jede MAC basierend auf:
- **Success Rate** (0-50): Erfolgsquote
- **Recency** (0-30): Aktualität des letzten Erfolgs
- **Reliability** (0-20): Gesamtzahl erfolgreicher Streams

---

### 3. Intelligente Sortierung
MACs werden nach Score sortiert (höchster zuerst).

**Prinzip**: Zuverlässigkeit schlägt Kapazität!

Beispiel:
```
MAC_A: limit=2, score=85  ← ZUERST
MAC_B: limit=5, score=30  ← SPÄTER
```

---

### 4. WebUI Integration
- Farb-kodierte Score-Badges
- Automatische Sortierung nach Score
- Tooltip mit Success/Fail-Counts
- Asynchrones Laden

---

### 5. Selbstlernendes System
- Immer aktiv (unabhängig von Settings)
- Updates bei jedem Stream
- Lernt aus Erfolgen und Fehlern
- Wird mit der Zeit besser

---

## Schnellstart

### Score verstehen
```
Score = Success Rate (0-50) + Recency (0-30) + Reliability (0-20)
```

### Farben im WebUI
- 🟢 **Grün (≥75)**: Exzellent - verwenden!
- 🔵 **Blau (≥50)**: Gut - zuverlässig
- 🟡 **Gelb (≥25)**: Mittel - funktioniert manchmal
- 🔴 **Rot (<25)**: Schlecht - meiden!

### Faustregel
Eine stabile MAC mit 2 Verbindungen ist besser als eine instabile MAC mit 5 Verbindungen!

---

## Häufige Fragen

### Wann wird der Score aktualisiert?
- Bei Stream-Tests (ffprobe/playlist)
- Bei Stream-Ende (basierend auf Dauer)
- Wenn kein Link generiert werden kann

### Kann ich das Scoring deaktivieren?
Nein, und das ist gut so! Das System lernt kontinuierlich und verbessert die Stream-Qualität automatisch.

### Was passiert bei "Clear Cache"?
- Scores werden auf 0 zurückgesetzt
- `playback_limit` bleibt erhalten
- System lernt neu

### Wie lange dauert es, bis Scores "reifen"?
Nach 5-10 Streams stabilisieren sich die Scores und werden aussagekräftig.

### Funktioniert es auch ohne Stream-Testing?
Ja! Das System lernt auch bei deaktiviertem Testing basierend auf der Stream-Dauer.

---

## Vorteile

✅ **Schnellere Stream-Starts**: Beste MAC wird zuerst probiert
✅ **Weniger Fehler**: Schlechte MACs werden gemieden
✅ **Selbstlernend**: Wird automatisch besser
✅ **Transparent**: Scores im WebUI sichtbar
✅ **Keine Konfiguration**: Immer aktiv, keine Settings nötig
✅ **Robust**: Fehlerbehandlung und Timeouts

---

## Technische Details

### Datenbank-Format
```
available_macs: "MAC_A:5:12:3:1708456789,MAC_B:2:8:1:1708450000"
```

### API-Endpoint
```
POST /portal/mac-scores
Response: { "mac_scores": { "MAC": { "score": 85.5, ... } } }
```

### Sortier-Algorithmus
```python
available_macs.sort(key=lambda x: x[5], reverse=True)  # x[5] = score
```

---

## Support

Bei Fragen oder Problemen:
1. Lies die [Hauptdokumentation](PLAYBACK_LIMIT_AND_SCORING_SYSTEM.md)
2. Schau in die [Quick Reference](QUICK_REFERENCE_SCORING.md)
3. Prüfe das [Changelog](CHANGELOG_2026-02-20.md)

---

## Version

**Implementiert**: 20. Februar 2026
**Status**: ✅ Produktiv
**Getestet**: ✅ Alle Features

---

*Dieses System macht dein Streaming-Erlebnis besser, ohne dass du etwas tun musst!* 🚀
