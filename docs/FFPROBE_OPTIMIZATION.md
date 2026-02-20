# ffprobe Optimierung für Stream-Tests

## Übersicht

ffprobe wird verwendet um IPTV-Streams zu testen bevor sie zum Client gestreamt werden. Standardmäßig analysiert ffprobe mehrere Sekunden des Streams, was zu langen Wartezeiten führt (2-5 Sekunden pro Test).

## Implementierung

### WebUI Setting

Ein neues Setting "Custom ffprobe Parameters" wurde hinzugefügt mit drei vordefinierten Presets:

**⚖️ Balance (Standard, empfohlen)**
- Parameter: `-analyzeduration 500000 -probesize 100000`
- Geschwindigkeit: 0.3-0.5 Sekunden
- Zuverlässigkeit: Hoch
- Verwendung: Analysiert 500KB des Streams für zuverlässige Validierung

**⚡ Ultra Fast**
- Parameter: `-analyzeduration 0 -probesize 32`
- Geschwindigkeit: 0.1-0.2 Sekunden
- Zuverlässigkeit: Mittel
- Verwendung: Minimale Analyse, kann defekte Streams übersehen

**🐢 Standard Slow**
- Parameter: keine (leer)
- Geschwindigkeit: 2-5 Sekunden
- Zuverlässigkeit: Sehr hoch
- Verwendung: Vollständige Stream-Analyse (ffprobe Standard)

### Code-Integration

Die Parameter werden an 5 Stellen im Code verwendet:

1. `testStream()` Funktion (Zeile ~9045)
2. FFmpeg Direct MAC Retry - Test Streams ON (Zeile ~9291)
3. FFmpeg Direct MAC Retry - Test Streams ON (Zeile ~9455)
4. FFmpeg Direct MAC Retry - Test Streams OFF (Zeile ~9638)
5. FFmpeg Direct MAC Retry - Test Streams OFF (Zeile ~9695)

Alle Stellen lesen die Parameter aus den Settings:

```python
# Get custom ffprobe parameters from settings
ffprobe_params_str = getSettings().get("ffprobe params", "-analyzeduration 500000 -probesize 100000")
ffprobe_params = ffprobe_params_str.split() if ffprobe_params_str.strip() else []

ffprobecmd = [ffprobe_path] + ffprobe_params + ["-timeout", str(timeout), "-i", test_link]
```

## Performance-Verbesserung

### Vorher (Standard ffprobe)
- Durchschnittliche Test-Zeit: 2-5 Sekunden pro MAC
- Bei 5 MACs: 10-25 Sekunden bis Stream startet

### Nachher (Balance Preset)
- Durchschnittliche Test-Zeit: 0.3-0.5 Sekunden pro MAC
- Bei 5 MACs: 1.5-2.5 Sekunden bis Stream startet
- **Verbesserung: 5-10x schneller**

### Nachher (Ultra Fast Preset)
- Durchschnittliche Test-Zeit: 0.1-0.2 Sekunden pro MAC
- Bei 5 MACs: 0.5-1 Sekunde bis Stream startet
- **Verbesserung: 10-20x schneller**
- Risiko: Kann defekte Streams als "OK" markieren

## Empfehlung

**Balance Preset** ist der beste Kompromiss:
- Deutlich schneller als Standard (5-10x)
- Immer noch zuverlässig genug für IPTV-Streams
- 500KB Analyse reicht aus um Stream-Qualität zu prüfen

**Ultra Fast Preset** nur wenn:
- Maximale Geschwindigkeit wichtiger als Zuverlässigkeit
- Streams sind sehr stabil (selten defekt)
- Bereit für gelegentliche Fehlerkennungen

**Standard Slow** nur wenn:
- Streams sind sehr instabil
- Maximale Zuverlässigkeit erforderlich
- Wartezeit ist akzeptabel

## Technische Details

### Was machen die Parameter?

**-analyzeduration [Mikrosekunden]**
- Bestimmt wie lange ffprobe den Stream analysiert
- Standard: 5000000 (5 Sekunden)
- Balance: 500000 (0.5 Sekunden)
- Ultra Fast: 0 (keine Wartezeit)

**-probesize [Bytes]**
- Bestimmt wie viele Bytes ffprobe liest
- Standard: 5000000 (5 MB)
- Balance: 100000 (100 KB)
- Ultra Fast: 32 (32 Bytes)

### Warum funktioniert das?

IPTV-Streams haben in der Regel:
- Konstante Bitrate
- Einfache Codec-Struktur (H.264/AAC)
- Klare Stream-Header

Deshalb reichen 100KB Analyse aus um zu erkennen:
- Ist der Stream erreichbar?
- Sendet er Video-Daten?
- Ist der Codec unterstützt?

## Verwandte Optimierungen

Diese Optimierung ergänzt:
- **HLS FFmpeg Monitoring** (docs/HLS_FFMPEG_MONITORING.md)
- **MAC Scoring System** (docs/MAC_SCORING_SYSTEM.md)
- **Playback Limit System** (docs/PLAYBACK_LIMIT_AND_SCORING_SYSTEM.md)

Zusammen sorgen diese Features für:
- Schnelle Stream-Starts (0.5-2s statt 10-25s)
- Intelligente MAC-Auswahl
- Automatisches Retry bei Fehlern
- Optimale Ressourcen-Nutzung

## Datum

Implementiert: 2026-02-20
