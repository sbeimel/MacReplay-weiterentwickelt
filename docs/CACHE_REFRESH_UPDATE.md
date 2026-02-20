# Cache Refresh Update

## Datum: 2026-02-20

## Änderung

"Refresh Channels" wurde umbenannt in "Refresh Cache" und respektiert jetzt die Genre-Filterung.

---

## Vorher

**"Refresh Channels" Button:**
- Lud ALLE Channels vom Portal (42.582)
- Speicherte ALLE in DB (ignorierte Genre-Filter)
- Überschrieb bestehende Channels
- DB wurde wieder groß (26 MB)

**Problem:**
- Nach Genre-Filterung (DB: 3 MB)
- "Refresh Channels" drücken
- DB wieder groß (26 MB) ❌

---

## Jetzt

**"Refresh Cache" Button:**
- Löscht Cache-Daten (stream_cmd, available_macs)
- Lädt Channels vom Portal
- Aktualisiert NUR Channels mit ausgewählten Genres
- VACUUM am Ende (gibt Speicher frei)
- DB bleibt klein (3 MB) ✅

---

## Workflow

### 1. Cache-Daten löschen

```python
cursor.execute('UPDATE channels SET stream_cmd = NULL, available_macs = NULL')
cleared_count = cursor.rowcount
conn.commit()
logger.info(f"Cleared cache data from {cleared_count} channels")
```

### 2. Channels vom Portal laden

```python
# Lädt ALLE Channels vom Portal (42.582)
mac_channels = stb.getAllChannels(url, mac, token, proxy)
mac_genres = stb.getGenreNames(url, mac, token, proxy)
```

### 3. Nur ausgewählte Genres cachen

```python
# Get selected genres for this portal
selected_genres = portal.get("selected genres", [])

for channel_id, channel in all_channels_map.items():
    genre = str(all_genres_dict.get(genre_id, ""))
    
    # Skip if genre not selected
    if selected_genres and genre not in selected_genres:
        skipped_count += 1
        continue
    
    # Update ONLY if channel exists in DB
    cursor.execute('''
        UPDATE channels 
        SET stream_cmd = ?, available_macs = ?
        WHERE portal = ? AND channel_id = ?
    ''', (stream_cmd, available_macs, portal_id, channel_id))
```

### 4. VACUUM am Ende

```python
logger.info("Running VACUUM to reclaim disk space...")
cursor.execute("VACUUM")
conn.commit()
logger.info("VACUUM completed")
```

---

## Dashboard Buttons

### "Refresh Cache" (neu)

**Was macht es?**
1. Löscht Cache-Daten (stream_cmd, available_macs)
2. Lädt Channels vom Portal
3. Aktualisiert NUR Channels mit ausgewählten Genres
4. VACUUM am Ende

**Wann verwenden?**
- Nach längerer Zeit (Cache-Daten veraltet)
- Wenn Streams nicht mehr funktionieren
- Nach Portal-Änderungen

**Wichtig:**
- Respektiert Genre-Filterung ✅
- Lädt NICHT alle Channels ✅
- DB bleibt klein ✅

---

### "Clear Cache"

**Was macht es?**
1. Löscht Cache-Daten (stream_cmd, available_macs)
2. Löscht Lineup-Cache
3. Löscht Playlist-Cache

**Wann verwenden?**
- Wenn Cache komplett geleert werden soll
- Vor "Refresh Cache"
- Bei Cache-Problemen

**Wichtig:**
- Löscht KEINE Channels aus DB
- Löscht KEINE Custom-Edits
- Nur Cache-Daten werden gelöscht

---

### "Optimize DB (VACUUM)"

**Was macht es?**
1. VACUUM auf channels.db
2. VACUUM auf vods.db
3. Zeigt Speicher-Ersparnis an

**Wann verwenden?**
- Nach "Clear Cache"
- Nach vielen Editor-Änderungen
- Wenn DB-Datei unerwartet groß ist

**Wichtig:**
- Löscht NICHTS
- Gibt nur ungenutzten Speicher frei
- Dauert 1-10 Sekunden

---

## Vorteile

### ✅ Genre-Filterung respektiert

- "Refresh Cache" lädt nur ausgewählte Genres
- DB bleibt klein nach Genre-Filterung
- Keine unerwünschten Channels

### ✅ Automatisches VACUUM

- Gibt Speicher sofort frei
- Keine manuelle Intervention nötig
- DB bleibt optimiert

### ✅ Klare Button-Namen

- "Refresh Cache" statt "Refresh Channels"
- Beschreibt was es tut
- Weniger Verwirrung

---

## Beispiel

**Ausgangssituation:**
- Portal mit 42.582 Channels
- Genre Selection: Sport, News, Entertainment
- DB: 5.000 Channels, 3 MB

**"Refresh Cache" drücken:**
```
[INFO] Cleared cache data from 5000 channels
[INFO] Selected genres: ['Sport', 'News', 'Entertainment']
[INFO] MAC 00:1A:79:00:14:97: Added 42582 channels
[INFO] Updated cache for 5000 channels
[INFO] Skipped 37582 channels (genres not selected)
[INFO] Running VACUUM to reclaim disk space...
[INFO] VACUUM completed
[INFO] Channel cache refresh complete. Total channels cached: 5000
```

**Ergebnis:**
- DB: 5.000 Channels, 3 MB (unverändert!)
- Cache-Daten aktualisiert
- Streams funktionieren wieder

---

## Migration

**Für bestehende Installationen:**

1. **Vor dem Update:**
   - "Refresh Channels" lädt alle Channels
   - DB wird groß (26 MB)

2. **Nach dem Update:**
   - Button heißt jetzt "Refresh Cache"
   - Respektiert Genre-Filterung
   - DB bleibt klein (3 MB)

3. **Empfehlung:**
   - Genre Selection neu machen
   - "Refresh Cache" drücken
   - DB ist optimiert

---

## Zusammenfassung

**Vorher:**
- ❌ "Refresh Channels" ignorierte Genre-Filter
- ❌ DB wurde wieder groß
- ❌ Unerwünschte Channels in DB

**Jetzt:**
- ✅ "Refresh Cache" respektiert Genre-Filter
- ✅ DB bleibt klein
- ✅ Nur ausgewählte Genres
- ✅ Automatisches VACUUM

---

**Implementiert am:** 2026-02-20
**Version:** MacReplayXC v3.0.1
