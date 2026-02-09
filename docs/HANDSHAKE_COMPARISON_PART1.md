# Handshake & Channel Parsing - Detaillierter Vergleich

## 🔍 Übersicht: Wie arbeiten die verschiedenen Projekte?

### 1. **FoxyMACSCANproV3_9** (Python CLI - 4317 Zeilen)

#### Handshake-Prozess:
```python
# URL 1: Handshake (Token holen)
url1 = httpX + panel + "/" + portal_idx + "?type=stb&action=handshake&prehash=false&JsHttpRequest=1-xml"

# URL 2: Get Profile (mit Token)
url2 = httpX + panel + "/" + portal_idx + "?type=stb&action=get_profile&JsHttpRequest=1-xml"

# URL 3: Account Info
url3 = httpX + panel + "/" + portal_idx + "?type=account_info&action=get_main_info&JsHttpRequest=1-xml"
```

#### Header-Struktur:
```python
def hea1(mac, uagent):
    # Header OHNE Token (für Handshake)
    headera = {
        'User-Agent': uagent,
        "Referer": httpX+panell,
        "Accept": "application/json,application/javascript,text/javascript,...",
        "Cookie": f"mac={macs}; stb_lang=en; timezone=Europe/Paris;",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "Keep-Alive",
        'X-Forwarded-For': random_ip,  # Random IP!
        'CF-Connecting-IP': random_ip,
        'X-Real-IP': random_ip
    }


def hea2(mac: str, token: str, portal_idx: str):
    # Header MIT Token (für alle weiteren Requests)
    headerd = {
        'User-Agent': uagentp,
        "Referer": referer,
        "Accept": "application/json,application/javascript,...",
        "Cookie": f"mac={macs}; stb_lang=en; timezone=Europe/Paris;",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "Keep-Alive",
        "X-User-Agent": "Model: MAG254; Link: Ethernet",
        "Authorization": f"Bearer {token}",  # TOKEN HIER!
        "CF-IPCountry": "US",
        "CF-Request-ID": "01GFXQJRYQJ7W0X1VWGV",
        "CF-RAY": "6f3c7b5f9f9f1234",
    }
```

#### Channel & Genre Parsing:
```python
def chlist(listlink, mac, token, livel):
    # Genres/Channels holen
    res = ses.get(listlink, headers=hea2(mac, token, portal_idx), timeout=20)
    veri = str(res.text)
    
    # Parsing: Einfaches String-Splitting
    if veri.count('title":"') > 0:
        for i in veri.split('title":"'):
            kanal = str((i.split('"')[0]).encode('utf-8').decode("unicode-escape"))
            kategori = kategori + kanal + livel
    
    return list
```


#### URLs für Channel-Abfrage:
```python
# Live TV Genres
liveurl = httpX + panel + "/" + portal_idx + "?type=itv&action=get_genres&JsHttpRequest=1-xml"

# VOD Categories
vodurl = httpX + panel + "/" + portal_idx + "?action=get_categories&type=vod&JsHttpRequest=1-xml"

# Series Categories
seriesurl = httpX + panel + "/" + portal_idx + "?action=get_categories&type=series&JsHttpRequest=1-xml"

# Channel Count
url6 = httpX + panel + "/" + portal_idx + "?type=itv&action=get_all_channels&force_ch_link_check=&JsHttpRequest=1-xml"
url7 = httpX + panel + "/" + portal_idx + "?type=itv&action=get_ordered_list&...&p=1&JsHttpRequest=1-xml"
url8 = httpX + panel + "/" + portal_idx + "?type=vod&action=get_ordered_list&...&p=1&JsHttpRequest=1-xml"
url9 = httpX + panel + "/" + portal_idx + "?type=series&action=get_ordered_list&...&p=1&JsHttpRequest=1-xml"
```

#### Scan-Ablauf:
```python
# 1. Handshake (Token holen)
res = ses.get(url1, headers=header__, timeout=5)
veri = str(res.text)

if "token" in veri:
    data = json.loads(veri)
    token = data['js']['token']
    
    # 2. Get Profile (mit Token)
    res = ses.get(url2, headers=hea2(mac, token, portal_idx), timeout=15)
    
    # 3. Account Info
    res = ses.get(url3, headers=hea2(mac, token, portal_idx), timeout=15)
    
    # 4. Channels zählen
    res = ses.get(url6, headers=hea2(mac, token, portal_idx), timeout=15)
    
    # 5. Genres holen
    livelist = chlist(liveurl, mac, token, ' «🔵» ')
    vodlist = chlist(vodurl, mac, token, ' «🔴» ')
    serieslist = chlist(seriesurl, mac, token, ' «🟡» ')
```

---

### 2. **MacAttackWeb-NEW** (Web Scanner - Optimiert)

#### Handshake-Prozess (3-Phasen):
```python
def test_mac(url, mac, proxy=None, timeout=10, compatible_mode=False):
    # PHASE 1: QUICK SCAN (Handshake only)
    handshake_url = f"{base_url}/{portal_type}?action=handshake&type=stb&token=&JsHttpRequest=1-xml"
    resp = do_request(handshake_url, cookies, headers, proxies, timeout)
    
    # Token-Check mit Mode-Selection
    if not token:
        if compatible_mode:
            # MacAttack.pyw: No token = MAC invalid, no retry
            return False, {"mac": mac, "error": "No token"}
        else:
            # Intelligent: Analyze response for retry decision
            if resp.text.strip() == "" or len(resp.text) < 10:
                raise ProxySlowError("Empty response - possible proxy issue")
            # ... weitere Analyse ...
    
    # PHASE 2: QUICK VALIDATION (Channel count)
    ch_url = f"{base_url}/{portal_type}?type=itv&action=get_all_channels&JsHttpRequest=1-xml"
    resp = do_request(ch_url, cookies, headers, proxies, timeout)
    channels_count = len(data["js"]["data"])
    
    if require_channels and channels_count < min_channels:
        return False, {"mac": mac, "error": f"Only {channels_count} channels"}
    
    # PHASE 3: FULL SCAN (All details)
    # ... get_profile, get_main_info, genres, vod, series ...
```
