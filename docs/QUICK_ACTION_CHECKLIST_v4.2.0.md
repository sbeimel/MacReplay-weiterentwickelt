# ⚡ QUICK ACTION CHECKLIST - MacReplayXC v4.2.0
## 1-Week Implementation Plan
**Goal**: Fix 6 critical issues → 8.2/10 to 8.8/10

---

## 📅 DAY 1: QUICK WINS (2 Hours)

### ✅ Task 1: Fix Consecutive Failure Tracking (30 min)
**File**: `app-docker.py`, Lines 119-192  
**Priority**: HIGH

```python
# Add to calculate_mac_score()
consecutive_failures = mac_stats.get('consecutive_failures', 0)
if consecutive_failures > 0:
    consecutive_penalty = min(30, 5 * (2 ** min(consecutive_failures, 4)))
    total_score -= consecutive_penalty
```

**Test**:
```bash
pytest tests/test_mac_scoring.py::test_consecutive_failures
```

- [ ] Code implemented
- [ ] Tests pass
- [ ] Committed to git

---

### ✅ Task 2: Fix Watchdog Timeout Validation (15 min)
**File**: `app-docker.py`, Lines ~9750  
**Priority**: HIGH

```python
# Replace default value with explicit check
if 'watchdog_timeout' not in profile:
    logger.warning(f"MAC {mac} - watchdog_timeout missing, skipping")
    continue

watchdog_timeout = profile['watchdog_timeout']
if not isinstance(watchdog_timeout, (int, float)):
    logger.warning(f"MAC {mac} - invalid watchdog_timeout type")
    continue

if watchdog_timeout < 60:
    logger.info(f"MAC {mac} is busy (watchdog: {watchdog_timeout}s)")
    continue
```

**Test**:
```bash
pytest tests/test_mac_selection.py::test_watchdog_validation
```

- [ ] Code implemented
- [ ] Tests pass
- [ ] Committed to git

---

### ✅ Task 3: Add HLS Segment Cleanup (10 min)
**File**: `app-docker.py`, Lines 1013-1055  
**Priority**: HIGH

```python
# Add to _stop_stream() method in HLSStreamManager
def _stop_stream(self, stream_key):
    # ... existing code ...
    
    # Cleanup HLS segments
    portal_id = stream_info.get('portal_id')
    channel_id = stream_info.get('channel_id')
    if portal_id and channel_id:
        output_path = f"/dev/shm/hls_{portal_id}_{channel_id}/"
        if os.path.exists(output_path):
            try:
                import shutil
                shutil.rmtree(output_path)
                logger.info(f"Cleaned up HLS segments: {output_path}")
            except Exception as e:
                logger.error(f"Failed to cleanup HLS segments: {e}")
```

**Test**:
```bash
# Start HLS stream, stop it, check /dev/shm
ls -la /dev/shm/hls_*  # Should be empty
```

- [ ] Code implemented
- [ ] Manual test passed
- [ ] Committed to git

---

### ✅ Task 4: Fix FFmpeg Resource Leak (10 min)
**File**: `app-docker.py`, HLS streaming section  
**Priority**: HIGH

```python
# Wrap FFmpeg subprocess in try-finally
ffmpeg_sp = None
try:
    ffmpeg_sp = subprocess.Popen([...])
    # ... streaming logic ...
finally:
    if ffmpeg_sp:
        try:
            ffmpeg_sp.terminate()
            ffmpeg_sp.wait(timeout=5)
        except:
            ffmpeg_sp.kill()
```

**Test**:
```bash
# Check for zombie processes
ps aux | grep ffmpeg | grep defunct  # Should be empty
```

- [ ] Code implemented
- [ ] Manual test passed
- [ ] Committed to git

---

### 📊 Day 1 Checkpoint

- [ ] All 4 tasks completed
- [ ] All tests pass
- [ ] Code committed
- [ ] Docker image rebuilt
- [ ] Deployed to staging
- [ ] Smoke test passed

**Time**: 2 hours  
**Score**: 8.2/10 → 8.3/10

---

## 📅 DAYS 2-3: CONNECTION LEAKS (2-3 Days)

### ✅ Task 5: Fix Connection Leaks (23 instances)
**Files**: `app-docker.py` (20), `vavoo2.py` (3)  
**Priority**: CRITICAL

**Pattern to Apply**:
```python
conn = None
try:
    conn = get_db_connection()
    # ... operations ...
except Exception as e:
    logger.error(f"Error: {e}")
    raise
finally:
    if conn:
        try:
            conn.close()
        except:
            pass
```

**Functions to Fix** (Top 10):
1. [ ] `vods_portals()` - Line 1970
2. [ ] `vods_categories()` - Line 2020
3. [ ] `editor_data()` - Line 4745
4. [ ] `generate_portal_m3u()` - Line 4111
5. [ ] `refresh_xmltv()` - Line 6329
6. [ ] `xc_get_playlist_impl()` - Line 7342
7. [ ] `editor_bulk_edit_undo()` - Line 5255
8. [ ] `cleanup_orphaned_channels()` - Line 5958
9. [ ] `vods_stream()` - Line 2780
10. [ ] `editor_deactivate_duplicates()` - Line 5504

**Remaining 13 functions**:
11. [ ] `vods_items()` - Line 2055
12. [ ] `vods_selection_get()` - Line 2109
13. [ ] `vods_settings_get()` - Line 2376
14. [ ] `vods_load_categories()` - Line 2599
15. [ ] `editor_portals()` - Line 4795
16. [ ] `editor_genres()` - Line 4820
17. [ ] `editor_portal_stats()` - Line 4847
18. [ ] `editor_portal_channels()` - Line 4900
19. [ ] `editor_bulk_edit_history()` - Line 5308
20. [ ] `editor_bulk_edit_saved_rules()` - Line 5344
21. [ ] `editor_bulk_edit_clear_saved_rules()` - Line 5379
22. [ ] `editor_reset_all_customizations()` - Line 5403
23. [ ] `editorReset()` - Line 5435

**Test**:
```bash
# Load test with 10 concurrent streams for 30 minutes
pytest tests/test_load.py::test_concurrent_streams

# Check for connection leaks
lsof -p $(pgrep -f app-docker.py) | grep channels.db
# Should be 0-2 connections, not 20+
```

### 📊 Days 2-3 Checkpoint

- [ ] All 23 functions fixed
- [ ] Load test passed (10 streams, 30 min)
- [ ] No connection leaks detected
- [ ] Code committed
- [ ] Deployed to staging
- [ ] Monitored for 24 hours

**Time**: 2-3 days  
**Score**: 8.3/10 → 8.5/10

---

## 📅 DAY 4: RACE CONDITIONS (1 Day)

### ✅ Task 6: Add Thread Locks
**File**: `app-docker.py`  
**Priority**: CRITICAL

**Step 1: Add locks at module level**
```python
# After imports, add:
import threading

occupied_lock = threading.Lock()
config_lock = threading.RLock()
mac_score_update_lock = threading.Lock()
```

- [ ] Locks added

**Step 2: Wrap occupied dictionary access**
```python
# Find all: occupied[key] = value
# Replace with:
with occupied_lock:
    occupied[key] = value

# Find all: value = occupied.get(key)
# Replace with:
with occupied_lock:
    value = occupied.get(key)
```

- [ ] All occupied access wrapped (~15 locations)

**Step 3: Wrap config dictionary access**
```python
# Find all: config["key"] = value
# Replace with:
with config_lock:
    config["key"] = value

# Find all: value = config.get("key")
# Replace with:
with config_lock:
    value = config.get("key")
```

- [ ] All config access wrapped (~20 locations)

**Step 4: Wrap MAC score updates**
```python
def update_mac_score_in_db(portal_id, channel_id, mac, is_success, duration=None):
    with mac_score_update_lock:
        conn = None
        try:
            conn = get_db_connection()
            # ... existing logic ...
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating MAC score: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
```

- [ ] MAC score updates wrapped (~5 locations)

**Test**:
```bash
# Concurrent access test
pytest tests/test_concurrent_access.py

# Monitor for "database is locked" errors
tail -f logs/app.log | grep "locked"  # Should be none
```

### 📊 Day 4 Checkpoint

- [ ] All locks implemented
- [ ] Concurrent test passed
- [ ] No race conditions detected
- [ ] Code committed
- [ ] Deployed to staging
- [ ] Monitored for 24 hours

**Time**: 1 day  
**Score**: 8.5/10 → 8.7/10

---

## 📅 DAY 5: TOKEN REFRESH (1 Day)

### ✅ Task 7: Implement Token Caching
**File**: `stb.py`  
**Priority**: CRITICAL

**Step 1: Add token cache at module level**
```python
# After imports in stb.py:
import threading
import time

_token_cache = {}  # {(url, mac): (token, timestamp)}
_token_cache_lock = threading.Lock()
```

- [ ] Token cache added

**Step 2: Add token refresh function**
```python
def get_or_refresh_token(url, mac, proxy=None):
    """Get token from cache or refresh if expired."""
    key = (url, mac)
    
    with _token_cache_lock:
        if key in _token_cache:
            token, timestamp = _token_cache[key]
            age = time.time() - timestamp
            
            # Token valid for 1 hour, refresh at 50 minutes
            if age < 3000:  # 50 minutes
                logger.debug(f"Using cached token for {mac} (age: {age:.0f}s)")
                return token
            else:
                logger.info(f"Token expired for {mac} (age: {age:.0f}s), refreshing...")
        
        # Get new token
        token = getToken(url, mac, proxy)
        if token:
            _token_cache[key] = (token, time.time())
            logger.info(f"Cached new token for {mac}")
        
        return token

def clear_token_cache():
    """Clear token cache (for testing or manual refresh)."""
    global _token_cache
    with _token_cache_lock:
        _token_cache.clear()
        logger.info("Token cache cleared")
```

- [ ] Token refresh function added

**Step 3: Replace all getToken() calls**
```bash
# In app-docker.py, find all:
token = stb.getToken(url, mac, proxy)

# Replace with:
token = stb.get_or_refresh_token(url, mac, proxy)
```

- [ ] All getToken() calls replaced (~10 locations)

**Test**:
```bash
# Test long stream (>1 hour)
pytest tests/test_token_refresh.py::test_long_stream

# Manual test: Play stream for 2 hours
# Should not fail after 1 hour
```

### 📊 Day 5 Checkpoint

- [ ] Token caching implemented
- [ ] Long stream test passed (>1 hour)
- [ ] Code committed
- [ ] Deployed to staging
- [ ] Monitored for 24 hours

**Time**: 1 day  
**Score**: 8.7/10 → 8.8/10

---

## 📊 WEEK 1 FINAL CHECKPOINT

### Completion Checklist

**Quick Wins (Day 1)**:
- [ ] Consecutive failure tracking fixed
- [ ] Watchdog validation fixed
- [ ] HLS cleanup added
- [ ] FFmpeg leak fixed

**Critical Fixes (Days 2-5)**:
- [ ] 23 connection leaks fixed
- [ ] Race conditions fixed
- [ ] Token refresh implemented

**Testing**:
- [ ] Unit tests pass
- [ ] Load test passed (10 streams, 30 min)
- [ ] Long stream test passed (>1 hour)
- [ ] No connection leaks detected
- [ ] No race conditions detected
- [ ] Monitored for 48 hours

**Deployment**:
- [ ] Code committed to git
- [ ] Docker image rebuilt
- [ ] Deployed to staging
- [ ] Smoke tests passed
- [ ] Ready for production

---

## 🎯 SUCCESS METRICS

### Before Week 1
- **Score**: 8.2/10
- **Critical Issues**: 6
- **Connection Leaks**: 23
- **Max Concurrent Users**: 50

### After Week 1
- **Score**: 8.8/10
- **Critical Issues**: 0
- **Connection Leaks**: 0
- **Max Concurrent Users**: 100+

### Improvement
- **Score**: +0.6 ⬆️
- **Issues Fixed**: 6 ✅
- **Stability**: 2x ⬆️
- **Capacity**: 2x ⬆️

---

## 🚨 ROLLBACK PLAN

### If Something Breaks

**Step 1: Stop application**
```bash
docker-compose down
```

**Step 2: Restore backup**
```bash
# Restore database
cp channels.db.backup.$(date +%Y%m%d) channels.db

# Restore code
git checkout main
git reset --hard HEAD~1
```

**Step 3: Restart**
```bash
docker-compose up -d
```

**Step 4: Verify**
```bash
# Check logs
docker logs -f macreplayxc

# Test stream
curl http://localhost:5004/play/portal1/channel1
```

---

## 📞 SUPPORT

### Common Issues

**"database is locked"**:
- Check locks are in place
- Verify finally blocks added
- Check concurrent access

**"Token expired"**:
- Check token cache: `/debug/tokens`
- Verify refresh logic
- Clear cache: `stb.clear_token_cache()`

**"No space left on device"**:
- Check HLS cleanup is working
- Manual cleanup: `rm -rf /dev/shm/hls_*`
- Verify _stop_stream() calls cleanup

---

**Total Time**: 1 week (5 days)  
**Total Impact**: 6 critical bugs fixed  
**Score Improvement**: 8.2/10 → 8.8/10  
**Status**: Ready for production deployment

