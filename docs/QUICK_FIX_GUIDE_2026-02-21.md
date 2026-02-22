# ⚡ QUICK FIX GUIDE - MacReplayXC v4.1.0
## Critical Bugs & Fast Fixes
**Date**: 2026-02-21  
**Target**: Developers  
**Goal**: Fix critical issues in 1 day

---

## 🚀 QUICK WINS (2 Hours Total)

### Fix #1: Bonus Calculation Bug (5 min)

**File**: `app-docker.py`  
**Lines**: 141-192  
**Impact**: HIGH - Scoring inaccurate

**Before**:
```python
if failure_rate < 0.05:
    bonus = (0.05 - failure_rate) * 100
    success_rate = base_success_rate + bonus  # Can exceed 45!
```

**After**:
```python
if failure_rate < 0.05:
    bonus = min(5, (0.05 - failure_rate) * 100)  # Cap at 5
    success_rate = min(45, base_success_rate + bonus)  # Cap at 45
```

**Test**:
```bash
pytest tests/test_mac_scoring.py::test_bonus_calculation
```

---

### Fix #2: HLS Segment Cleanup (10 min)

**File**: `app-docker.py`  
**Lines**: 1013-1055  
**Impact**: MEDIUM - RAM disk fills up

**Add to `_stop_stream()` method**:
```python
# After killing FFmpeg process, add:
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

---

### Fix #3: Watchdog Timeout Validation (15 min)

**File**: `app-docker.py`  
**Lines**: ~9750  
**Impact**: MEDIUM - MAC selection suboptimal

**Before**:
```python
watchdog_timeout = profile.get('watchdog_timeout', 999999)
if watchdog_timeout < 60:
    # MAC is busy
```

**After**:
```python
if 'watchdog_timeout' not in profile:
    logger.warning(f"MAC {mac} - watchdog_timeout missing, skipping")
    continue

watchdog_timeout = profile['watchdog_timeout']
if watchdog_timeout < 60:
    logger.warning(f"MAC {mac} is busy (watchdog: {watchdog_timeout}s)")
    continue
```

**Test**:
```bash
# Test with portal that doesn't return watchdog_timeout
pytest tests/test_mac_selection.py::test_missing_watchdog
```

---

### Fix #4: Timing Attack (1 hour)

**File**: `app-docker.py`  
**Lines**: 378-428  
**Impact**: MEDIUM - Security vulnerability

**Before**:
```python
if username != system_username or password != system_password:
    # String comparison not constant-time
```

**After**:
```python
import secrets

if not (secrets.compare_digest(username, system_username) and 
        secrets.compare_digest(password, system_password)):
    # Constant-time comparison
```

**Test**:
```bash
pytest tests/test_authentication.py::test_timing_attack
```

---

## 🔥 CRITICAL FIXES (1 Day Total)

### Fix #5: Race Conditions (1 day)

**Files**: `app-docker.py`  
**Lines**: 42, 617+, 9323+, 1313+  
**Impact**: HIGH - Data corruption

**Step 1: Add locks at module level**:
```python
# After imports, add:
import threading

occupied_lock = threading.Lock()
config_lock = threading.RLock()
mac_score_update_lock = threading.Lock()
```

**Step 2: Wrap occupied dictionary access**:
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

**Step 3: Wrap config dictionary access**:
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

**Step 4: Wrap MAC score updates**:
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

**Test**:
```bash
pytest tests/test_concurrent_access.py
```

---

### Fix #6: Token Refresh (1 day)

**File**: `stb.py`  
**Lines**: 219+  
**Impact**: HIGH - Streams break after 1h

**Step 1: Add token cache at module level**:
```python
# After imports in stb.py:
import threading
import time

_token_cache = {}  # {(url, mac): (token, timestamp)}
_token_cache_lock = threading.Lock()
```

**Step 2: Add token refresh function**:
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

**Step 3: Replace all getToken() calls**:
```bash
# In app-docker.py, find all:
token = stb.getToken(url, mac, proxy)

# Replace with:
token = stb.get_or_refresh_token(url, mac, proxy)
```

**Test**:
```bash
# Test long stream (>1 hour)
pytest tests/test_token_refresh.py::test_long_stream
```

---

## 📋 TESTING CHECKLIST

### After Quick Wins (2 hours)
- [ ] Run unit tests: `pytest tests/`
- [ ] Check logs for errors: `tail -f logs/app.log`
- [ ] Test stream playback: Open VLC, play channel
- [ ] Check /dev/shm: `ls -la /dev/shm/` (should be clean)
- [ ] Monitor memory: `docker stats macreplayxc`

### After Critical Fixes (1 day)
- [ ] Run concurrent test: `pytest tests/test_concurrent_access.py`
- [ ] Test long stream: Play channel for 2+ hours
- [ ] Check MAC scores: Visit `/portal_mac_scores/<portal_id>`
- [ ] Monitor database: `sqlite3 channels.db "SELECT COUNT(*) FROM channels"`
- [ ] Load test: 10 concurrent streams for 30 minutes

---

## 🐛 DEBUGGING TIPS

### Connection Leaks
```bash
# Check open connections
lsof -p $(pgrep -f app-docker.py) | grep channels.db

# Should be 0-2 connections, not 20+
```

### Race Conditions
```bash
# Enable debug logging
export FLASK_DEBUG=1

# Watch for "database is locked" errors
tail -f logs/app.log | grep "locked"
```

### Token Expiry
```bash
# Check token cache
# Add to app-docker.py:
@app.route('/debug/tokens')
def debug_tokens():
    import stb
    return jsonify({
        'cached_tokens': len(stb._token_cache),
        'tokens': [
            {
                'url': url,
                'mac': mac,
                'age': time.time() - ts
            }
            for (url, mac), (token, ts) in stb._token_cache.items()
        ]
    })
```

### HLS Segments
```bash
# Check segment count
watch -n 1 'ls -la /dev/shm/hls_* 2>/dev/null | wc -l'

# Should be 0 when no streams active
```

---

## 🚨 ROLLBACK PLAN

### If Something Breaks

**Step 1: Stop application**:
```bash
docker-compose down
```

**Step 2: Restore backup**:
```bash
# Restore database
cp channels.db.backup.$(date +%Y%m%d) channels.db

# Restore code
git checkout main
git reset --hard HEAD~1
```

**Step 3: Restart**:
```bash
docker-compose up -d
```

**Step 4: Verify**:
```bash
# Check logs
docker logs -f macreplayxc

# Test stream
curl http://localhost:5004/play/portal1/channel1
```

---

## 📞 SUPPORT

### If You Get Stuck

1. **Check logs**: `docker logs -f macreplayxc`
2. **Check database**: `sqlite3 channels.db ".schema"`
3. **Check processes**: `ps aux | grep ffmpeg`
4. **Check memory**: `free -h`
5. **Check disk**: `df -h /dev/shm`

### Common Errors

**"database is locked"**:
- Race condition not fixed
- Check locks are in place
- Reduce timeout: `conn.execute('PRAGMA busy_timeout = 30000')`

**"Token expired"**:
- Token refresh not working
- Check token cache: `/debug/tokens`
- Clear cache: `stb.clear_token_cache()`

**"No space left on device"**:
- HLS segments not cleaned up
- Manual cleanup: `rm -rf /dev/shm/hls_*`
- Check fix #2 is applied

---

## ✅ COMPLETION CHECKLIST

### Quick Wins (2 hours)
- [ ] Fix #1: Bonus calculation (5 min)
- [ ] Fix #2: HLS cleanup (10 min)
- [ ] Fix #3: Watchdog validation (15 min)
- [ ] Fix #4: Timing attack (1 hour)
- [ ] Run tests
- [ ] Commit changes
- [ ] Deploy to staging

### Critical Fixes (1 day)
- [ ] Fix #5: Race conditions (4 hours)
- [ ] Fix #6: Token refresh (4 hours)
- [ ] Run concurrent tests
- [ ] Load test (10 streams, 30 min)
- [ ] Monitor for 24 hours
- [ ] Deploy to production

---

**Total Time**: 1 day (8 hours)  
**Impact**: Fixes 6 critical bugs  
**Score Improvement**: 7.8/10 → 8.5/10

*For detailed analysis, see: MULTI_AGENT_CODE_REVIEW_2026-02-21.md*

