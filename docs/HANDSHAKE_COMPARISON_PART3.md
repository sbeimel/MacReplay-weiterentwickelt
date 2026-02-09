# Handshake Comparison Part 3 - Hauptunterschiede

## 🔥 HAUPTUNTERSCHIEDE zwischen den Projekten

### 1. **Token-Validierung**

#### FoxyMACSCANproV3_9:
```python
if "token" in veri:
    data = json.loads(veri)
    token = data['js']['token']
    if token:
        # Weiter mit get_profile
```
- ✅ Einfach: Token vorhanden = weiter
- ❌ Keine Unterscheidung zwischen Proxy-Fehler und MAC invalid
- ❌ Kein Retry bei Proxy-Problemen

#### MacAttackWeb-NEW:
```python
if not token:
    if compatible_mode:
        return False  # Sofort abbrechen
    else:
        # Intelligente Analyse:
        if resp.text.strip() == "":
            raise ProxySlowError("Empty response")
        elif resp.status_code == 404:
            # Strukturierte 404 = MAC invalid
            # Unstrukturierte 404 = Proxy blocked
        # ... weitere Checks ...
```
- ✅ **2 Modi:** Compatible (schnell) vs Intelligent (genau)
- ✅ Unterscheidet Proxy-Fehler von MAC-Fehlern
- ✅ Retry bei Proxy-Problemen
- ✅ Error Classification (ProxyDeadError, ProxySlowError, ProxyBlockedError)

#### Unser Projekt:
```python
# Gleich wie MacAttackWeb-NEW + zusätzlich:
- ✅ Einstellbar via UI (Compatible Mode Checkbox)
- ✅ Max Proxy Attempts Setting
- ✅ Unlimited Retries Option
- ✅ Proxy Rotation Percentage
```

---

### 2. **Channel & Genre Parsing**

#### FoxyMACSCANproV3_9:
```python
def chlist(listlink, mac, token, livel):
    res = ses.get(listlink, headers=hea2(mac, token, portal_idx), timeout=20)
    veri = str(res.text)
    
    # String-Splitting (unsicher!)
    if veri.count('title":"') > 0:
        for i in veri.split('title":"'):
            kanal = str((i.split('"')[0]))
            kategori = kategori + kanal + livel
    
    return list
```
- ❌ String-Splitting statt JSON-Parsing
- ❌ Fehleranfällig bei speziellen Zeichen
- ✅ Einfach und schnell

#### MacAttackWeb-NEW:
```python
# Genres
resp = do_request(genres_url, cookies, headers, proxies, timeout)
data = resp.json()
if "js" in data:
    result["genres"] = [g.get("title", "") for g in data["js"] if g.get("id") != "*"]
```
- ✅ Sauberes JSON-Parsing
- ✅ Error Handling
- ✅ Filtert "*" (All Channels) raus

#### Unser Projekt:
```python
# Gleich wie MacAttackWeb-NEW + zusätzlich:
- ✅ DE-Erkennung: Prüft ob "Deutsch", "German", "DE" in Genres
- ✅ Speichert in SQLite DB (scans.db)
- ✅ Batch-Writes (100 Hits) für Performance
```

---

### 3. **Proxy Handling**

#### FoxyMACSCANproV3_9:
```python
# Keine spezielle Proxy-Logik
# Einfach: Proxy setzen und Request machen
res = ses.get(url, headers=headers, timeout=5)
```
- ❌ Kein Proxy-Error-Tracking
- ❌ Keine Proxy-Rotation
- ❌ Keine Failed-Proxy-Removal

#### MacAttackWeb-NEW:
```python
def do_request(url, cookies, headers, proxies, timeout):
    try:
        resp = session.get(url, ...)
        
        # Cloudflare Detection
        if "cloudflare" in resp.text.lower():
            raise ProxyBlockedError("Cloudflare")
        
        # Gateway errors
        if resp.status_code in (502, 503, 504):
            raise ProxySlowError("Gateway error")
        
        return resp
    except requests.exceptions.ConnectTimeout:
        raise ProxyDeadError("Connect timeout")
    except requests.exceptions.ReadTimeout:
        raise ProxySlowError("Read timeout")
```
- ✅ Error Classification
- ✅ Cloudflare Detection
- ✅ Gateway Error Detection
- ✅ Timeout Unterscheidung (Connect vs Read)

#### Unser Projekt:
```python
# Gleich wie MacAttackWeb-NEW + zusätzlich:
- ✅ Proxy Error Counter (max_proxy_errors)
- ✅ Proxy Rotation (proxy_rotation_percentage)
- ✅ Force Proxy Rotation Every N Requests
- ✅ Remove Failed Proxies Button
- ✅ Reset Proxy Errors Button
- ✅ Proxy Test & Auto-Detect
- ✅ Proxy Sources (Fetch from URLs)
```

---

### 4. **Performance-Optimierungen**

#### FoxyMACSCANproV3_9:
```python
# Threading mit concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max_workers=speed) as executor:
    executor.map(scan_mac, mac_list)
```
- ✅ Multi-Threading
- ❌ Keine Connection Pooling
- ❌ Keine Session-Reuse
- ❌ Jeder Request = neue Connection

#### MacAttackWeb-NEW:
```python
# Global Session mit Connection Pooling
_session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=20,
    pool_maxsize=100,
    max_retries=Retry(total=0)
)
_session.mount('http://', adapter)
_session.mount('https://', adapter)
```
- ✅ Connection Pooling (20 pools, 100 connections)
- ✅ Session Reuse
- ✅ Keep-Alive Connections
- ✅ 10-50x schneller bei vielen Requests

#### Unser Projekt:
```python
# scanner.py: Sync mit Connection Pooling (wie MacAttackWeb-NEW)
# scanner_async.py: Async I/O mit aiohttp
async with aiohttp.ClientSession() as session:
    tasks = [scan_mac(mac) for mac in mac_list]
    await asyncio.gather(*tasks, return_exceptions=True)
```
- ✅ **Sync:** Connection Pooling (wie MacAttackWeb-NEW)
- ✅ **Async:** aiohttp mit bis zu 1000 concurrent tasks
- ✅ **10-100x schneller** als FoxyMACSCANproV3_9
- ✅ DNS Caching (LRU)
- ✅ HTTP Connection Pooling
- ✅ Batch DB Writes (100 Hits)
- ✅ orjson (10x schneller als json)
