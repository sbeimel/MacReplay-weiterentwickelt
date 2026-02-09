# DB-Based Streaming Optimization

## Übersicht

MacReplayXC v3.1.0 nutzt jetzt `channels.db` direkt für Streaming statt des Channel Cache. Dies führt zu:
- ✅ **Schnelleres Umschalten** zwischen Channels
- ✅ **Kein `getAllChannels()` mehr beim Streaming**
- ✅ **Intelligentes MAC-Routing** (probiert nur MACs die den Channel haben)
- ✅ **Automatisches Fallback** wenn Channel nicht in DB

## Wie es funktioniert

### 1. Editor Refresh (einmalig)

Wenn du im Editor auf "Refresh" klickst:

```python
# Für jedes Portal:
for mac in portal_macs:
    channels = getAllChannels(url, mac, token)  # API-Call
    
    for channel in channels:
        # Speichere in channels.db:
        - stream_cmd: "http://portal.com/stream/123.m3u8"
        - available_macs: "MAC1,MAC3,MAC4"  # Alle MACs die den Channel haben
```

**Ergebnis:** `channels.db` enthält alle Channels mit Stream-URLs und MAC-Zuordnung

### 2. Streaming (bei jedem Channel-Wechsel)

Wenn ein User einen Channel startet:

```python
# 1. Lese aus channels.db (schnell!)
row = SELECT stream_cmd, available_macs FROM channels WHERE channel_id = ...

if row:
    # Channel in DB gefunden!
    cmd = row["stream_cmd"]
    macs = row["available_macs"].split(',')  # ["MAC1", "MAC3", "MAC4"]
    
    # 2. Probiere MACs in Reihenfolge
    for mac in macs:
        if mac_is_free():
            token = getToken(mac)  # Schnell: ~0.1s
            link = getLink(token, cmd)  # Schnell: ~0.2s
            return stream  # ✅ Erfolg!
    
    return "All MACs busy"

else:
    # 3. FALLBACK: Channel nicht in DB
    # Probiere getAllChannels() und speichere für nächstes Mal
    for mac in portal_macs:
        channels = getAllChannels(url, mac, token)  # API-Call
        channel = find_in_list(channels, channel_id)
        if channel:
            # Speichere in DB für nächstes Mal
            INSERT INTO channels (stream_cmd, available_macs, enabled=1)
            return stream
```

## Vorteile

### Vorher (mit Channel Cache):

```
User startet Stream
  → channel_cache.find_channel_any_mac()
    → Cache MISS? → getAllChannels()  # 2-5 Sekunden! ❌
    → Probiere MAC1, MAC2, MAC3...
```

### Nachher (mit channels.db):

```
User startet Stream
  → SELECT FROM channels.db  # 0.001 Sekunden! ✅
  → Probiere nur MACs die den Channel haben
  → Kein getAllChannels() mehr!
```

## Performance-Vergleich

| Szenario | Vorher | Nachher |
|----------|--------|---------|
| **Channel-Wechsel (DB-Hit)** | 0.3-5s | 0.2-0.3s |
| **Channel-Wechsel (Cache-Miss)** | 2-5s | 0.2-0.3s |
| **MAC-Fallback** | Alle MACs probieren | Nur verfügbare MACs |
| **API-Calls beim Streaming** | Häufig | Nie (außer Fallback) |

## Neue DB-Spalten

### `channels.db`

```sql
ALTER TABLE channels ADD COLUMN stream_cmd TEXT;
ALTER TABLE channels ADD COLUMN available_macs TEXT;
```

**Beispiel-Daten:**

| channel_id | name | stream_cmd | available_macs | enabled |
|------------|------|------------|----------------|---------|
| 123 | ARD HD | http://portal.com/stream/123.m3u8 | MAC1,MAC3,MAC4 | 1 |
| 456 | ZDF HD | http://portal.com/stream/456.m3u8 | MAC1,MAC2 | 1 |

## Fallback-Mechanismus

Wenn ein Channel **nicht** in `channels.db` ist (z.B. neuer Channel, kein Refresh gemacht):

1. System probiert `getAllChannels()` für jede MAC
2. Findet Channel und speichert ihn in DB
3. Nächstes Mal: Direkt aus DB (schnell!)

**Auto-Learning:** System lernt automatisch neue Channels!

## Migration

Die Migration erfolgt automatisch:

1. **DB-Schema:** Spalten werden beim Start hinzugefügt (wenn nicht vorhanden)
2. **Bestehende Channels:** Beim nächsten Editor Refresh werden `stream_cmd` und `available_macs` gefüllt
3. **Streaming:** Funktioniert sofort mit Fallback für alte Channels

## Channel Cache Status

Der alte Channel Cache (lazy-ram, ram, disk, hybrid) ist jetzt **deprecated**:

- ✅ Bleibt für Backwards-Compatibility
- ✅ Wird nicht mehr für Streaming verwendet
- ✅ Kann in Zukunft entfernt werden

**Empfehlung:** Settings → Cache Mode kann auf "lazy-ram" bleiben (wird ignoriert)

## Troubleshooting

### Problem: "Channel not found"

**Ursache:** Channel nicht in `channels.db`

**Lösung:** 
1. Gehe zu Editor
2. Klicke "Refresh" für das Portal
3. Channel wird automatisch geladen

### Problem: "All MACs busy"

**Ursache:** Alle MACs die den Channel haben sind belegt

**Lösung:**
- Warte bis eine MAC frei wird
- Oder: Erhöhe "Streams per MAC" in Portal-Settings

### Problem: Langsames Streaming

**Ursache:** `stream_cmd` oder `available_macs` fehlt in DB

**Lösung:**
1. Editor → Refresh
2. System füllt fehlende Daten nach

## Technische Details

### Editor Refresh Code

```python
# In editor_refresh() Funktion:
channel_macs_map = {}  # channel_id -> [mac1, mac2, ...]

for mac in macs:
    channels = getAllChannels(url, mac, token)
    for channel in channels:
        channel_id = str(channel["id"])
        if channel_id not in channel_macs_map:
            channel_macs_map[channel_id] = []
        channel_macs_map[channel_id].append(mac)

# Speichere in DB:
stream_cmd = channel["cmd"]
available_macs = ",".join(channel_macs_map[channel_id])
```

### Streaming Code

```python
# In stream_channel() Funktion:
cursor.execute('''
    SELECT stream_cmd, available_macs, name, custom_name 
    FROM channels 
    WHERE portal = ? AND channel_id = ? AND enabled = 1
''', (portalId, channelId))

row = cursor.fetchone()
if row and row['stream_cmd'] and row['available_macs']:
    cmd = row['stream_cmd']
    available_macs = row['available_macs'].split(',')
    # Probiere MACs...
```

## Changelog

### v3.1.0 (2026-02-07)

- ✅ DB-Schema erweitert: `stream_cmd`, `available_macs`
- ✅ Editor Refresh speichert MAC-Zuordnung
- ✅ Streaming nutzt `channels.db` direkt
- ✅ Intelligentes MAC-Routing
- ✅ Automatisches Fallback
- ✅ Channel Cache deprecated

## Siehe auch

- [CACHE_MANAGEMENT.md](CACHE_MANAGEMENT.md) - Alte Cache-Dokumentation
- [PERFORMANCE_OPTIMIZATIONS.md](PERFORMANCE_OPTIMIZATIONS.md) - Performance-Tipps
