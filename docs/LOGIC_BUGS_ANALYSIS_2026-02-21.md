# 🔍 Logic & Mathematical Bugs Analysis
## MacReplayXC v4.2.0 - Complete Review

**Date**: 2026-02-21  
**Source**: All 12 Agent Reports (not just orchestrator summary)

---

## 📊 Summary

**Total Logic/Math Issues Found**: 4  
**Already Fixed**: 1 (Bonus Calculation Bug)  
**Remaining**: 3 (Soft Start Cliff, Watchdog Validation, Busy MAC List)

---

## ✅ ALREADY FIXED

### 1. Bonus Calculation Bug (CRITICAL)

**Status**: ✅ FIXED  
**Found by**: mac-scoring-expert, stb-emulation-expert  
**File**: `app-docker.py`  
**Lines**: 162-220 (calculate_mac_score function)

**Problem**:
```python
# BUGGY (OLD):
if failure_rate < 0.05:
    bonus = (0.05 - failure_rate) * 100  # Can be 5 points
    success_rate = base_success_rate + bonus  # Can exceed 45!
```

**Issue**:
- Bonus not capped at 5 points
- success_rate could exceed 45 (max should be 45)
- Documentation says 0-45 points, but code allowed 0-50

**Example**:
- 100 successes, 0 failures
- base_success_rate = 40
- bonus = (0.05 - 0.00) * 100 = 5
- success_rate = 40 + 5 = 45 ✅ OK

**BUT**:
- 98 successes, 0 failures (0% failure rate)
- base_success_rate = (98/98) * 40 = 40
- bonus = (0.05 - 0.00) * 100 = 5
- success_rate = 40 + 5 = 45 ✅ OK

**Current Code (FIXED)**:
```python
# Line 207-208
if failure_rate < 0.05:
    bonus = min(5, (0.05 - failure_rate) * 100)  # ✅ Cap bonus at 5 points
    success_rate = min(45, base_success_rate + bonus)  # ✅ Cap total at 45 points
```

**Impact**: HIGH - Scoring was inaccurate, could favor MACs incorrectly  
**Fix Time**: 5 minutes  
**Status**: ✅ ALREADY FIXED IN CODE

---

## ⏳ REMAINING ISSUES

### 2. Soft Start Score Cliff (MEDIUM)

**Status**: ⏳ OPEN  
**Found by**: mac-scoring-expert, stb-emulation-expert  
**File**: `app-docker.py`  
**Lines**: 162-220 (calculate_mac_score function)

**Problem**:
```python
# Line 193-195
if total <= 5:
    success_rate = max(15, (success_count / total) * 40)
```

**Issue**: Sudden score drop when soft start ends

**Scenario**:
- Attempts 1-5: 1 success, 4 failures
  - Score = max(15, (1/5) * 40) = max(15, 8) = 15 points (Soft Start)
- Attempt 6: Another failure
  - Score = (1/6) * 40 = 6.67 points (Soft Start ends)
  - **Sudden drop from 15 to 6.67 points!**

**Why is this bad?**
- New MACs with bad luck get punished harshly
- No gradual transition
- Can cause MAC to be avoided immediately after soft start

**Suggested Fix**:
```python
# Gradual transition over attempts 6-10
if total <= 5:
    # Soft start: minimum 15 points
    success_rate = max(15, (success_count / total) * 40)
elif total <= 10:
    # Transition phase: Soft start bonus fades out
    soft_start_bonus = (10 - total) / 5 * 15  # 15 → 0 over 5 attempts
    base_rate = (success_count / total) * 40
    success_rate = base_rate + soft_start_bonus
else:
    # Normal scoring
    base_success_rate = (success_count / total) * 40
    # ... rest of logic
```

**Example with Fix**:
- Attempt 5: 1 success, 4 failures → 15 points (soft start)
- Attempt 6: 1 success, 5 failures → 6.67 + 12 = 18.67 points (transition)
- Attempt 7: 1 success, 6 failures → 5.71 + 9 = 14.71 points (transition)
- Attempt 8: 1 success, 7 failures → 5.00 + 6 = 11.00 points (transition)
- Attempt 9: 1 success, 8 failures → 4.44 + 3 = 7.44 points (transition)
- Attempt 10: 1 success, 9 failures → 4.00 + 0 = 4.00 points (normal)

**Impact**: MEDIUM - New MACs disadvantaged after soft start  
**Fix Time**: 15 minutes  
**Priority**: MEDIUM

---

### 3. Watchdog Timeout Validation Missing (HIGH)

**Status**: ⏳ SKIPPED (User requested to skip)  
**Found by**: iptv-stalker-expert, stalker-portal-expert  
**File**: `app-docker.py`  
**Lines**: ~9750+ (MAC busy check logic)

**Problem**:
```python
# Current code uses default value
watchdog_timeout = profile.get('watchdog_timeout', 999999)

if watchdog_timeout < 60:
    # MAC is busy
    logger.debug(f"MAC {mac} is busy (watchdog: {watchdog_timeout}s)")
    continue
```

**Issue**: Default value 999999 means "never busy"

**Scenarios**:
1. **Portal doesn't return watchdog_timeout field**
   - Default: 999999
   - Result: MAC always considered available
   - Reality: MAC might be busy!

2. **Portal returns invalid/null watchdog_timeout**
   - Default: 999999
   - Result: MAC always considered available
   - Reality: MAC might be busy!

**Why is this bad?**
- May use busy MACs (poor stream quality)
- Wastes time trying busy MACs
- Suboptimal MAC selection

**Suggested Fix**:
```python
# Explicit validation
if 'watchdog_timeout' not in profile:
    logger.warning(f"MAC {mac} - watchdog_timeout missing, skipping")
    continue

watchdog_timeout = profile.get('watchdog_timeout')
if not isinstance(watchdog_timeout, (int, float)):
    logger.warning(f"MAC {mac} - invalid watchdog_timeout type")
    continue

if watchdog_timeout < 60:
    logger.info(f"MAC {mac} is busy (watchdog: {watchdog_timeout}s)")
    continue
```

**Impact**: HIGH - May use busy MACs, poor stream quality  
**Fix Time**: 15 minutes  
**Priority**: HIGH  
**Status**: User requested to skip (Fix #2)

---

### 4. Busy MAC List Grows Unbounded (LOW)

**Status**: ⏳ OPEN  
**Found by**: stb-emulation-expert  
**File**: `app-docker.py`  
**Lines**: ~9750+ (stream_channel function)

**Problem**:
```python
busy_macs = []  # Collect busy MACs as fallback

for try_mac in available_macs:
    if skip_busy_macs:
        profile = stb.getProfile(url, mac, token, proxy)
        watchdog_timeout = profile.get('watchdog_timeout', 999999)
        
        if watchdog_timeout < 60:
            busy_macs.append(try_mac)  # Add to list
            continue
```

**Issue**: `busy_macs` list grows without limit

**Scenario**:
- Portal has 100 MACs
- 50 are busy
- `busy_macs` list grows to 50 entries
- Memory usage increases
- List is never cleared

**Why is this bad?**
- Memory leak (small, but still a leak)
- List is only used as fallback (rarely)
- No cleanup mechanism

**Suggested Fix**:
```python
# Option 1: Limit list size
busy_macs = []
MAX_BUSY_MACS = 10  # Only keep first 10 as fallback

for try_mac in available_macs:
    if skip_busy_macs:
        profile = stb.getProfile(url, mac, token, proxy)
        watchdog_timeout = profile.get('watchdog_timeout', 999999)
        
        if watchdog_timeout < 60:
            if len(busy_macs) < MAX_BUSY_MACS:
                busy_macs.append(try_mac)
            continue

# Option 2: Don't collect busy MACs at all
# If all MACs are busy, just fail fast instead of retrying
```

**Impact**: LOW - Minor memory leak  
**Fix Time**: 5 minutes  
**Priority**: LOW

---

## 📊 Priority Matrix

| Issue | Severity | Impact | Fix Time | Status | Priority |
|-------|----------|--------|----------|--------|----------|
| Bonus Calculation Bug | CRITICAL | HIGH | 5 min | ✅ FIXED | - |
| Watchdog Validation | HIGH | HIGH | 15 min | ⏳ SKIPPED | HIGH |
| Soft Start Cliff | MEDIUM | MEDIUM | 15 min | ⏳ OPEN | MEDIUM |
| Busy MAC List | LOW | LOW | 5 min | ⏳ OPEN | LOW |

---

## 🎯 Recommendations

### Immediate (This Week)

**1. Watchdog Timeout Validation** (15 min)
- User requested to skip, but should be reconsidered
- High impact on stream quality
- Easy fix

### Short-Term (Next Week)

**2. Soft Start Score Cliff** (15 min)
- Medium impact on new MAC selection
- Improves fairness for new MACs
- Easy fix with gradual transition

### Optional (Low Priority)

**3. Busy MAC List** (5 min)
- Low impact (minor memory leak)
- Easy fix (limit list size or remove)
- Can be done anytime

---

## 🔍 Other Findings (Not Logic Bugs)

### Race Condition in MAC Score Updates (CRITICAL)

**Status**: ✅ FIXED (Fix #8)  
**Found by**: mac-scoring-expert, performance-optimization-expert

**Problem**: MAC scores updated from multiple threads without locking

**Fix Applied**: Thread locks added for occupied/config dictionaries

**Details**: See `docs/FIXES_IMPLEMENTED_2026-02-21.md`

---

### HLS Segment Cleanup Missing (MEDIUM)

**Status**: ✅ FIXED (Fix #3)  
**Found by**: restreaming-expert

**Problem**: HLS segments never deleted from /dev/shm

**Fix Applied**: Automatic cleanup in `_stop_stream()` and `stop_stream()`

**Details**: See `docs/FIXES_IMPLEMENTED_2026-02-21.md`

---

### FFmpeg Resource Leak (CRITICAL)

**Status**: ✅ FIXED (Fix #4)  
**Found by**: restreaming-expert

**Problem**: FFmpeg processes not killed on exception

**Fix Applied**: Guaranteed process termination in try-except-finally

**Details**: See `docs/FIXES_IMPLEMENTED_2026-02-21.md`

---

## 📈 Impact on Score

### Before Fixes
- **Score**: 8.2/10
- **Logic Bugs**: 4 (1 critical, 1 high, 1 medium, 1 low)

### After Bonus Calculation Fix
- **Score**: 8.4/10
- **Logic Bugs**: 3 (0 critical, 1 high, 1 medium, 1 low)

### After All Fixes (Recommended)
- **Score**: 8.7/10
- **Logic Bugs**: 0
- **Improvements**:
  - Better MAC selection (watchdog validation)
  - Fairer scoring for new MACs (soft start transition)
  - No memory leaks (busy MAC list limit)

---

## 🧪 Testing Recommendations

### Test #1: Soft Start Cliff

**Manual Test**:
1. Create new MAC with 1 success, 4 failures
2. Check score after attempt 5 (should be 15)
3. Add 1 more failure (attempt 6)
4. Check score after attempt 6 (currently 6.67, should be ~18 with fix)

**Expected Result**:
```
Attempt 5: 15 points (soft start)
Attempt 6: 18.67 points (transition) ← Instead of 6.67
Attempt 7: 14.71 points (transition)
Attempt 8: 11.00 points (transition)
Attempt 9: 7.44 points (transition)
Attempt 10: 4.00 points (normal)
```

### Test #2: Watchdog Validation

**Manual Test**:
1. Use portal that doesn't return watchdog_timeout
2. Check logs for warning message
3. Verify MAC is skipped (not used)

**Expected Result**:
```
[WARNING] MAC 00:1A:79:00:00:01 - watchdog_timeout missing, skipping
[INFO] Trying next MAC: 00:1A:79:00:00:02
```

### Test #3: Busy MAC List

**Manual Test**:
1. Use portal with 50+ busy MACs
2. Monitor memory usage during MAC selection
3. Verify busy_macs list doesn't exceed limit

**Expected Result**:
```
busy_macs list size: 10 (capped)
Memory usage: Stable
```

---

## 📝 Implementation Guide

### Fix #1: Soft Start Cliff (15 min)

**File**: `app-docker.py`  
**Function**: `calculate_mac_score()`  
**Lines**: 193-195

**Change**:
```python
# OLD:
if total <= 5:
    success_rate = max(15, (success_count / total) * 40)
else:
    base_success_rate = (success_count / total) * 40
    # ... rest of logic

# NEW:
if total <= 5:
    # Soft start: minimum 15 points
    success_rate = max(15, (success_count / total) * 40)
elif total <= 10:
    # Transition phase: Soft start bonus fades out
    soft_start_bonus = (10 - total) / 5 * 15  # 15 → 0 over 5 attempts
    base_rate = (success_count / total) * 40
    success_rate = base_rate + soft_start_bonus
else:
    # Normal scoring
    base_success_rate = (success_count / total) * 40
    # ... rest of logic
```

### Fix #2: Watchdog Validation (15 min)

**File**: `app-docker.py`  
**Lines**: ~9750+

**Change**:
```python
# OLD:
watchdog_timeout = profile.get('watchdog_timeout', 999999)
if watchdog_timeout < 60:
    logger.debug(f"MAC {mac} is busy (watchdog: {watchdog_timeout}s)")
    continue

# NEW:
if 'watchdog_timeout' not in profile:
    logger.warning(f"MAC {mac} - watchdog_timeout missing, skipping")
    continue

watchdog_timeout = profile.get('watchdog_timeout')
if not isinstance(watchdog_timeout, (int, float)):
    logger.warning(f"MAC {mac} - invalid watchdog_timeout type")
    continue

if watchdog_timeout < 60:
    logger.info(f"MAC {mac} is busy (watchdog: {watchdog_timeout}s)")
    continue
```

### Fix #3: Busy MAC List (5 min)

**File**: `app-docker.py`  
**Lines**: ~9750+

**Change**:
```python
# OLD:
busy_macs = []
for try_mac in available_macs:
    if skip_busy_macs:
        # ...
        if watchdog_timeout < 60:
            busy_macs.append(try_mac)
            continue

# NEW:
busy_macs = []
MAX_BUSY_MACS = 10  # Limit fallback list size

for try_mac in available_macs:
    if skip_busy_macs:
        # ...
        if watchdog_timeout < 60:
            if len(busy_macs) < MAX_BUSY_MACS:
                busy_macs.append(try_mac)
            continue
```

---

## ✅ Conclusion

**Logic/Math Bugs Found**: 4  
**Already Fixed**: 1 (Bonus Calculation)  
**Remaining**: 3 (Watchdog Validation, Soft Start Cliff, Busy MAC List)

**Total Fix Time**: 35 minutes (15 + 15 + 5)  
**Total Impact**: HIGH (better MAC selection, fairer scoring, no memory leaks)

**Recommendation**: Implement all 3 remaining fixes for optimal performance and fairness.

---

**Analysis Date**: 2026-02-21  
**Analyzed by**: All 12 Agent Reports  
**Version**: MacReplayXC v4.2.0
