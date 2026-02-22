# Legacy Code Cleanup - 2026-02-21

## Übersicht
Entfernung von ungenutztem Legacy Code und Integration der experimentellen Multi-API MAC Busy Checks an der richtigen Stelle.

## Problem
Es existierten zwei verschiedene MAC-Auswahl-Systeme parallel:

### 1. DB-basiertes Scoring (AKTIV in Production)
- **Funktion**: `calculate_mac_score()` in `app-docker.py`
- **Verwendet von**: Alle Streaming-Modi (FFmpeg, Proxy, HLS, Redirect)
- **Basis**: Success/Fail Counter aus Datenbank
- **Score**: 0-110+ Punkte
- **Features**:
  - Success Rate (0-45 Punkte)
  - Recency/Aktualität (0-40 Punkte)
  - Reliability Bonus (0-20 Punkte)
  - Soft Start für neue MACs
  - Failure Rate Acceleration
  - Consecutive Failures Penalty

### 2. Stalker API-basiertes Scoring (LEGACY, ungenutzt)
- **Funktion**: `getMacAvailabilityScore()` in `stb.py`
- **Verwendet von**: `selectBestMac()` - ABER diese Funktion wurde NIRGENDWO aufgerufen!
- **Basis**: watchdog_timeout Schätzung
- **Score**: 0-100 Punkte
- **Features**:
  - Usage Ratio Berechnung
  - Internal Usage Penalty
  - Available Streams Bonus

## Durchgeführte Änderungen

### 1. Legacy Code entfernt (stb.py)

#### Gelöschte Funktionen:
```python
# Hauptfunktionen
- getMacAvailabilityScore()          # 0-100 Scoring (ungenutzt)
- selectBestMac()                     # MAC-Auswahl (ungenutzt)

# Helper-Funktionen (alle nutzten selectBestMac)
- getAllChannelsWithSmartMac()
- getStreamLinkWithSmartMac()
- getEpgWithSmartMac()
- getVodCategoriesWithSmartMac()
- getVodItemsWithSmartMac()
- getSeriesCategoriesWithSmartMac()
- getSeriesItemsWithSmartMac()
- getVodLinkWithSmartMac()
- getSeriesLinkWithSmartMac()
- getMacStatusSummary()
```

**Grund**: Diese Funktionen wurden in Production nicht verwendet. Das DB-basierte Scoring-System (`calculate_mac_score()`) ist das aktive System.

#### Behalten:
```python
- checkMacStatus()                    # Wird von WebUI genutzt (MAC Status Anzeige)
- check_ministra_modern_api()         # EXPERIMENTAL - für Data Collection
- check_xc_xui_api()                  # EXPERIMENTAL - für Data Collection
```

### 2. Experimentelle Multi-API Checks integriert (app-docker.py)

**Stelle**: PROXY RETRY Mode, Lines ~9945-10000

**Vorher**:
```python
if skip_busy:
    profile = stb.getProfile(url, try_mac, try_token, proxy)
    watchdog_timeout = profile['watchdog_timeout']
    if watchdog_timeout < 60:
        logger.warning(f"[PROXY RETRY] MAC {try_mac} is busy (watchdog: {watchdog_timeout}s), trying next")
        continue
    logger.info(f"[PROXY RETRY] MAC {try_mac} looks available (watchdog: {watchdog_timeout}s)")
```

**Nachher**:
```python
if skip_busy:
    profile = stb.getProfile(url, try_mac, try_token, proxy)
    watchdog_timeout = profile['watchdog_timeout']
    
    # ============================================================================
    # EXPERIMENTAL: Multi-API MAC Busy Check (Data Collection Mode)
    # ============================================================================
    # Status: EXPERIMENTAL - Logging only, not used for decision yet
    # Date: 2026-02-21
    # Purpose: Collect data from modern APIs to compare with watchdog estimation
    # 
    # Decision still based on watchdog_timeout < 60 (UNCHANGED)
    # Modern API data is only logged for analysis
    # ============================================================================
    
    # EXPERIMENTAL: Try Ministra Modern API for additional data
    try:
        ministra_result = stb.check_ministra_modern_api(url, try_mac, proxy)
        if ministra_result.get('success'):
            logger.info(f"[EXPERIMENTAL] 🔍 Ministra API data for MAC {try_mac}:")
            logger.info(f"[EXPERIMENTAL]   ├─ Online: {ministra_result.get('online')}")
            logger.info(f"[EXPERIMENTAL]   ├─ Current Stream: {ministra_result.get('current_stream') or 'None'}")
            logger.info(f"[EXPERIMENTAL]   ├─ Active Sessions: {ministra_result.get('active_sessions')}")
            logger.info(f"[EXPERIMENTAL]   └─ Max Sessions: {ministra_result.get('max_sessions')}")
            
            # Highlight if data conflicts with watchdog
            if ministra_result.get('online') or ministra_result.get('current_stream'):
                logger.warning(f"[EXPERIMENTAL] ⚠️ Ministra shows BUSY (online={ministra_result.get('online')}, stream={ministra_result.get('current_stream')}) vs watchdog={watchdog_timeout}s")
    except Exception as e:
        logger.debug(f"[EXPERIMENTAL] Ministra API check failed: {e}")
    
    # EXPERIMENTAL: Try XC/XUI API for additional data
    try:
        xc_result = stb.check_xc_xui_api(url, try_mac, proxy)
        if xc_result.get('success'):
            logger.info(f"[EXPERIMENTAL] 🔍 XC/XUI API data for MAC {try_mac}:")
            logger.info(f"[EXPERIMENTAL]   ├─ Active Connections: {xc_result.get('active_cons')}")
            logger.info(f"[EXPERIMENTAL]   ├─ Max Connections: {xc_result.get('max_connections')}")
            logger.info(f"[EXPERIMENTAL]   └─ Status: {xc_result.get('status')}")
            
            # Highlight if data conflicts with watchdog
            active_cons = int(xc_result.get('active_cons', 0))
            if active_cons > 0:
                logger.warning(f"[EXPERIMENTAL] ⚠️ XC/XUI shows {active_cons} active connection(s) vs watchdog={watchdog_timeout}s")
    except Exception as e:
        logger.debug(f"[EXPERIMENTAL] XC/XUI API check failed: {e}")
    
    # ============================================================================
    # PRIMARY DECISION: Still based on watchdog_timeout (UNCHANGED)
    # ============================================================================
    
    if watchdog_timeout < 60:
        logger.warning(f"[PROXY RETRY] MAC {try_mac} is busy (watchdog: {watchdog_timeout}s), trying next")
        continue
    logger.info(f"[PROXY RETRY] MAC {try_mac} looks available (watchdog: {watchdog_timeout}s)")
```

## Wichtige Punkte

### 1. Keine Breaking Changes
- ✅ Entscheidungslogik UNVERÄNDERT (watchdog_timeout < 60)
- ✅ Scoring-System UNVERÄNDERT (DB-basiert)
- ✅ Alle Production-Features funktionieren weiter
- ✅ Nur ungenutzter Code entfernt

### 2. Experimentelle Features
- ✅ Klar als EXPERIMENTAL markiert
- ✅ Nur Logging, keine Entscheidungen
- ✅ Fehler werden abgefangen (try/except)
- ✅ Keine Auswirkung auf Stream-Performance

### 3. Data Collection Ziel
Die experimentellen Checks sammeln Daten um zu vergleichen:
- **Watchdog Estimation** (aktuell): Schätzt Auslastung aus watchdog_timeout
- **Ministra Modern API**: Zeigt direkt online/offline Status
- **XC/XUI API**: Zeigt direkt aktive Verbindungen

**Beispiel Log**:
```
[PROXY RETRY] MAC 00:1A:79:XX:XX looks available (watchdog: 87s)
[EXPERIMENTAL] 🔍 Ministra API data for MAC 00:1A:79:XX:XX:
[EXPERIMENTAL]   ├─ Online: 1
[EXPERIMENTAL]   ├─ Current Stream: Channel 123
[EXPERIMENTAL]   ├─ Active Sessions: 2
[EXPERIMENTAL]   └─ Max Sessions: 3
[EXPERIMENTAL] ⚠️ Ministra shows BUSY (online=1, stream=Channel 123) vs watchdog=87s
```

→ Hier sieht man: Watchdog sagt "verfügbar" (87s), aber Ministra zeigt "busy" (aktiver Stream)!

## Nächste Schritte

### Phase 1: Data Collection (JETZT)
- ✅ Experimentelle Checks implementiert
- ✅ Logging aktiviert
- ⏳ Daten sammeln (1-2 Wochen)
- ⏳ Logs analysieren

### Phase 2: Evaluation (später)
- Vergleich: Watchdog vs. Modern APIs
- Fragen:
  - Wie oft stimmen sie überein?
  - Wie oft widersprechen sie sich?
  - Welche Methode ist zuverlässiger?

### Phase 3: Implementation (optional)
Falls Modern APIs besser sind:
- Entscheidungslogik anpassen
- Fallback-Chain implementieren
- Testing in Production

Falls Watchdog besser ist:
- Experimentelle Checks entfernen
- Bei watchdog_timeout bleiben

## Statistik

### Code entfernt:
- **10 Funktionen** gelöscht (~400 Zeilen)
- **0 Breaking Changes**

### Code hinzugefügt:
- **~50 Zeilen** experimentelles Logging
- **0 Änderungen** an Entscheidungslogik

### Netto:
- **~350 Zeilen** weniger Code
- **Klarere Struktur** (nur ein Scoring-System)
- **Bessere Wartbarkeit**

## Dateien geändert

### stb.py
- ❌ Gelöscht: `getMacAvailabilityScore()`
- ❌ Gelöscht: `selectBestMac()`
- ❌ Gelöscht: 8x `*WithSmartMac()` Funktionen
- ✅ Behalten: `checkMacStatus()` (WebUI)
- ✅ Behalten: `check_ministra_modern_api()` (EXPERIMENTAL)
- ✅ Behalten: `check_xc_xui_api()` (EXPERIMENTAL)

### app-docker.py
- ✅ Hinzugefügt: Experimentelles Logging im PROXY RETRY Mode
- ✅ Markiert: Alle experimentellen Checks mit EXPERIMENTAL Header
- ✅ Unverändert: Entscheidungslogik (watchdog_timeout < 60)

## Version
Implementiert in Version 4.2.0 (2026-02-21)

## Siehe auch
- [MAC_SCORING_SYSTEM.md](MAC_SCORING_SYSTEM.md) - DB-basiertes Scoring (aktiv)
- [MAC_BUSY_CHECK_MULTI_API.md](MAC_BUSY_CHECK_MULTI_API.md) - Experimentelle Checks
- [FIXES_IMPLEMENTED_2026-02-21.md](FIXES_IMPLEMENTED_2026-02-21.md) - Alle Fixes
