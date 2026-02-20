# MAC Retry Refactoring Plan

## Problem
- 5x duplizierter ffprobe Code
- "Test Streams OFF" nutzt trotzdem ffprobe (Bug!)
- Schwer wartbar, inkonsistent

## Lösung

### 1. Zentrale Funktionen (✅ Done)
```python
def test_stream_with_ffprobe(test_link, proxy, mac, log_prefix):
    """Test stream with ffprobe, return (success, duration)"""
```

### 2. Neue MAC Retry Logik

```python
# Für jede MAC in available_macs (sortiert nach Score):
for try_mac in available_macs:
    # 1. Check if MAC is free (playback_limit)
    if MAC_is_full:
        continue
    
    # 2. Get token
    token = stb.getToken(url, try_mac, proxy)
    if not token:
        continue
    
    # 3. Check if busy (optional: skip_busy_macs setting)
    if skip_busy_macs:
        profile = stb.getProfile(...)
        if watchdog < 60:
            busy_macs.append(try_mac)  # Save for fallback
            continue
    
    # 4. Generate link
    link = generate_link_for_mac(try_mac)
    if not link:
        continue
    
    # 5. Test with ffprobe (ONLY if test_streams_enabled!)
    if test_streams_enabled:
        success, duration = test_stream_with_ffprobe(link, proxy, try_mac, "[MAC RETRY]")
        if not success:
            update_db_fail(try_mac)
            continue
    
    # 6. MAC works!
    update_db_success(try_mac)
    return link, try_mac

# Fallback: Try busy MACs
if not mac_found and busy_macs:
    # Same logic but with busy MACs
```

### 3. Was wird entfernt
- ❌ Kompletter "Test Streams OFF" Block (Zeilen 9518-9800+)
- ❌ Duplizierter ffprobe Code (5 Stellen)
- ❌ Busy MAC Fallback Duplikation

### 4. Was bleibt
- ✅ MAC Scoring (immer aktiv)
- ✅ Playback Limit Check (immer aktiv)
- ✅ Skip Busy MACs (optional)
- ✅ Test Streams (optional, nur wenn enabled)
- ✅ Busy MAC Fallback

## Ergebnis
- Von ~600 Zeilen auf ~200 Zeilen
- Klare Logik, keine Duplikation
- Test Streams OFF funktioniert korrekt (kein ffprobe!)
- Einfacher zu warten und zu verstehen
