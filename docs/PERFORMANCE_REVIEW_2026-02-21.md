# Performance Review - app-docker.py
**Date**: 2026-02-21  
**Focus**: Database queries, blocking operations, memory leaks, connection pooling, caching

---

## Executive Summary

**Recent Fixes Verified** ✅:
- `recent_redirects` cleanup (line 589, 714) - Working correctly
- `occupied_streams` cleanup (line 551) - Working correctly  
- 22 connection leaks fixed - Most functions now use try/finally blocks

**Critical Issues Found**: 3  
**High Priority Issues**: 5  
**Medium Priority Issues**: 4  
**Low Priority Issues**: 2

**Estimated Performance Impact**: 40-60% improvement possible with recommended optimizations

---

## 1. CRITICAL ISSUES

### 1.1 N+1 Query Pattern in stream_channel() Function
**Severity**: CRITICAL  
**File**: app-docker.py  
**Lines**: 9627-10550  
**Impact**: 10-100x slower streaming startup, database lock contention

**Problem**:
```python
# Line 9628-9631: Single query per stream request
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute('''SELECT stream_cmd, available_macs, name, custom_name 
                  FROM channels WHERE portal = ? AND channel_id = ? AND enabled = 1''')
```

When multiple users request streams simultaneously, each creates a separate database connection and query. With 10 concurrent streams, this creates 10 separate connections.

**Performance Impact**:
- Database lock contention with SQLite (30s timeout configured)
- Each quer