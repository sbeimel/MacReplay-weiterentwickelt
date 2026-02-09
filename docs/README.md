# MacReplayXC v3.0.0

Proxy and management system for Stalker/MAC portals with XC API compatibility.

## ✨ What's New in v3.0.0

- **Advanced Channel Cache System** - 4 cache modes (lazy-ram, ram, disk, hybrid) with up to 10x faster access
- **Intelligent MAC Fallback** - Automatic MAC selection with cache-aware channel discovery
- **XC API Portal Filtering** - Filter by Portal ID or Portal Name
- **MAC Region Detection** - Automatic flag display (🇩🇪🇦🇹🇨🇭) based on genres
- **Dashboard Cache Management** - Rebuild/Clear cache with live statistics
- **Feature Wiki** - Complete documentation of all features and improvements
- **9 EPG Improvements** - Raw XML passthrough, variant deduplication, enrichment
- **Comprehensive Documentation** - 4,000+ lines of new documentation

See [CHANGELOG.md](docs/CHANGELOG.md) for full details.

## Features

- **Portal Management**: Multiple Stalker/MAC portals with unlimited MAC addresses
- **XC API**: Full Xtream Codes API compatibility for IPTV players
- **M3U Playlist**: Automatic playlist generation with EPG support
- **EPG Manager**: EPG data from portals with fallback support
- **Advanced Caching**: 4 cache modes for optimal performance
- **Intelligent MAC Management**: Automatic MAC selection and region detection
- **Channel Editor**: Rename, sort, enable/disable channels
- **VOD & Series**: Manage movie and series categories
- **Bulk Edit**: Mass editing of channel names with regex support
- **Proxy Support**: HTTP, SOCKS5 and Shadowsocks proxy support
- **Multi-User**: Multiple XC API users with individual credentials
- **Dark/Light Mode**: Modern UI with theme support

## Quick Start

### Docker (Recommended)

```bash
# Clone repository
git clone https://gitlab.com/Un1x/macreplayxc.git
cd MacReplayXC

# Start container
docker-compose up -d

# View logs
docker-compose logs -f
```

### Docker Compose (Standalone)

Create a `docker-compose.yml` file:

```yaml
services:
  macreplayxc:
    build: .
  # image: registry.gitlab.com/un1x/macreplayxc:latest
    container_name: MacReplayXC
    ports:
      - "8001:8001"
    dns:
      - 1.1.1.1
      - 1.0.0.1
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - HOST=0.0.0.0:8001
      - CONFIG=/app/data/MacReplayXC.json
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

Then run:
```bash
docker-compose up -d
```

### Docker Pull

```bash
docker pull registry.gitlab.com/un1x/macreplayxc:latest
```

The application is available at: `http://localhost:8001`

### Manual

```bash
# Install dependencies
pip install -r requirements.txt

# Start application
python app-docker.py
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0:8001` | Host and port |
| `CONFIG` | `/app/data/MacReplayXC.json` | Path to configuration file |

### Directories

| Path | Description |
|------|-------------|
| `data/` | Configuration and databases |
| `logs/` | Log files |

## Usage

### Add Portal

1. Navigate to **Portals**
2. Click **Add Portal**
3. Enter portal URL and MAC address(es)
4. Save

### XC API Users

1. Navigate to **XC Users**
2. Create user with username/password
3. Use credentials in your IPTV player

### XC API Endpoints

```
Server: http://your-server:8001
Username: your-username
Password: your-password
```

**Playlist URL:**
```
http://your-server:8001/get.php?username=USER&password=PASS&type=m3u_plus&output=ts
```

**Playlist URL (filtered by portal):**
```
http://your-server:8001/get.php?username=USER&password=PASS&type=m3u_plus&output=ts&portal_id=PORTAL_ID
```

**Or use Portal Name:**
```
http://your-server:8001/get.php?username=USER&password=PASS&type=m3u_plus&output=ts&portal_id=My%20Portal
```

**EPG URL:**
```
http://your-server:8001/xmltv.php?username=USER&password=PASS
```

**Note:** Portal filtering supports both Portal ID and Portal Name (case-insensitive). See [XC API Portal Filtering](docs/XC_API_PORTAL_FILTERING.md) for details.

### M3U Playlist

Direct playlist without XC API:
```
http://your-server:8001/playlist.m3u
```

EPG:
```
http://your-server:8001/xmltv
```

## Proxy Configuration

MacReplayXC supports various proxy types:

### HTTP/SOCKS5

In portal settings:
```
Proxy URL: socks5://user:pass@host:port
```

### Shadowsocks

```
Proxy URL: ss://method:password@host:port
```

Supported methods: `aes-256-cfb`, `aes-128-cfb`, `chacha20-ietf-poly1305`

See [Proxy Documentation](docs/PROXY_SUPPORT.md) for details.

## Project Structure

```
macreplayxc/
├── app-docker.py      # Main application
├── stb.py             # STB/Portal API client
├── utils.py           # Utility functions
├── templates/         # HTML templates
│   ├── dashboard.html
│   ├── portals.html
│   ├── editor.html
│   ├── epg.html
│   ├── vods.html
│   └── ...
├── static/            # CSS, icons
├── data/              # Configuration, databases
├── logs/              # Log files
└── docs/              # Documentation
```

## API Reference

### Live Streams

```
GET /player_api.php?username=X&password=X&action=get_live_streams
GET /player_api.php?username=X&password=X&action=get_live_categories
```

### VOD

```
GET /player_api.php?username=X&password=X&action=get_vod_streams
GET /player_api.php?username=X&password=X&action=get_vod_categories
```

### Series

```
GET /player_api.php?username=X&password=X&action=get_series
GET /player_api.php?username=X&password=X&action=get_series_categories
```

## Development

### Run Tests

```bash
pytest
```

### Logs

```bash
# Docker
docker-compose logs -f macreplayxc

# Manual
tail -f logs/MacReplayXC.log
```

## Known Limitations

- Some portals with aggressive Cloudflare protection may not work
- Shadowsocks requires compatible encryption methods

## Changelog

See [CHANGELOG.md](docs/CHANGELOG.md)

## License

MIT License
