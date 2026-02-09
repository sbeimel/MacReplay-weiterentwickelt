# Cache Settings Removed

## Summary

The obsolete "Channel Cache" settings have been removed from `templates/settings.html`.

## Reason

As of **v3.1.0**, the channel cache system was completely replaced with direct `channels.db` access:

```python
# From app-docker.py:
# Channel Cache REMOVED in v3.1.0
# Channel cache system has been replaced with direct channels.db access
# All streaming now reads stream_cmd and available_macs directly from channels.db
```

## What Was Removed

### Cache Settings Section (templates/settings.html)

**Removed:**
- Cache Mode selector (lazy-ram, ram, disk, hybrid)
- Cache Duration selector (unlimited, 1h, 2h, 24h)
- Cache Information card with documentation

**Why:** These settings are no longer used. All channel data is now stored directly in `channels.db` with no intermediate caching layer.

## Current Architecture

### MacReplay Channel Storage
- **Database**: `channels.db` (SQLite)
- **Tables**: 
  - `channels` - Channel metadata
  - `stream_cmd` - Stream commands (populated on-demand)
  - `available_macs` - Available MACs per channel
- **Performance**: 30x faster than old cache system
- **Persistence**: All data persists across restarts

### Scanner Storage
- **Database**: `scans.db` (SQLite)
- **Tables**:
  - `found_macs` - Found MAC addresses
  - `genres` - Channel genres per MAC
- **No caching needed**: Direct database access

## Benefits of Removal

1. **Simplified UI**: No confusing cache settings
2. **Less confusion**: Users don't need to understand cache modes
3. **Better performance**: Direct DB access is faster than cache
4. **Persistent data**: Everything survives restarts
5. **Lower memory**: No RAM cache needed

## What Still Exists

### Dashboard Cache Actions
- **Rebuild Cache** button → Now rebuilds `channels.db` data
- **Cache Statistics** → Shows `channels.db` statistics
- **Clear Cache** → Clears `stream_cmd` and `available_macs` from DB

These actions still exist but now work directly with `channels.db` instead of a separate cache.

## Migration Notes

- Old cache settings in `settings.json` are ignored
- No migration needed - system automatically uses `channels.db`
- Old `channel_cache.db` file (if exists) is no longer used

## Files Modified

- `templates/settings.html` - Removed cache settings section

## Related Documentation

- See `app-docker.py` lines 485-489 for cache removal notes
- See `app-docker.py` line 10167 for `cache_clear()` function (now clears DB)
