# MacReplay MOD Changelog

## [Latest] - 2025-12-08

### Added

#### EPG Settings Modal
- **EPG Fallback Configuration**
  - Added "Settings" button next to "Refresh EPG" button on EPG page
  - Modal dialog for configuring EPG fallback settings
  - Enable/disable EPG fallback checkbox
  - Fallback countries input (comma-separated country codes)
  - Info alert showing available countries
  - Settings saved to backend and persist across restarts
  - Toast notification on successful save
  - Backend endpoints: `/epg/settings` (GET/POST)
  - **Automatic Fallback Application**: EPG refresh now automatically applies fallback EPG for channels without portal EPG
  - Custom EPG IDs from database (set via EPG page) are used with highest priority during refresh
  - Priority order: 1. Database custom EPG ID, 2. JSON config custom EPG ID, 3. Channel number

#### Grid-Based Channel Editor
- **Complete Editor Redesign**
  - New grid-based category view inspired by modern IPTV interfaces
  - Categories displayed as grid cards showing enabled/total channel counts
  - Click on category to view and edit channels in that category
  - Cleaner, more intuitive interface for managing large channel lists
  - Real-time category and channel statistics
  - Search/filter categories by name
  - Filter by portal
  - Responsive grid layout adapts to screen size
  - Channel items show: enable toggle, play button, name, number, EPG ID
  - All editing functions preserved: enable/disable, rename, renumber, EPG mapping
  - Video player modal with HLS support
  - Legacy table view still available at `/editor/table`
  - Removed all hover effects (transform, box-shadow changes) as requested
  - Clean, distraction-free interface

#### Settings & Dashboard UI Improvements
- **Settings Page Enhancements**
  - Added descriptive subtitles to each settings section
  - Better visual hierarchy with section headers
  - Improved spacing and grouping
  - Consistent card styling across all sections
  - Flash messages converted to toast notifications
  - Cleaner, more professional appearance
  - Reorganized layout: Output Format, HLS Options, Stream Options in first row
  - EPG Fallback settings added to Settings page
  - HD HomeRun and Custom FFmpeg side-by-side
  - All cards have equal heights with `h-100` class

- **Dashboard Complete Redesign**
  - **Statistics Cards**: Active Streams, Total Channels, Server Status, Last Updated
  - **Modern Layout**: Two-column design with URLs and Quick Actions
  - **Real-time Updates**: Auto-refresh every 30 seconds for streams and stats
  - **New API Endpoint**: `/dashboard/stats` for total channels and last update time
  - **Better URL Display**: Monospace font for easy copying
  - **Quick Actions**: Large buttons for common tasks (Refresh, Download)
  - **Empty States**: Helpful messages when no streams active
  - **Live Stream Count**: Updates automatically in statistics card
  - Consistent styling with other pages (Portals, Editor, EPG, XC Users)

#### XC Users Page Redesign
- **Modern Grid-Based Layout**
  - Redesigned `/xc-users` page with grid-based card layout
  - User cards show: avatar icon, username, password, status badge
  - Connection stats: active/max connections with color coding
  - Expiration display with smart formatting (days, weeks, months)
  - Status badges: Active (green), Disabled (gray), Expired (red)
  - Sticky filter bar with search and status filter
  - Real-time statistics: total users and active connections
  - Green border hover effect on cards
  - **Copy Playlist Button**: One-click copy of XC API playlist URL with username/password
  - Playlist URL format: `http://server/get.php?username=USER&password=PASS&type=m3u_plus&output=ts`
  - Visual feedback on copy (button turns green with checkmark)
  - Toast notification on successful copy
  - Edit and Delete buttons in card footer
  - Empty state when no users or no results
  - Toast notifications for user actions
  - Responsive grid layout adapts to screen size
  - Consistent design with other pages (Portals, Editor, EPG)

#### Tabler Modal Dialogs
- **Replaced All Browser Alerts**
  - Replaced all `alert()` calls with Tabler modal dialogs
  - Replaced all `confirm()` calls with Tabler confirmation modals
  - Global `showAlert(message, title, type)` function for alerts
  - Global `showConfirm(message, title, onConfirm, onCancel, type)` function for confirmations
  - Modals support types: success, danger, warning, info
  - Color-coded icons and buttons based on type
  - Auto-cleanup after closing
  - Applied across all templates:
    - `templates/portals.html` - Portal management alerts
    - `templates/genre_selection.html` - Genre selection confirmations
    - `templates/dashboard.html` - Dashboard operation alerts
    - `templates/xc_users.html` - User management confirmations
    - `templates/epg_simple.html` - EPG operation alerts
    - `templates/editor_grid.html` - Editor operation alerts
    - `templates/editor.html` - Legacy editor alerts
  - Combined multiple sequential alerts into single modals where appropriate
  - Better UX with themed, consistent dialogs

#### Complete Design System Upgrade
- **Tabler.io-Based Modern Design**
  - Complete redesign of all UI components using only Tabler.io framework
  - Enhanced card system with better shadows, hover effects, and rounded corners (0.75rem)
  - Comprehensive badge system with proper light/dark mode support
  - All badges now have theme-aware colors that work correctly in both modes
  - Added "-lt" badge variants for subtle backgrounds (e.g., `bg-success-lt`)
  - Badge colors properly adjusted for both themes:
    - Light theme: solid colors with white text, subtle variants with dark text
    - Dark theme: darker solid colors, transparent subtle variants with light text
  - Improved button system with smooth transitions and hover effects
  - Enhanced form controls with better focus states and borders
  - Modern modal dialogs with rounded corners and proper shadows
  - Theme-aware alert system with consistent colors
  - Improved dropdown menus with better spacing and hover states
  - Enhanced navbar with smooth transitions
  - Pagination system with rounded buttons
  - Progress bars with smooth animations
  - List groups with hover effects
  - Custom scrollbar styling for both themes
  - Responsive design adjustments for mobile devices
  - Print-friendly styles
  - All components follow consistent design language
  - Smooth transitions throughout the interface (0.2s ease-in-out)
  - Proper color contrast for accessibility in both themes
  - Updated genre selection page to use theme-aware styles
  - Removed hardcoded dark theme colors from templates
  - All inline styles now respect current theme setting

#### Portals Page Redesign
- **Edit Portal Modal Overhaul**
  - Modern two-column layout with card sections
  - Status toggle card at top with avatar and enable/disable switch
  - Basic Settings section: Portal Name, URL, Proxy
  - Configuration section: Streams per MAC, EPG Offset, Retest option
  - MAC Addresses section split into two columns:
    - Left: Current MACs table with status badges (days until expiry)
    - Right: Update MACs textarea that fills available height
  - Clean dark mode styling with proper table colors
  - Removed ugly Bootstrap table-warning/danger backgrounds in dark mode
  - Custom table styling with transparent backgrounds
  - MAC code styling with proper dark/light mode colors

- **Genre Selection Modal Improvements**
  - Sticky search bar with glass effect (matches Editor/EPG modals)
  - Gradient fade effect for smooth scroll transition
  - Badge-style buttons for All/None/Refresh actions
  - Consistent styling with other modal dialogs

- **Portal Cards Simplified**
  - Removed Info button (redundant with Edit modal)
  - Three-button layout: Genres, Edit, Delete
  - Cleaner card footer with equal-width buttons

### Fixed

#### Channel Caching System (Docker Version)
- **SQLite Database Caching Implementation**
  - Ported complete channel caching system from app.py to app-docker.py
  - Channels cached in SQLite database (`/app/data/channels.db`)
  - Eliminates repeated API calls to portals on every page load
  - Database automatically initialized on first startup
  - Auto-refresh from portals if database is empty
  - Dramatic performance improvement for editor page
  - Database includes: portal, channel_id, name, number, genre, logo, enabled status, custom fields

#### EPG Page Performance Optimization
- **Database-Only EPG Status Loading**
  - `/epg/portal-status` route now uses database only - NO portal API queries
  - Eliminated token request spam when loading EPG page
  - EPG status calculated from database `custom_epg_id` field
  - Instant page load without waiting for portal responses
  - 5-minute cache for EPG status data
  - Prevents hundreds of unnecessary API calls on page load

#### EPG Fallback Matching Improvements
- **VERY Strict Matching Rules - Better No EPG Than Wrong EPG**
  - Completely redesigned `find_best_epg_match()` with ultra-conservative matching
  - Only exact matches (100% confidence) are automatically applied
  - Substring matches require 80% length similarity (increased from 60%)
  - Word-by-word matching is DISABLED by default (too many false positives)
  - Channels without confident matches get NO EPG ID (empty) instead of wrong data
  - Prevents false matches like "MÜNCHEN.TV" → "ntv" or "NRWISION" → Brazilian channels
  - Users can manually set EPG IDs for channels that don't auto-match
  - Applied to both manual fallback and automatic fallback during XMLTV refresh

#### Portal EPG Detection in Database
- **Track Portal EPG Availability**
  - Added `has_portal_epg` field to database schema
  - During cache refresh, checks ALL MACs for EPG data and stores status
  - EPG page now shows accurate portal EPG status from database
  - "Apply Fallback to All" button only applies to channels WITHOUT portal EPG
  - Prevents overwriting existing portal EPG with fallback data
  - Channels with portal EPG (like Magenta Sport) keep their original EPG IDs

#### EPG Mapping Performance Optimization
- **Direct Database Updates for EPG Mappings**
  - All EPG mapping routes now update database directly instead of JSON files
  - `/epg/save-mapping` - saves custom EPG IDs to database
  - `/epg/apply-fallback` - applies fallback EPG to database
  - `/epg/apply-fallback-all` - batch updates database for multiple channels
  - Prevents Gateway Timeout (504) errors on large channel lists
  - Increased limit to 5000 channels for batch fallback operations
  - Additional filtering to only process channels without portal EPG
  - Progress logging every 100 channels during batch operations

#### Multi-MAC Channel Discovery
- **Complete Channel Loading from All MACs**
  - All functions now query **ALL** MAC addresses and merge results
  - `portal_load_genres()` - Loads channels from ALL MACs and merges
  - `portal_save_genre_selection()` - Fetches from ALL MACs before saving
  - `refresh_channels_cache()` - Queries ALL MACs and merges into database
  - Ensures all available channels and genres are discovered
  - Different MACs may provide different channel sets (e.g., NL vs DE content)
  - Prevents missing channels when only first MAC is queried
  - Detailed logging shows channels loaded from each MAC

#### Multi-MAC EPG Collection
- **EPG Loading from All MACs**
  - EPG is now fetched from **ALL** configured MAC addresses
  - EPG data is merged intelligently - keeps version with most programmes
  - `refresh_xmltv()` - Merges EPG from all MACs
  - `epg_portal_status()` - Checks EPG from all MACs
  - `epg_channels()` - Collects EPG data from all MACs
  - Added detailed logging to show EPG collection from each MAC
  - Fixed issue where only first MAC's EPG was used
  - Maximizes EPG coverage across all available sources

#### EPG Fallback Matching
- **Improved Channel Name Matching**
  - Added `normalize_channel_name()` function to remove HD/SD/FHD/4K suffixes
  - Added `find_best_epg_match()` with multi-level matching:
    1. Exact normalized match
    2. Partial substring match
    3. Word-by-word matching with scoring
  - Removes special characters and extra whitespace for better matching
  - Case-insensitive matching throughout
  - Significantly improved fallback EPG assignment accuracy

#### Playlist Categories
- **Removed Portal Prefix from Category Names**
  - Categories now show as "IDE INACHRICHT" instead of "Anbieter - IDE INACHRICHT"
  - Cleaner category display in IPTV clients
  - Reduces clutter in category lists

---

## [Released] - 2025-12-06

### Added

#### Authentication & Security
- **Session-based Login System**
  - Replaced HTTP Basic Auth with session-based login using forms
  - Added `/login` page with username/password form
  - Added `/logout` endpoint to clear sessions
  - Added logout button in navigation bar
  - Sessions persist across browser restarts with `session.permanent = True`

#### Xtream Codes API
- **Complete XC API Implementation**
  - `/player_api.php` - Main API endpoint with user info, streams, and categories
  - `/get.php` - M3U playlist generation for XC clients
  - `/xmltv.php` - EPG/XMLTV endpoint for XC clients
  - `/<username>/<password>/<stream_id>` - Stream playback endpoint
  - `/live/<username>/<password>/<stream_id>` - Alternative stream endpoint with `/live/` prefix
  - Support for both `/xc/` prefixed and standard XC API URL formats

- **XC User Management**
  - `/xc-users` - User management interface
  - Add/Edit/Delete XC API users
  - Per-user connection limits (max simultaneous streams)
  - Per-user portal access control
  - User expiration dates
  - Enable/disable users
  - Real-time active connection tracking

- **XC API Features**
  - Numeric stream IDs using deterministic MD5 hashing for client compatibility
  - Automatic connection cleanup when streams end
  - Inactive connection cleanup (60 seconds timeout)
  - Device tracking per user
  - Proper XC API error responses with `user_info.auth = 0` format
  - `container_extension` field for stream format indication
  - Filtered categories - only shows categories with enabled channels
  - Filtered streams - only shows enabled channels from selected genres

#### EPG Enhancements
- **Multi-MAC EPG Fetching**
  - EPG is now fetched from ALL configured MAC addresses and merged
  - Different MACs provide different channels (e.g., NL vs DE content)
  
- **EPG Fallback System**
  - Automatic EPG fallback from epgshare01.online for channels without portal EPG
  - Configurable fallback countries (comma-separated: "DE, NL, UK")
  - Channel name matching (case-insensitive, exact or partial)
  - Only loads EPG for configured countries to save memory

- **EPG Management Page** (`/epg`)
  - **Portal Status Tab**: Shows actual EPG channel counts per portal
  - **EPG Mapping Tab**: Manual EPG ID assignment with search functionality
  - **EPG Fallback Tab**: Configure fallback settings
  - Individual "Apply Fallback" button per channel (cloud icon)
  - "Apply Fallback to All" button for bulk application
  - Real-time EPG refresh functionality

#### Settings Improvements
- **Reorganized Settings Page**
  - Clear hierarchical structure with section headers
  - **Streaming Settings**: HLS and basic streaming options at the top
  - **Security & Access**: Admin login and XC API settings
  - **Integrations**: HD HomeRun emulation
  - **Advanced**: Custom FFmpeg commands
  - Compact layout with better grouping
  - Clearer labels and descriptions

- **HLS Settings**
  - Prominent placement at top of settings (most important feature)
  - Inline layout for all HLS options
  - Clear descriptions for Plex optimization
  - Preset recommendations removed from settings (kept in documentation)

- **Security Settings**
  - Renamed "Enable HTTP authentication" to "Require login for web interface"
  - Renamed "Username/Password" to "Admin Username/Admin Password"
  - Added clarification that XC API is not affected by login requirement

#### UI/UX Improvements
- **Theme System**
  - Fixed dark/light mode switching
  - Changed from `@media (prefers-color-scheme)` to `[data-bs-theme]` attribute
  - Dynamic body class (`theme-dark`/`theme-light`) set before page load
  - Proper theme persistence in localStorage

- **Visual Improvements**
  - Removed hover effects from all cards globally
  - Cleaner, less distracting interface
  - Better form layouts with inline groups
  - Improved button placement in headers

### Changed

#### Memory Management
- **EPG Caching**
  - Added 5-minute cache for EPG routes to prevent repeated API calls
  - Explicit `gc.collect()` after EPG operations
  - Removed memory-intensive `minidom.parseString()` from `refresh_xmltv()`

- **Session Management**
  - Implemented session lifecycle management in `stb.py`
  - Automatic session refresh every 5 minutes
  - Explicit deletion of large data structures after use

#### Streaming
- **Content-Type Headers**
  - Changed from `application/octet-stream` to `video/mp2t` for MPEG-TS streams
  - Added `Accept-Ranges: none` header
  - Proper MIME type for better client compatibility

- **Stream URLs**
  - XC API streams now use standard format: `http://server/username/password/stream_id.ts`
  - Added `.ts` extension to all stream URLs for better IPTV client compatibility
  - Support for multiple URL formats (standard, `/xc/`, `/live/`)

#### Configuration
- **Error Handling**
  - Added try-catch for HLS settings parsing
  - Default values used when config contains invalid data
  - Prevents container crashes from malformed configuration

### Fixed

#### Authentication
- **Decorator Issues**
  - Fixed `@authorise` decorator missing `return decorated` statement
  - Created `@xc_auth_only` decorator for XC API routes (no HTTP Basic Auth fallback)
  - Created `@xc_auth_optional` decorator for routes that support both auth methods
  - Fixed decorator execution order issues

#### Streaming
- **XC API Stream Playback**
  - Fixed stream playback by calling `stream_channel()` directly instead of redirecting
  - Separated `stream_channel()` internal function from `channel()` route
  - Added proper connection cleanup wrapper for XC API streams
  - Fixed numeric stream ID reverse lookup using deterministic MD5 hashing

#### Routes
- **Protected Routes**
  - Added `/data/<path:filename>` route that returns 403 to block direct config access
  - Added checks in XC stream routes to block `/data/` and `MacReplay.json` access
  - Prevented route conflicts between XC API and system paths

#### EPG
- **XMLTV for XC API**
  - Fixed `/xmltv.php` to return cached XMLTV directly without auth issues
  - Removed double authentication in XC XMLTV endpoint
  - Proper content type and headers for XMLTV responses

#### UI
- **Settings Page**
  - Fixed duplicate form field IDs
  - Improved form validation
  - Better error messages
  - Fixed theme switcher initialization

### Security

- **Access Control**
  - XC API routes now properly isolated from web UI authentication
  - Admin login required for web interface (configurable)
  - XC API uses separate user authentication system
  - Protected `/data/` directory from external access
  - Connection limits per XC user to prevent abuse

- **Session Management**
  - Secure session cookies
  - Automatic session cleanup
  - CSRF protection via session tokens

### Performance

- **Caching**
  - 5-minute cache for EPG data
  - 5-minute cache for XMLTV
  - Reduced redundant API calls to portal providers

- **Memory Optimization**
  - Explicit garbage collection after heavy operations
  - Removed memory-intensive XML parsing
  - Session lifecycle management
  - Automatic cleanup of inactive connections

### Developer Experience

- **Code Organization**
  - Separated authentication decorators for different use cases
  - Created reusable `stream_channel()` function
  - Better error handling and logging
  - Consistent naming conventions

- **Logging**
  - Added XC API request logging
  - Connection tracking logs
  - Cleanup operation logs
  - Debug logs for troubleshooting

### Documentation

- **Settings UI**
  - Clearer descriptions for all settings
  - Inline help text for complex options
  - Examples for configuration values
  - Links to related features

- **XC Users Page**
  - Shows actual server URL for client configuration
  - Example URLs for different endpoints
  - Status indicators for API and users
  - Connection count display

## Migration Notes

### Breaking Changes

- **Authentication**: HTTP Basic Auth replaced with session-based login. Users must log in via `/login` page.
- **XC API**: Stream IDs are now numeric instead of string format `portal_id_channel_id`. Existing XC clients must refresh their playlists.

### Configuration Changes

- **Settings**: "Enable HTTP authentication" renamed to "Require login for web interface"
- **HLS Settings**: Invalid values now use defaults instead of crashing

### Upgrade Steps

1. Backup your `MacReplay.json` configuration file
2. Pull latest changes and rebuild container: `docker-compose up --build -d`
3. Log in to web interface with your existing credentials
4. If using XC API: Delete and re-add playlists in IPTV clients
5. Review and update settings if needed

## Known Issues

- None at this time

## Future Enhancements

- [ ] Multi-language support for UI
- [ ] Advanced EPG mapping with regex patterns
- [ ] Automatic portal health monitoring
- [ ] Statistics and analytics dashboard
