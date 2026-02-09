# 🐳 Docker Proxy Setup Guide

Vollständige Anleitung zur Installation aller Proxy-Abhängigkeiten in Docker.

## 📦 Automatische Installation

### Option 1: Dockerfile erweitern (Empfohlen)

Fügen Sie diese Zeilen zu Ihrem `Dockerfile` hinzu:

```dockerfile
# Proxy-Abhängigkeiten installieren
RUN pip install --no-cache-dir \
    requests[socks]==2.31.0 \
    PySocks==1.7.1 \
    shadowsocks-libev>=1.3.0 \
    cryptography>=3.4.8 \
    pycryptodome>=3.15.0

# Alternative für ältere Python-Versionen
# RUN pip install shadowsocks==2.8.2
```

### Option 2: Requirements.txt verwenden

Die aktualisierte `requirements.txt` enthält bereits alle notwendigen Abhängigkeiten:

```bash
# Container neu bauen
docker-compose build --no-cache
```

## 🔧 Manuelle Installation in laufendem Container

### SOCKS5-Unterstützung:
```bash
docker exec -it MacReplayXC pip install requests[socks] PySocks
```

### Shadowsocks-Unterstützung (alle Python-Versionen):
```bash
docker exec -it MacReplayXC pip install shadowsocks==2.8.2 cryptography pycryptodome
```

**Hinweis:** Die Anwendung enthält einen automatischen Kompatibilitäts-Fix für Python 3.10+

## 🧪 Installation testen

### Test-Befehle im Container:
```bash
# SOCKS5-Test
docker exec -it MacReplayXC python -c "import socks; print('✅ PySocks available')"

# Shadowsocks-Test (neue Version)
docker exec -it MacReplayXC python -c "import shadowsocks; print('✅ Shadowsocks-libev available')"

# Shadowsocks-Test (alte Version)
docker exec -it MacReplayXC python -c "import shadowsocks.local; print('✅ Shadowsocks available')"

# Vollständiger Proxy-Test
docker exec -it MacReplayXC python test_proxy_docker.py "socks5://127.0.0.1:1080"
```

## 🐋 Komplettes Docker-Setup

### docker-compose.yml mit Proxy-Support:
```yaml
version: '3.8'
services:
  macreplayxc:
    build: .
    container_name: MacReplayXC
    ports:
      - "8001:8001"
    environment:
      - HOST=0.0.0.0:8001
      - CONFIG=/app/data/MacReplay.json
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    # Zusätzliche Abhängigkeiten für Proxy-Support
    depends_on:
      - gluetun  # Optional: VPN-Container
    
  # Optional: Gluetun für VPN/Proxy-Services
  gluetun:
    image: qmcgaw/gluetun
    container_name: gluetun
    cap_add:
      - NET_ADMIN
    environment:
      - VPN_SERVICE_PROVIDER=your_provider
      - SHADOWSOCKS=on
      - SHADOWSOCKS_PASSWORD=your_password
      - SHADOWSOCKS_METHOD=aes-256-gcm
      - SHADOWSOCKS_PORT=8388
    ports:
      - "8388:8388"  # Shadowsocks
      - "1080:1080"  # SOCKS5
    restart: unless-stopped
```

## 🔍 Troubleshooting

### Häufige Probleme und Lösungen:

#### 1. "No module named 'shadowsocks'"
```bash
# Lösung A: Moderne Version installieren
docker exec -it MacReplayXC pip install shadowsocks-libev

# Lösung B: Legacy Version installieren
docker exec -it MacReplayXC pip install shadowsocks==2.8.2
```

#### 2. "collections.MutableMapping" Fehler
```bash
# Python 3.10+ Kompatibilitätsproblem
docker exec -it MacReplayXC pip uninstall shadowsocks
docker exec -it MacReplayXC pip install shadowsocks-libev
```

#### 3. "No module named 'socks'"
```bash
# SOCKS5-Unterstützung installieren
docker exec -it MacReplayXC pip install requests[socks] PySocks
```

#### 4. Kryptographie-Fehler
```bash
# Kryptographie-Bibliotheken installieren
docker exec -it MacReplayXC pip install cryptography pycryptodome
```

## 📋 Vollständige Abhängigkeitsliste

### Für SOCKS5-Proxies:
- `requests[socks]==2.31.0`
- `PySocks==1.7.1`

### Für Shadowsocks-Proxies:
- `shadowsocks==2.8.2` (mit Python 3.10+ Kompatibilitäts-Fix)
- `cryptography>=3.4.8`
- `pycryptodome>=3.15.0`

### Für HTTP/HTTPS-Proxies:
- `requests==2.31.0` (bereits enthalten)
- `urllib3==2.0.7`

## ✅ Verifikation

Nach der Installation sollten diese Tests erfolgreich sein:

```bash
# Im Container ausführen
docker exec -it MacReplayXC python -c "
import requests
import socks
print('✅ SOCKS5 support ready')

try:
    import shadowsocks
    print('✅ Shadowsocks support ready')
except ImportError:
    print('⚠️ Shadowsocks not available (optional)')

print('🎯 All proxy dependencies installed!')
"
```

## 🚀 Produktive Nutzung

Nach erfolgreicher Installation können Sie alle Proxy-Typen verwenden:

```bash
# SOCKS5-Proxy testen
curl -x socks5://gluetun:1080 http://httpbin.org/ip

# Shadowsocks in MacReplayXC konfigurieren
# Portal-Einstellungen: ss://aes-256-gcm:password@gluetun:8388
```

---

**Hinweis:** Die aktualisierte `requirements.txt` enthält bereits alle notwendigen Abhängigkeiten. Ein einfaches `docker-compose build --no-cache` sollte ausreichen.