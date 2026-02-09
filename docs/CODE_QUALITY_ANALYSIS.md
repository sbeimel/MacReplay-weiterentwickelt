# Code Quality Analysis - MacReplayXC Scanner

**Date**: 2026-02-08  
**Scope**: scanner.py, scanner_async.py, app-docker.py, templates  
**Status**: Gute Qualität mit Verbesserungspotenzial

---

## 📊 GESAMTBEWERTUNG

| Kategorie | Score | Status |
|-----------|-------|--------|
| **Funktionalität** | 9/10 | ✅ Exzellent |
| **Sicherheit** | 7/10 | 🟡 Gut (nach Fixes) |
| **Performance** | 8/10 | ✅ Sehr gut |
| **Wartbarkeit** | 6/10 | 🟡 Akzeptabel |
| **Dokumentation** | 7/10 | 🟡 Gut |
| **Testing** | 4/10 | 🔴 Schwach |
| **GESAMT** | **7.0/10** | 🟡 **Gut** |

---

## ✅ STÄRKEN

### 1. Funktionalität ⭐⭐⭐⭐⭐
- **Vollständiges Feature-Set**: Alle MacAttack-Features implementiert
- **Dual-Scanner**: Sync + Async Versionen
- **SSE Live-Updates**: Echtzeit-Feedback
- **Batch-Writing**: Performance-optimiert
- **Proxy-Scoring**: Intelligente Rotation

### 2. Performance ⭐⭐⭐⭐
- **DNS-Caching**: LRU-Cache für Lookups
- **Connection-Pooling**: HTTP-Session-Reuse
- **Async I/O**: 10-50x schneller als Sync
- **Batch-DB-Writes**: 10-50x schneller als einzeln
- **orjson**: 10x schneller als standard JSON

### 3. Architektur ⭐⭐⭐⭐
- **Separation of Concerns**: Scanner, STB, App getrennt
- **Thread-Safe**: Locks für shared state
- **Resource Management**: Cleanup-Timer
- **Database-First**: Persistent storage

### 4. Dokumentation ⭐⭐⭐⭐
- **Inline-Kommentare**: Gut dokumentiert
- **Docstrings**: Meiste Funktionen haben Docs
- **README-Dateien**: Umfangreiche Dokumentation
- **Fix-Dokumentation**: Alle Änderungen dokumentiert

---

## 🔴 SCHWÄCHEN

### 1. Code-Duplikation ⚠️

**Problem**: scanner.py und scanner_async.py haben ~70% identischen Code

**Beispiele**:
```python
# Beide Dateien haben identische Funktionen:
- calculate_cpm()
- calculate_eta()
- calculate_hit_rate()
- generate_mac()
- generate_neighbor_macs()
- get_cloudflare_headers()
- init_scanner_db()
- get_db_connection()
- load_scanner_config()
- save_scanner_config()
- add_found_mac()
- get_found_macs()
- get_found_macs_stats()
- get_portals_list()
- clear_found_macs()
- get_portals_from_db()
- add_portal_to_db()
- update_portal_in_db()
- delete_portal_from_db()
- get_proxies_from_db()
- add_proxy_to_db()
- update_proxy_stats_in_db()
- delete_proxy_from_db()
- clear_proxies_from_db()
- get_proxy_sources_from_db()
- add_proxy_source_to_db()
- update_proxy_source_in_db()
- delete_proxy_source_from_db()
```

**Impact**:
- Wartungsaufwand verdoppelt
- Fehler müssen zweimal gefixt werden
- Inkonsistenzen möglich

**Lösung**:
```python
# scanner_common.py erstellen
"""
Shared functions for sync and async scanner
"""

def calculate_cpm(state):
    """Calculate Checks Per Minute (CPM)"""
    current_time = time.time()
    elapsed = current_time - state["start_time"]
    
    if elapsed < 1:
        return 0
    
    cpm = (state["tested"] / elapsed) * 60
    return min(int(cpm), 10000)

# ... alle gemeinsamen Funktionen

# In scanner.py und scanner_async.py:
from scanner_common import (
    calculate_cpm,
    calculate_eta,
    calculate_hit_rate,
    # ... etc
)
```

---

### 2. Fehlende Unit-Tests ⚠️

**Problem**: Keine automatisierten Tests vorhanden

**Was fehlt**:
- Unit-Tests für Funktionen
- Integration-Tests für Scanner
- End-to-End-Tests für UI
- Performance-Tests
- Security-Tests

**Impact**:
- Regressions nicht erkennbar
- Refactoring riskant
- Bugs erst in Production

**Lösung**:
```python
# tests/test_scanner_common.py
import pytest
from scanner_common import calculate_cpm, validate_mac

def test_calculate_cpm_zero_elapsed():
    state = {"start_time": time.time(), "tested": 0}
    assert calculate_cpm(state) == 0

def test_calculate_cpm_normal():
    state = {"start_time": time.time() - 60, "tested": 100}
    cpm = calculate_cpm(state)
    assert 90 <= cpm <= 110  # ~100 CPM

def test_calculate_cpm_max_limit():
    state = {"start_time": time.time() - 1, "tested": 100000}
    cpm = calculate_cpm(state)
    assert cpm == 10000  # Max limit

def test_validate_mac_valid():
    assert validate_mac("00:1A:79:00:00:01") == True

def test_validate_mac_invalid():
    assert validate_mac("invalid") == False
    assert validate_mac("00:1A:79") == False
```

---

### 3. Magische Zahlen ⚠️

**Problem**: Hardcoded Werte ohne Konstanten

**Beispiele**:
```python
# scanner.py
if len(state["found_macs"]) > 100:  # Warum 100?
    state["found_macs"] = state["found_macs"][-100:]

time.sleep(1)  # Warum 1 Sekunde?

if elapsed < 1:  # Warum 1?
    return 0

cpm = min(int(cpm), 10000)  # Warum 10000?

MAX_CONCURRENT_SCANS = 10  # OK, aber könnte konfigurierbar sein
```

**Lösung**:
```python
# scanner_config.py
"""Scanner configuration constants"""

# Memory Management
MAX_HITS_IN_MEMORY = 100  # Keep last N hits in memory
MAX_LOGS_IN_MEMORY = 50   # Keep last N logs in memory

# Performance
SSE_UPDATE_INTERVAL = 1.0  # Seconds between SSE updates
MIN_CPM_ELAPSED = 1.0      # Minimum elapsed time for CPM calculation
MAX_CPM_VALUE = 10000      # Maximum CPM value (sanity check)

# Concurrency
MAX_CONCURRENT_SCANS = 10  # Maximum parallel scans
MAX_CONCURRENT_TASKS = 1000  # Maximum async tasks

# Cleanup
CLEANUP_INTERVAL = 300  # Seconds between cleanup runs
CLEANUP_MAX_AGE = 3600  # Remove scans older than N seconds

# SSE
SSE_TIMEOUT = 3600  # SSE connection timeout in seconds

# In scanner.py:
from scanner_config import *

if len(state["found_macs"]) > MAX_HITS_IN_MEMORY:
    state["found_macs"] = state["found_macs"][-MAX_HITS_IN_MEMORY:]
```

---

### 4. Fehlerbehandlung inkonsistent ⚠️

**Problem**: Unterschiedliche Error-Handling-Strategien

**Beispiele**:
```python
# Manchmal try-except mit logging:
try:
    conn = sqlite3.connect(SCANNER_DB_FILE)
    # ...
except Exception as e:
    logger.error(f"Error: {e}")

# Manchmal try-except ohne logging:
try:
    parsed = urlparse(portal_url)
except:
    return False

# Manchmal kein try-except:
def get_next_proxy(self, proxies, portal=None):
    # Kein error handling!
    valid.sort(key=lambda x: x[1])
    # Was wenn valid leer ist?
```

**Lösung**:
```python
# Konsistente Error-Handling-Strategie:

class ScannerError(Exception):
    """Base exception for scanner errors"""
    pass

class DatabaseError(ScannerError):
    """Database operation failed"""
    pass

class ValidationError(ScannerError):
    """Input validation failed"""
    pass

# In Funktionen:
def get_db_connection():
    """Get database connection"""
    try:
        db_dir = os.path.dirname(SCANNER_DB_FILE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(SCANNER_DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except OSError as e:
        logger.error(f"Failed to create database directory: {e}")
        raise DatabaseError(f"Cannot create database directory: {e}")
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database: {e}")
        raise DatabaseError(f"Cannot connect to database: {e}")
```

---

### 5. Lange Funktionen ⚠️

**Problem**: Einige Funktionen sind zu lang (>200 Zeilen)

**Beispiele**:
- `run_scanner_attack()` - ~500 Zeilen
- `run_scanner_attack_async()` - ~400 Zeilen
- `scanner_stream()` - ~100 Zeilen

**Impact**:
- Schwer zu verstehen
- Schwer zu testen
- Schwer zu warten

**Lösung**:
```python
# Aufteilen in kleinere Funktionen:

def run_scanner_attack(attack_id):
    """Main scanner loop"""
    state = get_attack_state(attack_id)
    
    try:
        initialize_scanner(state)
        
        while state["running"]:
            mac = get_next_mac(state)
            if not mac:
                break
            
            result = scan_mac(state, mac)
            handle_scan_result(state, mac, result)
            
            update_metrics(state)
        
        finalize_scanner(state)
    except Exception as e:
        handle_scanner_error(state, e)

def initialize_scanner(state):
    """Initialize scanner state"""
    # ...

def get_next_mac(state):
    """Get next MAC to scan"""
    # ...

def scan_mac(state, mac):
    """Scan a single MAC"""
    # ...

def handle_scan_result(state, mac, result):
    """Handle scan result"""
    # ...

def update_metrics(state):
    """Update performance metrics"""
    # ...

def finalize_scanner(state):
    """Cleanup after scan"""
    # ...
```

---

### 6. Globale Variablen ⚠️

**Problem**: Viele globale Variablen

**Beispiele**:
```python
# scanner.py
scanner_attacks = {}
scanner_attacks_lock = threading.Lock()
scanner_data = {...}
proxy_state = {...}
batch_writer = BatchWriter()
proxy_scorer = ProxyScorer()
```

**Impact**:
- Schwer zu testen
- Nicht thread-safe (trotz Locks)
- Schwer zu mocken

**Lösung**:
```python
# Scanner als Klasse:
class Scanner:
    """Scanner manager"""
    
    def __init__(self, config_file, db_file):
        self.config_file = config_file
        self.db_file = db_file
        self.attacks = {}
        self.attacks_lock = threading.Lock()
        self.data = self._load_config()
        self.proxy_state = {...}
        self.batch_writer = BatchWriter()
        self.proxy_scorer = ProxyScorer()
    
    def start_attack(self, portal_url, mode, **kwargs):
        """Start new scanner attack"""
        # ...
    
    def stop_attack(self, attack_id):
        """Stop scanner attack"""
        # ...
    
    def get_attacks(self):
        """Get all attacks"""
        with self.attacks_lock:
            return list(self.attacks.values())

# In app-docker.py:
scanner = Scanner(SCANNER_CONFIG_FILE, SCANNER_DB_FILE)
scanner_async = AsyncScanner(SCANNER_CONFIG_FILE, SCANNER_DB_FILE)
```

---

## 🟡 VERBESSERUNGSPOTENZIAL

### 7. Type Hints fehlen

**Problem**: Keine Type-Annotations

**Lösung**:
```python
from typing import Dict, List, Optional, Tuple, Any

def calculate_cpm(state: Dict[str, Any]) -> int:
    """Calculate Checks Per Minute (CPM)"""
    current_time: float = time.time()
    elapsed: float = current_time - state["start_time"]
    
    if elapsed < 1:
        return 0
    
    cpm: float = (state["tested"] / elapsed) * 60
    return min(int(cpm), 10000)

def get_found_macs(
    portal: Optional[str] = None,
    min_channels: int = 0,
    de_only: bool = False,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get found MACs from database with optional filters"""
    # ...
```

---

### 8. Logging-Levels inkonsistent

**Problem**: Alles wird als INFO geloggt

**Lösung**:
```python
# Richtige Log-Levels verwenden:
logger.debug(f"Checking MAC: {mac}")  # Debug info
logger.info(f"Scanner started: {attack_id}")  # Important events
logger.warning(f"Proxy failed: {proxy}")  # Warnings
logger.error(f"Database error: {e}")  # Errors
logger.critical(f"Scanner crashed: {e}")  # Critical errors
```

---

### 9. Frontend-Code nicht modular

**Problem**: 1500+ Zeilen JavaScript in einem File

**Lösung**:
```javascript
// scanner-ui.js
class ScannerUI {
    constructor() {
        this.seenHits = new Set();
        this.sseConnection = null;
    }
    
    connectSSE() { /* ... */ }
    updateScannerUI(data) { /* ... */ }
    addHitRow(hit) { /* ... */ }
}

// scanner-api.js
class ScannerAPI {
    async startScan(config) { /* ... */ }
    async stopScan(attackId) { /* ... */ }
    async loadActiveScans() { /* ... */ }
}

// main.js
const ui = new ScannerUI();
const api = new ScannerAPI();
```

---

### 10. Keine Input-Sanitization im Frontend

**Problem**: User-Input wird direkt in HTML eingefügt

**Bereits identifiziert**: Fix 7 (HTML-Escape)

---

## 📈 METRIKEN

### Code-Komplexität:
```
scanner.py:
- Zeilen: 2249
- Funktionen: 45
- Klassen: 2
- Durchschnittliche Funktionslänge: 50 Zeilen
- Längste Funktion: 500 Zeilen (run_scanner_attack)
- Cyclomatic Complexity: Hoch (>20 in main loop)

scanner_async.py:
- Zeilen: 2043
- Funktionen: 42
- Klassen: 2
- Durchschnittliche Funktionslänge: 48 Zeilen
- Längste Funktion: 400 Zeilen (run_scanner_attack_async)
- Cyclomatic Complexity: Hoch (>20 in main loop)

app-docker.py:
- Zeilen: 11162
- Funktionen: 200+
- Klassen: 5
- Durchschnittliche Funktionslänge: 55 Zeilen
```

### Code-Duplikation:
```
scanner.py vs scanner_async.py:
- Identische Funktionen: ~30
- Ähnliche Funktionen: ~10
- Duplikations-Rate: ~70%
```

### Test-Coverage:
```
Unit-Tests: 0%
Integration-Tests: 0%
E2E-Tests: 0%
```

---

## 🎯 EMPFEHLUNGEN (Priorität)

### 🔴 HOCH (sofort):
1. ✅ **Unit-Tests schreiben** - Mindestens für kritische Funktionen
2. ✅ **Code-Duplikation reduzieren** - scanner_common.py erstellen
3. ✅ **Magische Zahlen eliminieren** - Konstanten definieren

### 🟡 MITTEL (bald):
4. ⏳ **Type Hints hinzufügen** - Bessere IDE-Unterstützung
5. ⏳ **Error-Handling vereinheitlichen** - Custom Exceptions
6. ⏳ **Lange Funktionen aufteilen** - Max 100 Zeilen

### 🟢 NIEDRIG (später):
7. ⏳ **Globale Variablen eliminieren** - Scanner als Klasse
8. ⏳ **Logging-Levels korrigieren** - DEBUG/INFO/WARNING/ERROR
9. ⏳ **Frontend modularisieren** - ES6 Modules
10. ⏳ **Dokumentation erweitern** - API-Docs, Architecture-Docs

---

## 📊 VERGLEICH MIT BEST PRACTICES

| Best Practice | Status | Kommentar |
|---------------|--------|-----------|
| **DRY (Don't Repeat Yourself)** | 🔴 Nein | 70% Code-Duplikation |
| **SOLID Principles** | 🟡 Teilweise | Separation OK, aber globale Variablen |
| **Error Handling** | 🟡 Teilweise | Inkonsistent |
| **Testing** | 🔴 Nein | Keine Tests |
| **Documentation** | 🟢 Ja | Gut dokumentiert |
| **Type Safety** | 🔴 Nein | Keine Type Hints |
| **Security** | 🟡 Teilweise | Nach Fixes besser |
| **Performance** | 🟢 Ja | Sehr gut optimiert |
| **Maintainability** | 🟡 Teilweise | Lange Funktionen |
| **Scalability** | 🟢 Ja | Async, Threading, DB |

---

## ✅ POSITIVE ASPEKTE

### Was gut gemacht ist:
1. ✅ **Performance-Optimierungen**: DNS-Cache, Connection-Pool, Batch-Writes
2. ✅ **Async-Support**: Echtes async/await mit aiohttp
3. ✅ **Database-Design**: Gute Schema-Struktur mit Indices
4. ✅ **SSE-Implementation**: Echtzeit-Updates funktionieren
5. ✅ **Proxy-Scoring**: Intelligente Rotation-Logik
6. ✅ **Resource-Management**: Cleanup-Timer, Memory-Limits
7. ✅ **Logging**: Umfangreiches Logging vorhanden
8. ✅ **Dokumentation**: Viele Kommentare und Docstrings

---

## 📝 ZUSAMMENFASSUNG

### Stärken:
- ✅ Funktional vollständig
- ✅ Performance-optimiert
- ✅ Gut dokumentiert
- ✅ Moderne Technologien (async, SSE, SQLite)

### Schwächen:
- 🔴 Keine Tests
- 🔴 Hohe Code-Duplikation
- 🟡 Lange Funktionen
- 🟡 Globale Variablen
- 🟡 Keine Type Hints

### Gesamtbewertung:
**7.0/10 - Gut**

Der Code ist funktional und performant, aber hat Verbesserungspotenzial in Wartbarkeit und Testbarkeit.

---

**Empfehlung**: 
1. Sofort: Tests schreiben, Code-Duplikation reduzieren
2. Mittelfristig: Refactoring für bessere Wartbarkeit
3. Langfristig: Type Hints, Modularisierung

**Status**: 🟢 Production-Ready, aber Refactoring empfohlen

