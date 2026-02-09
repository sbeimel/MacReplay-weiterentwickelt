# 📁 STB.PY DATEIEN ÜBERSICHT

**Datum**: 2026-02-07  
**Frage**: Welche stb.py wird wo verwendet?

---

## 🎯 KLARE ANTWORT

Es gibt **5 verschiedene stb.py Dateien**, aber nur **EINE wird aktiv genutzt**:

### ✅ AKTIV GENUTZT (Root Projekt):

```
./stb.py  (1944 Zeilen)
```

**Verwendet von:**
- ✅ `app-docker.py` (Zeile 269: `import stb`)
- ✅ `scanner.py` (Zeile 24: `import stb`)
- ✅ `scanner_async.py` (indirekt über scanner.py)

**Features:**
- MacReplayXC Version (erweitert)
- Cloudflare Bypass Support (cloudscraper)
- Shadowsocks Proxy Support
- Session Management mit Auto-Refresh
- Multi-Endpoint Support (portal.php, load.php, etc.)
- Enhanced Cookies & Headers
- MAG250/MAG254/MAG420 Fallbacks
- Proxy-Type Detection (HTTP, SOCKS5, Shadowsocks)

---

## 📦 NICHT GENUTZT (Andere Projekte):

### 1. MacAttackWeb-NEW/stb.py (657 Zeilen)
```
./MacAttackWeb-NEW/stb.py
```
- **Status**: ❌ Nicht verwendet im Root Projekt
- **Zweck**: Separate MacAttackWeb-NEW Installation
- **Features**: Optimiert für Speed, Connection Pooling, 2-Phase Scan

### 2. andere sources/MacAttackWeb-NEW/stb.py
```
./andere sources/MacAttackWeb-NEW/stb.py
```
- **Status**: ❌ Nicht verwendet (Backup/Referenz)
- **Zweck**: Kopie für Analyse

### 3. andere sources/MacReplay-weiterentwickelt/stb.py
```
./andere sources/MacReplay-weiterentwickelt/stb.py
```
- **Status**: ❌ Nicht verwendet (Backup/Referenz)
- **Zweck**: Ältere Version für Vergleich

### 4. andere sources/MacReplay-rpi/stb.py
```
./andere sources/MacReplay-rpi/stb.py
```
- **Status**: ❌ Nicht verwendet (Backup/Referenz)
- **Zweck**: Raspberry Pi optimierte Version

---

## 🔍 IMPORT CHAIN

```
app-docker.py
    ↓
import stb  ← ./stb.py (ROOT)
    ↓
scanner.py
    ↓
import stb  ← ./stb.py (ROOT)
    ↓
scanner_async.py
    ↓
stb.getToken()  ← ./stb.py (ROOT)
stb.getProfile()  ← ./stb.py (ROOT)
stb.getAllChannels()  ← ./stb.py (ROOT)
```

**Python Import Regel:**
- `import stb` sucht IMMER zuerst im aktuellen Verzeichnis
- Da `app-docker.py` im Root liegt → `./stb.py` wird verwendet
- Da `scanner.py` im Root liegt → `./stb.py` wird verwendet

---

## ⚠️ WICHTIG: KEINE VERWECHSLUNGSGEFAHR!

### Warum keine Konflikte?

1. **Root Projekt** nutzt `./stb.py`
2. **MacAttackWeb-NEW/** ist ein **separates Projekt** mit eigener `stb.py`
3. **andere sources/** sind **Backups/Referenzen** (nicht im Python Path)

### Wenn du Änderungen machst:

✅ **SICHER**: `./stb.py` ändern (Root)
- Betrifft: app-docker.py, scanner.py, scanner_async.py
- Keine Auswirkung auf andere Projekte

❌ **NICHT ÄNDERN**: `MacAttackWeb-NEW/stb.py`
- Ist separates Projekt
- Wird nicht vom Root Projekt verwendet

❌ **NICHT ÄNDERN**: `andere sources/*/stb.py`
- Sind Backups/Referenzen
- Werden nirgends importiert

---

## 📊 DATEI VERGLEICH

| Datei | Zeilen | Version | Verwendet? |
|-------|--------|---------|------------|
| `./stb.py` | 1944 | MacReplayXC v3.1.0 | ✅ **JA** |
| `MacAttackWeb-NEW/stb.py` | 657 | MacAttackWeb v2.0 | ❌ Nein (separates Projekt) |
| `andere sources/.../stb.py` | Variiert | Verschiedene | ❌ Nein (Backups) |

---

## 🔧 WENN DU FIXES MACHST

### Für Scanner Fixes (Error-Handling, etc.):

**NUR DIESE DATEI ÄNDERN:**
```bash
./stb.py  # ← ROOT stb.py
```

**Beispiel Fix:**
```python
# In ./stb.py
def getAllChannels(url, mac, token, proxy=None):
    try:
        # ... code ...
        channels = response.json()["js"]["data"]
        return channels if channels else []  # ✅ FIX
    except Exception as e:
        logger.error(f"Error: {e}")
        return []  # ✅ FIX (statt None)
```

### Andere Dateien NICHT anfassen:
- ❌ `MacAttackWeb-NEW/stb.py` (separates Projekt)
- ❌ `andere sources/*/stb.py` (Backups)

---

## 🎯 ZUSAMMENFASSUNG

**Eine einfache Regel:**

> **Alle Änderungen an `./stb.py` (Root)**
> 
> Alle anderen stb.py Dateien sind entweder:
> - Separate Projekte (MacAttackWeb-NEW/)
> - Backups/Referenzen (andere sources/)

**Keine Verwechslungsgefahr!** Python importiert automatisch die richtige Datei.

---

## 🚨 WICHTIGE HINWEISE

### 1. Python Import Priorität:
```python
import stb  # Sucht in dieser Reihenfolge:
# 1. Aktuelles Verzeichnis (./stb.py) ← WIRD VERWENDET
# 2. Python Path
# 3. Site-packages
```

### 2. Separate Projekte:
- `MacAttackWeb-NEW/` hat eigene `app.py` die eigene `stb.py` importiert
- Komplett unabhängig vom Root Projekt
- Keine Überschneidungen

### 3. Backups in "andere sources/":
- Sind NICHT im Python Path
- Werden nirgends importiert
- Nur für Referenz/Vergleich

---

## ✅ FAZIT

**Du kannst sicher `./stb.py` (Root) ändern!**

- ✅ Betrifft nur das Root Projekt
- ✅ Keine Auswirkung auf MacAttackWeb-NEW
- ✅ Keine Auswirkung auf Backups
- ✅ Scanner nutzt diese Datei
- ✅ app-docker.py nutzt diese Datei

**Keine Sorge vor Überschreiben!** Jedes Projekt hat seine eigene stb.py.
