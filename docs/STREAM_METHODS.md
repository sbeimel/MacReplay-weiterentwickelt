# Stream Methods Dokumentation

MacReplayXC bietet 4 verschiedene Stream Methods für unterschiedliche Anforderungen:

## 1. FFmpeg (Standard)

**Beschreibung:** Streams werden durch FFmpeg geleitet mit Remuxing und Fehlerkorrektur.

**Vorteile:**
- ✅ Format-Konvertierung (MPEG-TS ↔ HLS)
- ✅ Fehlerkorrektur (`-fflags +discardcorrupt`)
- ✅ HLS-Generierung möglich
- ✅ Connection Tracking
- ✅ Playback Limit Prüfung
- ✅ MAC Scoring & Retry
- ✅ Höchste Kompatibilität

**Nachteile:**
- ❌ Höhere CPU Last
- ❌ Leichte Latenz durch Processing

**Wann nutzen:**
- Wenn HLS Format benötigt wird
- Wenn Fehlerkorrektur wichtig ist
- Wenn maximale Kompatibilität gewünscht ist

**CPU Last:** Mittel (bei `-c copy` gering)

---

## 2. Proxy (NEU)

**Beschreibung:** Streams werden direkt durchgeleitet ohne FFmpeg (Pass-Through).

**Vorteile:**
- ✅ Minimale CPU Last
- ✅ Connection Tracking
- ✅ Playback Limit Prüfung
- ✅ MAC Scoring & Retry
- ✅ Keine Latenz
- ✅ Alle Features außer Format-Konvertierung

**Nachteile:**
- ❌ Kein HLS (nur MPEG-TS)
- ❌ Keine Fehlerkorrektur
- ❌ Keine Format-Konvertierung

**Wann nutzen:**
- Wenn MPEG-TS Streams stabil sind
- Wenn CPU gespart werden soll
- Wenn Connection Tracking benötigt wird
- Für 1-5 Clients pro Channel

**CPU Last:** Minimal

---

## 3. HLS

**Beschreibung:** FFmpeg generiert HLS Segmente in RAM (`/dev/shm/`).

**Vorteile:**
- ✅ HLS Format für Web-Player
- ✅ Segment-basiertes Streaming
- ✅ Connection Tracking
- ✅ Playback Limit Prüfung
- ✅ MAC Scoring & Retry
- ✅ Automatischer MAC Retry bei Fehlern

**Nachteile:**
- ❌ Höhere CPU Last
- ❌ RAM Disk Nutzung
- ❌ Höhere Latenz (Segment-Dauer)

**Wann nutzen:**
- Für Web-Player (Browser)
- Wenn HLS Format erforderlich ist
- Für moderne Streaming-Clients

**CPU Last:** Mittel-Hoch

---

## 4. Direct Redirect

**Beschreibung:** Client verbindet sich direkt zum Portal (HTTP 302 Redirect).

**Vorteile:**
- ✅ Keine CPU Last
- ✅ Minimale Latenz
- ✅ Maximale Performance
- ✅ MAC Scoring & Selection
- ✅ Skip Busy MACs
- ✅ Learning Logic (passiv)

**Nachteile:**
- ❌ Kein Connection Tracking
- ❌ Keine Playback Limit Prüfung
- ❌ Kein Test Streams möglich
- ❌ Server sieht Stream nicht

**Wann nutzen:**
- Wenn maximale Performance gewünscht ist
- Wenn Connection Tracking nicht benötigt wird
- Für stabile Portale
- Wenn CPU komplett gespart werden soll

**CPU Last:** Keine

---

## Vergleichstabelle

| Feature | FFmpeg | Proxy | HLS | Redirect |
|---------|--------|-------|-----|----------|
| CPU Last | Mittel | Minimal | Hoch | Keine |
| Connection Tracking | ✅ | ✅ | ✅ | ❌ |
| Playback Limits | ✅ | ✅ | ✅ | ❌ |
| MAC Scoring | ✅ | ✅ | ✅ | ✅ |
| MAC Retry | ✅ | ✅ | ✅ | ❌ |
| Test Streams | ✅ | ✅ | ✅ | ❌ |
| Format-Konvertierung | ✅ | ❌ | ✅ | ❌ |
| HLS Generierung | ✅ | ❌ | ✅ | ❌ |
| Fehlerkorrektur | ✅ | ❌ | ✅ | ❌ |
| Latenz | Niedrig | Minimal | Mittel | Minimal |

---

## Empfehlungen

### Für Heimnutzer (1-3 Clients):
- **Proxy** - Beste Balance zwischen Features und Performance

### Für Web-Player:
- **HLS** - Beste Kompatibilität mit Browsern

### Für maximale Kompatibilität:
- **FFmpeg** - Funktioniert mit allen Clients

### Für maximale Performance:
- **Direct Redirect** - Wenn Connection Tracking nicht benötigt wird

### Für instabile Streams:
- **FFmpeg** - Fehlerkorrektur hilft bei Problemen

---

## Output Format

Das Output Format bestimmt das Stream-Format für den Client:

### MPEG-TS (Standard)
- Kompatibel mit allen Stream Methods
- Niedrige Latenz
- Gut für IPTV Player

### HLS
- Nur mit FFmpeg/HLS Method
- Segment-basiert
- Gut für Web-Player
- Bei Direct Redirect: Versucht HLS vom Portal, sonst MPEG-TS

---

## Technische Details

### FFmpeg
```bash
ffmpeg -user_agent <agent> -timeout <timeout> -i <url> -c copy -f mpegts pipe:
```

### Proxy
```python
response = requests.get(url, stream=True, headers={'User-Agent': agent})
for chunk in response.iter_content(chunk_size=8192):
    yield chunk
```

### HLS
```bash
ffmpeg -i <url> -c copy -f hls -hls_time 3 -hls_list_size 8 \
  -hls_flags independent_segments+omit_endlist+delete_segments \
  -hls_delete_threshold 10 /dev/shm/stream.m3u8
```

### Direct Redirect
```python
return redirect(portal_url)  # HTTP 302
```

---

## Changelog

**2026-02-21:**
- Proxy Mode hinzugefügt
- Dokumentation erweitert
- Output Format Beschreibungen hinzugefügt
