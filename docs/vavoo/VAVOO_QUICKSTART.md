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
http://your-domain.com:4323/playlist/IT.m3u

# Mehrere Regionen kombiniert
http://your-domain.com:4323/playlist/DE_FR_IT.m3u
```

### Streams
```
# Proxy Mode (für Internet)
http://your-domain.com:4323/vavoo?channel=<id>&region=DE

# HLS Playlist
http://your-domain.com:4323/hls/<id>/<region>/playlist.m3u8
```

---

## Verfügbare Regionen

| Code | Land | Code | Land |
|------|------|------|------|
| DE | Deutschland | FR | Frankreich |
| IT | Italien | ES | Spanien |
| GB | UK | NL | Niederlande |
| PL | Polen | PT | Portugal |
| RO | Rumänien | TR | Türkei |
| AL | Albanien | BG | Bulgarien |
| CR | Kroatien | | |

---

## Konfiguration

### docker-compose.yml
```yaml
services:
  macreplayxc:
    ports:
      - "8001:8001"  # MacReplayXC
      - "4323:4323"  # Vavoo
    environment:
      - HOST=http://your-domain.com:8001  # ← Anpassen!
```

### Environment Variables (automatisch)
```bash
VAVOO_PUBLIC_HOST=your-domain.com  # Aus HOST extrahiert
VAVOO_PORT=4323                    # Fest konfiguriert
```

---

## Testing

### 1. Container-Logs prüfen
```bash
docker logs -f MacReplayXC
```

**Erwartete Ausgabe:**
```
🚀 Starting MacReplayXC + Vavoo...
📡 Vavoo public host: your-domain.com:4323
📡 Starting Vavoo on port 4323...
✅ Vavoo started (PID: 7)
🚀 Starting Waitress server (production-ready)...
🎬 Starting MacReplayXC on port 8001...
```

### 2. Web-Interface testen
```bash
# Browser öffnen
http://your-domain.com:8001/vavoo_page
```

**Erwartetes Ergebnis:**
- Login-Seite (falls Security enabled)
- Vavoo UI im iFrame
- Dunkles Theme (Tabler Dark)

### 3. Playlist testen
```bash
# Playlist herunterladen
curl http://your-domain.com:4323/playlist/DE.m3u

# In VLC öffnen
vlc http://your-domain.com:4323/playlist/DE.m3u
```

---

## Troubleshooting

### Problem: "Die Server-IP-Adresse von vavoo wurde nicht gefunden"
**Lösung:** HOST-Variable in docker-compose.yml anpassen
```yaml
environment:
  - HOST=http://your-domain.com:8001  # Nicht 0.0.0.0!
```

### Problem: "localhost hat die Verbindung abgelehnt"
**Lösung:** Port 4323 freigeben
```yaml
ports:
  - "4323:4323"  # Vavoo port
```

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

## Dokumentation

### Detaillierte Dokumentation
- **VAVOO_INTEGRATION_CHANGELOG.md**: Alle Änderungen im Detail
- **VAVOO_IMPLEMENTATION_COMPLETE.md**: Zusammenfassung & Status
- **VAVOO_FILES_SUMMARY.md**: Übersicht aller Dateien

### Web-Dokumentation
- **Wiki:** `http://your-domain.com:8001/wiki`
- **Vavoo-Sektion:** Erweiterte Setup-Anleitung

---

## Nächste Schritte

### 1. Produktiv-Deployment
```bash
# 1. HOST-Variable anpassen
vim docker-compose.yml

# 2. Container neu starten
docker-compose down
docker-compose up -d

# 3. Logs prüfen
docker logs -f MacReplayXC
```

### 2. Reverse Proxy (optional)
```nginx
# Nginx Beispiel
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8001;
    }
    
    location /vavoo {
        proxy_pass http://localhost:4323;
    }
}
```

### 3. Backup einrichten
```bash
# Daten sichern
docker cp MacReplayXC:/app/data ./backup/
docker cp MacReplayXC:/app/logs ./backup/
```

---

## Support

### Logs anzeigen
```bash
# Alle Logs
docker logs -f MacReplayXC

# Nur Vavoo
docker logs MacReplayXC 2>&1 | grep Vavoo

# Nur Fehler
docker logs MacReplayXC 2>&1 | grep -i error
```

### Container neu starten
```bash
docker-compose restart
```

### Container neu bauen
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## Checkliste

### ✅ Vor dem Start
- [ ] HOST-Variable in docker-compose.yml angepasst
- [ ] Ports 8001 und 4323 freigegeben
- [ ] Dokumentation gelesen

### ✅ Nach dem Start
- [ ] Container läuft ohne Fehler
- [ ] Vavoo-Tab in Navigation sichtbar
- [ ] Web-Interface erreichbar
- [ ] Theme ist dunkel
- [ ] Playlists funktionieren

---

## Zusammenfassung

**Was funktioniert:**
- ✅ Single Container (beide Apps)
- ✅ Tabler Dark Theme
- ✅ Einheitliches Login
- ✅ Automatischer Start
- ✅ Multi-Region Support
- ✅ Proxy & Direct Streaming

**Was zu tun ist:**
1. HOST-Variable anpassen
2. Container starten
3. Vavoo nutzen

**Das war's!** 🎉

---

**Erstellt:** 2026-02-06  
**Version:** MacReplayXC v3.0.0 + Vavoo Integration  
**Status:** ✅ READY TO USE
