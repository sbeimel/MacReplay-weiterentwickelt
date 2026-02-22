# Hardcoded Values Information - MacReplayXC v4.2.0

**Date**: 2026-02-21  
**Status**: INFO ONLY (Not implemented)  
**Related Issues**: Fix #10 (Hardcoded Timeout Values)

---

## 1. HARDCODED TIMEOUT VALUES

### app-docker.py

#### Database Connections
- **Line 1560**: `timeout=30.0` - SQLite connection timeout (30 seconds)
  - Location: `get_db_connection()`
  - Purpose: Prevents deadlocks during concurrent database access

#### HLS Stream Manager
- **Line 1053**: `inactive_timeout = 120` - HLS stream inactive timeout (2 minutes)
  - Location: `HLSStreamManager.__init__()`
  - Purpose: Auto-cleanup of inactive HLS streams
  - Note: Overrides constructor parameter default of 30

- **Line 1133**: `timeout=5` - FFmpeg graceful termination timeout (5 seconds)
  - Location: `HLSStreamManager._stop_stream()`
  - Purpose: Wait time before force-killing FFmpeg

- **Line 1138**: `timeout=2` - FFmpeg force-kill timeout (2 seconds)
  - Location: `HLSStreamManager._stop_stream()`
  - Purpose: Final wait after kill signal

- **Line 1267**: `timeout = 3000000` - FFmpeg read timeout (3 seconds in microseconds)
  - Location: `HLSStreamManager.start_stream()`
  - Purpose: Default FFmpeg input timeout if not configured

- **Line 1405**: `timeout=2` - FFmpeg error cleanup timeout (2 seconds)
  - Location: `HLSStreamManager.start_stream()` exception handler
  - Purpose: Wait time when killing FFmpeg after error

#### XC User Session Management
- **Line 2105**: `timeout = 300` - XC user session timeout (5 minutes)
  - Location: `cleanup_xc_user_sessions()`
  - Purpose: Remove inactive XC user sessions

#### API Requests
- **Line 3398**: `timeout=30` - Stalker API channel request (30 seconds)
  - Location: `getChannelLink()` - Stalker portal channel fetch

- **Line 3480**: `timeout=5` - Stream link test timeout (5 seconds)
  - Location: `getChannelLink()` - Quick stream validation

- **Line 4820**: `timeout=10` - Stalker handshake (10 seconds)
  - Location: `/api/test_portal` - Portal handshake test

- **Line 4850**: `timeout=10` - Stalker profile fetch (10 seconds)
  - Location: `/api/test_portal` - Get profile test

- **Line 4874**: `timeout=10` - Stalker account info (10 seconds)
  - Location: `/api/test_portal` - Account info test

- **Line 6726**: `timeout=60` - EPG download (60 seconds)
  - Location: `getEPGFallback()` - EPG XML download

- **Line 9010**: `timeout=10` - Stream URL HEAD request (10 seconds)
  - Location: `/stream_proxy` - Check stream availability

- **Line 9090**: `timeout=5` - FFprobe termination (5 seconds)
  - Location: `/stream_proxy` - FFprobe cleanup

- **Line 9141**: `timeout=10` - Stream HEAD request (10 seconds)
  - Location: `/stream_direct` - Get stream headers

- **Line 9156**: `timeout=60` - Stream GET request (60 seconds)
  - Location: `/stream_direct` - Stream data fetch

- **Line 12065**: `timeout=10` - Proxy test (10 seconds)
  - Location: `testProxy()` - Proxy connectivity test

- **Line 12181**: `inactive_timeout = 30` - Default HLS inactive timeout (30 seconds)
  - Location: Main initialization - Fallback value

- **Line 12222**: `channel_timeout=8192` - CherryPy channel timeout (2+ hours)
  - Location: CherryPy server config
  - Purpose: Long-running stream support

### stb.py

#### Portal Discovery & Token Requests
- **Line 185**: `timeout=10` - xpcom.common.js discovery (10 seconds)
  - Location: `getToken()` - Portal URL discovery

- **Line 204**: `timeout=10` - xpcom.common.js no-proxy fallback (10 seconds)
  - Location: `getToken()` - Portal URL discovery without proxy

- **Line 324**: `timeout=20` - Token request (20 seconds)
  - Location: `getToken()` - Initial token fetch

- **Line 350**: `timeout=20` - Token request MAG254 fallback (20 seconds)
  - Location: `getToken()` - MAG254 device emulation

- **Line 371**: `timeout=20` - Token request MAG420 fallback (20 seconds)
  - Location: `getToken()` - MAG420 device emulation

#### Channel & Genre Requests
- **Line 458**: `timeout=15` - All channels request (15 seconds)
  - Location: `getAllChannels()` - Fetch all channels

- **Line 479**: `timeout=15` - All channels retry (15 seconds)
  - Location: `getAllChannels()` - Retry on failure

- **Line 538**: `timeout=15` - Ordered channels request (15 seconds)
  - Location: `getOrderedChannels()` - Fetch ordered channels

- **Line 549**: `timeout=15` - Ordered channels retry (15 seconds)
  - Location: `getOrderedChannels()` - Retry on failure

- **Line 611**: `timeout=30` - Channels by genre (30 seconds)
  - Location: `getChannelsByGenre()` - Fetch genre channels

- **Line 632**: `timeout=30` - Channels by genre retry (30 seconds)
  - Location: `getChannelsByGenre()` - Retry on failure

- **Line 674**: `timeout=10` - Genre list request (10 seconds)
  - Location: `getGenres()` - Fetch available genres

- **Line 692**: `timeout=10` - Genre list retry (10 seconds)
  - Location: `getGenres()` - Retry on failure

#### VOD & Series Requests
- **Line 748**: `timeout=15` - VOD categories (15 seconds)
  - Location: `getVODCategories()` - Fetch VOD categories

- **Line 765**: `timeout=15` - VOD categories retry (15 seconds)
  - Location: `getVODCategories()` - Retry on failure

- **Line 807**: `timeout=30` - VOD list (30 seconds)
  - Location: `getVODList()` - Fetch VOD items

- **Line 824**: `timeout=30` - VOD list retry (30 seconds)
  - Location: `getVODList()` - Retry on failure

- **Line 918**: `timeout=10` - Stream link test (10 seconds)
  - Location: `testStreamLink()` - Test stream availability

- **Line 956**: `timeout=15` - VOD info (15 seconds)
  - Location: `getVODInfo()` - Fetch VOD details

- **Line 973**: `timeout=15` - VOD info retry (15 seconds)
  - Location: `getVODInfo()` - Retry on failure

- **Line 999**: `timeout=15` - Series categories (15 seconds)
  - Location: `getSeriesCategories()` - Fetch series categories

- **Line 1016**: `timeout=15` - Series categories retry (15 seconds)
  - Location: `getSeriesCategories()` - Retry on failure

- **Line 1042**: `timeout=30` - Series list (30 seconds)
  - Location: `getSeriesList()` - Fetch series items

- **Line 1059**: `timeout=30` - Series list retry (30 seconds)
  - Location: `getSeriesList()` - Retry on failure

#### EPG & Additional Requests
- **Line 1172**: `timeout=15` - EPG request (15 seconds)
  - Location: `getEPG()` - Fetch EPG data

- **Line 1189**: `timeout=15` - EPG retry (15 seconds)
  - Location: `getEPG()` - Retry on failure

- **Line 1302**: `timeout=15` - Series info (15 seconds)
  - Location: `getSeriesInfo()` - Fetch series details

- **Line 1319**: `timeout=15` - Series info retry (15 seconds)
  - Location: `getSeriesInfo()` - Retry on failure

- **Line 1376**: `timeout=15` - Series seasons (15 seconds)
  - Location: `getSeriesSeasons()` - Fetch season list

- **Line 1393**: `timeout=15` - Series seasons retry (15 seconds)
  - Location: `getSeriesSeasons()` - Retry on failure

- **Line 1427**: `timeout=15` - Watchlist (15 seconds)
  - Location: `getWatchlist()` - Fetch user watchlist

- **Line 1444**: `timeout=15` - Watchlist retry (15 seconds)
  - Location: `getWatchlist()` - Retry on failure

- **Line 1484**: `timeout=10` - Stream URL fetch (10 seconds)
  - Location: `getStreamUrl()` - Get final stream URL

- **Line 1501**: `timeout=10` - Stream URL retry (10 seconds)
  - Location: `getStreamUrl()` - Retry on failure

### vavoo/vavoo2.py

#### FFmpeg & FFprobe
- **Line 39**: `FFMPEG_PROCESS_TIMEOUT = 12` - FFmpeg process timeout (12 seconds)
  - Purpose: Maximum FFmpeg execution time

- **Line 40**: `FFPROBE_PROCESS_TIMEOUT = 15` - FFprobe timeout (15 seconds)
  - Purpose: Maximum FFprobe execution time

#### Connection & Cache
- **Line 42**: `CONNECTION_TIMEOUT = 300` - Connection timeout (5 minutes)
  - Purpose: HTTP connection timeout

- **Line 56**: `REFRESH_HARD_TIMEOUT = 300` - Refresh hard timeout (5 minutes)
  - Purpose: Maximum time for refresh operations

#### HTTP Requests
- **Line 201**: `timeout=1.2` - HEAD request timeout (1.2 seconds)
  - Location: `head_url()` - Quick URL check

- **Line 2044**: `timeout=6` - GET request timeout (6 seconds)
  - Location: Stream fetch

- **Line 2142**: `timeout=6` - GET request timeout (6 seconds)
  - Location: Stream fetch with headers

- **Line 2546**: `timeout=10` - Auth signature request (10 seconds)
  - Location: `get_auth_signature()` - Authentication

- **Line 2591**: `timeout=10` - Auth request (10 seconds)
  - Location: Authentication flow

#### Server Configuration
- **Line 3491**: `channel_timeout=120` - CherryPy channel timeout (2 minutes)
  - Location: CherryPy server config

### utils.py

- **Line 644**: `timeout=10` - Shadowsocks connectivity test (10 seconds)
  - Location: `create_shadowsocks_session()` - Test proxy connection

---

## 2. USER-AGENT INCONSISTENCIES

### Overview
The codebase uses multiple different User-Agent strings across different modules and functions. This can cause issues with portal compatibility and tracking.

### User-Agent Variants Found

#### Variant 1: Short MAG Emulation
```
"Mozilla/5.0 (QtEmbedded; U; Linux; C)"
```
**Used in**:
- `app-docker.py`: Lines 3367, 9002, 9118
- `stb.py`: Lines 654, 723, 786, 899, 935, 978, 1021, 1151, 1281, 1355, 1406, 1466

**Purpose**: Minimal MAG device emulation

#### Variant 2: Full MAG200 Emulation
```
"Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
```
**Used in**:
- `stb.py`: Lines 169, 250, 431, 511, 586

**Purpose**: Complete MAG200 device emulation with version info

#### Variant 3: Full MAG250 Emulation (with X-User-Agent)
```
User-Agent: "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3"
X-User-Agent: "Model: MAG250; Link: WiFi; MAC: {mac_address}"
```
**Used in**:
- `app-docker.py`: Lines 4811-4812, 9849

**Purpose**: MAG250 emulation with extended device info

#### Variant 4: MAG254 Fallback
```
User-Agent: "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2712 Safari/533.3"
X-User-Agent: "Model: MAG254; Link: WiFi"
```
**Used in**:
- `stb.py`: Lines 341-342

**Purpose**: MAG254 fallback when MAG250 fails

#### Variant 5: MAG420 Fallback
```
User-Agent: "Mozilla/5.0 (Linux; Android 7.0; MAG420) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.84 Mobile Safari/537.36"
X-User-Agent: "Model: MAG420; Link: WiFi"
```
**Used in**:
- `stb.py`: Lines 363-364

**Purpose**: MAG420 Android-based fallback

#### Variant 6: Vavoo Electron
```
"electron-fetch/1.0 electron (+https://github.com/arantes555/electron-fetch)"
```
**Used in**:
- `vavoo/vavoo2.py`: Lines 162, 204, 1756, 2000, 2046, 2144

**Purpose**: Vavoo service emulation

#### Variant 7: Vavoo MediaHubMX
```
"MediaHubMX/2"
```
**Used in**:
- `vavoo/vavoo2.py`: Line 1124

**Purpose**: MediaHubMX API authentication

#### Variant 8: Vavoo OkHttp
```
"okhttp/4.11.0"
```
**Used in**:
- `vavoo/vavoo2.py`: Lines 2519, 2563

**Purpose**: Android OkHttp client emulation

#### Variant 9: Configurable User-Agent
```python
getSettings().get("user agent", "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3")
```
**Used in**:
- `app-docker.py`: Line 9849

**Purpose**: User-configurable User-Agent from settings

### Inconsistency Issues

1. **Mixed MAG Versions**: Code uses MAG200, MAG250, MAG254, and MAG420 strings inconsistently
2. **Version Numbers**: Different stbapp versions (ver: 2, ver: 4) and revisions (rev: 250, rev: 2116, rev: 2712)
3. **X-User-Agent Header**: Sometimes included, sometimes not
4. **MAC Address**: Sometimes included in X-User-Agent, sometimes not
5. **Vavoo Module**: Uses completely different User-Agent strings (Electron, MediaHubMX, OkHttp)

### Recommendations (INFO ONLY)

#### For Stalker/MAG Portals:
- **Standardize on MAG250**: Most compatible with modern portals
- **Always include X-User-Agent**: Required by many portals
- **Include MAC in X-User-Agent**: Improves portal tracking
- **Use fallback chain**: MAG250 → MAG254 → MAG420 (already implemented in `getToken()`)

#### For Vavoo:
- Keep separate User-Agent strings (required by Vavoo service)
- No changes needed

#### Suggested Standard User-Agent:
```python
# Primary (MAG250)
User-Agent: "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3"
X-User-Agent: "Model: MAG250; Link: WiFi; MAC: {mac_address}"

# Fallback 1 (MAG254)
User-Agent: "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2712 Safari/533.3"
X-User-Agent: "Model: MAG254; Link: WiFi"

# Fallback 2 (MAG420)
User-Agent: "Mozilla/5.0 (Linux; Android 7.0; MAG420) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.84 Mobile Safari/537.36"
X-User-Agent: "Model: MAG420; Link: WiFi"
```

---

## Summary

### Hardcoded Timeouts
- **Total Found**: 50+ hardcoded timeout values
- **Range**: 1.2 seconds to 8192 seconds (2+ hours)
- **Most Common**: 10 seconds (API requests), 15 seconds (data fetches), 30 seconds (large requests)
- **Critical**: Database (30s), HLS streams (120s), FFmpeg (5s/2s)

### User-Agent Strings
- **Total Variants**: 9 different User-Agent patterns
- **Stalker/MAG**: 5 variants (inconsistent)
- **Vavoo**: 3 variants (intentional, service-specific)
- **Configurable**: 1 variant (user settings)

### Impact
- **Hardcoded Timeouts**: Could be made configurable for different network conditions
- **User-Agent Inconsistencies**: May cause portal compatibility issues, but fallback chain mitigates this

---

**Note**: This document is for INFORMATION ONLY. No implementation changes were made.
