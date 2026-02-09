# 📊 DB vs JSON - Analyse für Scanner-Daten

## 🎯 Aktuelle Situation

**Aktuell:** JSON (`scanner_config.json`)
```json
{
  "settings": { ... },
  "found_macs": [
    {"mac": "...", "portal": "...", ...},
    ...
  ],
  "proxies": [...],
  "proxy_sources": [...]
}
```

---

## ⚖️ Vergleich: JSON vs SQLite DB

### 📁 JSON (Aktuell)

#### ✅ Vorteile:
1. **Einfach** - Keine DB-Setup nötig
2. **Portabel** - Eine Datei, easy Backup
3. **Lesbar** - Direkt editierbar
4. **Schnell** - Für kleine Datenmengen (<1000 Hits)
5. **Atomic** - Ganze Datei wird geschrieben
6. **Keine Dependencies** - Python `json` Modul

#### ❌ Nachteile:
1. **Langsam bei vielen Hits** - Ganze Datei laden/schreiben
2. **Keine Queries** - Kein Filter/Sort ohne alles zu laden
3. **Keine Indizes** - Suche ist O(n)
4. **Keine Relationen** - Schwer zu normalisieren
5. **Speicher** - Ganze Datei im RAM
6. **Concurrent Access** - File-Locking problematisch

#### 📊 Performance:
```
100 Hits:    ~1ms read,  ~2ms write   ✅ Gut
1,000 Hits:  ~10ms read, ~20ms write  ✅ OK
10,000 Hits: ~100ms read, ~200ms write ⚠️ Langsam
100,000 Hits: ~1s read, ~2s write     ❌ Zu langsam
```

---

### 🗄️ SQLite DB

#### ✅ Vorteile:
1. **Schnell** - Auch bei vielen Hits (Millionen)
2. **Queries** - SQL Filter/Sort/Group
3. **Indizes** - Schnelle Suche O(log n)
4. **Relationen** - Normalisierte Daten
5. **Partial Load** - Nur benötigte Daten laden
6. **Concurrent Access** - Besseres Locking
7. **Transactions** - ACID-Garantien
8. **Aggregationen** - COUNT, AVG, etc. in DB

#### ❌ Nachteile:
1. **Komplexer** - SQL Schema, Migrations
2. **Weniger portabel** - Binary Format
3. **Nicht editierbar** - Braucht Tools
4. **Overhead** - Für kleine Datenmengen

#### 📊 Performance:
```
100 Hits:    ~1ms read,  ~1ms write   ✅ Gut
1,000 Hits:  ~2ms read,  ~2ms write   ✅ Gut
10,000 Hits: ~5ms read,  ~5ms write   ✅ Gut
100,000 Hits: ~20ms read, ~20ms write ✅ Gut
1,000,000 Hits: ~50ms read, ~50ms write ✅ Gut
```

---

## 🎯 Empfehlung für Scanner

### Wann JSON?
- ✅ **Wenige Hits** (<1000)
- ✅ **Einfachheit** wichtiger als Performance
- ✅ **Portabilität** wichtig
- ✅ **Keine komplexen Queries**

### Wann SQLite DB?
- ✅ **Viele Hits** (>1000)
- ✅ **Komplexe Queries** (Filter, Group, Stats)
- ✅ **Performance** wichtig
- ✅ **Concurrent Access**
- ✅ **Relationen** (z.B. Portal-Tabelle)

---

## 💡 Hybrid-Ansatz (Empfohlen!)

### Struktur:
```
/app/data/
├── scanner_config.json          ← Settings, Proxies, Sources
└── scanner_hits.db              ← Found MACs (SQLite)
```

### Warum Hybrid?
1. **Settings in JSON** - Einfach editierbar
2. **Hits in DB** - Schnelle Queries
3. **Best of Both** - Einfachheit + Performance

---

## 🗄️ DB Schema (Vorschlag)

### Tabelle: `found_macs`
```sql
CREATE TABLE found_macs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac TEXT NOT NULL,
    portal TEXT NOT NULL,
    expiry TEXT,
    channels INTEGER DEFAULT 0,
    has_de BOOLEAN DEFAULT 0,
    backend_url TEXT,
    username TEXT,
    password TEXT,
    max_connections INTEGER,
    created_at TEXT,
    client_ip TEXT,
    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indizes für schnelle Suche
    UNIQUE(mac, portal)
);

CREATE INDEX idx_portal ON found_macs(portal);
CREATE INDEX idx_has_de ON found_macs(has_de);
CREATE INDEX idx_channels ON found_macs(channels);
CREATE INDEX idx_found_at ON found_macs(found_at);
```

### Tabelle: `genres`
```sql
CREATE TABLE genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mac_id INTEGER NOT NULL,
    genre TEXT NOT NULL,
    is_de BOOLEAN DEFAULT 0,
    
    FOREIGN KEY (mac_id) REFERENCES found_macs(id) ON DELETE CASCADE
);

CREATE INDEX idx_mac_id ON genres(mac_id);
CREATE INDEX idx_is_de ON genres(is_de);
```

### Tabelle: `portals` (Optional)
```sql
CREATE TABLE portals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    name TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_hits INTEGER DEFAULT 0
);
```

---

## 📊 Query-Beispiele mit DB

### 1. Filter by Portal
```sql
SELECT * FROM found_macs 
WHERE portal = 'http://portal.com/c'
ORDER BY found_at DESC;
```

### 2. Group by Portal
```sql
SELECT portal, COUNT(*) as hits, AVG(channels) as avg_channels
FROM found_macs
GROUP BY portal
ORDER BY hits DESC;
```

### 3. DE Hits only
```sql
SELECT * FROM found_macs
WHERE has_de = 1
ORDER BY channels DESC;
```

### 4. Min Channels Filter
```sql
SELECT * FROM found_macs
WHERE channels >= 100
ORDER BY found_at DESC;
```

### 5. Stats
```sql
SELECT 
    COUNT(*) as total_hits,
    COUNT(DISTINCT portal) as unique_portals,
    SUM(CASE WHEN has_de = 1 THEN 1 ELSE 0 END) as de_hits,
    AVG(channels) as avg_channels,
    MAX(channels) as max_channels
FROM found_macs;
```

### 6. Top Portals
```sql
SELECT portal, COUNT(*) as hits
FROM found_macs
GROUP BY portal
ORDER BY hits DESC
LIMIT 10;
```

---

## 🚀 Migration: JSON → DB

### Schritt 1: Create DB
```python
import sqlite3

def init_scanner_db():
    conn = sqlite3.connect('/app/data/scanner_hits.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS found_macs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT NOT NULL,
            portal TEXT NOT NULL,
            expiry TEXT,
            channels INTEGER DEFAULT 0,
            has_de BOOLEAN DEFAULT 0,
            backend_url TEXT,
            username TEXT,
            password TEXT,
            max_connections INTEGER,
            created_at TEXT,
            client_ip TEXT,
            found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(mac, portal)
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_portal ON found_macs(portal)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_has_de ON found_macs(has_de)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_channels ON found_macs(channels)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_found_at ON found_macs(found_at)')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_id INTEGER NOT NULL,
            genre TEXT NOT NULL,
            is_de BOOLEAN DEFAULT 0,
            FOREIGN KEY (mac_id) REFERENCES found_macs(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mac_id ON genres(mac_id)')
    
    conn.commit()
    conn.close()
```

### Schritt 2: Migrate Data
```python
def migrate_json_to_db():
    # Load JSON
    with open('/app/data/scanner_config.json', 'r') as f:
        data = json.load(f)
    
    found_macs = data.get('found_macs', [])
    
    # Insert into DB
    conn = sqlite3.connect('/app/data/scanner_hits.db')
    cursor = conn.cursor()
    
    for hit in found_macs:
        cursor.execute('''
            INSERT OR REPLACE INTO found_macs 
            (mac, portal, expiry, channels, has_de, backend_url, username, password, 
             max_connections, created_at, client_ip, found_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            hit['mac'], hit['portal'], hit.get('expiry'), hit.get('channels', 0),
            hit.get('has_de', False), hit.get('backend_url'), hit.get('username'),
            hit.get('password'), hit.get('max_connections'), hit.get('created_at'),
            hit.get('client_ip'), hit.get('found_at')
        ))
        
        mac_id = cursor.lastrowid
        
        # Insert genres
        for genre in hit.get('genres', []):
            is_de = 'DE' in genre.upper() or 'GERMAN' in genre.upper()
            cursor.execute('''
                INSERT INTO genres (mac_id, genre, is_de)
                VALUES (?, ?, ?)
            ''', (mac_id, genre, is_de))
    
    conn.commit()
    conn.close()
```

### Schritt 3: Update Code
```python
def add_found_mac_db(hit_data):
    """Add found MAC to DB"""
    conn = sqlite3.connect('/app/data/scanner_hits.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO found_macs 
        (mac, portal, expiry, channels, has_de, backend_url, username, password, 
         max_connections, created_at, client_ip, found_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        hit_data['mac'], hit_data['portal'], hit_data.get('expiry'),
        hit_data.get('channels', 0), hit_data.get('has_de', False),
        hit_data.get('backend_url'), hit_data.get('username'),
        hit_data.get('password'), hit_data.get('max_connections'),
        hit_data.get('created_at'), hit_data.get('client_ip'),
        hit_data.get('found_at')
    ))
    
    mac_id = cursor.lastrowid
    
    # Insert genres
    cursor.execute('DELETE FROM genres WHERE mac_id = ?', (mac_id,))
    for genre in hit_data.get('genres', []):
        is_de = 'DE' in genre.upper() or 'GERMAN' in genre.upper()
        cursor.execute('''
            INSERT INTO genres (mac_id, genre, is_de)
            VALUES (?, ?, ?)
        ''', (mac_id, genre, is_de))
    
    conn.commit()
    conn.close()

def get_found_macs_db(portal=None, min_channels=0, de_only=False):
    """Get found MACs from DB with filters"""
    conn = sqlite3.connect('/app/data/scanner_hits.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = 'SELECT * FROM found_macs WHERE 1=1'
    params = []
    
    if portal:
        query += ' AND portal = ?'
        params.append(portal)
    
    if min_channels > 0:
        query += ' AND channels >= ?'
        params.append(min_channels)
    
    if de_only:
        query += ' AND has_de = 1'
    
    query += ' ORDER BY found_at DESC'
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    # Convert to dict
    results = []
    for row in rows:
        hit = dict(row)
        
        # Get genres
        cursor.execute('SELECT genre FROM genres WHERE mac_id = ?', (hit['id'],))
        hit['genres'] = [g[0] for g in cursor.fetchall()]
        
        results.append(hit)
    
    conn.close()
    return results
```

---

## 📊 Performance-Vergleich

### Szenario: 10,000 Hits

| Operation | JSON | SQLite | Speedup |
|-----------|------|--------|---------|
| Load All | 100ms | 20ms | **5x** |
| Filter by Portal | 100ms | 2ms | **50x** |
| Filter by Channels | 100ms | 2ms | **50x** |
| Group by Portal | 100ms | 5ms | **20x** |
| Stats (COUNT, AVG) | 100ms | 1ms | **100x** |
| Add Hit | 200ms | 1ms | **200x** |

---

## 🎯 Finale Empfehlung

### Für Scanner: **Hybrid-Ansatz**

```
scanner_config.json:
- settings
- proxies
- proxy_sources

scanner_hits.db:
- found_macs (mit Indizes)
- genres (normalisiert)
- portals (optional)
```

### Warum?
1. ✅ **Settings bleiben einfach** (JSON)
2. ✅ **Hits werden schnell** (DB)
3. ✅ **Komplexe Queries möglich** (SQL)
4. ✅ **Skaliert gut** (Millionen Hits)
5. ✅ **Filter/Group im WebUI** (schnell)

### Wann umstellen?
- **Jetzt**: Wenn du viele Scans planst (>1000 Hits)
- **Später**: Wenn Performance-Probleme auftreten
- **Nie**: Wenn du nur wenige Hits hast (<100)

---

## 🚀 Implementation

Soll ich den Hybrid-Ansatz implementieren?

**Was würde sich ändern:**
1. ✅ Settings bleiben in JSON
2. ✅ Hits gehen in SQLite DB
3. ✅ API bekommt Filter-Parameter
4. ✅ WebUI bekommt schnelle Queries
5. ✅ Migration-Script für bestehende Daten

**Aufwand:** ~2 Stunden
**Benefit:** 10-100x schneller bei vielen Hits

---

**Deine Entscheidung:** JSON behalten oder auf Hybrid umstellen?
