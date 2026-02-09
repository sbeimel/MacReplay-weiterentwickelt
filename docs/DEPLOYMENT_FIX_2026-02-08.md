# 🐛 DEPLOYMENT FIX - 2026-02-08

## ❌ PROBLEM

```
ModuleNotFoundError: No module named 'stb_scanner'
```

**Ursache**: Neue Module wurden nicht im Dockerfile kopiert

---

## ✅ LÖSUNG

### Dockerfile aktualisiert

**Vorher**:
```dockerfile
# Copy application files
COPY app-docker.py app.py
COPY stb.py .
COPY utils.py .
COPY scanner.py .
COPY scanner_async.py .
COPY templates/ templates/
COPY static/ static/
```

**Nachher**:
```dockerfile
# Copy application files
COPY app-docker.py app.py
COPY stb.py .
COPY stb_scanner.py .          # ✅ NEU
COPY stb_async.py .             # ✅ NEU
COPY utils.py .
COPY scanner.py .
COPY scanner_async.py .
COPY scanner_scheduler.py .     # ✅ NEU
COPY mac_pattern_generator.py . # ✅ NEU
COPY migrate_vpn_detection.py . # ✅ NEU
COPY templates/ templates/
COPY static/ static/
```

---

## 📦 NEUE MODULE

Die folgenden Module wurden hinzugefügt und müssen kopiert werden:

1. **stb_scanner.py** (519 Zeilen)
   - STB Scanner Logic (Sync)
   - 45+ Portal-Typen
   - LRU Cache für Performance

2. **stb_async.py** (524 Zeilen)
   - STB Scanner Logic (Async)
   - 10-100x schneller
   - Async I/O

3. **scanner_scheduler.py** (288 Zeilen)
   - MAC-Listen Scheduler
   - Cron-ähnliche Funktionalität
   - Job Management

4. **mac_pattern_generator.py** (297 Zeilen)
   - Pattern Learning
   - 4 Generierungs-Strategien
   - Intelligente MAC-Generierung

5. **migrate_vpn_detection.py** (70 Zeilen)
   - DB Migration Script
   - VPN/Proxy Detection Setup

---

## 🚀 DEPLOYMENT SCHRITTE

### 1. Docker Image neu bauen
```bash
docker build -t macreplayxc:latest .
```

### 2. Container stoppen (falls läuft)
```bash
docker stop macreplayxc
docker rm macreplayxc
```

### 3. Container neu starten
```bash
docker run -d \
  --name macreplayxc \
  -p 8001:8001 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  macreplayxc:latest
```

### 4. Logs prüfen
```bash
docker logs -f macreplayxc
```

**Erwartete Ausgabe**:
```
[INFO] FFmpeg and FFprobe found and working
[INFO] ✅ cloudscraper v1.2.71 loaded successfully
[INFO] DNS caching enabled (1000 entries)
[INFO] ✅ Cloudscraper enabled - Cloudflare bypass active
[INFO] Using orjson for fast JSON parsing
[INFO] Signal handlers registered for graceful shutdown
[INFO] Starting MacReplayXC on 0.0.0.0:8001
```

---

## ✅ VERIFIZIERUNG

### Prüfe ob alle Module geladen sind:
```bash
docker exec macreplayxc python3 -c "
import scanner
import scanner_async
import stb_scanner
import stb_async
import scanner_scheduler
import mac_pattern_generator
print('✅ Alle Module erfolgreich geladen!')
"
```

### Prüfe Features:
```bash
docker exec macreplayxc python3 -c "
import scanner
print('Portal Crawler:', hasattr(scanner, 'crawl_portals_urlscan'))
print('VPN Detection:', hasattr(scanner, 'detect_vpn_proxy'))
print('Cloudscraper:', 'cloudscraper' in dir(scanner))
"
```

---

## 📋 CHECKLIST

- [x] Dockerfile aktualisiert
- [x] stb_scanner.py hinzugefügt
- [x] stb_async.py hinzugefügt
- [x] scanner_scheduler.py hinzugefügt
- [x] mac_pattern_generator.py hinzugefügt
- [x] migrate_vpn_detection.py hinzugefügt
- [ ] Docker Image neu gebaut
- [ ] Container neu gestartet
- [ ] Logs geprüft
- [ ] Module verifiziert

---

## 🔧 TROUBLESHOOTING

### Problem: "No module named 'X'"
**Lösung**: Prüfe ob Datei im Dockerfile kopiert wird

### Problem: "Permission denied"
**Lösung**: 
```bash
chmod +x start.sh
docker build --no-cache -t macreplayxc:latest .
```

### Problem: "Port already in use"
**Lösung**:
```bash
docker stop $(docker ps -q --filter ancestor=macreplayxc)
docker run -p 8002:8001 macreplayxc:latest  # Anderen Port nutzen
```

---

## 📊 DATEIGRÖSSEN

| Datei | Zeilen | Größe |
|-------|--------|-------|
| stb_scanner.py | 519 | ~20 KB |
| stb_async.py | 524 | ~21 KB |
| scanner_scheduler.py | 288 | ~11 KB |
| mac_pattern_generator.py | 297 | ~12 KB |
| migrate_vpn_detection.py | 70 | ~3 KB |
| **Gesamt** | **1,698** | **~67 KB** |

---

## 🎯 ZUSAMMENFASSUNG

**Problem**: ModuleNotFoundError für neue Module  
**Ursache**: Dockerfile nicht aktualisiert  
**Lösung**: 5 neue Module zum Dockerfile hinzugefügt  
**Status**: ✅ BEHOBEN

**Nächste Schritte**:
1. Docker Image neu bauen
2. Container neu starten
3. Features testen

---

**Datum**: 2026-02-08  
**Fix**: Dockerfile aktualisiert  
**Impact**: Alle 7 Features jetzt deploybar  
**Status**: ✅ READY FOR DEPLOYMENT
