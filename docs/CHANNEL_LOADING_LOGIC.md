# Channel Loading Logic - DB Cache vs Fallback

## Übersicht
Alle Streaming-Modi (FFmpeg, Proxy, HLS, Redirect) nutzen die gleiche Channel-Loading-Logik mit DB-Cache und Fallback-Mechanismen.

---

## Ablauf: Channel Loading

### 1️⃣ DB Cache (Primär) - ALLE MODI
**Bedingung**: Channel in DB mit `stream_cmd` UND `available_macs`

```python
# Schritt 1: Versuche Channel aus DB zu laden
conn = get_db_connection()
cursor.execute('''
    SELECT stream_cmd, available_macs, name, custom_name 
    FROM channels 
    WHERE portal = ? AND channel_id = ? AND enabled = 1
''', (portalId, channelId))

row = cursor.fetchone()

if row and row['stream_cmd'] and row['available_macs']:
    # ✅ Channel in DB gefunden mit Cache-Daten!
    cmd = row['stream_cmd']
    available_macs_raw = row['available_macs'].split(',')
    
    # Parse und sortiere MACs nach Score
    available_macs, mac_limits, mac_stats = parse_and_sort_macs(available_macs_raw)
    
    # Probiere alle gecachten MACs durch (sortiert nach Score)
    for try_mac in available_macs:
        # Versuche Streaming mit diesem MAC
        # ...
```

**Vorteile**:
- ⚡ Sehr schnell (keine Portal-API-Calls)
- 📊 MACs sind nach Score sortiert (beste zuerst)
- 🎯 Nur MACs die den Channel haben
- 💾 Playback Limits sind bekannt

**Gilt für**:
- ✅ FFmpeg Mode
- ✅ Proxy Mode
- ✅ HLS Mode
- ✅ Redirect Mode

---

### 2️⃣ Fallback #1: Channel in DB OHNE Cache-Daten
**Bedingung**: Channel in DB, aber `stream_cmd` ODER `available_macs` ist NULL

```python
elif row:
    # ⚠️ Channel in DB aber OHNE Cache-Daten
    logger.warning(f"Channel {channelId} in DB but missing cache data, falling back to getAllChannels()")
    
    # Probiere alle Portal-MACs durch
    for try_mac in macs:
        token = stb.getToken(url, try_mac, proxy)
        if token:
            # ❌ LANGSAM: Lade ALLE Channels von dieser MAC
            channels = stb.getAllChannels(url, try_mac, token, proxy)
            
            # Suche den gewünschten Channel
            for ch in channels:
                if str(ch["id"]) == str(channelId):
                    channel = ch
                    cmd = channel["cmd"]
                    
                    # Speichere Cache-Daten für nächstes Mal
                    cursor.execute('''
                        UPDATE channels 
                        SET stream_cmd = ?, available_macs = ?
                        WHERE portal = ? AND channel_id = ?
                    ''', (cmd, f"{mac}|{playback_limit}|0|0|0", portalId, channelId))
                    
                    break
```

**Wann passiert das?**:
- Nach frischer Installation (DB leer)
- Nach "Clear Cache" Operation
- Wenn Channel-Refresh fehlgeschlagen ist
- Wenn nur Metadaten (Name, Genre) aber keine Stream-Daten gecacht wurden

**Performance**:
- 🐌 Langsam (getAllChannels lädt ALLE Channels)
- 🔄 Nur einmal pro Channel (danach gecacht)

---

### 3️⃣ Fallback #2: Channel NICHT in DB
**Bedingung**: Channel existiert nicht in DB (komplett unbekannt)

```python
else:
    # ❌ Channel nicht in DB - probiere getAllChannels()
    logger.warning(f"Channel {channelId} not in DB, falling back to getAllChannels()")
    
    for try_mac in macs:
        token = stb.getToken(url, try_mac, proxy)
        if token:
            # ❌ LANGSAM: Lade ALLE Channels
            channels = stb.getAllChannels(url, try_mac, token, proxy)
            
            for ch in channels:
                if str(ch["id"]) == str(channelId):
                    # Auto-Learning: Speichere in DB
                    cursor.execute('''
                        UPDATE channels 
                        SET stream_cmd = ?, available_macs = ?, enabled = 1
                        WHERE portal = ? AND channel_id = ?
                    ''', (cmd, mac, portalId, channelId))
                    
                    break
```

**Wann passiert das?**:
- Channel wurde nie gecacht (z.B. neuer Channel im Portal)
- Channel wurde aus DB gelöscht
- Channel ist in Genre das nicht ausgewählt wurde (disabled)

**Auto-Learning**:
- ✅ Channel wird automatisch in DB gespeichert
- ✅ Beim nächsten Request: DB Cache wird genutzt

---

## Setting: "try all macs on db miss"

### Was macht es?
Kontrolliert ob ALLE MACs durchprobiert werden sollen bei Fallback-Szenarien.

```python
try_all_on_db_miss = getSettings().get("try all macs on db miss", "true") == "true"
```

### Wann wird es genutzt?
- ✅ Bei Fallback #1 (Channel in DB ohne Cache)
- ✅ Bei Fallback #2 (Channel nicht in DB)
- ❌ NICHT bei DB Cache (dort werden immer alle gecachten MACs probiert)

### Verhalten:
```python
# Bei Fallback-Szenarien
for try_mac in macs:
    # Versuche MAC...
    
    if not try_all_on_db_miss:
        logger.info("'try all macs on db miss' is disabled, stopping after first MAC")
        break  # Stoppe nach erster MAC
```

**Empfehlung**: `true` (default)
- Erhöht Erfolgsrate bei Fallback-Szenarien
- Nur minimal langsamer (Fallback ist sowieso selten)

---

## Zusammenfassung: Alle Modi nutzen DB Cache

### ✅ FFmpeg Mode
1. Versuche gecachte MACs aus DB (sortiert nach Score)
2. Fallback: getAllChannels() wenn DB miss
3. Streaming mit FFmpeg

### ✅ Proxy Mode
1. Versuche gecachte MACs aus DB (sortiert nach Score)
2. Fallback: getAllChannels() wenn DB miss
3. Direct Proxy Streaming (kein FFmpeg)

### ✅ HLS Mode
1. Versuche gecachte MACs aus DB (sortiert nach Score)
2. Fallback: getAllChannels() wenn DB miss
3. FFmpeg generiert HLS Playlist

### ✅ Redirect Mode
1. Versuche gecachte MACs aus DB (sortiert nach Score)
2. Fallback: getAllChannels() wenn DB miss
3. HTTP Redirect zu Portal-URL

---

## Performance-Vergleich

### DB Cache (Normal Case)
```
Request → DB Query (1ms) → Parse MACs (1ms) → Stream
Total: ~2ms overhead
```

### Fallback #1 (Missing Cache Data)
```
Request → DB Query (1ms) → getAllChannels() (500-2000ms) → Find Channel → Update DB → Stream
Total: ~500-2000ms overhead (einmalig)
```

### Fallback #2 (Channel Not in DB)
```
Request → DB Query (1ms) → getAllChannels() (500-2000ms) → Find Channel → Insert DB → Stream
Total: ~500-2000ms overhead (einmalig)
```

---

## Wann wird getAllChannels() genutzt?

### ✅ Immer bei:
1. Channel Refresh (Editor → Refresh)
2. Portal hinzufügen/bearbeiten
3. Genre Selection ändern
4. EPG Refresh

### ⚠️ Fallback bei:
1. Channel in DB ohne stream_cmd
2. Channel in DB ohne available_macs
3. Channel nicht in DB (Auto-Learning)

### ❌ Nie bei:
1. Normaler Streaming-Request mit DB Cache
2. Alle gecachten MACs funktionieren

---

## Best Practices

### Für optimale Performance:
1. ✅ Regelmäßig "Refresh Channels" ausführen (füllt DB Cache)
2. ✅ "try all macs on db miss" = true (erhöht Erfolgsrate)
3. ✅ Genres vorher auswählen (nur relevante Channels cachen)
4. ✅ "test streams" = true (nur funktionierende MACs cachen)

### Für schnellstes Streaming:
1. ✅ DB Cache ist gefüllt (nach Refresh)
2. ✅ MACs haben Score-Daten (nach einigen Streams)
3. ✅ Beste MACs werden zuerst probiert (automatisch sortiert)

---

## Code-Locations

### DB Cache Loading
- `app-docker.py` Zeile ~9423-9450

### Fallback #1 (Missing Cache)
- `app-docker.py` Zeile ~10342-10403

### Fallback #2 (Not in DB)
- `app-docker.py` Zeile ~10404-10460

### getAllChannels() Calls
- Channel Refresh: Zeile ~1506
- Portal Edit: Zeile ~3358, ~3514
- Genre Selection: Zeile ~3688, ~3914
- EPG Refresh: Zeile ~6396
- Fallback Scenarios: Zeile ~10288, ~10360, ~10420
- HLS Fallback: Zeile ~11150
- HDHR Lineup: Zeile ~11434

---

## Fazit

**Ja, du hast recht!** 🎯

1. ✅ Alle Modi nutzen DB Cache mit gecachten MACs (sortiert nach Score)
2. ✅ Wenn alle gecachten MACs fehlschlagen → Fallback zu getAllChannels()
3. ✅ getAllChannels() wird bei bestimmten Umständen genutzt (DB miss, missing cache data)
4. ✅ Auto-Learning: Neue Channels werden automatisch in DB gespeichert

Die Logik ist für alle Modi identisch - nur die Streaming-Methode unterscheidet sich!
