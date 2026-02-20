# Fix: Output Format HLS verwendet jetzt korrektes Retry-System

## Problem
Wenn "Output Format" auf "HLS (segmented)" gesetzt wurde, wurde trotzdem die FFmpeg Direct Route mit ffprobe verwendet. Das war falsch!

### Symptome:
- User setzt "Output Format" auf HLS
- Logs zeigen trotzdem: `'test streams' enabled - will test all MACs with ffprobe until one works`
- ffprobe wird verwendet statt FFmpeg stderr monitoring
- HLS Retry-System wird nicht genutzt

## Ursache
Das "output format" Setting wurde im Python Code nicht ausgewertet. Die `/play/` Route hat immer FFmpeg Direct Streaming gemacht, egal welches Format eingestellt war.

## Lösung
Neue Logik in der `stream_channel()` Funktion:

```python
output_format = getSettings().get("output format", "mpegts")

if output_format == "hls":
    # HLS mode: Return playlist URL instead of direct stream
    # The HLS route will handle MAC retry with FFmpeg stderr monitoring
    hls_url = f"/hls/{portalId}/{channelId}/playlist.m3u8"
    return Response(playlist_content, mimetype="application/vnd.apple.mpegurl")
```

### Verhalten jetzt:

**Output Format = MPEG-TS (pipe):**
- Verwendet `/play/` Route
- FFmpeg Direct Streaming
- MAC Retry mit ffprobe (wenn "Test Streams" ON)
- Schneller Start, aber blockiert Player bis Stream läuft

**Output Format = HLS (segmented):**
- Gibt M3U8 Playlist zurück die auf `/hls/` Route zeigt
- HLS Streaming mit Segmenten
- MAC Retry mit FFmpeg stderr monitoring (KEIN ffprobe!)
- Instant channel startup (Plex empfohlen)
- Verwendet `monitor_ffmpeg_hls_output()` für schnelle Stream-Erkennung

## Vorteile HLS Mode
1. **Kein ffprobe**: Verwendet FFmpeg stderr monitoring (50-90% schneller)
2. **Instant startup**: Player startet sofort, lädt Segmente nach
3. **Bessere Fehlerbehandlung**: Erkennt FFmpeg Fehler in Echtzeit
4. **Plex optimiert**: Empfohlener Modus für Plex

## Vorteile MPEG-TS Mode
1. **Einfacher**: Direktes Piping ohne Segment-Management
2. **Weniger Overhead**: Keine Segment-Dateien auf Disk
3. **Kompatibilität**: Funktioniert mit allen Playern

## Datum
2026-02-20

## Related Files
- `app-docker.py` (Zeile ~9860: Output Format Check)
- `templates/settings.html` (Zeile 51: Output Format Setting)
- `docs/HLS_FFMPEG_MONITORING.md` (FFmpeg stderr monitoring)
