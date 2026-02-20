# Bugfix: ffprobe in "Test Streams OFF" Block

## Problem
Es gab einen kritischen Bug im Code: Wenn "Test Streams" auf OFF gesetzt war, wurde trotzdem ffprobe verwendet.

### Details
- **Zeilen 9601-9822**: Buggy Block der ffprobe verwendete obwohl er im `else:` Block (Test Streams OFF) war
- Der Block startete mit: `logger.info(f"'test streams' enabled - will test MACs until one works (try all macs: disabled)")`
- Dieser Block war ein Duplikat und sollte nie im "Test Streams OFF" Zweig sein

## Lösung
Der gesamte buggy Block (Zeilen 9601-9822) wurde gelöscht.

### Korrekte Struktur jetzt:
```python
if testStreams:
    # Test Streams enabled: Use ffprobe to test MACs
    # ... (ffprobe logic)
else:
    # Test Streams disabled: Try MACs without ffprobe
    logger.info(f"'test streams' disabled - will try all MACs without ffprobe test")
    
    for try_mac in available_macs:
        # ... (no ffprobe, just try MAC directly)
```

## Verifikation
- **Test Streams ON**: System verwendet ffprobe zum Testen der MACs
- **Test Streams OFF**: System probiert MACs direkt ohne ffprobe (schneller, aber weniger zuverlässig)

## Datum
2026-02-20

## Related Files
- `app-docker.py` (Zeilen 9551-9598: korrekter "Test Streams OFF" Block)
