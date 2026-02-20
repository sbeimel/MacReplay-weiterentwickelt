# MAC Scoring System - Intelligentes Lernsystem

## Übersicht
Version 4.0.0 führt ein revolutionäres MAC Scoring System ein, das automatisch lernt, welche MACs zuverlässig sind und diese bevorzugt. Das System arbeitet vollständig automatisch und unabhängig von den Benutzer-Einstellungen.

## Kernkonzept

### Warum Scoring?
Traditionell wurden MACs nach `playback_limit` (Kapazität) sortiert. Problem: Eine MAC mit hoher Kapazität kann unzuverlässig sein, während eine MAC mit niedriger Kapazität perfekt funktioniert.

**Lösung**: Intelligentes Scoring-System das Zuverlässigkeit über Kapazität stellt.

## Score-Berechnung (0-100 Punkte)

### 1. Erfolgsrate (0-50 Punkte)
```
Erfolgsrate = (Erfolge / (Erfolge + Fehler)) × 50

Beispiele:
- 10 Erfolge, 0 Fehler → 50 Punkte
- 5 Erfolge, 5 Fehler → 25 Punkte
- 0 Erfolge, 10 Fehler → 0 Punkte
- Nie getestet → 25 Punkte (neutral)
```

### 2. Aktualität (0-30 Punkte)
```
Wie kürzlich war der letzte Erfolg?

- < 1 Stunde → 30 Punkte
- < 24 Stunden → 20 Punkte
- < 1 Woche → 10 Punkte
- > 1 Woche → 5 Punkte
- Nie erfolgreich → 0 Punkte
```

### 3. Zuverlässigkeits-Bonus (0-20 Punkte)
```
Bewährte MACs bekommen Bonus:

- ≥ 10 Erfolge → 20 Punkte
- ≥ 5 Erfolge → 10 Punkte
- < 5 Erfolge → 0 Punkte
```

### Gesamt-Score
```
Score = Erfolgsrate + Aktualität + Zuverlässigkeit

Beispiele:
- MAC_A: 50 Erfolge, 2 Fehler, vor 10min → Score: 95
- MAC_B: 5 Erfolge, 5 Fehler, vor 1h → Score: 45
- MAC_C: 0 Erfolge, 10 Fehler → Score: 0
- MAC_D: Nie getestet → Score: 25
```

## Sortierung

### Nur nach Score (Zuverlässigkeit schlägt Kapazität!)
```python
MACs werden NUR nach Score sortiert (höher = besser)
playback_limit wird NICHT für Sortierung verwendet
```

### Beispiel:
```
Vor dem Lernen (alle Score: 25):
1. MAC_A (limit:5, score:25)
2. MAC_B (limit:5, score:25)
3. MAC_C (limit:2, score:25)

Nach Tests:
MAC_A: 10 Erfolge, 0 Fehler → Score: 95
MAC_B: 2 Erfolge, 8 Fehler → Score: 15
MAC_C: 8 Erfolge, 0 Fehler → Score: 85

Neue Sortierung (nur nach Score):
1. MAC_A (score:95, limit:5) ← Beste
2. MAC_C (score:85, limit:2) ← Zuverlässig schlägt Kapazität!
3. MAC_B (score:15, limit:5) ← Unzuverlässig, ganz hinten
```

## Score-Updates (Automatisches Lernen)

### Immer aktiv - unabhängig von Settings!

#### 1. Mit Stream-Test ("try all macs" + "test streams")
```
Zeitpunkt: Während MAC-Retry (vor Stream-Start)

Erfolg (ffprobe returncode 0):
  → success +1
  → last_ts = jetzt
  → Log: [MAC RETRY] ✓ MAC XX works!

Fehler (ffprobe returncode ≠ 0):
  → fail +1
  → Log: [MAC RETRY] ✗ MAC XX failed test

Kein Link (getLink() = None):
  → fail +2 (härter bestraft!)
  → Log: [MAC RETRY] No link generated
```

#### 2. Ohne Stream-Test (Direct Streaming)
```
Zeitpunkt: Bei Stream-Ende (unoccupy)

Erfolg (Stream lief ≥5 Sekunden):
  → success +1
  → last_ts = jetzt
  → Log: [SCORE UPDATE] MAC XX success (stream ran 45.2s)

Fehler (Stream starb <5 Sekunden):
  → fail +1
  → Log: [SCORE UPDATE] MAC XX fail (stream died after 2.1s)
```

#### 3. HLS mit Auto-Retry
```
Zeitpunkt: Während MAC-Retry (vor Stream-Start)

Erfolg (Playlist erstellt):
  → success +1
  → last_ts = jetzt
  → Log: [HLS RETRY] ✓ MAC XX works!

Fehler (Keine Playlist):
  → fail +1
  → Log: [HLS RETRY] ✗ MAC XX failed

Kein Link:
  → fail +2
  → Log: [HLS RETRY] Failed to generate link
```

## Datenbank-Format

### Struktur
```
available_macs: "MAC:limit:success:fail:last_ts,MAC:limit:success:fail:last_ts"

Beispiel:
"00:1A:79:XX:XX:XX:5:10:2:1708456789,00:1A:79:YY:YY:YY:2:8:0:1708456123"

Bedeutung:
- MAC: MAC-Adresse
- limit: playback_limit (max. Verbindungen)
- success: Anzahl erfolgreicher Streams
- fail: Anzahl fehlgeschlagener Streams
- last_ts: Unix-Timestamp des letzten Erfolgs (0 = nie)
```

### Abwärtskompatibilität
```
Alte Formate werden automatisch erkannt:

"MAC_A,MAC_B" → limit:1, score:25 (neutral)
"MAC_A:5,MAC_B:2" → score:25 (neutral)
"MAC_A:5:10:2:1708456789" → Volle Score-Daten
```

## WebUI Integration

### Portal-Verwaltung
```
Neue "Score" Spalte in MAC-Tabelle:

┌─────────────────┬─────┬───────┬─────────┐
│ MAC             │ DE? │ Score │ Expires │
├─────────────────┼─────┼───────┼─────────┤
│ 00:1A:79:XX:XX  │ ✓   │  95   │ 45d     │ ← Grün (Excellent)
│ 00:1A:79:YY:YY  │     │  55   │ 30d     │ ← Blau (Good)
│ 00:1A:79:ZZ:ZZ  │ ✓   │  25   │ 60d     │ ← Gelb (Neutral)
│ 00:1A:79:AA:AA  │     │  10   │ 20d     │ ← Rot (Poor)
└─────────────────┴─────┴───────┴─────────┘

Farben:
- Grün (≥75): Exzellente Zuverlässigkeit
- Blau (≥50): Gute Zuverlässigkeit
- Gelb (≥25): Moderat/Ungetestet
- Rot (<25): Schlechte Zuverlässigkeit

Tooltip zeigt: "Success: 10, Fail: 2"
```

### Settings-Seite
```
Neue Sektion: "🎯 MAC Scoring System"

Erklärt:
- Wie Scores berechnet werden
- Wie Sortierung funktioniert
- Wann Updates passieren
- Zusammenspiel mit anderen Settings
```

### Live-Logs
```
Neue Log-Nachrichten:

[14:05:38] Channel 1929428 found in DB with 7 MAC(s) (sorted by score):
[14:05:38]   00:1A:79:XX:XX: score=95.0, limit=5, success=50, fail=2
[14:05:38]   00:1A:79:YY:YY: score=85.0, limit=2, success=20, fail=1
[14:05:38]   00:1A:79:ZZ:ZZ: score=25.0, limit=5, success=0, fail=0

[14:05:41] [MAC RETRY] ✓ MAC 00:1A:79:XX:XX works!
[14:05:41] [SCORE UPDATE] MAC 00:1A:79:XX:XX success (stream ran 45.2s)
```

## Zusammenspiel mit Settings

### Scoring ist IMMER aktiv
```
Unabhängig von Settings:
✓ Sortierung nach Score
✓ Score-Updates
✓ Detaillierte Logs

Settings beeinflussen nur WANN/WIE getestet wird
```

### "Try all MACs" + "Test streams"
```
Verhalten:
- Testet alle MACs mit ffprobe
- Bei Fehler → nächste MAC
- Erste funktionierende wird verwendet

Score-Update:
- Bei jedem ffprobe Test
- Erfolg/Fehler sofort erfasst
```

### "Skip busy MACs"
```
Verhalten:
- Prüft watchdog_timeout vor Test
- Überspringt busy MACs (watchdog <60s)
- Busy MACs als Fallback

Score-Update:
- Wie oben (je nach anderen Settings)
- Sortierung nach Score bleibt
```

### Keine Settings aktiv
```
Verhalten:
- Erste freie MAC ohne Test
- Schnellster Start

Score-Update:
- Bei Stream-Ende
- Basierend auf Laufzeit (≥5s = Erfolg)
```

## Vorteile

### 1. Automatisches Lernen
```
✓ System lernt welche MACs funktionieren
✓ Keine manuelle Konfiguration nötig
✓ Passt sich automatisch an Portal-Änderungen an
```

### 2. Schnellere Stream-Starts
```
✓ Zuverlässige MACs werden zuerst probiert
✓ Weniger fehlgeschlagene Versuche
✓ Minimale Wartezeit für User
```

### 3. Optimale Ressourcen-Nutzung
```
✓ Funktionierende MACs werden bevorzugt
✓ Problematische MACs automatisch aussortiert
✓ Bessere Verteilung über alle MACs
```

### 4. Transparenz
```
✓ Scores im Portal sichtbar
✓ Detaillierte Logs
✓ Klare Indikatoren für MAC-Qualität
```

## Cache-Verwaltung

### Clear Cache
```
Löscht:
✓ stream_cmd
✓ available_macs (inkl. Scores)

Behält:
✓ playback_limit (im Portal-Config)
✓ Sortierung nach playback_limit

Ergebnis:
- Alle Scores zurück auf 25 (neutral)
- System lernt von vorne
```

### Refresh Cache
```
Aktualisiert:
✓ stream_cmd
✓ playback_limit (aus getProfile)

Behält:
✓ Bestehende Scores (wenn MACs gleich)

Ergebnis:
- Scores bleiben erhalten
- Nur neue MACs starten bei 25
```

## Performance

### Overhead
```
Minimal:
- 3 zusätzliche Integer pro MAC in DB
- Score-Berechnung: ~0.001ms pro MAC
- DB-Update: ~5ms (nur bei Stream-Ende)
```

### Vorteile
```
Gewinn:
- Weniger fehlgeschlagene Streams
- Weniger API-Calls zum Portal
- Schnellere Stream-Starts
- Bessere User-Experience
```

## Technische Details

### Race Condition Schutz
```python
# SQLite Timeout erhöht
conn = sqlite3.connect(dbPath, timeout=30.0)

# Automatisches Locking durch SQLite
# Mehrere gleichzeitige Updates werden serialisiert
```

### Fehlerbehandlung
```python
# Graceful Degradation
try:
    # Score-Update
except Exception as e:
    logger.error(f"[SCORE UPDATE] Error: {e}")
    # Stream läuft weiter, nur Score-Update fehlgeschlagen
```

### Logging
```
Neue Prefixes:
[SCORE UPDATE] - Score-Updates bei Stream-Ende
[MAC RETRY] - MAC-Tests mit Retry-Logik
[HLS RETRY] - HLS MAC-Tests

Log-Level:
INFO - Erfolge, wichtige Events
WARNING - Fehler, Timeouts
DEBUG - Detaillierte Informationen
```

## Migration

### Automatisch
```
Keine manuelle Migration nötig!

Beim ersten Start nach Update:
1. Alte Formate werden erkannt
2. Scores starten bei 25 (neutral)
3. System beginnt zu lernen
4. Nach einigen Streams: Optimale Sortierung
```

### Empfehlung
```
Nach Update:
1. "Refresh Cache" ausführen
2. Einige Streams testen
3. Scores im Portal prüfen
4. System lernt automatisch weiter
```

## Bekannte Einschränkungen

### HLS ohne Auto-Retry
```
Einschränkung:
- HLS ohne "hls auto retry" lernt nicht automatisch
- Zu komplex zu implementieren

Workaround:
- "HLS auto retry" aktivieren (empfohlen)
- Oder Direct Streaming nutzen
```

### Score-Reset bei Clear Cache
```
Verhalten:
- Clear Cache löscht alle Scores
- System lernt von vorne

Grund:
- available_macs wird komplett gelöscht
- Scores sind Teil von available_macs
```

## Version
Implementiert in Version 4.0.0 (2026-02-20)

## Siehe auch
- [PLAYBACK_LIMIT_CACHING.md](PLAYBACK_LIMIT_CACHING.md) - Technische Details
- [CHANGELOG.md](CHANGELOG.md) - Versions-Historie
- Settings-Seite im WebUI - Interaktive Erklärungen
