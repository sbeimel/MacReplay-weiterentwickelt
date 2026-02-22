# Code Analysis - Bugs Found (2026-02-21)

## Summary
Comprehensive code analysis performed on `app-docker.py`, `utils.py`, and `vavoo/vavoo2.py` to identify logic errors, bugs, and potential issues.

---

## CRITICAL BUGS FOUND

### 🔴 BUG #1: Unclosed Database Connection in unoccupy() Exception Handler
**Location**: `app-docker.py` lines ~9225-9226  
**Severity**: HIGH  
**Type**: Resource Leak

**Problem**:
```python
conn = get_db_connection()
cursor = conn.cursor()
# ... database operations ...
conn.close()
except Exception as e:
    logger.error(f"[SCORE UPDATE] Error updating score: {e}")
    # ❌ BUG: Connection NOT closed in exception handler!
```

**Impact**:
- Database connection leak when exception occurs during score update
- Can lead to "database is locked" errors under high load
- Connection pool exhaustion over time

**Fix Required**:
```python
conn = None
try:
    conn = get_db_connection()
    cursor = conn.cursor()
    # ... database operations ...
    conn.commit()
    conn.close()
except Exception as e:
    logger.error(f"[SCORE UPDATE] Error updating score: {e}")
finally:
    if conn:
        try:
            conn.close()
        except:
            pass
```

---

### 🔴 BUG #2: Unclosed Database Connection in update_mac_stats_on_redirect() Exception Handler
**Location**: `app-docker.py` lines ~9373-9374  
**Severity**: HIGH  
**Type**: Resource Leak

**Problem**:
```python
conn = get_db_connection()
cursor = conn.cursor()
# ... database operations ...
conn.commit()
conn.close()

except Exception as e:
    logger.error(f"Error updating MAC stats on redirect: {e}")
    # ❌ BUG: Connection NOT closed in exception handler!
```

**Impact**:
- Same as Bug #1
- Affects redirect mode specifically
- Can cause connection leaks during MAC learning

**Fix Required**:
Same pattern as Bug #1 - use try-finally block

---

### 🟡 BUG #3: Potential Race Condition in Proxy Mode DB Updates
**Location**: `app-docker.py` lines ~9580-9700 (multiple locations in proxy mode)  
**Severity**: MEDIUM  
**Type**: Race Condition

**Problem**:
Multiple places in proxy mode open DB connection, read available_macs, modify, and write back:
```python
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute('SELECT available_macs FROM channels WHERE portal = ? AND channel_id = ?', ...)
row = cursor.fetchone()
# Parse and modify macs
cursor.execute('UPDATE channels SET available_macs = ? WHERE portal = ? AND channel_id = ?', ...)
conn.commit()
conn.close()
```

**Impact**:
- If two streams for same channel update simultaneously, one update can be lost
- Score updates might not be accurate under concurrent load
- SQLite timeout=30s helps but doesn't eliminate race condition

**Mitigation** (already in place):
- SQLite connection timeout of 30 seconds
- WAL mode (if enabled) helps with concurrent reads
- Issue is rare in practice due to short update windows

**Potential Fix** (optional):
- Use database-level atomic operations (UPDATE ... SET success = success + 1)
- Or implement application-level locking for MAC score updates

---

## POTENTIAL ISSUES (Not Bugs, But Worth Noting)

### ⚠️ ISSUE #1: startTime Variable Scope Check
**Location**: `app-docker.py` line ~9142  
**Severity**: LOW  
**Type**: Logic Issue

**Code**:
```python
if 'startTime' not in locals() and 'startTime' not in globals():
    logger.debug("[SCORE UPDATE] No startTime available, skipping score update")
    return
```

**Analysis**:
- This check will ALWAYS fail because `startTime` is defined in outer scope (line ~9229)
- The check is defensive but unnecessary
- Not a bug because startTime is always defined before unoccupy() is called

**Recommendation**: Remove this check or document why it exists

---

### ⚠️ ISSUE #2: Multiple DB Connection Opens in Proxy Mode
**Location**: `app-docker.py` lines ~9580-9780  
**Severity**: LOW  
**Type**: Performance

**Problem**:
Proxy mode opens/closes DB connection multiple times during streaming:
- On HTML detection (line ~9581)
- On low bitrate detection (line ~9613)
- On stream success (line ~9643)
- On stream failure (line ~9669)
- On HTTP error (line ~9712)
- On timeout (line ~9743)
- On connection error (line ~9773)

**Impact**:
- Multiple DB open/close operations per stream
- Slight performance overhead
- Not a bug, but could be optimized

**Potential Optimization**:
- Batch updates or use a single connection for the entire stream
- Trade-off: More complex code vs. minimal performance gain

---

### ⚠️ ISSUE #3: No Connection Pooling
**Location**: `app-docker.py` line ~1221  
**Severity**: LOW  
**Type**: Performance

**Current Implementation**:
```python
def get_db_connection():
    conn = sqlite3.connect(dbPath, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn
```

**Analysis**:
- Each call creates a new SQLite connection
- SQLite is lightweight, so this is acceptable
- Connection pooling would add complexity for minimal gain

**Recommendation**: Keep as-is for SQLite, but document this design decision

---

## CODE QUALITY OBSERVATIONS

### ✅ GOOD: Global Scoring Functions
- `calculate_mac_score()` and `parse_and_sort_macs()` are properly unified
- All modes use same scoring logic
- Bug fix from previous session (sorting) is correctly implemented

### ✅ GOOD: Independent Streaming Modes
- Proxy Mode: Early exit, independent (line ~9435)
- Direct Redirect Mode: Early exit, independent (line ~9680)
- FFmpeg Mode: Independent flow (line ~9850)
- HLS Mode: Independent (line ~10600)
- No variable inheritance or fall-through

### ✅ GOOD: FFmpeg Exit Code Detection
- Properly implemented in unoccupy() function
- Accurate distinction between user stop (exit 0) and portal failure (exit ≠0)

### ✅ GOOD: Proxy Mode Optimizations
- Connect timeout detection: ✓
- Read timeout detection: ✓
- Connection error detection: ✓
- HTML detection: ✓
- Bitrate monitoring: ✓

### ✅ GOOD: Redirect Mode Learning
- Two-tier fail detection (<5s = fail+2, <10s = fail+1)
- Success detection (>30s = success)
- Proper MAC exclusion on retry

---

## RECOMMENDATIONS

### Priority 1 (HIGH): Fix Connection Leaks
1. Fix Bug #1: Add finally block to unoccupy() function
2. Fix Bug #2: Add finally block to update_mac_stats_on_redirect() function
3. Search for similar patterns in other functions

### Priority 2 (MEDIUM): Code Review
1. Review all exception handlers that use get_db_connection()
2. Ensure all have proper cleanup (finally blocks or context managers)
3. Consider creating a context manager for DB connections:
   ```python
   @contextmanager
   def db_connection():
       conn = get_db_connection()
       try:
           yield conn
       finally:
           conn.close()
   ```

### Priority 3 (LOW): Performance Optimization
1. Consider batching DB updates in proxy mode
2. Document why connection pooling is not used
3. Remove unnecessary startTime check in unoccupy()

---

## FILES ANALYZED
- ✅ `app-docker.py` (11,700+ lines) - Main application
- ✅ `utils.py` (460+ lines) - Utility functions
- ✅ `vavoo/vavoo2.py` (2,600+ lines) - Vavoo integration

## ANALYSIS METHODS
- Code signature extraction
- Pattern matching for common bugs
- Database connection tracking
- Exception handler analysis
- Race condition detection

---

## CONCLUSION

**Critical Issues**: 2 (connection leaks in exception handlers)  
**Potential Issues**: 3 (race condition, performance, code quality)  
**Overall Code Quality**: GOOD

The codebase is well-structured with proper separation of concerns. The main issues are related to exception handling in database operations. These should be fixed to prevent resource leaks under error conditions.

All previous bug fixes (MAC sorting, unified scoring, independent modes) are correctly implemented.
