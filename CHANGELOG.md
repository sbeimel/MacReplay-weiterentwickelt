# MacReplayXC v2.2 - Changelog

## 🚀 Major Improvements & New Features

### 1. **Enhanced Portal Compatibility**

#### Multiple Endpoint Support (`stb.py`)
- Added support for alternative portal endpoints:
  - Standard: `?type=stb&action=handshake`
  - Alternative 1: `/portal.php?type=stb&action=handshake`
  - Alternative 2: `/server/load.php?type=stb&action=handshake`
  - Stalker variants: `/stalker_portal/server/load.php`
  - Custom path support: `/c/portal.php`

#### GET + POST Request Support
- All API functions now try GET first, then fallback to POST
- Affected functions:
  - `getToken()`
  - `getAllChannels()`
  - `getEpg()`
  - `getGenres()`
  - `getLink()`

#### Enhanced Headers for Cloudflare Bypass
- MAG-Device-Fingerprint headers:
  ```
  User-Agent: Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3
  X-User-Agent: Model: MAG250; Link: WiFi
  Referer: [portal-url]
  ```

#### Cloudflare Protection Bypass
- Added `cloudscraper` library support
- Automatic Cloudflare challenge solving
- Browser TLS fingerprint emulation
- Added to `requirements.txt`: `cloudscraper==1.2.71`

#### M3U Playlist Support
- New function: `parseM3U()` - Parse M3U playlist content
- New function: `getM3UChannels()` - Fetch and parse M3U URLs
- Supports:
  - `tvg-id` (EPG ID)
  - `tvg-name` (Channel Name)
  - `tvg-logo` (Logo URL)
  - `group-title` (Genre/Category)

---

### 2. **Real-Time Progress Tracking**

#### EPG Refresh Progress (`/epg`)
**Backend Changes (`app-docker.py`):**
- Detailed progress tracking in `refresh_xmltv()`:
  - Loading EPG settings
  - Fetching fallback EPG
  - Per-portal progress
  - Per-MAC progress (Authenticating, Fetching channels, Fetching EPG)
  - Channel processing by genre
  - XMLTV generation
  - Final statistics

**Frontend Changes (`templates/epg.html`):**
- Enhanced progress bar with:
  - Portal name display
  - Percentage badge
  - Detailed step descriptions
  - Smooth progress bar animation
  - Success state (green) on completion
  - Auto-reload after completion

**Progress Updates Show:**
- "Starting Portal X..."
- "Authenticating MAC 1/3"
- "Fetching channels from MAC 1/3"
- "Fetching EPG from MAC 1/3"
- "Processing Sports (10/120 channels)"
- "Completed - 5000 total programmes"

#### Channel Refresh Progress (`/editor`)
**Backend Changes (`app-docker.py`):**
- New progress tracking system: `editor_refresh_progress`
- Wrapper function: `refresh_channels_cache_with_progress()`
- Detailed progress in `refresh_channels_cache()`:
  - Loading portals
  - Per-portal processing
  - Per-MAC fetching
  - Channel count updates
  - EPG availability checks
  - Database saving

**Frontend Changes (`templates/editor.html`):**
- Progress bar matching EPG design
- Real-time updates every second
- Shows current portal and step
- Percentage display
- Auto-reload on completion

**New Endpoint:**
- `GET /editor/refresh/progress` - Get refresh progress status

---

### 3. **Advanced Bulk Search & Replace System**

#### Enhanced UI Component (`templates/editor.html`)
**"Bulk Edit" Button** in Channel Editor with comprehensive modal:

**Improved Quick Presets (2x3 Grid Layout):**
- **Remove "VIP"** - Removes VIP, ★VIP★, [VIP], (VIP)
- **Remove Emojis** - Removes all emoji characters using regex
- **Remove Country Codes** - Advanced regex: `^(DE|UK|US|FR|IT|ES|NL|BE|AT|CH)[:|\\-_\\s]+`
  - Supports multiple separators: `:`, `|`, `-`, `_`, space
  - Handles brackets: `[DE]`, `(DE)`
  - Supports 2-letter and 3-letter codes
- **Remove [Brackets]** - Removes content in [] and () using regex
- **Clean Separators** - NEW: Removes multiple pipes, dashes, trailing separators
- **Fix Spacing** - NEW: Removes multiple spaces, cleans separator spacing

**Persistent Custom Rules:**
- ✅ **Auto-Save to Database** - Rules are automatically saved when applied
- ✅ **Auto-Load on Open** - Last 10 used rules loaded automatically
- ✅ **Survives Restarts** - Rules persist after CTRL+F5 and server restart
- ✅ **Smart Deduplication** - Same rules update `last_used` timestamp
- ✅ **Rule Management** - Clear saved rules button
- Visual rule builder (Search → Replace)
- Unlimited rules per session

**Enhanced Options:**
- ☑ Apply to Channel Names
- ☑ Apply to Genres  
- ☑ Case Sensitive
- ☑ Use Regular Expressions
- Settings are remembered between sessions

**Advanced Features:**
- Preview function with sample changes
- Rule history tracking
- Undo/Redo functionality
- Reset all customizations option

#### Backend Implementation (`app-docker.py`)

**New Database Tables:**
```sql
-- Rule persistence
CREATE TABLE bulk_edit_saved_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_text TEXT NOT NULL,
    replace_text TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_used TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Edit history for undo
CREATE TABLE bulk_edit_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    rules TEXT NOT NULL,
    apply_to_names INTEGER NOT NULL,
    apply_to_genres INTEGER NOT NULL,
    channels_backup TEXT NOT NULL
);
```

**New Endpoints:**
- `POST /editor/bulk-edit` - Apply bulk search & replace
- `GET /editor/bulk-edit/saved-rules` - Load persistent rules
- `POST /editor/bulk-edit/clear-saved-rules` - Clear saved rules
- `GET /editor/bulk-edit/history` - Get edit history
- `POST /editor/bulk-edit/undo` - Undo last edit
- `POST /editor/reset-all` - Reset all customizations

**Enhanced Features:**
- ✅ **Database Integration** - All changes stored in `channels` table
- ✅ **XC API Compatibility** - Changes immediately visible in XC players
- ✅ **M3U Playlist Sync** - Auto-refreshes M3U playlists
- ✅ **History System** - Complete backup before each edit
- ✅ **Undo Functionality** - Restore previous state
- ✅ **Rule Persistence** - Rules saved automatically
- Processes all channels in single transaction
- Supports regex and plain text
- Case-sensitive/insensitive matching
- Automatic whitespace cleanup

---

### 4. **XC API Database Integration**

#### Complete XC API Overhaul (`app-docker.py`)
**Problem:** XC API was reading from config files instead of database, so bulk edits weren't reflected in IPTV players.

**Solution:** Complete rewrite of XC API functions to use database:

**Updated Functions:**
- `xc_get_playlist()` - M3U playlist generation
- `xc_get_live_streams()` - Stream list for players
- `xc_get_live_categories()` - Category list

**Key Changes:**
```python
# OLD: Config-based (didn't reflect bulk edits)
custom_names = portal.get("custom channel names", {})
channel_name = custom_names.get(channel_id, channel.get("name"))

# NEW: Database-based (reflects all edits immediately)
cursor.execute('SELECT custom_name, name FROM channels WHERE...')
channel_name = db_channel['custom_name'] or db_channel['name']
```

**Benefits:**
- ✅ **Immediate Updates** - Bulk edits visible instantly in players
- ✅ **Consistent Data** - M3U and XC API use same source
- ✅ **Better Performance** - No portal queries needed
- ✅ **Offline Capability** - Works even when portals are down
- ✅ **Custom Values** - Respects all custom names, genres, numbers

#### Fixed Category Matching
**Problem:** Empty categories in UHF/IPTV players

**Root Cause:** Category IDs didn't match between streams and categories:
- Categories: `"portal_id_genre_name"`
- Streams: `"genre_name"`

**Solution:**
```python
# Consistent category_id format
category_id = f"{portal_id}_{genre}"
```

**Result:** All channels now appear in correct categories

---

### 5. **Enhanced Playlist Generation**

#### Database-Driven M3U Generation (`app-docker.py`)
**Complete rewrite of `generate_playlist()` function:**

**OLD System (Config-based):**
- Read from portal config files
- Required live portal connections
- Didn't reflect database changes
- Slow and unreliable

**NEW System (Database-driven):**
```python
# Direct database query
cursor.execute('''
    SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
           number, custom_number, custom_epg_id
    FROM channels 
    WHERE enabled = 1
''')

# Use custom values with fallbacks
channel_name = custom_name or name or "Unknown Channel"
genre = custom_genre or genre or "Unknown"
```

**Improvements:**
- ✅ **Instant Updates** - Bulk edits immediately in M3U
- ✅ **Robust Sorting** - Safe sorting with error handling
- ✅ **Quote Escaping** - Proper M3U attribute escaping
- ✅ **Null Handling** - Safe handling of empty values
- ✅ **Performance** - No external API calls needed

#### Fixed Sorting Crashes
**Problem:** Playlist generation crashed with 500 errors

**Root Causes:**
1. Missing `epg_id` column in database
2. Unsafe string splitting for sorting
3. Unescaped quotes in M3U attributes

**Solutions:**
```python
# Safe sorting with fallbacks
def get_channel_number(k):
    try:
        if 'tvg-chno="' in k:
            return int(k.split('tvg-chno="')[1].split('"')[0])
        return 999999  # Put channels without numbers at end
    except (ValueError, IndexError):
        return 999999

# Quote escaping
def escape_quotes(text):
    return str(text).replace('"', '&quot;') if text else ""
```

---

### 6. **UI/UX Improvements**

#### Fixed Portal Edit Modal Scrolling (`templates/portals.html`)
**Problem:** With many MAC addresses, "Save Changes" button was unreachable

**Solution:**
```css
#editPortalModal .modal-body {
    max-height: calc(100vh - 200px);
    overflow-y: auto;
}

#editPortalModal .modal-dialog {
    max-height: 90vh;
}
```

**Result:**
- ✅ Modal body scrolls independently
- ✅ Header & footer remain fixed
- ✅ "Save Changes" always accessible
- ✅ Responsive to screen size

---

### 5. **Better Error Handling & Logging**

#### Enhanced `getUrl()` Function (`stb.py`)
- Extended path search:
  - `/c/xpcom.common.js`
  - `/portal/c/xpcom.common.js`
  - `/server/c/xpcom.common.js`
  - Dynamic path detection from URL
- Detailed debug logging
- Tries with and without proxy
- Better error messages

#### Session Management
- Automatic session refresh every 5 minutes
- Prevents memory leaks
- Connection pooling with retry logic

---

## 📝 Configuration Changes

### Updated Files

#### `requirements.txt`
```diff
Flask==3.0.0
waitress==3.0.0
requests==2.31.0
+cloudscraper==1.2.71
pytest==7.4.0
pytest-mock==3.11.1
```

#### `Dockerfile`
- No changes needed (already installs from requirements.txt)

---

## 🔧 API Changes

### New Endpoints

1. **`GET /editor/refresh/progress`**
   - Returns channel refresh progress
   - Response:
     ```json
     {
       "running": true,
       "current_portal": "Portal Name",
       "current_step": "Fetching from MAC 1/3",
       "portals_done": 1,
       "portals_total": 3,
       "started_at": 1234567890
     }
     ```

2. **`GET /epg/refresh/progress`**
   - Returns EPG refresh progress
   - Same response format as above

3. **`POST /editor/bulk-edit`**
   - Apply bulk search & replace
   - Request:
     ```json
     {
       "rules": [
         {"search": "VIP", "replace": ""}
       ],
       "apply_to_names": true,
       "apply_to_genres": false,
       "case_sensitive": false,
       "use_regex": false
     }
     ```
   - Response:
     ```json
     {
       "success": true,
       "updated": 150
     }
     ```

4. **`GET /editor/bulk-edit/saved-rules`**
   - Load persistent bulk edit rules
   - Response:
     ```json
     {
       "success": true,
       "rules": [
         {
           "search": "VIP",
           "replace": "",
           "last_used": "2024-12-10 15:30:00"
         }
       ]
     }
     ```

5. **`POST /editor/bulk-edit/undo`**
   - Undo last bulk edit operation
   - Response:
     ```json
     {
       "success": true,
       "message": "Last bulk edit undone successfully"
     }
     ```

6. **`POST /editor/reset-all`**
   - Reset all custom names and genres to original values
   - Response:
     ```json
     {
       "success": true,
       "message": "All customizations reset successfully"
     }
     ```

---

## 🐛 Bug Fixes

1. **Portal Edit Modal Scrolling**
   - Fixed: Modal body now scrolls properly with many MAC addresses
   - "Save Changes" button always accessible
   - Enhanced CSS with flexbox layout

2. **Portal URL Detection**
   - Fixed: Now correctly detects portal.php at root level
   - Example: `http://dlta4k.com/portal.php` (not `/c/portal.php`)

3. **EPG Progress Bar**
   - Fixed: Progress bar now moves correctly
   - Shows actual progress percentage

4. **Channel Refresh Progress**
   - Fixed: Portal count now updates correctly
   - Shows "Processing X of Y" accurately

5. **XC API Empty Categories**
   - Fixed: Categories now show channels correctly
   - Problem: Category IDs didn't match between streams and categories
   - Solution: Consistent `portal_id_genre` format

6. **Playlist Generation Crashes**
   - Fixed: 500 Internal Server Error on playlist update
   - Problem: Missing `epg_id` column, unsafe sorting, unescaped quotes
   - Solution: Database schema fix, safe sorting, quote escaping

7. **Bulk Edit Not Reflecting in Players**
   - Fixed: Changes now immediately visible in XC API players
   - Problem: XC API read from config instead of database
   - Solution: Complete XC API rewrite to use database

8. **Country Code Removal**
   - Fixed: Now removes `DE|` and other separator variants
   - Enhanced regex patterns for better detection
   - Added "Clean Separators" preset for leftover symbols

---

## 🔒 Security Improvements

1. **Cloudflare Bypass**
   - Added cloudscraper for legitimate portal access
   - Better handling of protected portals

2. **Session Management**
   - Automatic session cleanup
   - Prevents memory leaks
   - Connection pooling

---

## 📊 Performance Improvements

1. **Progress Tracking**
   - Real-time updates without blocking
   - Threading for background operations
   - Efficient polling (1 second intervals)

2. **Bulk Edit System**
   - Processes all channels in single transaction
   - Efficient regex compilation
   - Automatic whitespace cleanup
   - Rule persistence with deduplication
   - Smart rule loading (only when needed)

3. **XC API Optimization**
   - No more live portal queries for XC API
   - Direct database access
   - Cached channel data
   - Faster response times

4. **Playlist Generation**
   - Database-driven instead of config-based
   - No external API dependencies
   - Efficient sorting algorithms
   - Reduced memory usage

5. **Session Management**
   - Connection pooling with retry logic
   - Automatic session refresh
   - Reduced overhead

---

## 🎯 Known Limitations

1. **Cloudflare Protection**
   - Some portals with aggressive Cloudflare protection may still not work
   - Requires residential IP (not datacenter/VPN)
   - Example: `dlta4k.com` works from residential IP but not from Docker

2. **M3U Support**
   - M3U parsing implemented but not yet integrated into UI
   - Requires portal type selection in UI

---

## 🚀 Migration Guide

### For Existing Users

1. **Update Dependencies:**
   ```bash
   docker-compose down
   docker-compose build --no-cache
   docker-compose up -d
   ```

2. **Or Install in Running Container:**
   ```bash
   docker exec -it macreplay pip install cloudscraper==1.2.71
   docker restart macreplay
   ```

3. **No Configuration Changes Required**
   - All improvements are backward compatible
   - Existing portals will work better automatically

### For New Users

1. **Standard Installation:**
   ```bash
   docker-compose up -d
   ```

2. **All features work out of the box**

---

## 📖 Usage Examples

### Enhanced Bulk Edit Examples

**Remove VIP from all channels:**
1. Open Channel Editor
2. Click "Bulk Edit"
3. Click "Remove VIP" preset
4. Click "Preview" to see changes
5. Click "Apply Changes"
6. Rules are automatically saved for next time

**Remove Country Codes (Enhanced):**
1. Click "Bulk Edit"
2. Click "Remove Country Codes" preset
3. Now removes: `DE:`, `DE|`, `DE-`, `DE_`, `[DE]`, `(DE)`
4. Apply - works with any separator

**Clean Leftover Separators:**
1. Click "Bulk Edit"
2. Click "Clean Separators" preset
3. Removes: `|||`, `---`, trailing `|`, leading `-`
4. Apply

**Fix Spacing Issues:**
1. Click "Bulk Edit"
2. Click "Fix Spacing" preset
3. Removes multiple spaces, cleans separator spacing
4. Apply

**Persistent Rules:**
1. Add custom rules
2. Apply changes
3. Close modal
4. Refresh page (CTRL+F5) or restart server
5. Open "Bulk Edit" - your rules are back!

**Undo Changes:**
1. Click "Bulk Edit"
2. Click "Undo Last" button
3. Restores previous state

**Reset Everything:**
1. Click "Bulk Edit"
2. Click "Reset All" button
3. All custom names/genres back to original

---

## 🙏 Credits

- **SFVIP Player** - Inspiration for portal compatibility improvements
- **cloudscraper** - Cloudflare bypass library
- **mitmproxy** - Understanding of proxy-based portal access

---

## 📅 Release Date

December 10, 2024 (v2.2)

---

## 🔮 Future Improvements

1. **M3U Portal Type**
   - Add portal type selection in UI
   - Full M3U playlist support

2. **Advanced Rule Management**
   - Rule templates/presets sharing
   - Import/export rule sets
   - Rule scheduling

3. **Health Check System**
   - Automatic portal health monitoring
   - Status indicators

4. **Channel Deduplication**
   - Automatic duplicate detection
   - Smart merging

5. **Enhanced Undo System**
   - Multiple undo levels
   - Selective undo by rule
   - Change diff viewer

6. **Backup & Restore**
   - Configuration backup
   - Database export/import
   - Automated backups

7. **Webhook Notifications**
   - Discord/Telegram notifications
   - Event-based alerts

---

## 🎉 What's New in v2.2

### Key Highlights:
- ✅ **Persistent Bulk Edit Rules** - Never lose your rules again!
- ✅ **XC API Database Integration** - Changes instantly visible in players
- ✅ **Enhanced Country Code Removal** - Handles all separator types
- ✅ **Undo/Redo System** - Safely experiment with changes
- ✅ **Fixed Empty Categories** - All channels show up correctly
- ✅ **Robust Playlist Generation** - No more 500 errors
- ✅ **6 Quick Presets** - Clean separators, fix spacing, and more

### Upgrade Benefits:
- **For Power Users:** Advanced bulk editing with persistence
- **For IPTV Players:** Instant updates, no more refresh delays
- **For Stability:** Robust error handling, no more crashes
- **For Convenience:** Rules remember your preferences
