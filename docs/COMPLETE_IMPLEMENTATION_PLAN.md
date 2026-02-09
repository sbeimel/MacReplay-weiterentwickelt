# 🚀 VOLLSTÄNDIGE IMPLEMENTIERUNG - Plan

## ✅ ERLEDIGT

### 1. Neighbor Range auf 20 erhöht
- ✅ scanner.py: Default 5 → 20
- ✅ scanner_async.py: Default 5 → 20  
- ✅ scanner.html: Max 20 → 50, Default 20
- ✅ scanner-new.html: Max 20 → 50, Default 20

---

## 📋 NOCH ZU TUN

### 2. Portal Management mit Drag & Drop (2-3h)
**Dateien**: 
- `templates/scanner.html` - Portal Management Tab
- `templates/scanner-new.html` - Portal Management Tab
- `app-docker.py` - Backend Endpoints

**Features**:
- Portal-Liste speichern (localStorage + DB)
- Drag & Drop (Sortable.js)
- Add/Edit/Delete Portale
- Kategorien
- Drag to Scanner

### 3. Pattern Generator UI (2h)
**Dateien**:
- `templates/scanner.html` - Pattern Generator Sektion
- `templates/scanner-new.html` - Pattern Generator Sektion
- `app-docker.py` - Backend Endpoints für Pattern Generator

**Features**:
- Learn from Found MACs Button
- Statistics Anzeige
- Generate Candidates
- Strategy Auswahl
- Integration in Scan-Start

### 4. Scheduler UI (2h)
**Dateien**:
- `templates/scanner.html` - Scheduler Tab
- `templates/scanner-new.html` - Scheduler Tab
- `app-docker.py` - Backend Endpoints für Scheduler

**Features**:
- Job Liste
- Add/Edit/Delete Jobs
- Cron Schedule UI
- Enable/Disable
- Job Statistics

### 5. Database Statistics Fix (1h)
**Problem**: Cached Channels bleibt bei 0

**Zu prüfen**:
- Channel Caching Logik
- DB Schema
- Statistics Berechnung
- Session Management

### 6. Sessions Analyse (1h)
**Zu prüfen**:
- Session Leaks
- Session Refresh
- Session Pooling
- Memory Usage

### 7. WebUI Wiki Update (1h)
**Zu erstellen**:
- Vollständige Feature-Dokumentation
- Settings-Guide
- Tipps & Tricks
- Troubleshooting

---

## 🎯 PRIORITÄT

**JETZT** (Kritisch):
1. Database Statistics Fix
2. Sessions Analyse

**DANACH** (Wichtig):
3. Portal Management
4. Pattern Generator UI
5. Scheduler UI

**ZULETZT** (Dokumentation):
6. WebUI Wiki Update

---

**Geschätzter Aufwand**: 10-12 Stunden
**Status**: In Arbeit
