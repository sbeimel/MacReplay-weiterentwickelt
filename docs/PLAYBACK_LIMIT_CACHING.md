# Playback Limit Caching & MAC Scoring System

## Overview
Implemented comprehensive MAC scoring system (0-100 points) that learns from stream success/failure patterns and prioritizes reliable MACs with high connection capacity.

## Database Format

### Format
```
available_macs: "MAC_A:limit:success:fail:last_ts,MAC_B:limit:success:fail:last_ts"
```

Each MAC stores:
- `limit`: playback_limit from portal (max connections)
- `success`: Number of successful streams
- `fail`: Number of failed streams  
- `last_ts`: Unix timestamp of last successful stream

## MAC Scoring Algorithm (0-100 Points)

### 1. Success Rate (0-50 points)
```python
total = success + fail
if total > 0:
    success_rate = (success / total) * 50
else:
    success_rate = 25  # Neutral for untested
```

### 2. Recency (0-30 points)
```python
if last_success > 0:
    age_hours = (current_time - last_success) / 3600
    if age_hours < 1:      recency = 30  # Very recent
    elif age_hours < 24:   recency = 20  # Recent
    elif age_hours < 168:  recency = 10  # This week
    else:                  recency = 5   # Older
else:
    recency = 0  # Never successful
```

### 3. Reliability Bonus (0-20 points)
```python
if success >= 10:  reliability = 20  # Proven reliable
elif success >= 5: reliability = 10  # Somewhat reliable
else:              reliability = 0   # Unproven
```

### Total Score
```
score = success_rate + recency + reliability
```

## Sorting Logic

### Single Priority: Score (reliability beats capacity!)
MACs are sorted ONLY by score (0-100), not by playback_limit.

**Why?** 
- Reliable MAC with limit:2 is better than unreliable MAC with limit:5
- System learns automatically which MACs work
- Failed MACs sink quickly, even with high capacity
- playback_limit is already reflected in score (more capacity = more success opportunities)

### Example:
```
Start (all neutral, score=25):
MAC_A: limit=5, score=25
MAC_B: limit=5, score=25
MAC_C: limit=2, score=25

After testing:
MAC_A: 10 success, 0 fail → score=95
MAC_B: 2 success, 8 fail → score=15 (crashes!)
MAC_C: 8 success, 0 fail → score=85

Sorted by score only:
1. MAC_A (score:95, limit:5) ← Best overall
2. MAC_C (score:85, limit:2) ← Reliability beats capacity!
3. MAC_B (score:15, limit:5) ← Unreliable, even with high limit
```

## Score Updates

### Automatic Learning - ALWAYS Active

The system updates scores automatically in multiple scenarios:

#### 1. With Stream Testing ("try all macs" + "test streams")
- **Success**: ffprobe test passes → success +1, last_ts updated
- **Failure**: ffprobe test fails → fail +1
- **No Link**: getLink() returns None → fail +2 (harder penalty)

#### 2. Without Stream Testing (Direct Streaming)
- **Success**: Stream runs ≥5 seconds → success +1, last_ts updated
- **Failure**: Stream dies <5 seconds → fail +1
- Updates happen when stream ends (unoccupy)

#### 3. HLS Auto Retry ("hls auto retry")
- **Success**: Playlist created → success +1, last_ts updated
- **Failure**: No playlist after timeout → fail +1
- **No Link**: getLink() returns None → fail +2

### Result:
- ✅ System learns even without stream testing
- ✅ Scores reflect real-world reliability
- ✅ Works for all streaming modes

## Implementation Details

### 1. Cache Refresh Operations
All cache refresh operations initialize scores to 0:

- **Portal Add** (line ~2900): `"MAC:limit:0:0:0"`
- **Portal Edit** (line ~3180): `"MAC:limit:0:0:0"`
- **Genre Selection** (line ~3620): `"MAC:limit:0:0:0"`
- **Refresh Cache** (line ~1230): `"MAC:limit:0:0:0"`

### 2. Score Updates During Streaming

#### Direct Streaming (FFmpeg)
- **Success** (line ~9010): Increments `success`, updates `last_ts`
- **Failure** (line ~9030): Increments `fail`
- **Fallback Success** (line ~9100): Increments `success`, updates `last_ts`

#### HLS Streaming
- **Success** (line ~9650): Increments `success`, updates `last_ts`
- **Failure** (line ~9680): Increments `fail`
- **Fallback Success** (line ~9780): Increments `success`, updates `last_ts`

### 3. Score Display in WebUI

#### Portal Management Page
- New "Score" column in MAC table
- Color-coded badges:
  - Green (≥75): Excellent reliability
  - Blue (≥50): Good reliability
  - Yellow (≥25): Moderate/Untested
  - Red (<25): Poor reliability
- Tooltip shows success/fail counts
- Loads asynchronously via `/portal/mac-scores` API

#### Settings Page
- Comprehensive documentation of scoring system
- Explains how scores are calculated
- Shows how sorting works

## Benefits

### 1. Intelligent Learning
- System learns which MACs are reliable over time
- Automatically adapts to portal changes
- No manual configuration needed

### 2. Faster Stream Starts
- Reliable MACs are tried first
- Reduces failed connection attempts
- Minimizes user wait time

### 3. Optimal Resource Usage
- High-capacity MACs prioritized
- Proven MACs preferred over untested
- Failed MACs deprioritized automatically

### 4. Transparency
- Users can see MAC scores in portal management
- Clear indication of which MACs work well
- Helps identify problematic MACs

## Logging

Enhanced logging shows scores and stats:

```
[MAC RETRY] Channel 123 found in DB with 3 MAC(s) (sorted by limit+score):
  MAC_A: limit=5, score=95.0, success=50, fail=2
  MAC_B: limit=5, score=55.0, success=5, fail=5
  MAC_C: limit=2, score=85.0, success=20, fail=1

[MAC RETRY] ✓ MAC MAC_A works!
[MAC RETRY] Updated DB: MAC MAC_A success count: 51
```

## Cache Management

### Clear Cache Button
- Clears `stream_cmd` and `available_macs` from DB
- Resets all scores to 0
- Does NOT affect portal configuration
- Scores rebuild automatically as streams are tested

### Refresh Cache Button
- Reloads channels from portal
- Preserves existing scores (only updates if MAC list changes)
- Updates playback_limit from fresh `getProfile()` calls

## Compatibility

### Backward Compatibility
Handles multiple formats:
- Old: `"MAC_A,MAC_B"` → Defaults to limit:1, score:25
- Medium: `"MAC_A:5,MAC_B:2"` → Uses limits, score:25
- New: `"MAC_A:5:10:2:1708456789"` → Full scoring data

### Migration
No manual migration needed. Scores build up automatically as:
1. Streams are tested
2. Cache is refreshed
3. Portal configuration is updated

## Settings Integration

Works with existing settings:
- **skip_busy_macs**: Enables score-based sorting
- **hls_skip_busy**: Same for HLS streaming
- **try_all_macs + test_streams**: Updates scores during MAC retry
- **hls_auto_retry**: Updates scores during HLS retry

## Performance Impact

- **Minimal overhead**: 3 additional integers per MAC in DB
- **Faster MAC selection**: Pre-sorted by capacity + score
- **Better success rate**: Reliable MACs tried first
- **Reduced API calls**: Fewer failed attempts = fewer retries

## Version
Implemented in version 4.0.0 (2026-02-20)
