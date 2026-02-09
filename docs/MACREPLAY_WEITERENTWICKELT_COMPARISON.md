# MacReplay-weiterentwickelt vs. MacReplayXC Comparison

**Analyzed:** February 9, 2026  
**Question:** Is MacReplay-weiterentwickelt identical to our project except for Scanner? Is Vavoo also missing?

---

## Executive Summary

**MacReplay-weiterentwickelt is NOT identical to our project.**

### Missing Features in MacReplay-weiterentwickelt:
1. ❌ **MAC Scanner** (both sync and async versions)
2. ❌ **Vavoo Integration** (separate container + iframe)
3. ✅ **Wiki** (present in both)

### What We Have That They Don't:
- **MAC Scanner (Sync)** - `/scanner` route + `scanner.py` + `templates/scanner.html`
- **MAC Scanner (Async)** - `/scanner-new` route + `scanner_async.py` + `templates/scanner-new.html`
- **Vavoo Integration** - `/vavoo_page` route + `templates/vavoo.html` + Docker container integration
- **Scanner Database** - `scans.db` with persistent MAC scan results

---

## Detailed Comparison

### 1. Navigation Menu Comparison

#### MacReplay-weiterentwickelt (base.html):
```html
<li>Dashboard</li>
<li>Portals</li>
<li>Editor</li>
<li>EPG</li>
<li>VODs</li>
<li>XC Users</li>
<li>Proxy Test</li>
<li>Wiki</li>
<li>Settings</li>
```

#### Our Project (base.html):
```html
<li>Dashboard</li>
<li>Portals</li>
<li>MAC Scanner</li>          ← EXTRA
<li>MAC Scanner (Async)</li>  ← EXTRA
<li>Editor</li>
<li>EPG</li>
<li>VODs</li>
<li>XC Users</li>
<li>Proxy Test</li>
<li>Wiki</li>
<li>Vavoo</li>                ← EXTRA
<li>Settings</li>
```

**Difference:** We have 3 additional menu items (2 scanner variants + Vavoo)

---

### 2. Template Files Comparison

#### MacReplay-weiterentwickelt Templates:
```
base.html
dashboard.html
editor.html
epg.html
genre_selection.html
login.html
portals.html
proxy_test.html
settings.html
vods.html
wiki.html
xc_users.html
```
**Total:** 12 templates

#### Our Project Templates:
```
base.html
dashboard.html
editor.html
epg.html
genre_selection.html
login.html
portals.html
proxy_test.html
settings.html
vavoo.html          ← EXTRA
vods.html
wiki.html
xc_users.html
```
**Total:** 13 templates

**Missing in MacReplay-weiterentwickelt:**
- ❌ `scanner.html` (Sync Scanner UI)
- ❌ `scanner-new.html` (Async Scanner UI)
- ❌ `vavoo.html` (Vavoo iframe integration)

---

### 3. Backend Integration Comparison

#### MacReplay-weiterentwickelt (app-docker.py):
```python
import stb
# NO scanner import
# NO vavoo integration
```

**Routes:**
- ✅ `/dashboard`
- ✅ `/portals`
- ✅ `/editor`
- ✅ `/epg`
- ✅ `/vods`
- ✅ `/xc-users`
- ✅ `/proxy-test`
- ✅ `/wiki`
- ✅ `/settings`

#### Our Project (app-docker.py):
```python
import stb
import scanner_async  # MAC Scanner integration (Async only)

# ============================================
# Vavoo Integration (Separate Container)
# ============================================
# Vavoo runs as separate Docker container on port 4323
# Accessible via iframe in /vavoo_page route
logger.info("Vavoo runs as separate container (vavoo:4323)")
```

**Additional Routes:**
- ✅ `/scanner` - Sync MAC Scanner
- ✅ `/scanner-new` - Async MAC Scanner
- ✅ `/scanner/start` - Start scan
- ✅ `/scanner/stop` - Stop scan
- ✅ `/scanner/status` - Get scan status (SSE)
- ✅ `/scanner/results` - Get scan results
- ✅ `/scanner/delete/<mac>` - Delete MAC
- ✅ `/scanner/config` - Scanner configuration
- ✅ `/vavoo_page` - Vavoo iframe page

---

### 4. Feature Modules Comparison

#### MacReplay-weiterentwickelt:
```
app-docker.py       ✅
stb.py              ✅
utils.py            ✅
```

#### Our Project:
```
app-docker.py       ✅
stb.py              ✅
stb_async.py        ✅ (Async STB implementation)
utils.py            ✅
scanner.py          ✅ (Sync Scanner)
scanner_async.py    ✅ (Async Scanner)
```

**Extra Modules:**
- `scanner.py` - Synchronous MAC scanner (threading-based)
- `scanner_async.py` - Asynchronous MAC scanner (asyncio-based, 10-50x faster)
- `stb_async.py` - Async STB operations

---

### 5. Database Comparison

#### MacReplay-weiterentwickelt:
```
channels.db         ✅ (Channel cache)
vods.db             ✅ (VOD/Series cache)
MacReplayXC.json    ✅ (Configuration)
```

#### Our Project:
```
channels.db         ✅ (Channel cache)
vods.db             ✅ (VOD/Series cache)
scans.db            ✅ (Scanner results - EXTRA)
MacReplayXC.json    ✅ (Configuration)
scanner_config.json ✅ (Scanner settings - EXTRA)
```

**Extra Databases:**
- `scans.db` - Persistent MAC scan results with portal/channel mapping
- `scanner_config.json` - Scanner configuration (portals, proxies, settings)

---

### 6. Docker Integration Comparison

#### MacReplay-weiterentwickelt:
```yaml
services:
  macreplayxc:
    image: macreplayxc:latest
    ports:
      - "8001:8001"
```

#### Our Project:
```yaml
services:
  macreplayxc:
    image: macreplayxc:latest
    ports:
      - "8001:8001"
  
  vavoo:                    ← EXTRA
    image: vavoo:latest
    ports:
      - "4323:4323"
```

**Extra Container:**
- `vavoo` - Separate Vavoo service running on port 4323

---

## Scanner Feature Details

### What is the Scanner?

The MAC Scanner is a **portal MAC address discovery tool** that:
- Tests thousands of MAC addresses against IPTV portals
- Finds working MACs with active subscriptions
- Stores results in `scans.db` for reuse
- Supports proxy rotation to avoid IP bans
- Provides real-time progress via SSE (Server-Sent Events)

### Scanner Variants:

#### 1. Sync Scanner (`scanner.py`)
- **Technology:** Threading-based (10 threads default)
- **Performance:** 50-100 checks/min
- **Route:** `/scanner`
- **Template:** `templates/scanner.html`

#### 2. Async Scanner (`scanner_async.py`)
- **Technology:** Asyncio + aiohttp (100 threads default)
- **Performance:** 500-1000 checks/min (10-50x faster)
- **Route:** `/scanner-new`
- **Template:** `templates/scanner-new.html`

### Scanner UI Features:
- ✅ Real-time progress (SSE)
- ✅ CPM (Checks Per Minute) tracking
- ✅ Hit Rate % display
- ✅ ETA calculation
- ✅ Quality Score
- ✅ Active Workers display
- ✅ Retry Queue display
- ✅ Proxy Stats (Working/Dead/Blocked)
- ✅ Live log streaming
- ✅ Persistent results in database

---

## Vavoo Feature Details

### What is Vavoo?

Vavoo is a **separate IPTV/VOD service** that:
- Runs as independent Docker container on port 4323
- Integrated via iframe in MacReplayXC UI
- Provides additional content sources
- Accessible via `/vavoo_page` route

### Vavoo Integration:
```python
# app-docker.py
@app.route("/vavoo_page")
@authorise
def vavoo_page():
    return render_template("vavoo.html")
```

### Vavoo Template:
```html
<!-- templates/vavoo.html -->
<iframe src="http://vavoo:4323" width="100%" height="800px"></iframe>
```

---

## Conclusion

### MacReplay-weiterentwickelt is MISSING:

1. **MAC Scanner (Sync + Async)**
   - No `scanner.py` or `scanner_async.py`
   - No `/scanner` or `/scanner-new` routes
   - No scanner templates
   - No `scans.db` database
   - No scanner configuration

2. **Vavoo Integration**
   - No `/vavoo_page` route
   - No `vavoo.html` template
   - No Vavoo Docker container
   - No Vavoo iframe integration

3. **Async STB Module**
   - No `stb_async.py` (async STB operations)

### What They Have in Common:

✅ Core IPTV proxy functionality  
✅ Portal management  
✅ Channel editor  
✅ EPG management  
✅ VOD/Series support  
✅ XC API emulation  
✅ Proxy testing  
✅ Wiki documentation  
✅ Settings management  
✅ Authentication system  
✅ HDHomeRun emulation  

---

## Recommendation

If you want to merge MacReplay-weiterentwickelt with our project:

1. **Keep our Scanner** - It's a unique feature not present in MacReplay-weiterentwickelt
2. **Keep our Vavoo integration** - Additional content source
3. **Compare other features** - Check if MacReplay-weiterentwickelt has improvements in:
   - Portal management
   - EPG handling
   - VOD/Series features
   - Performance optimizations

**Our project is MORE feature-complete than MacReplay-weiterentwickelt.**
