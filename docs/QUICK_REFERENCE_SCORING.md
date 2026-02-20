# MAC Scoring System - Quick Reference

## Was ist das?

Ein selbstlernendes System, das jede MAC-Adresse mit einem Score von 0-100 bewertet und die beste MAC für Streams auswählt.

## Score-Berechnung

```
Score = Success Rate (0-50) + Recency (0-30) + Reliability (0-20)
```

### Success Rate (0-50 Punkte)
- Verhältnis erfolgreiche/fehlgeschlagene Streams
- Beispiel: 10 Erfolge, 2 Fehler = 83% = 42 Punkte

### Recency (0-30 Punkte)
- <1 Stunde: 30 Punkte
- <24 Stunden: 20 Punkte
- <1 Woche: 10 Punkte
- >1 Woche: 5 Punkte
- Nie erfolgreich: 0 Punkte

### Reliability (0-20 Punkte)
- ≥10 Erfolge: 20 Punkte
- ≥5 Erfolge: 10 Punkte
- <5 Erfolge: 0 Punkte

## Beispiele

| Szenario | Success | Fail | Last Success | Score | Bewertung |
|----------|---------|------|--------------|-------|-----------|
| Perfekte MAC | 20 | 0 | 30 min | 100 | 50+30+20 |
| Sehr gut | 15 | 2 | 2h | 74 | 44+20+10 |
| Gut | 8 | 3 | 1 Tag | 56 | 36+20+0 |
| Mittel | 3 | 3 | 3 Tage | 35 | 25+10+0 |
| Schlecht | 1 | 9 | 1 Woche | 15 | 5+10+0 |
| Ungetestet | 0 | 0 | Nie | 25 | 25+0+0 |

## Wann wird der Score aktualisiert?

### ✅ Mit Stream-Testing
- Erfolgreicher Test: `success +1`, `last_ts = jetzt`
- Fehlgeschlagener Test: `fail +1`

### ✅ Ohne Stream-Testing
- Stream läuft ≥5s: `success +1`, `last_ts = jetzt`
- Stream stirbt <5s: `fail +1`

### ✅ Kein Link generiert
- `getLink()` gibt `None`: `fail +2` (härtere Strafe)

## Sortierung

**Nur nach Score, nicht nach playback_limit!**

```
MAC_A: limit=2, score=85  ← ZUERST
MAC_B: limit=5, score=30  ← SPÄTER
```

**Warum?** Zuverlässigkeit schlägt Kapazität!

## WebUI

### Farben
- 🟢 Grün (≥75): Exzellent
- 🔵 Blau (≥50): Gut
- 🟡 Gelb (≥25): Mittel
- 🔴 Rot (<25): Schlecht

### Sortierung
MACs werden im Portal-Dialog nach Score sortiert (höchster zuerst).

## Settings

**Wichtig**: Scoring ist IMMER aktiv, unabhängig von Settings!

Settings beeinflussen nur:
- Ob Streams getestet werden
- Ob ausgelastete MACs übersprungen werden
- Ob bei Fehler alle MACs probiert werden

## Cache-Management

### Clear Cache
- Löscht Scores (zurück auf 0)
- Behält `playback_limit` im Portal-Config

### Refresh Cache
- Aktualisiert `playback_limit`
- Behält Scores (oder initialisiert neu)

## Vorteile

✅ Selbstlernend - wird mit der Zeit besser
✅ Schnellere Stream-Starts - beste MAC zuerst
✅ Weniger Fehler - schlechte MACs werden gemieden
✅ Transparent - Scores im WebUI sichtbar
✅ Immer aktiv - keine Konfiguration nötig

## Einschränkungen

⚠️ Neue MACs brauchen 5-10 Streams zum "Lernen"
⚠️ HLS ohne auto-retry lernt nicht automatisch
⚠️ Race Conditions bei sehr vielen gleichzeitigen Streams möglich (aber selten)

## Datenbank-Format

```
MAC:limit:success:fail:last_ts
```

Beispiel:
```
00:1A:79:XX:XX:XX:5:12:3:1708456789
```

- MAC: `00:1A:79:XX:XX:XX`
- Limit: `5` (max. 5 gleichzeitige Streams)
- Success: `12` (12 erfolgreiche Streams)
- Fail: `3` (3 fehlgeschlagene Streams)
- Last Success: `1708456789` (Unix Timestamp)

## API

### GET /portal/mac-scores
```json
{
  "mac_scores": {
    "00:1A:79:XX:XX:XX": {
      "score": 85.5,
      "success": 12,
      "fail": 3,
      "channels": 50
    }
  }
}
```

## Zusammenfassung

Das MAC Scoring System wählt automatisch die beste MAC für jeden Stream aus. Es lernt kontinuierlich und bevorzugt zuverlässige MACs über MACs mit hoher Kapazität.

**Faustregel**: Eine stabile MAC mit 2 Verbindungen ist besser als eine instabile MAC mit 5 Verbindungen!
