# 🔧 MacReplayXC Proxy Testing Guide

Dieses Dokument erklärt, wie Sie SOCKS5 und Shadowsocks Proxies in MacReplayXC testen können.

## 🚀 Schnellstart

### 1. Web-Interface (Einfachste Methode)

1. **Starten Sie MacReplayXC:**
   ```bash
   docker-compose up -d
   ```

2. **Öffnen Sie den Proxy-Test:**
   - Gehen Sie zu: `http://localhost:8001/proxy-test`
   - Loggen Sie sich ein (falls Sicherheit aktiviert ist)
   - Geben Sie Ihre Proxy-URL ein und klicken Sie "Test Proxy"

### 2. Kommandozeilen-Tests

#### Basis-Validierungstests:
```bash
# In Docker Container
docker exec -it MacReplayXC python test_socks5_support.py
docker exec -it MacReplayXC python test_shadowsocks_support.py
docker exec -it MacReplayXC python test_shadowsocks_integration.py

# Auf Host-System (im MacReplayXC Verzeichnis)
python test_socks5_support.py
python test_shadowsocks_support.py
python test_shadowsocks_integration.py
```

#### Spezifische Proxy-Tests:
```bash
# SOCKS5 Proxy testen
docker exec -it MacReplayXC python test_proxy_docker.py "socks5://127.0.0.1:1080"

# Shadowsocks testen
docker exec -it MacReplayXC python test_proxy_docker.py "ss://aes-256-gcm:password@server:8388"

# HTTP Proxy testen
docker exec -it MacReplayXC python test_proxy_docker.py "http://proxy.com:8080"
```

#### Shadowsocks Konnektivitätstest:
```bash
docker exec -it MacReplayXC python test_shadowsocks_connectivity.py "ss://aes-256-gcm:password@server:8388"
```

### 3. Komplettes Test-Suite

```bash
# Alle Tests ausführen
docker exec -it MacReplayXC bash run_proxy_tests.sh
```

## 🐳 Docker Test-Setup mit Gluetun

### Test-Environment starten:
```bash
# Test-Compose mit Gluetun verwenden
docker-compose -f docker-compose-test.yml up -d

# Warten bis Services bereit sind
sleep 30

# Tests ausführen
docker exec -it macreplayxc-test bash run_proxy_tests.sh
```

### Verfügbare Test-Proxies:
- **Gluetun SOCKS5:** `socks5://gluetun:1080`
- **Gluetun Shadowsocks:** `ss://aes-256-gcm:test_password_123@gluetun:8388`
- **Standalone SOCKS5:** `socks5://socks5-test:1080`
- **HTTP Proxy:** `http://http-proxy-test:3128`

## 📋 Unterstützte Proxy-Formate

### SOCKS5 Proxies
```
socks5://127.0.0.1:1080
socks5://user:password@proxy.example.com:1080
socks4://127.0.0.1:1080
```

### Shadowsocks Proxies
```
ss://aes-256-gcm:password@server.example.com:8388
ss://chacha20-ietf-poly1305:secretkey@proxy.com:443
ss://aes-128-gcm:mypassword@192.168.1.100:8388
```

### HTTP/HTTPS Proxies
```
http://proxy.example.com:8080
https://proxy.example.com:8080
http://user:password@proxy.example.com:8080
```

## 🔍 Test-Methoden

### 1. Web-Interface (`/proxy-test`)
- **Vorteile:** Benutzerfreundlich, visuelles Feedback
- **Tests:** Validierung, HTTP-Konnektivität, Shadowsocks-Bibliothek
- **Zugriff:** `http://localhost:8001/proxy-test`

### 2. API-Endpoint (`/proxy/test`)
```bash
curl -X POST http://localhost:8001/proxy/test \
     -H "Content-Type: application/json" \
     -d '{"proxy_url":"socks5://127.0.0.1:1080"}'
```

### 3. Kommandozeilen-Tools
- `test_proxy_docker.py` - Umfassender Proxy-Test
- `test_shadowsocks_connectivity.py` - Shadowsocks-spezifisch
- `test_socks5_support.py` - SOCKS5-Validierung
- `test_shadowsocks_support.py` - Shadowsocks-Validierung

## 🛠️ Troubleshooting

### Häufige Probleme:

#### 1. "Shadowsocks library not available"
```bash
# In Docker Container
docker exec -it MacReplayXC pip install shadowsocks==2.8.2

# Oder Dockerfile erweitern
RUN pip install shadowsocks==2.8.2
```

#### 2. "Connection refused" bei Gluetun
```bash
# Gluetun Status prüfen
docker logs gluetun | grep -i shadowsocks
docker logs gluetun | grep -i error

# Port-Verfügbarkeit testen
docker exec gluetun netstat -tlnp | grep 8388
```

#### 3. "Unexpected EOF" bei Shadowsocks
```bash
# Konnektivitätstest ausführen
docker exec -it MacReplayXC python test_shadowsocks_connectivity.py "ss://method:pass@server:port"

# Gluetun Troubleshooting Guide lesen
cat GLUETUN_SHADOWSOCKS_TROUBLESHOOTING.md
```

### Debug-Informationen sammeln:
```bash
# Container-Logs
docker logs MacReplayXC --tail 50
docker logs gluetun --tail 50

# Netzwerk-Tests
docker exec MacReplayXC ping gluetun
docker exec MacReplayXC telnet gluetun 8388
```

## 📊 Test-Ergebnisse verstehen

### Erfolgreiche Tests zeigen:
- ✅ **Validation:** Proxy-URL ist korrekt formatiert
- ✅ **Parsing:** Proxy kann für requests-Bibliothek geparst werden
- ✅ **Connectivity:** HTTP-Request durch Proxy erfolgreich
- ✅ **External IP:** Andere IP als lokale (bei VPN/Proxy)

### Fehlgeschlagene Tests zeigen:
- ❌ **Invalid format:** Proxy-URL falsch formatiert
- ❌ **Connection timeout:** Proxy nicht erreichbar
- ❌ **Proxy error:** Authentifizierung oder Proxy-Fehler
- ❌ **Library missing:** Shadowsocks-Bibliothek nicht installiert

## 🎯 Produktive Nutzung

### Portal mit Proxy konfigurieren:
1. Gehen Sie zu `/portals`
2. Bearbeiten Sie ein Portal oder erstellen Sie ein neues
3. Geben Sie die Proxy-URL im "Proxy" Feld ein:
   - `socks5://gluetun:1080` (für Gluetun SOCKS5)
   - `ss://aes-256-gcm:password@gluetun:8388` (für Gluetun Shadowsocks)
4. Speichern Sie die Konfiguration
5. Testen Sie das Portal mit "Test MACs"

### Empfohlene Konfigurationen:

#### Für VPN-Routing (einfach):
```
socks5://gluetun:1080
```

#### Für Zensur-Umgehung (erweitert):
```
ss://aes-256-gcm:strong_password@gluetun:8388
```

## 📚 Weitere Ressourcen

- **Proxy-Dokumentation:** `PROXY_SUPPORT.md`
- **Shadowsocks-Implementation:** `SHADOWSOCKS_IMPLEMENTATION_SUMMARY.md`
- **Gluetun-Troubleshooting:** `GLUETUN_SHADOWSOCKS_TROUBLESHOOTING.md`
- **Test-Dateien:** `test_*.py`

## 🔧 Entwicklung

### Neue Tests hinzufügen:
1. Erweitern Sie `test_proxy_docker.py`
2. Fügen Sie Tests zu `test_shadowsocks_support.py` hinzu
3. Aktualisieren Sie `run_proxy_tests.sh`

### Web-Interface erweitern:
1. Bearbeiten Sie `templates/proxy_test.html`
2. Erweitern Sie den `/proxy/test` Endpoint in `app-docker.py`

---

**Hinweis:** Alle Tests sind so konzipiert, dass sie sowohl in Docker-Containern als auch auf Host-Systemen funktionieren. Die Web-Interface-Tests erfordern eine laufende MacReplayXC-Instanz.