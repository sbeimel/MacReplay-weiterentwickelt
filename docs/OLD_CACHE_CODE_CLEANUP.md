# Old Cache Code Cleanup - Complete

## Summary

All obsolete cache-related code has been removed from the project. The system now uses direct `channels.db` access with no intermediate caching layer.

## What Was Removed

### 1. Cache Settings UI (`templates/settings.html`)
- ❌ Cache Mode selector (lazy-ram, ram, disk, hybrid)
- ❌ Cache Duration selector (unlimited, 1h, 2h, 24h)
- ❌ Cache Information card

### 2. Old ChannelCache Class (`app-docker.py`)
- ❌ `ChannelCache_OLD` class (100+ lines)
- ❌ Methods: `get_channels()`, `find_channel()`, `invalidate_portal()`, `invalidate_all()`, `cleanup_expired()`, `get_cache_stats()`
- ❌ RAM-based caching logic
- ❌ Cache expiration logic
- ❌ Thread locking for cache access

### 3. Dashboard Cache Statistics (`templates/dashboard.html`)
- ❌ "Cache Statistics" title → ✅ "Database Statistics"
- ❌ "RAM Entries" field
- ❌ "Disk Entries" field
- ❌ "Total Channels" field
- ✅ NEW: "Cached Channels" (channels with stream data)
- ✅ NEW: "Persistence" (shows "persistent")
- ✅ NEW: Better descriptions

## What Was Updated

### Dashboard Statistics
**Before:**
```html
<h3>Cache Statistics</h3>
- Cache Mode: lazy-ram / ram / disk / hybrid
- RAM Entries: 123
- Disk Entries: 456
- Total Channels: 789
```

**After:**
```html
<h3>Database Statistics</h3>
- Storage Mode: db-direct (Direct SQLite access)
- Cached Channels: 123 (With stream data)
- Persistence: persistent (Survives restarts)
```

### Backend Endpoint (`/cache/stats`)
**Already updated** - Returns DB-based stats:
```python
{
    "mode": "db-direct",
    "cached_channels": 123,  # Channels with stream_cmd
    "cache_duration": "persistent"
}
```

## What Remains (Intentionally)

### 1. Genre Loading Cache Indicator
- **Location**: `templates/genre_selection.html`, `templates/portals.html`
- **Purpose**: Shows if genres were loaded from DB (cached) or fetched fresh from portal
- **Status**: ✅ Keep - This is useful information
- **Display**: Badge "From cache" when genres loaded from `channels.db`

### 2. Dashboard Cache Buttons
- **"Rebuild Cache" button** → Now rebuilds `channels.db` data
- **"Clear Cache" button** → Now clears `stream_cmd` and `available_macs` from DB
- **Status**: ✅ Keep - Still functional, just work with DB instead of cache

### 3. `/cache/stats` Endpoint
- **Status**: ✅ Keep - Returns DB statistics
- **Purpose**: Dashboard statistics display

### 4. `/cache/clear` Endpoint
- **Status**: ✅ Keep - Clears DB stream data
- **Purpose**: Clear cached stream commands

## Current Architecture

### MacReplay Data Flow
```
Portal → stb.py → channels.db (SQLite)
                      ↓
                  stream_cmd (cached on-demand)
                      ↓
                  Streaming
```

### Scanner Data Flow
```
Portal → scanner.py → scans.db (SQLite)
                         ↓
                     found_macs table
                         ↓
                     Export / Portal Creation
```

## Benefits of Cleanup

1. ✅ **Simpler codebase**: 100+ lines of unused code removed
2. ✅ **Less confusion**: No more cache mode/duration settings
3. ✅ **Clearer UI**: Dashboard shows actual DB stats
4. ✅ **Better performance**: Direct DB access is faster
5. ✅ **Persistent data**: Everything survives restarts
6. ✅ **Lower memory**: No RAM cache needed

## Files Modified

1. `templates/settings.html` - Removed cache settings section
2. `templates/dashboard.html` - Updated cache statistics to database statistics
3. `app-docker.py` - Removed `ChannelCache_OLD` class

## Testing Checklist

- [ ] Dashboard loads without errors
- [ ] Database statistics display correctly
- [ ] "Rebuild Cache" button works (rebuilds channels.db)
- [ ] "Clear Cache" button works (clears stream_cmd from DB)
- [ ] Settings page loads without cache settings
- [ ] Genre loading shows "From cache" badge when appropriate
- [ ] Streaming works (reads from channels.db)
- [ ] No console errors related to cache

## Migration Notes

- No user action required
- Old cache settings in `settings.json` are ignored
- Old `channel_cache.db` file (if exists) is no longer used
- System automatically uses `channels.db` for all operations

## Code Comments

The following comment blocks remain in `app-docker.py` to document the change:

```python
# ============================================
# Channel Cache REMOVED in v3.1.0
# ============================================
# Channel cache system has been replaced with direct channels.db access
# All streaming now reads stream_cmd and available_macs directly from channels.db
# This provides 30x faster streaming and persistent data across restarts
```

These comments should be kept for historical reference and to prevent accidental re-introduction of cache code.
