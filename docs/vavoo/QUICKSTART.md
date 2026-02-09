# 🚀 Vavoo Integration - Quick Start Guide

## TL;DR - In 3 Schritten zu Vavoo

### 1️⃣ HOST-Variable anpassen
```yaml
# docker-compose.yml
environment:
  - HOST=http://your-domain.com:8001  # ← HIER ANPASSEN!
```

### 2️⃣ Container starten
```bash
docker-compose up -d
docker logs -f MacReplayXC
```

### 3️⃣ Vavoo nutzen
- **Web:** `http://your-domain.com:8001/vavoo_page`
- **Playlist:** `http://your-domain.com:4323/playlist/DE.m3u`

---

## Was wurde implementiert?

### ✅ Single Container Solution
- Vavoo läuft im gleichen Container wie MacReplayXC
- Port 8001: MacReplayXC
- Port 4323: Vavoo

### ✅ Tabler Dark Theme
- Vavoo nutzt MacReplayXC Design
- Dunkles Theme (Tabler Dark)
- Konsistente Optik

### ✅ Einheitliches Login
- Gleiche Credentials wie MacReplayXC
- Keine separate Authentifizierung

### ✅ Automatischer Start
- `start.sh` startet beide Apps
- Vavoo im Hintergrund
- MacReplayXC im Vordergrund

---

## Wichtige URLs

### Web-Interface
```
http://your-domain.com:8001/vavoo_page
```

### Playlists
```
# Einzelne Region
http://your-domain.com:4323/playlist/DE.m3u
http://your-domain.com:4323/playlist/FR.m3u

# Mehrere Regionen kombiniert
http://your-domain.com:4323/playlist/DE_FR_IT.m3u
```

### Streams
```
# Proxy Mode
http://your-domain.com:4323/vavoo?channel=<id>&region=DE

# HLS Playlist
http://your-domain.com:4323/hls/<id>/<region>/playlist.m3u8
```

---

## Verfügbare Regionen

DE, FR, IT, ES, GB, NL, PL, PT, RO, TR, AL, BG, CR

---

## Troubleshooting

### Problem: Vavoo startet nicht
**Lösung:** Logs prüfen
```bash
docker logs MacReplayXC | grep Vavoo
```

### Problem: Theme ist nicht dunkel
**Lösung:** CSS-Datei prüfen
```bash
docker exec MacReplayXC ls -la /app/vavoo/static/
```

---

**Version:** MacReplayXC v3.0.0 + Vavoo Integration  
**Status:** ✅ READY TO USE
