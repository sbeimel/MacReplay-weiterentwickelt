# MacReplay MOD Changelog

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
