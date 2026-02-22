# Stalker Portal Protocol - Quick Reference Guide

## Correct API Endpoint Formats

### 1. Handshake (Get Token)
```
GET /portal.php?type=stb&action=handshake&token=&prehash=false&JsHttpRequest=1-xml

Cookies: mac, stb_lang, timezone
Headers: Authorization: Bearer undefined

Response:
{
  "js": {
    "token": "abc123...",
    "random": "xyz789..."
  }
}
```

### 2. Get Profile (Check Watchdog)
```
GET /portal.php?type=stb&action=get_profile&hd=1&ver=ImageDescription&JsHttpRequest=1-xml

Cookies: mac, stb_lang, timezone
Headers: Authorization: Bearer {token}

Response:
{
  "js": {
    "watchdog_timeout": 300,
    "playback_limit": 2,
    "status": 1,
    "mac": "00:1A:79:XX:XX:XX"
  }
}
```

### 3. Get Channel List (Ordered)
```
GET /portal.php?type=itv&action=get_ordered_list&genre=*&force_ch_link_check=0&fav=0&sortby=number&hd=0&JsHttpRequest=1-xml

Cookies: mac, stb_lang, timezone
Headers: Authorization: Bearer {token}

Response:
{
  "js": {
    "data": [
      {
        "id": "1",
        "name": "Channel Name",
        "cmd": "ffmpeg http://localhost/ch/1234_",
        "tv_genre_id": "1",
        "number": "1"
      }
    ],
    "total_items": 100
  }
}
```

### 4. Get Genres
```
GET /portal.php?type=itv&action=get_genres&JsHttpRequest=1-xml

Cookies: mac, stb_lang, timezone
Headers: Authorization: Bearer {token}

Response:
{
  "js": [
    {"id": "1", "title": "News"},
    {"id": "2", "title": "Sports"}
  ]
}
```

### 5. Create Link (Get Stream URL)
```
GET /portal.php?type=itv&action=create_link&cmd=ffmpeg%20http://localhost/ch/1234_&series=&forced_storage=&disable_ad=0&download=0&JsHttpRequest=1-xml

Cookies: mac, stb_lang, timezone
Headers: Authorization: Bearer {token}

Response:
{
  "js": {
    "cmd": "ffmpeg http://actual-stream-url.com/stream.ts",
    "id": "1234"
  }
}
```

### 6. Get Account Info
```
GET /portal.php?type=account&action=get_main_info&JsHttpRequest=1-xml

Cookies: mac, stb_lang, timezone
Headers: Authorization: Bearer {token}

Response:
{
  "js": {
    "phone": "2026-12-31",  # Expiry date
    "status": 1,
    "mac": "00:1A:79:XX:XX:XX"
  }
}
```

---

## Required Cookies

```python
cookies = {
    "mac": "00:1A:79:XX:XX:XX",
    "stb_lang": "en",
    "timezone": "Europe/London",
    "deviceId": hashlib.sha256(mac.encode()).hexdigest(),
    "deviceId2": hashlib.sha256((mac + "salt").encode()).hexdigest(),
    "serial_number": hashlib.md5(mac.encode()).hexdigest().upper(),
    "sn": hashlib.md5(mac.encode()).hexdigest().upper(),
    "rand": random_16_char_string
}
```

---

## Required Headers

```python
headers = {
    "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Referer": "http://portal-url.com/",
    "X-User-Agent": "Model: MAG200; Link: WiFi; MAC: 00:1A:79:XX:XX:XX",
    "Authorization": "Bearer {token}"  # or "Bearer undefined" for handshake
}
```

---

## Watchdog Timeout Interpretation

```python
if watchdog_timeout < 60:
    # Device is VERY ACTIVE - likely streaming
    status = "BUSY"
elif watchdog_timeout < 300:
    # Device is ACTIVE - some activity
    status = "ACTIVE"
elif watchdog_timeout < 1800:
    # Device is IDLE - minimal activity
    status = "IDLE"
else:
    # Device is INACTIVE - no recent activity
    status = "AVAILABLE"
```

---

## CMD Format

### Live TV Channels
```
ffmpeg http://localhost/ch/CHANNEL_ID_
```

### VOD Content
```
ffmpeg http://localhost/vod/MOVIE_ID.mp4
```

### Series Episodes
```
ffmpeg http://localhost/vod/SERIES_ID_S01E01.mp4
```

**Important:** Always extract CMD from channel/VOD data, don't reconstruct it!

---

## Error Response Format

```json
{
  "js": {
    "error": "Error message",
    "error_code": 403
  }
}
```

### Common Error Codes
- `403` - Token expired or invalid
- `404` - Channel/content not found
- `500` - Server error
- `503` - Service unavailable

---

## Parameter Value Types

### Boolean Parameters
Use string "0" or "1", NOT "false" or "true":
```python
"disable_ad": "0",  # ✅ Correct
"disable_ad": "false",  # ❌ Wrong
```

### Empty Parameters
Use empty string "", NOT "0":
```python
"series": "",  # ✅ Correct for single-part content
"series": "0",  # ❌ Wrong (means first part of multi-part)
```

### Wildcard Parameters
Use "*" for "all":
```python
"genre": "*",  # All genres
"category": "*",  # All categories
```

---

## Session Flow

```
1. HANDSHAKE
   ↓ (get token)
2. GET_PROFILE
   ↓ (check watchdog, get limits)
3. GET_ORDERED_LIST
   ↓ (get channels)
4. CREATE_LINK
   ↓ (get stream URL)
5. STREAM
   ↓ (periodic watchdog updates)
6. GET_PROFILE (every 5 minutes)
   ↓ (update watchdog)
```

---

## Quick Fix Checklist

- [ ] Add `token=` to handshake endpoint
- [ ] Add `hd=1&ver=ImageDescription` to get_profile
- [ ] Change `get_all_channels` to `get_ordered_list`
- [ ] Add `genre=*&fav=0&sortby=number&hd=0` to get_ordered_list
- [ ] Use empty string for `series=` in create_link
- [ ] Use "0"/"1" instead of "false"/"true" for boolean parameters
- [ ] Maintain consistent cookies across all requests
- [ ] Call get_profile before starting stream (watchdog update)
- [ ] Check for error responses in all API calls
- [ ] Persist session per MAC address

---

## Testing Commands

### Test Handshake
```bash
curl -H "Cookie: mac=00:1A:79:00:00:01; stb_lang=en; timezone=Europe/London" \
     -H "Authorization: Bearer undefined" \
     "http://portal.com/portal.php?type=stb&action=handshake&token=&JsHttpRequest=1-xml"
```

### Test Profile
```bash
curl -H "Cookie: mac=00:1A:79:00:00:01; stb_lang=en; timezone=Europe/London" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     "http://portal.com/portal.php?type=stb&action=get_profile&hd=1&ver=ImageDescription&JsHttpRequest=1-xml"
```

### Test Channel List
```bash
curl -H "Cookie: mac=00:1A:79:00:00:01; stb_lang=en; timezone=Europe/London" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     "http://portal.com/portal.php?type=itv&action=get_ordered_list&genre=*&force_ch_link_check=0&fav=0&sortby=number&hd=0&JsHttpRequest=1-xml"
```

---

## Common Mistakes to Avoid

1. ❌ Missing `token=` in handshake
2. ❌ Using `get_all_channels` instead of `get_ordered_list`
3. ❌ Missing `hd=1&ver=ImageDescription` in get_profile
4. ❌ Using "false" instead of "0" for boolean parameters
5. ❌ Reconstructing CMD instead of using from channel data
6. ❌ Not checking watchdog_timeout before streaming
7. ❌ Not updating watchdog when starting stream
8. ❌ Not handling token expiration
9. ❌ Inconsistent cookies across requests
10. ❌ Not persisting session per MAC

---

## Reference Implementation

```python
def stalker_handshake(url, mac):
    """Correct Stalker handshake implementation."""
    cookies = {
        "mac": mac,
        "stb_lang": "en",
        "timezone": "Europe/London"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3",
        "Authorization": "Bearer undefined",
        "X-User-Agent": f"Model: MAG200; Link: WiFi; MAC: {mac}"
    }
    
    response = requests.get(
        f"{url}/portal.php?type=stb&action=handshake&token=&prehash=false&JsHttpRequest=1-xml",
        cookies=cookies,
        headers=headers,
        timeout=10
    )
    
    data = response.json()
    if "js" in data and "token" in data["js"]:
        return data["js"]["token"]
    return None


def stalker_get_profile(url, mac, token):
    """Correct Stalker get_profile implementation."""
    cookies = {
        "mac": mac,
        "stb_lang": "en",
        "timezone": "Europe/London"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3",
        "Authorization": f"Bearer {token}",
        "X-User-Agent": f"Model: MAG200; Link: WiFi; MAC: {mac}"
    }
    
    response = requests.get(
        f"{url}/portal.php?type=stb&action=get_profile&hd=1&ver=ImageDescription&JsHttpRequest=1-xml",
        cookies=cookies,
        headers=headers,
        timeout=10
    )
    
    data = response.json()
    if "js" in data:
        return data["js"]
    return None


def stalker_get_channels(url, mac, token):
    """Correct Stalker get_ordered_list implementation."""
    cookies = {
        "mac": mac,
        "stb_lang": "en",
        "timezone": "Europe/London"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3",
        "Authorization": f"Bearer {token}",
        "X-User-Agent": f"Model: MAG200; Link: WiFi; MAC: {mac}"
    }
    
    response = requests.get(
        f"{url}/portal.php?type=itv&action=get_ordered_list&genre=*&force_ch_link_check=0&fav=0&sortby=number&hd=0&JsHttpRequest=1-xml",
        cookies=cookies,
        headers=headers,
        timeout=30
    )
    
    data = response.json()
    if "js" in data and "data" in data["js"]:
        return data["js"]["data"]
    return None


def stalker_create_link(url, mac, token, cmd):
    """Correct Stalker create_link implementation."""
    from urllib.parse import quote
    
    cookies = {
        "mac": mac,
        "stb_lang": "en",
        "timezone": "Europe/London"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3",
        "Authorization": f"Bearer {token}",
        "X-User-Agent": f"Model: MAG200; Link: WiFi; MAC: {mac}"
    }
    
    # URL encode the CMD
    cmd_encoded = quote(cmd)
    
    response = requests.get(
        f"{url}/portal.php?type=itv&action=create_link&cmd={cmd_encoded}&series=&forced_storage=&disable_ad=0&download=0&JsHttpRequest=1-xml",
        cookies=cookies,
        headers=headers,
        timeout=10
    )
    
    data = response.json()
    if "js" in data and "cmd" in data["js"]:
        # Extract URL from response CMD
        link = data["js"]["cmd"].split()[-1]
        return link
    return None
```

---

**Last Updated:** 2026-02-21  
**Version:** 1.0  
**For:** MacReplayXC v4.2.0
