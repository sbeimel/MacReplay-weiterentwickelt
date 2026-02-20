# Bugfix: Doppelter ffprobe Test

## Problem
Wenn "Test Streams" aktiviert war, wurde ffprobe 2x aufgerufen:
1. **[MAC RETRY]** - ffprobe zum Testen der MAC (z.B. 0.70s)
2. **[STREAM TEST]** - ffprobe nochmal zum Testen des finalen Streams (z.B. 0.70s)

Das bedeutete doppelte Wartezeit und unnötige Serverlast.

### Beispiel aus Log:
```
[20:19:40] [INFO] [MAC RETRY] Testing link for MAC 00:1A:79:EA:69:A6
[20:19:43] [INFO] [MAC RETRY] ✓ MAC 00:1A:79:EA:69:A6 works! (ffprobe: 0.70s)
[20:19:45] [INFO] [STREAM TEST] ✓ Stream test passed (ffprobe: 0.70s)
```

## Ursache
Die Logik war:
```python
if getSettings().get("test streams", "true") == "false" or testStream():
```

Das bedeutete:
- Test Streams OFF → kein Test ✓
- Test Streams ON → ruft `testStream()` auf, auch wenn MAC bereits mit ffprobe getestet wurde ✗

## Lösung
Neue Variable `already_tested_with_ffprobe` trackt ob ffprobe bereits im MAC RETRY Block verwendet wurde.

### Änderungen:
1. Variable initialisiert: `already_tested_with_ffprobe = False`
2. Bei erfolgreichem MAC RETRY Test: `already_tested_with_ffprobe = True`
3. Neue Bedingung:
```python
if getSettings().get("test streams", "true") == "false" or already_tested_with_ffprobe or testStream():
```

### Verhalten jetzt:
- Test Streams OFF → kein ffprobe Test
- Test Streams ON + MAC RETRY erfolgreich → nur 1x ffprobe (im MAC RETRY)
- Test Streams ON + kein MAC RETRY → 1x ffprobe (im STREAM TEST)

## Performance Verbesserung
- **Vorher**: 2x ffprobe = ~1.4s Wartezeit
- **Nachher**: 1x ffprobe = ~0.7s Wartezeit
- **Ersparnis**: ~50% schneller bei aktiviertem "Test Streams"

## Datum
2026-02-20

## Related Files
- `app-docker.py` (Zeilen 9120, 9347, 9519, 9860)
