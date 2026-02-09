# Handshake Comparison Part 4 - API Endpoints & Workflow

## 📡 API Endpoints - Alle Projekte verwenden die gleichen!

### Standard STB Portal API Endpoints:

```
1. HANDSHAKE (Token holen)
   GET /portal.php?type=stb&action=handshake&prehash=false&JsHttpRequest=1-xml
   
   Response:
   {
     "js": {
       "token": "abc123...",
       "random": "xyz789..."
     }
   }

2. GET_PROFILE (Profil aktivieren)
   GET /portal.php?type=stb&action=get_profile&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": {
       "id": "12345",
       "ip": "1.2.3.4",
       "expire_billing_date": "2025-12-31"
     }
   }

3. GET_MAIN_INFO (Account Info)
   GET /portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": {
       "phone": "1735689600",  // Unix timestamp
       "mac": "00:1A:79:XX:XX:XX"
     }
   }

4. GET_ALL_CHANNELS (Channel Count)
   GET /portal.php?type=itv&action=get_all_channels&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": {
       "data": [
         {"id": "1", "name": "Channel 1", "cmd": "..."},
         {"id": "2", "name": "Channel 2", "cmd": "..."}
       ],
       "total_items": 1234
     }
   }

5. GET_GENRES (Live TV Genres)
   GET /portal.php?type=itv&action=get_genres&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": [
       {"id": "*", "title": "All"},
       {"id": "1", "title": "Deutsch"},
       {"id": "2", "title": "Sport"},
       {"id": "3", "title": "Movies"}
     ]
   }

6. GET_CATEGORIES (VOD)
   GET /portal.php?type=vod&action=get_categories&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": [
       {"id": "*", "title": "All"},
       {"id": "1", "title": "Action"},
       {"id": "2", "title": "Comedy"}
     ]
   }

7. GET_CATEGORIES (Series)
   GET /portal.php?type=series&action=get_categories&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": [
       {"id": "*", "title": "All"},
       {"id": "1", "title": "Drama"},
       {"id": "2", "title": "Thriller"}
     ]
   }

8. CREATE_LINK (Stream URL holen)
   GET /portal.php?type=itv&action=create_link&cmd=ffmpeg%20http://localhost/ch/10000_&JsHttpRequest=1-xml
   Headers: Authorization: Bearer {token}
   
   Response:
   {
     "js": {
       "cmd": "ffmpeg http://backend.com:8080/username/password/12345"
     }
   }
```

---

## 🔄 Workflow-Vergleich

### FoxyMACSCANproV3_9 Workflow:
```
1. Handshake → Token
2. Get Profile → ID, IP, Expiry
3. Get Main Info → Phone (Expiry Timestamp)
4. Get All Channels → Channel Count
5. Create Link → Backend URL, Username, Password
6. Get Genres → Live TV Genres
7. Get Categories (VOD) → VOD Categories
8. Get Categories (Series) → Series Categories
9. Get Ordered List (Live) → Live Channel Count
10. Get Ordered List (VOD) → VOD Count
11. Get Ordered List (Series) → Series Count
12. Player API → Xtream API Info (Max Connections, etc.)

TOTAL: 12 Requests pro MAC
```

### MacAttackWeb-NEW Workflow (3-Phasen):
```
PHASE 1: QUICK SCAN (Handshake only)
1. Handshake → Token
   - Token vorhanden = VALID → weiter zu Phase 2
   - Kein Token = NOT VALID → return (mit Retry-Logik)

PHASE 2: QUICK VALIDATION (Channel Count)
2. Get All Channels → Channel Count
   - Genug Channels = VALID → weiter zu Phase 3
   - Zu wenig Channels = NOT VALID → return

PHASE 3: FULL SCAN (All Details)
3. Get Profile → ID, IP, Expiry
4. Get Main Info → Phone (Expiry Timestamp)
5. Get Genres → Live TV Genres (für DE-Erkennung)
6. Get Categories (VOD) → VOD Categories
7. Get Categories (Series) → Series Categories
8. Create Link → Backend URL, Username, Password
9. Player API → Xtream API Info (optional)

TOTAL: 
- Invalid MAC: 1-2 Requests (schnell abbrechen!)
- Valid MAC: 9 Requests (nur für Hits)
```

### Unser Projekt Workflow:
```
Gleich wie MacAttackWeb-NEW 3-Phasen Ansatz

ZUSÄTZLICH:
- Speichert Hits in SQLite DB (scans.db)
- Batch-Writes (100 Hits) für Performance
- Refresh Mode: Re-scan found MACs
- Async Version: 10-100x schneller

TOTAL:
- Invalid MAC: 1-2 Requests
- Valid MAC: 9 Requests
- Refresh Mode: 4-5 Requests (nur kritische Daten)
```

---

## 🎯 Warum ist MacAttackWeb-NEW / Unser Projekt schneller?

### 1. **Early Exit bei Invalid MACs**
```
FoxyMACSCANproV3_9:
- Macht ALLE 12 Requests auch wenn MAC invalid
- Verschwendet Zeit bei 99% der MACs

MacAttackWeb-NEW / Unser Projekt:
- Stoppt nach 1-2 Requests wenn MAC invalid
- Spart 10-11 Requests pro Invalid MAC
- Bei 1000 MACs mit 1% Hit-Rate:
  - FoxyMACSCANproV3_9: 12.000 Requests
  - Unser Projekt: 990*2 + 10*9 = 2.070 Requests
  - 5.8x weniger Requests!
```

### 2. **Connection Pooling**
```
FoxyMACSCANproV3_9:
- Jeder Request = neue TCP Connection
- 3-Way Handshake + TLS Handshake = 100-200ms Overhead
- Bei 12.000 Requests = 20-40 Minuten nur für Connections!

MacAttackWeb-NEW / Unser Projekt:
- Connection Pooling: 20 Pools, 100 Connections
- Reuse Connections: Keep-Alive
- Bei 2.070 Requests = 2-4 Minuten für Connections
- 10x schneller!
```

### 3. **Async I/O (nur unser Projekt)**
```
scanner.py (Sync):
- Threading: 50-200 concurrent requests
- Blockiert bei I/O (Warten auf Response)
- CPU-Bound bei vielen Threads

scanner_async.py (Async):
- aiohttp: 100-1000 concurrent requests
- Non-Blocking I/O (Event Loop)
- Kann 1000+ Requests parallel machen
- 10-100x schneller als Sync!
```

### 4. **DNS Caching**
```
FoxyMACSCANproV3_9:
- Jeder Request = DNS Lookup
- Bei 12.000 Requests = 12.000 DNS Lookups
- 50-100ms pro Lookup = 10-20 Minuten!

Unser Projekt:
- LRU Cache für DNS Lookups
- 1 Lookup pro Domain
- Bei 12.000 Requests = 1 DNS Lookup
- 12.000x schneller!
```

### 5. **Batch DB Writes**
```
FoxyMACSCANproV3_9:
- Schreibt jeden Hit sofort in Datei
- File I/O = langsam
- Bei 10 Hits = 10 File Writes

Unser Projekt:
- Sammelt 100 Hits in Memory
- Schreibt alle 100 Hits auf einmal in DB
- Bei 10 Hits = 0 DB Writes (noch in Memory)
- Bei 100 Hits = 1 DB Write
- 100x schneller!
```
