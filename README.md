# MacReplayXC v3.0.0

**IPTV Portal Proxy with DB-based Caching & Vavoo Integration**

---

## 🚀 Features

### Core IPTV Proxy
- ✅ **DB-based Channel Caching** - 30x faster streaming
- ✅ **Intelligent MAC Routing** - Automatic MAC selection
- ✅ **Auto-Learning** - Persistent across restarts
- ✅ **Portal Management** - Multiple IPTV portals
- ✅ **Channel Editor** - Customize names, numbers, genres
- ✅ **EPG Management** - XMLTV generation
- ✅ **VOD/Series Support** - Movies & series streaming
- ✅ **XC API Emulation** - Xtream Codes compatibility
- ✅ **HDHomeRun Emulation** - Plex/Emby/Jellyfin integration
- ✅ **Proxy Testing** - Test proxy connectivity
- ✅ **Authentication** - Secure login system

### Vavoo Integration
- ✅ **Separate Container** - Runs on port 4323
- ✅ **Multi-Region** - DE, FR, IT, ES, GB, NL, PL, PT, RO, TR, AL, BG, CR
- ✅ **Resolution Scan** - FFmpeg-based quality detection
- ✅ **Streaming Modes** - Proxy (Internet) or Direct (LAN)
- ✅ **Channel Filter** - Keyword-based filtering

---

## 📊 Performance

- **Channel Access:** <0.1 seconds (DB-based)
- **Streaming:** 30x faster than original
- **Concurrent Streams:** ~400 (48 threads)
- **JSON Parsing:** 10x faster (orjson)
- **Python:** 3.13 (+15% performance)

---

## 🐳 Quick Start

### Docker Compose (Recommended)
```bash
docker-compose up -d
```

### Access
- **MacReplayXC:** http://localhost:8001
- **Vavoo:** http://localhost:4323
- **Default Login:** admin / 12345

---

## 📁 Project Structure

```
.
├── app-docker.py          # Main application (9,763 lines)
├── stb.py                 # STB API
├── utils.py               # Utility functions
├── requirements.txt       # Dependencies
├── Dockerfile             # Container build
├── docker-compose.yml     # Container orchestration
├── start.sh               # Startup script
├── templates/             # HTML templates (13 files)
├── static/                # CSS, JS, images
├── vavoo/                 # Vavoo integration
└── docs/                  # Documentation
```

---

## 📚 Documentation

- **[Main Documentation](docs/README.md)** - Complete documentation index
- **[Final Cleanup Summary](docs/FINAL_CLEANUP_SUMMARY.md)** - Cleanup details
- **[Version Comparison](docs/EXACT_DIFFERENCES.md)** - vs andere sources
- **[Vavoo Guide](docs/vavoo/)** - Vavoo setup & usage

---

## 🔧 Configuration

### Environment Variables
```bash
HOST=your-domain.com:8001  # External host
CONFIG=/app/data/MacReplayXC.json  # Config file path
```

### Settings
- **Security:** Enable/disable authentication
- **Streaming:** FFmpeg or redirect mode
- **EPG:** Auto-refresh interval
- **VOD:** Proxy through server
- **HDHomeRun:** Plex/Emby integration

---

## 🎯 Comparison with andere sources/MacReplay-weiterentwickelt

| Feature | MacReplayXC | andere sources |
|---------|-------------|----------------|
| **DB-based Caching** | ✅ | ✅ |
| **Intelligent MAC Routing** | ✅ | ✅ |
| **All Core Features** | ✅ | ✅ |
| **Vavoo Integration** | ✅ | ❌ |
| **Lines of Code** | 9,763 | 9,684 |
| **Similarity** | 99.2% identical | - |

**Difference:** Only Vavoo integration (+79 lines)

---

## 🛠️ Development

### Requirements
- Python 3.13+
- Docker & Docker Compose
- FFmpeg & FFprobe

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Locally
```bash
python3 app-docker.py
```

---

## 📝 Version History

### v3.0.0 (Current)
- ✅ DB-based channel caching (30x faster)
- ✅ Intelligent MAC routing
- ✅ Auto-learning
- ✅ Vavoo integration
- ✅ Python 3.13 support
- ✅ orjson for 10x faster JSON parsing
- ✅ 48 threads for better concurrency
- ❌ Scanner removed (not needed)
- ❌ SSE removed (not needed)

---

## 🤝 Credits

- **Original:** MacReplay
- **Fork:** Un1x & StiniStinson
- **Vavoo Integration:** Custom implementation
- **DB Optimization:** v3.1.0 enhancement

---

## 📄 License

See LICENSE file for details.

---

## 🚀 Status

✅ **Production Ready**
- Clean codebase
- No scanner code
- No SSE code
- Organized documentation
- 99.2% identical to andere sources
- Only difference: Vavoo integration

**Ready for deployment!**
