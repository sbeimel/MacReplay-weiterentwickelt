# 🚀 Phase 1 + Portal Crawler - Implementierungsplan

## ✅ GESTOPPT AUF USER-WUNSCH

Die Implementierung wurde gestoppt. Hier ist der vollständige Plan für die zukünftige Umsetzung:

---

## 📋 GEPLANTE FEATURES

### 1. M3U Export für alle MACs (30 Min)

**Backend Endpoint**: `/scanner/export-all-m3u`

**Funktionalität**:
- Exportiert alle gefundenen MACs als eine M3U Playlist
- Filter: Portal, Min. Channels, nur DE Channels
- Limit: Max 50 MACs (konfigurierbar)
- Gruppierung nach Portal in group-title

**Code-Änderungen**:
- `app-docker.py`: Neuer Endpoint nach `/scanner/convert-mac2m3u`
- Iteriert durch alle gefundenen MACs
- Generiert M3U mit allen Channels
- Download als .m3u Datei

**Frontend**:
- Button "Export All to M3U" in Found MACs Tab
- Modal mit Filtern (Portal, Min Channels, DE only)
- Progress Indicator während Export

---

### 2. Cloudscraper Integration (1 Stunde)

**Was**: Cloudflare Challenge Bypass

**Code-Änderungen**:
```python
# scanner.py & scanner_async.py
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
    http_session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    http_session = requests.Session()
```

**Vorteile**:
- Automatisches CF-Challenge Lösen
- Drop-in Replacement für requests
- Keine weiteren Code-Änderungen nötig

**Installation**:
```bash
pip install cloudscraper
```

---

### 3. VPN/Proxy Detection (30 Min)

**Was**: Erkennen ob Portal hinter VPN/Proxy läuft

**Backend Funktion**: `detect_vpn_proxy(portal_url)`

**Code-Änderungen**:
```python
# scanner.py
def detect_vpn_proxy(portal_url, timeout=5):
    """Detect if portal is behind VPN/Proxy using IP-API.com"""
    from urllib.parse import urlparse
    
    hostname = urlparse(portal_url).hostname
    
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{hostname}?fields=status,proxy,hosting",
            timeout=timeout
        )
        data = resp.json()
        
        if data.get("status") == "success":
            return {
                "is_vpn": data.get("hosting", False),
                "is_proxy": data.get("proxy", False),
                "confidence": 0.8 if (data.get("proxy") or data.get("hosting")) else 0.9
            }
    except:
        pass
    
    return {"is_vpn": False, "is_proxy": False, "confidence": 0.0}
```

**Integration**:
- Beim Portal-Scan VPN Detection durchführen
- Ergebnis in DB speichern (neue Spalten: `is_vpn`, `is_proxy`)
- In UI anzeigen mit Badge

**DB Migration**:
```sql
ALTER TABLE found_macs ADD COLUMN is_vpn BOOLEAN DEFAULT 0;
ALTER TABLE found_macs ADD COLUMN is_proxy BOOLEAN DEFAULT 0;
```

---

### 4. Portal Crawler (1 Stunde)

**Was**: Automatisch neue Portale von urlscan.io finden

**Backend Funktion**: `crawl_portals_urlscan()`

**Code-Änderungen**:
```python
# scanner.py
def crawl_portals_urlscan():
    """Crawl new portals from urlscan.io"""
    try:
        base_url = "https://urlscan.io/api/v1/search/?q=filename%3A%22portal.php%3Ftype%3Dstb%26action%3Dhandshake%26token%3D%26prehash%3D0%26JsHttpRequest%3D1-xml%22"
        
        response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        portals = []
        for entry in data.get('results', []):
            if 'page' in entry and entry['page'].get('status') == "200":
                url = entry['page']['url']
                url = url.replace("https://", "http://")
                portals.append(url)
        
        portals = list(set(portals))  # Deduplicate
        
        logger.info(f"Found {len(portals)} portals from urlscan.io")
        return portals
    
    except Exception as e:
        logger.error(f"Portal crawl failed: {e}")
        return []
```

**Backend Endpoint**: `/scanner/crawl-portals`

```python
# app-docker.py
@app.route("/scanner/crawl-portals", methods=["POST"])
@authorise
def scanner_crawl_portals():
    """Crawl new portals from urlscan.io"""
    try:
        portals = scanner.crawl_portals_urlscan()
        return jsonify({"success": True, "portals": portals, "count": len(portals)})
    except Exception as e:
        logger.error(f"Portal crawl failed: {e}")
        return jsonify({"success": False, "error": str(e)})
```

**Frontend**:
```html
<!-- In scanner.html & scanner-new.html -->
<button class="btn btn-info" onclick="crawlPortals()">
    <i class="ti ti-world-search"></i> Find New Portals
</button>

<script>
async function crawlPortals() {
    const resp = await fetch('/scanner/crawl-portals', {method: 'POST'});
    const result = await resp.json();
    
    if (result.success) {
        alert(`Found ${result.count} new portals!`);
        // Display portals in modal or list
        showPortalsModal(result.portals);
    }
}

function showPortalsModal(portals) {
    // Create modal with portal list
    // Allow user to select portals to scan
}
</script>
```

---

## 📊 IMPLEMENTIERUNGS-REIHENFOLGE

### Schritt 1: Backend Funktionen (1.5h)
1. `crawl_portals_urlscan()` in scanner.py
2. `detect_vpn_proxy()` in scanner.py
3. Cloudscraper Integration in scanner.py & scanner_async.py

### Schritt 2: Backend Endpoints (30min)
1. `/scanner/export-all-m3u` in app-docker.py
2. `/scanner/crawl-portals` in app-docker.py

### Schritt 3: DB Migration (15min)
1. Neue Spalten für VPN/Proxy Detection
2. Migration Script erstellen

### Schritt 4: Frontend Integration (1h)
1. "Export All to M3U" Button + Modal
2. "Find New Portals" Button + Modal
3. VPN/Proxy Badges in Found MACs Tabelle

### Schritt 5: Testing (30min)
1. M3U Export testen
2. Portal Crawler testen
3. VPN Detection testen
4. Cloudscraper testen

**Gesamt**: ~3.5 Stunden

---

## 🎯 ERWARTETE ERGEBNISSE

### M3U Export für alle MACs
- ✅ Eine M3U Datei mit allen gefundenen MACs
- ✅ Gruppierung nach Portal
- ✅ Filter-Optionen
- ✅ Progress Indicator

### Cloudscraper Integration
- ✅ Automatischer CF-Challenge Bypass
- ✅ Keine Code-Änderungen nötig
- ✅ Drop-in Replacement

### VPN/Proxy Detection
- ✅ Automatische Erkennung
- ✅ Anzeige in UI mit Badge
- ✅ Speicherung in DB

### Portal Crawler
- ✅ Automatisch neue Portale finden
- ✅ urlscan.io Integration
- ✅ Deduplizierung
- ✅ UI für Portal-Auswahl

---

## 📝 NÄCHSTE SCHRITTE

Wenn du bereit bist, die Implementierung fortzusetzen:

1. **Bestätigung**: Sag mir Bescheid, wenn ich weitermachen soll
2. **Priorisierung**: Welches Feature zuerst? (M3U Export, Crawler, VPN Detection, Cloudscraper)
3. **Testing**: Nach jeder Implementierung testen

---

## ⚠️ WICHTIGE HINWEISE

### Cloudscraper
- Benötigt Installation: `pip install cloudscraper`
- Optional: Wenn nicht installiert, fällt auf requests zurück

### VPN Detection
- Nutzt kostenlose IP-API.com API
- Limit: 45 Requests/Minute
- Keine API-Key nötig

### Portal Crawler
- Nutzt urlscan.io API
- Keine Authentifizierung nötig
- Findet nur Portale mit Status 200

### M3U Export
- Kann bei vielen MACs lange dauern
- Limit auf 50 MACs empfohlen
- Progress Indicator wichtig

---

**Status**: ⏸️ PAUSIERT AUF USER-WUNSCH
**Datum**: 2026-02-07
**Bereit für**: Fortsetzung auf Anfrage
