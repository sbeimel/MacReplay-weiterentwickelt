# Handshake Comparison Part 2

## MacAttackWeb-NEW (Fortsetzung)

#### Header-Struktur:
```python
def get_headers(token=None, token_random=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept-Encoding": "identity",
        "Accept": "*/*",
        "Connection": "close",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if token_random is not None:
        headers["X-Random"] = str(token_random)
    return headers
```

#### Cookies:
```python
def get_cookies(mac):
    sn, device_id, device_id2, hw_version_2 = generate_device_ids(mac)
    return {
        "adid": hw_version_2,
        "debug": "1",
        "device_id2": device_id2,
        "device_id": device_id,
        "hw_version": "1.7-BD-00",
        "mac": mac,
        "sn": sn,
        "stb_lang": "en",
        "timezone": "America/Los_Angeles",
    }
```

#### Device ID Generation:
```python
def generate_device_ids(mac):
    sn = hashlib.md5(mac.encode()).hexdigest().upper()[:13]
    device_id = hashlib.sha256(sn.encode()).hexdigest().upper()
    device_id2 = hashlib.sha256(mac.encode()).hexdigest().upper()
    hw_version_2 = hashlib.sha1(mac.encode()).hexdigest()
    return sn, device_id, device_id2, hw_version_2
```

#### Error Classification (Intelligent Retry):
```python
class ProxyDeadError(ProxyError):
    """Proxy unreachable (connection refused, DNS fail)"""
    pass

class ProxySlowError(ProxyError):
    """Proxy timeout"""
    pass

class ProxyBlockedError(ProxyError):
    """Proxy blocked by portal (403, rate limit)"""
    pass

def do_request(url, cookies, headers, proxies, timeout):
    try:
        resp = session.get(url, cookies=cookies, headers=headers, 
                          proxies=proxies, timeout=(connect_timeout, timeout))
        
        # Cloudflare Detection
        if "text/html" in content_type:
            if "cloudflare" in resp.text.lower():
                raise ProxyBlockedError("Cloudflare detected")
        
        # Gateway errors = Proxy slow
        if resp.status_code in (502, 503, 504):
            raise ProxySlowError(f"Gateway error {resp.status_code}")
        
        # 429 = Rate limit
        if resp.status_code == 429:
            raise ProxyBlockedError("Rate limit exceeded")
        
        return resp
        
    except requests.exceptions.ConnectTimeout:
        raise ProxyDeadError("Connect timeout")
    except requests.exceptions.ReadTimeout:
        raise ProxySlowError("Read timeout")
    except requests.exceptions.ProxyError:
        raise ProxyDeadError("Proxy error")
```

#### Connection Pooling:
```python
def get_optimized_session():
    global _session
    if _session is None:
        _session = requests.Session()
        
        # Configure adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=20,      # Number of connection pools
            pool_maxsize=100,         # Max connections per pool
            max_retries=Retry(total=0)
        )
        
        _session.mount('http://', adapter)
        _session.mount('https://', adapter)
    
    return _session
```

---

### 3. **Unser Projekt (scanner.py / scanner_async.py)**

#### Handshake-Prozess:
```python
# Ähnlich wie MacAttackWeb-NEW, aber mit zusätzlichen Features:

# 1. Handshake
handshake_url = f"{portal_url}?type=stb&action=handshake&prehash=false&JsHttpRequest=1-xml"
resp = session.get(handshake_url, headers=headers, cookies=cookies, 
                   proxies=proxies, timeout=timeout)

# Token-Check
data = resp.json()
token = data.get("js", {}).get("token")

if not token:
    # Compatible Mode Check
    if settings.get("macattack_compatible_mode"):
        return {"valid": False, "error": "No token (compatible mode)"}
    else:
        # Intelligent retry logic
        # ... Analyse ob Proxy-Problem oder MAC invalid ...

# 2. Get Profile
profile_url = f"{portal_url}?type=stb&action=get_profile&JsHttpRequest=1-xml"
resp = session.get(profile_url, headers=headers_with_token, ...)

# 3. Channels
channels_url = f"{portal_url}?type=itv&action=get_all_channels&JsHttpRequest=1-xml"
resp = session.get(channels_url, headers=headers_with_token, ...)

# 4. Genres (für DE-Erkennung)
genres_url = f"{portal_url}?type=itv&action=get_genres&JsHttpRequest=1-xml"
resp = session.get(genres_url, headers=headers_with_token, ...)
```
