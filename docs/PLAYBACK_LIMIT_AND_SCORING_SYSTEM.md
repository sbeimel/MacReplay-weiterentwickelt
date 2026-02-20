# Playback Limit Caching & MAC Scoring System

## Übersicht

Dieses Dokument beschreibt zwei wichtige Features, die zusammen die MAC-Auswahl und Stream-Zuverlässigkeit optimieren:

1. **Playback Limit Caching**: Speichert die maximale Anzahl gleichzeitiger Verbindungen pro MAC
2. **MAC Scoring System**: Bewertet MACs basierend auf Erfolgsrate, Aktualität und Zuverlässigkeit (0-100 Punkte)

## 1. Playback Limit Caching

### Zweck
Jede MAC-Adresse hat ein unterschiedliches `playback_limit` (z.B. 1, 2, 5 gleichzeitige Streams). Dieses Limit wird beim Cache-Refresh von der API abgerufen und in der Datenbank gespeichert.

### Datenbank-Format
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

### Wann wird das Limit aktualisiert?

Das `playback_limit` wird NUR bei folgenden Operationen aktualisiert:

1. **Portal Add**: Beim Hinzufügen eines neuen Portals
2. **Portal Edit mit "Retest all MACs"**: Beim Bearbeiten und Neuladen aller MACs
3. **Genre Selection**: Beim Speichern der Genre-Auswahl
4. **Refresh Cache**: Bei manueller Cache-Aktualisierung

**NICHT aktualisiert bei:**
- Stream-Tests (ffprobe/playlist)
- Normalen Stream-Starts
- Fallback-Versuchen

### Implementierung

```python
# API-Aufruf für jede MAC
profile = getProfile(url, mac, proxy)
playback_limit = profile.get("max_connections", 1)

# Speichern im Format MAC:limit:success:fail:last_ts
available_macs = f"{mac}:{playback_limit}:0:0:0"
```

## 2. MAC Scoring System

### Zweck
Bewertet jede MAC-Adresse mit einem Score von 0-100 Punkten basierend auf:
- Erfolgsrate (wie oft funktioniert die MAC?)
- Aktualität (wann war der letzte Erfolg?)
- Zuverlässigkeit (wie viele erfolgreiche Streams insgesamt?)

### Score-Berechnung

```python
def calculate_mac_score(success_count, fail_count, last_success_ts):
    """
    Berechnet MAC Reliability Score (0-100)
    
    Komponenten:
    1. Success Rate (0-50 Punkte)
    2. Recency (0-30 Punkte)
    3. Reliability Bonus (0-20 Punkte)
    """
    
    # 1. Success Rate (0-50 Punkte)
    total = success_count + fail_count
    if total > 0:
        success_rate = (success_count / total) * 50
    else:
        success_rate = 25  # Neutral für ungetestete MACs
    
    # 2. Recency (0-30 Punkte)
    if last_success_ts > 0:
        age_hours = (current_time - last_success_ts) / 3600
        if age_hours < 1:
            recency = 30      # Sehr aktuell
        elif age_hours < 24:
            recency = 20      # Heute erfolgreich
        elif age_hours < 168:  # 1 Woche
            recency = 10      # Diese Woche
        else:
            recency = 5       # Älter als 1 Woche
    else:
        recency = 0  # Noch nie erfolgreich
    
    # 3. Reliability Bonus (0-20 Punkte)
    if success_count >= 10:
        reliability = 20    # Sehr zuverlässig
    elif success_count >= 5:
        reliability = 10    # Zuverlässig
    else:
        reliability = 0     # Noch nicht bewährt
    
    return success_rate + recency + reliability
```

### Score-Beispiele

| MAC | Success | Fail | Last Success | Score | Interpretation |
|-----|---------|------|--------------|-------|----------------|
| MAC_A | 20 | 2 | 30 min ago | 95 | Exzellent: 45 + 30 + 20 |
| MAC_B | 10 | 5 | 2 Stunden | 53 | Gut: 33 + 20 + 0 |
| MAC_C | 2 | 8 | 3 Tage | 15 | Schlecht: 10 + 5 + 0 |
| MAC_D | 0 | 0 | Nie | 25 | Ungetestet: 25 + 0 + 0 |

### Wann wird der Score aktualisiert?

Der Score wird in folgenden Szenarien aktualisiert:

#### A) Mit Stream-Testing (ffprobe/playlist)
```python
# Bei erfolgreichem Test
success += 1
last_ts = current_time

# Bei fehlgeschlagenem Test
fail += 1
```

#### B) Ohne Stream-Testing (Direct Streaming)
```python
# In unoccupy() Funktion basierend auf Stream-Dauer
if stream_duration >= 5:
    success += 1
    last_ts = current_time
else:
    fail += 1
```

#### C) Kein Link generiert
```python
# Wenn getLink() None zurückgibt
fail += 2  # Härtere Strafe
```

### Sortierung nach Score

**Wichtig**: Die Sortierung erfolgt NUR nach Score, NICHT nach playback_limit!

```python
# Sortierung: Höchster Score zuerst
available_macs.sort(key=lambda x: x[5], reverse=True)  # x[5] = score
```

**Rationale**: Eine zuverlässige MAC mit `limit:2` ist besser als eine unzuverlässige MAC mit `limit:5`.

Beispiel:
```
MAC_A: limit=2, score=85  ← Wird ZUERST verwendet
MAC_B: limit=5, score=30  ← Wird SPÄTER verwendet
```

## 3. WebUI Integration

### Portal-Ansicht

In der Portal-Übersicht wird für jede MAC der Score angezeigt:

```html
<td id="score_00_1A_79_XX_XX_XX">
    <span class="badge bg-success-lt" title="Success: 12, Fail: 3">85</span>
</td>
```

**Farb-Kodierung**:
- Grün (≥75): Exzellent
- Blau (≥50): Gut
- Gelb (≥25): Mittel
- Rot (<25): Schlecht

### Sortierung im WebUI

Die MACs werden im Portal-Dialog nach Score sortiert (höchster zuerst):

```javascript
// Nach Score sortieren (höchster zuerst)
rows.sort((a, b) => {
    const scoreA = parseFloat(a.getAttribute('data-score')) || 0;
    const scoreB = parseFloat(b.getAttribute('data-score')) || 0;
    return scoreB - scoreA;
});

// Zeilen neu anordnen
rows.forEach(row => tbody.appendChild(row));
```

Dies entspricht der Sortierung im Backend beim Stream-Start.

**Ablauf**:
1. Portal wird geöffnet → MACs werden in ursprünglicher Reihenfolge angezeigt
2. Scores werden asynchron geladen
3. Nach dem Laden werden die Zeilen automatisch sortiert
4. Beste MAC steht oben, schlechteste unten

## 4. Settings-Unabhängigkeit

**Wichtig**: Das Scoring-System ist IMMER aktiv, unabhängig von den Settings!

Die Settings beeinflussen nur:
- **Test Streams**: Ob Streams vor Verwendung getestet werden
- **Skip Busy MACs**: Ob ausgelastete MACs übersprungen werden
- **Try All MACs**: Ob bei Fehler alle MACs durchprobiert werden

Das Scoring selbst läuft immer im Hintergrund und lernt kontinuierlich.

## 5. Cache-Management

### Clear Cache
```python
# Löscht Scores, aber NICHT playback_limit
cursor.execute('DELETE FROM channels WHERE portal = ?', (portal_id,))
```

Nach "Clear Cache":
- Scores werden auf 0 zurückgesetzt
- `playback_limit` bleibt im Portal-Config erhalten
- Sortierung erfolgt nach gespeichertem `playback_limit` bis neue Scores gesammelt werden

### Refresh Cache
```python
# Aktualisiert playback_limit UND behält Scores
for mac in macs:
    profile = getProfile(url, mac, proxy)
    playback_limit = profile.get("max_connections", 1)
    # Scores bleiben erhalten oder werden neu initialisiert
```

## 6. DE-Content Detection

### Zweck
Erkennt, ob eine MAC deutschen Content liefert (wichtig für deutsche Nutzer).

### Caching-Strategie

Die DE-Erkennung wird NUR bei folgenden Operationen durchgeführt:

1. **Portal Add**: Beim Hinzufügen eines neuen Portals
2. **Portal Edit mit "Retest all MACs"**: Beim Bearbeiten und Neuladen

**NICHT bei:**
- Jedem Portal-Öffnen (zu langsam!)
- Stream-Tests
- Cache-Refresh

### Speicherung

```python
# Im Portal-Config
portal["mac_has_de"] = {
    "00:1A:79:XX:XX:XX": True,
    "00:1A:79:YY:YY:YY": False
}
```

### WebUI-Anzeige

```html
<td id="flags_00_1A_79_XX_XX_XX">
    <span class="text-success">✓</span>  <!-- Wenn DE gefunden -->
</td>
```

## 7. Workflow-Beispiele

### Beispiel 1: Neues Portal hinzufügen

1. User fügt Portal mit 3 MACs hinzu
2. System ruft `getProfile()` für jede MAC auf
3. Speichert `playback_limit` (z.B. 1, 2, 5)
4. Prüft DE-Content für jede MAC
5. Initialisiert Scores mit 25 (neutral)
6. Lädt Channels und speichert in DB

### Beispiel 2: Stream starten (mit Testing)

1. User startet Stream
2. System lädt verfügbare MACs aus DB
3. Sortiert nach Score (höchster zuerst)
4. Prüft Auslastung (skip_busy_macs)
5. Testet Stream mit ffprobe
6. Bei Erfolg: `success += 1`, `last_ts = now`
7. Bei Fehler: `fail += 1`, nächste MAC probieren
8. Aktualisiert DB mit neuen Scores

### Beispiel 3: Stream starten (ohne Testing)

1. User startet Stream
2. System lädt verfügbare MACs aus DB
3. Sortiert nach Score (höchster zuerst)
4. Prüft Auslastung (skip_busy_macs)
5. Generiert Link direkt (kein Test)
6. Bei Stream-Ende in `unoccupy()`:
   - Dauer ≥5s: `success += 1`, `last_ts = now`
   - Dauer <5s: `fail += 1`
7. Aktualisiert DB mit neuen Scores

### Beispiel 4: Kein Link generiert

1. User startet Stream
2. System versucht Link zu generieren
3. `getLink()` gibt `None` zurück (MAC tot/blockiert)
4. System: `fail += 2` (härtere Strafe)
5. Probiert nächste MAC
6. Aktualisiert DB mit neuen Scores

## 8. Performance-Überlegungen

### Vorteile
- Schnellere Stream-Starts durch intelligente MAC-Auswahl
- Weniger API-Requests durch Caching
- Selbstlernend: System wird mit der Zeit besser

### Trade-offs
- Mehr DB-Writes (bei jedem Stream-Ende)
- Komplexere Logik
- Scores müssen "reifen" (brauchen Zeit zum Lernen)

### Optimierungen
- SQLite Timeout erhöht (5s → 30s) für Race Conditions
- Batch-Updates wo möglich
- Asynchrones Laden im WebUI

## 9. Bekannte Einschränkungen

### HLS ohne Auto-Retry
- Lernt NICHT automatisch (zu komplex)
- User muss manuell neuen Stream starten
- Akzeptabel, da selten verwendet

### Race Conditions
- Theoretisch möglich bei vielen gleichzeitigen Streams
- SQLite hat eingebautes Locking
- Timeout erhöht für bessere Stabilität

### Score-Reifung
- Neue MACs starten mit neutralem Score (25)
- Brauchen Zeit zum "Lernen"
- Nach 5-10 Streams stabilisiert sich der Score

## 10. Zusammenfassung

Das kombinierte System aus Playback Limit Caching und MAC Scoring bietet:

✅ Intelligente MAC-Auswahl basierend auf Zuverlässigkeit
✅ Selbstlernendes System, das sich kontinuierlich verbessert
✅ Schnellere Stream-Starts durch optimierte Sortierung
✅ Transparenz im WebUI (Scores sichtbar)
✅ Unabhängig von Settings (immer aktiv)
✅ Robuste Fehlerbehandlung

Das System priorisiert Zuverlässigkeit über Kapazität: Eine stabile MAC mit wenigen Verbindungen ist besser als eine instabile MAC mit vielen Verbindungen.
