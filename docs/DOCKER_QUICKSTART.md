# 🚀 DOCKER QUICKSTART
## MacReplayXC mit Scanner in 5 Minuten starten

---

## ⚡ SCHNELLSTART

```bash
# 1. Verzeichnisse erstellen
mkdir -p data logs

# 2. Build & Start
docker-compose up -d

# 3. Logs ansehen
docker-compose logs -f

# 4. Öffnen
open http://localhost:8001
```

**Fertig! 🎉**

---

## 📋 VORAUSSETZUNGEN

- ✅ Docker installiert
- ✅ Docker Compose installiert
- ✅ Ports 8001 und 4323 frei

**Prüfen:**
```bash
docker --version
docker-compose --version
```

---

## 🔧 DETAILLIERTE SCHRITTE

### Schritt 1: Repository klonen (falls noch nicht geschehen)
```bash
git clone <your-repo>
cd <your-repo>
```

### Schritt 2: Verzeichnisse erstellen
```bash
mkdir -p data logs
```

### Schritt 3: Docker Image bauen
```bash
docker-compose build
```

**Dauer:** ~5-10 Minuten (beim ersten Mal)

### Schritt 4: Container starten
```bash
docker-compose up -d
```

**Warte 60 Sekunden** für Health Check und Initialisierung

### Schritt 5: Status prüfen
```bash
docker ps
```

**Erwartete Ausgabe:**
```
CONTAINER ID   IMAGE                  STATUS                    PORTS
abc123def456   macreplayxc:3.0.0     Up 2 minutes (healthy)    0.0.0.0:8001->8001/tcp, 0.0.0.0:4323->4323/tcp
```

### Schritt 6: Web UI öffnen
```bash
# Browser öffnen:
open http://localhost:8001

# Oder manuell:
# http://localhost:8001
```

---

## 🎯 ERSTE SCHRITTE

### 1. Dashboard öffnen
```
http://localhost:8001/dashboard
```

### 2. Portal hinzufügen
```
http://localhost:8001/portals
→ "Add Portal" klicken
→ Portal URL, MAC eingeben
→ Speichern
```

### 3. Scanner ausprobieren (Sync)
```
http://localhost:8001/scanner
→ Portal URL eingeben
→ Mode: Random
→ Speed: 10
→ Start klicken
```

### 4. Scanner ausprobieren (Async) ✨
```
http://localhost:8001/scanner-new
→ Portal URL eingeben
→ Mode: Random
→ Speed: 100
→ Start klicken
```

### 5. Refresh Mode testen ✨
```
# Erst Random Mode laufen lassen (MACs finden)
# Dann:
→ Mode: Refresh
→ Gleiches Portal
→ Start klicken
→ MACs werden aus DB geladen und re-gescannt
```

---

## 🛠️ NÜTZLICHE COMMANDS

### Container Management:
```bash
# Status prüfen
docker ps

# Logs ansehen (live)
docker-compose logs -f

# Logs ansehen (letzte 100 Zeilen)
docker-compose logs --tail=100

# Container stoppen
docker-compose down

# Container neu starten
docker-compose restart

# Container neu bauen
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### In Container einloggen:
```bash
docker exec -it MacReplayXC bash
```

### Dateien prüfen:
```bash
# Scanner Module prüfen
docker exec -it MacReplayXC ls -la /app/scanner*.py

# Dependencies prüfen
docker exec -it MacReplayXC pip list | grep aio

# Config prüfen
docker exec -it MacReplayXC cat /app/data/MacReplayXC.json
```

### Health Check manuell:
```bash
curl http://localhost:8001/dashboard/stats
```

---

## 📊 VERFÜGBARE FEATURES

### MacReplayXC Core:
- ✅ Portal Management
- ✅ Channel Editor
- ✅ EPG Management
- ✅ VOD/Series Management
- ✅ XC API Integration
- ✅ Proxy Support
- ✅ M3U Playlist Generation
- ✅ Vavoo Integration

### Scanner (Sync):
- ✅ Random Mode
- ✅ List Mode
- ✅ Refresh Mode ✨
- ✅ Proxy Management
- ✅ Smart Rotation
- ✅ 2-5x schneller als Original

### Scanner (Async) ✨:
- ✅ Random Mode
- ✅ List Mode
- ✅ Refresh Mode ✨
- ✅ 10-100x schneller
- ✅ Async I/O
- ✅ 1000 concurrent tasks

---

## 🌐 URLS

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:8001/dashboard |
| Portals | http://localhost:8001/portals |
| Scanner (Sync) | http://localhost:8001/scanner |
| Scanner (Async) ✨ | http://localhost:8001/scanner-new |
| Editor | http://localhost:8001/editor |
| EPG | http://localhost:8001/epg |
| VODs | http://localhost:8001/vods |
| XC Users | http://localhost:8001/xc-users |
| Proxy Test | http://localhost:8001/proxy-test |
| Vavoo | http://localhost:4323 |

---

## 📁 DATEN & LOGS

### Data Verzeichnis:
```
./data/
├── MacReplayXC.json          # MacReplay Config
├── scanner_config.json       # Scanner Config
├── scans.db                  # Scanner Database (SQLite)
├── channels.db               # MacReplay Database (SQLite)
└── vavoo_playlists/          # Vavoo Playlists
```

### Logs Verzeichnis:
```
./logs/
├── macreplayxc.log          # Application Logs
└── vavoo.log                # Vavoo Logs
```

**Backup:**
```bash
# Backup erstellen
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/

# Restore
tar -xzf backup-20260207.tar.gz
```

---

## ⚙️ KONFIGURATION

### Host URL ändern:
```bash
# In docker-compose.yml:
environment:
  - HOST=http://your-domain.com:8001

# Dann neu starten:
docker-compose down
docker-compose up -d
```

### Scanner Settings:
```
http://localhost:8001/scanner
→ Settings Icon klicken
→ Speed, Timeout, etc. anpassen
→ Speichern
```

### Proxy hinzufügen:
```
http://localhost:8001/scanner
→ Proxies Tab
→ Proxies eingeben (eine pro Zeile)
→ Speichern
→ Test klicken
```

---

## 🐛 TROUBLESHOOTING

### Container startet nicht:
```bash
# Logs prüfen
docker-compose logs

# Ports prüfen
netstat -an | grep 8001
netstat -an | grep 4323

# Neu bauen
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Health Check UNHEALTHY:
```bash
# Warte 60 Sekunden
sleep 60

# Status prüfen
docker ps

# Logs prüfen
docker-compose logs -f

# Manuell testen
curl http://localhost:8001/dashboard/stats
```

### Scanner funktioniert nicht:
```bash
# Module prüfen
docker exec -it MacReplayXC ls -la /app/scanner*.py

# Dependencies prüfen
docker exec -it MacReplayXC pip list | grep -E "aiohttp|aiodns|orjson"

# Logs prüfen
docker-compose logs -f | grep -i scanner
```

### Async Scanner Fehler:
```bash
# Dependencies installieren (falls fehlen)
docker exec -it MacReplayXC pip install aiohttp aiodns

# Container neu starten
docker-compose restart
```

### Datenbank Fehler:
```bash
# Database neu erstellen
docker exec -it MacReplayXC rm /app/data/scans.db
docker-compose restart
```

---

## 📈 PERFORMANCE TIPPS

### Scanner Performance:
```
Sync Scanner:
- Speed: 10-50 (optimal: 20)
- Mit Proxies: Speed erhöhen (30-50)
- Ohne Proxies: Speed niedrig (10-20)

Async Scanner:
- Speed: 100-500 (optimal: 200)
- Mit vielen Proxies (>50): Speed erhöhen (300-500)
- Ohne Proxies: Speed moderat (100-200)
```

### Container Resources:
```yaml
# In docker-compose.yml hinzufügen:
services:
  macreplayxc:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

---

## 🔄 UPDATES

### Code Update:
```bash
# 1. Neuen Code pullen
git pull

# 2. Container neu bauen
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# 3. Logs prüfen
docker-compose logs -f
```

### Dependencies Update:
```bash
# requirements.txt bearbeiten
# Dann:
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## 🎉 FERTIG!

### Dein Setup läuft jetzt:
✅ MacReplayXC auf http://localhost:8001  
✅ Scanner (Sync) auf http://localhost:8001/scanner  
✅ Scanner (Async) auf http://localhost:8001/scanner-new ✨  
✅ Vavoo auf http://localhost:4323  

### Nächste Schritte:
1. Portal hinzufügen
2. Scanner ausprobieren
3. Refresh Mode testen ✨
4. Async Scanner testen ✨
5. Genießen! 🎉

---

**Viel Spaß mit MacReplayXC! 🚀**
