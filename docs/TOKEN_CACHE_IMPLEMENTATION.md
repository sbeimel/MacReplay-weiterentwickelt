# Token Cache Implementation - Wie Macstrom

## Übersicht

Die Token-Cache-Implementierung ist jetzt vollständig wie in Macstrom implementiert. Alle Streaming-Modi (FFmpeg, HLS, Proxy, Redirect) nutzen den Token-Cache für schnellere Stream-Starts.

## Features

### 1. Token-Cache-Klasse (`TokenCache`)

- **Thread-safe**: Verwendet `threading.Lock()` für sichere Concurrent-Access
- **Memory-Management**: 
  - Max. 500 Einträge (verhindert unbegrenztes Wachstum)
  - Automatische Bereinigung abgelaufener Tokens
  - LRU-Eviction bei vollem Cache
- **TTL-basiert**: Tokens werden mit konfigurierbarer TTL gecacht (Standard: 270s)

### 2. Streaming-Modi mit Token-Cache

Alle 4 Streaming-Modi nutzen jetzt `get_token_cached()`:

#### FFmpeg-Modus (MPEG-TS)
```python
token = get_token_cached(url, mac, proxy)
```
- Zeile ~11055: MAC-Retry-Logik mit Token-Cache
- Zeile ~11244: MAC-Retry-Fallback mit Token-Cache
- Zeile ~11411: Freie MACs mit Token-Cache

#### HLS-Modus
```python
token = get_token_cached(url, try_mac, proxy)
```
- Zeile ~11921: HLS-Retry-Logik mit Token-Cache
- Zeile ~12118: HLS-Retry-Fallback mit Token-Cache
- Zeile ~12261: HLS-Fallback mit Token-Cache

#### Proxy-Modus
```python
try_token = get_token_cached(url, try_mac, proxy)
```
- Zeile ~10744: Proxy-Retry-Logik mit Token-Cache

#### Redirect-Modus
```python
token = get_token_cached(url, try_mac, proxy)
```
- Zeile ~10969: Direct-Redirect mit Token-Cache

### 3. Settings-Integration

#### Token Cache aktivieren/deaktivieren
- **Setting**: `token cache enabled` (Standard: `true`)
- **Verhalten wenn aktiviert**: Tokens werden gecacht, schnellerer Stream-Start
- **Verhalten wenn deaktiviert**: Bei jedem Sender wird neuer Token geholt (wie vorher)

#### Token Cache TTL
- **Setting**: `token cache ttl` (Standard: `270` Sekunden)
- **Bereich**: 30-600 Sekunden
- **Empfehlung**: 270s = watchdog_timeout × 0.9
- **UI**: TTL-Einstellung wird nur angezeigt wenn Token-Cache aktiviert ist

### 4. Automatische Cache-Verwaltung

#### Invalidierung bei Fehlern
```python
def invalidate_token_cache(url, mac):
    """Invalidate cached token for a MAC (call on stream failure)."""
    token_cache.invalidate(url, mac)
```
- Wird aufgerufen bei Stream-Fehlern (Zeile ~2547)
- Verhindert, dass fehlerhafte Tokens wiederverwendet werden

#### Memory-Management
- **Max. Einträge**: 500 (verhindert Speicherlauf)
- **Automatische Bereinigung**: 
  - Bei vollem Cache werden abgelaufene Einträge entfernt
  - Falls immer noch voll: Ältester Eintrag wird entfernt (LRU)
- **Cleanup-Funktion**: `token_cache.cleanup_expired()` entfernt abgelaufene Einträge

#### Cache-Statistiken
```python
stats = token_cache.stats()
# Returns: {"total": 123, "valid": 100, "expired": 23}
```

## Vergleich mit Macstrom

| Feature | Macstrom | MacReplayXC | Status |
|---------|----------|-------------|--------|
| Token-Cache pro (URL, MAC) | ✅ | ✅ | ✅ Identisch |
| Thread-safe | ✅ | ✅ | ✅ Identisch |
| TTL-basiert | ✅ | ✅ | ✅ Identisch |
| Memory-Limit | ✅ | ✅ (500) | ✅ Identisch |
| Automatische Bereinigung | ✅ | ✅ | ✅ Identisch |
| Invalidierung bei Fehler | ✅ | ✅ | ✅ Identisch |
| Alle Streaming-Modi | ✅ | ✅ | ✅ Identisch |
| Settings-Integration | ✅ | ✅ | ✅ Identisch |

## Implementierungsdetails

### get_token_cached() Funktion

```python
def get_token_cached(url, mac, proxy=None):
    """
    Get token with caching. If enabled in settings, returns cached token if available.
    Falls back to fresh handshake on cache miss, when disabled, or if cached token fails.
    """
    settings = getSettings()
    cache_enabled = settings.get("token cache enabled", "true") == "true"

    if cache_enabled:
        cached = token_cache.get(url, mac)
        if cached:
            logger.debug(f"[TOKEN CACHE] Hit for MAC {mac}")
            return cached

    # Fresh handshake
    token = stb.getToken(url, mac, proxy)
    if token and cache_enabled:
        ttl = int(settings.get("token cache ttl", "270"))
        token_cache.set(url, mac, token, ttl)
        logger.debug(f"[TOKEN CACHE] Stored token for MAC {mac} (TTL: {ttl}s)")
    elif not token and cache_enabled:
        # Token failed - remove any stale cached entry
        token_cache.invalidate(url, mac)

    return token
```

### TokenCache Klasse

```python
class TokenCache:
    """Thread-safe in-memory token cache keyed by (portal_url, mac)."""
    MAX_ENTRIES = 500  # Prevent unbounded memory growth

    def __init__(self):
        self._cache = {}  # (url, mac) -> {"token": str, "expires_at": float}
        self._lock = threading.Lock()

    def get(self, url, mac):
        """Return cached token if still valid, else None."""
        key = (url, mac)
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.time() < entry["expires_at"]:
                return entry["token"]
            elif entry:
                del self._cache[key]
        return None

    def set(self, url, mac, token, ttl_seconds=270):
        """Cache a token with TTL. Evicts expired entries if cache is full."""
        key = (url, mac)
        with self._lock:
            # Evict expired entries if at capacity
            if len(self._cache) >= self.MAX_ENTRIES:
                now = time.time()
                expired = [k for k, v in self._cache.items() if now >= v["expires_at"]]
                for k in expired:
                    del self._cache[k]
                # If still full after eviction, remove oldest entry
                if len(self._cache) >= self.MAX_ENTRIES:
                    oldest = min(self._cache.items(), key=lambda x: x[1]["expires_at"])
                    del self._cache[oldest[0]]
            self._cache[key] = {
                "token": token,
                "expires_at": time.time() + ttl_seconds
            }

    def invalidate(self, url, mac):
        """Remove a token from cache (e.g. on stream failure)."""
        key = (url, mac)
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """Clear all cached tokens."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self):
        """Remove all expired entries. Called periodically."""
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._cache.items() if now >= v["expires_at"]]
            for k in expired:
                del self._cache[k]
            return len(expired)

    def stats(self):
        """Return cache statistics."""
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._cache.values() if now < e["expires_at"])
            return {"total": len(self._cache), "valid": valid, "expired": len(self._cache) - valid}
```

## Testing

### Test 1: Token-Cache aktiviert (Standard)
1. Settings öffnen
2. "Token Cache" ist aktiviert (grüner Schalter)
3. "Token Cache TTL" ist sichtbar (270s)
4. Sender wechseln → Logs zeigen `[TOKEN CACHE] Hit for MAC ...`
5. Schnellerer Stream-Start (keine Handshake-Verzögerung)

### Test 2: Token-Cache deaktiviert
1. Settings öffnen
2. "Token Cache" deaktivieren
3. "Token Cache TTL" wird ausgeblendet
4. Sender wechseln → Logs zeigen KEINE Cache-Meldungen
5. Bei jedem Sender wird neuer Token geholt (wie vorher)

### Test 3: Memory-Management
1. Viele verschiedene MACs verwenden (>500)
2. Cache bleibt bei 500 Einträgen
3. Älteste Einträge werden automatisch entfernt
4. Keine Memory-Leaks

### Test 4: Invalidierung bei Fehler
1. Stream startet mit MAC A
2. Stream schlägt fehl
3. Token für MAC A wird aus Cache entfernt
4. Nächster Versuch holt frischen Token

## Vorteile

1. **Schnellerer Stream-Start**: Keine Handshake-Verzögerung beim Channel-Wechsel
2. **Weniger Portal-Last**: Weniger Handshake-Requests an Portal
3. **Bessere User-Experience**: Instant Channel-Switching wie in Macstrom
4. **Memory-Safe**: Automatische Bereinigung verhindert Speicherlauf
5. **Flexibel**: Kann per Setting aktiviert/deaktiviert werden
6. **Alle Modi**: FFmpeg, HLS, Proxy, Redirect nutzen alle den Cache

## Changelog

- **2026-04-15**: Token-Cache vollständig implementiert wie Macstrom
  - Alle 4 Streaming-Modi nutzen `get_token_cached()`
  - Settings-Integration mit dynamischer TTL-Anzeige
  - Memory-Management mit 500-Einträge-Limit
  - Automatische Invalidierung bei Fehlern
  - Thread-safe Implementierung
