# 🚀 DEPLOYMENT CHECKLIST

**Datum**: 2026-02-08  
**Version**: 2.5.0  
**Status**: Bereit für Deployment

---

## ✅ PRE-DEPLOYMENT CHECKLIST

### Code & Tests
- [x] Alle Features implementiert
- [x] Syntax-Tests bestanden
- [x] Unit-Tests bestanden (5/5)
- [x] Keine Python-Fehler
- [x] Keine JavaScript-Fehler
- [x] Dokumentation vollständig

### Dateien
- [x] templates/scanner.html aktualisiert
- [x] templates/scanner-new.html aktualisiert
- [x] app-docker.py aktualisiert
- [x] Sortable.js CDN eingebunden
- [x] Alle neuen Routes implementiert

### Features
- [x] Portal Management funktioniert
- [x] Pattern Generator funktioniert
- [x] Scheduler funktioniert
- [x] Backend Routes funktionieren
- [x] Auto-Initialisierung funktioniert

---

## 🐳 DOCKER BUILD

### Schritt 1: Build Image
```bash
docker build -t macreplayxc:2.5.0 .
```

**Erwartetes Ergebnis**:
- Build erfolgreich ohne Fehler
- Image erstellt: `macreplayxc:2.5.0`

### Schritt 2: Run Container
```bash
docker run -d \
  --name macreplayxc \
  -p 8001:8001 \
  -v $(pwd)/data:/app/data \
  macreplayxc:2.5.0
```

**Erwartetes Ergebnis**:
- Container startet ohne Fehler
- Port 8001 ist erreichbar
- Logs zeigen "Scheduler started"
- Logs zeigen "Pattern Generator patterns loaded"

### Schritt 3: Check Logs
```bash
docker logs macreplayxc
```

**Erwartete Log-Einträge**:
```
[INFO] MAC Scanner Scheduler started
[INFO] MAC Pattern Generator patterns loaded
[INFO] Starting Waitress server on 0.0.0.0:8001
```

---

## 🧪 FUNCTIONAL TESTS

### Test 1: Scanner-Seite laden
```
URL: http://localhost:8001/scanner
Erwartung: Seite lädt ohne Fehler
```

**Checklist**:
- [ ] Seite lädt in <3 Sekunden
- [ ] Keine JavaScript-Fehler in Konsole
- [ ] Alle 7 Tabs sichtbar
- [ ] Sortable.js geladen (keine 404)

### Test 2: Portal Management
```
Tab: Portal Management
```

**Checklist**:
- [ ] Tab öffnet ohne Fehler
- [ ] "Add Portal" Button funktioniert
- [ ] Portal-Dialog erscheint
- [ ] Portal wird zur Liste hinzugefügt
- [ ] Portal kann bearbeitet werden
- [ ] Portal kann gelöscht werden
- [ ] Drag & Drop funktioniert
- [ ] Kategorien werden aktualisiert

### Test 3: Pattern Generator
```
Tab: Pattern Generator
```

**Checklist**:
- [ ] Tab öffnet ohne Fehler
- [ ] Statistics zeigen 0 MACs
- [ ] "Learn from Found MACs" Button funktioniert
- [ ] "Generate Candidates" Button funktioniert
- [ ] Strategy Dropdown funktioniert
- [ ] Count Input funktioniert
- [ ] Auto-Scan Checkbox funktioniert
- [ ] Kandidaten werden angezeigt

### Test 4: Scheduler
```
Tab: Scheduler
```

**Checklist**:
- [ ] Tab öffnet ohne Fehler
- [ ] Status zeigt "Running"
- [ ] "Add Job" Button funktioniert
- [ ] Job-Dialog erscheint
- [ ] Job wird zur Liste hinzugefügt
- [ ] Toggle funktioniert
- [ ] Job kann gelöscht werden
- [ ] Statistics werden aktualisiert

### Test 5: Integration
```
Alle Features zusammen
```

**Checklist**:
- [ ] Portal Management → Portal zu Scanner ziehen
- [ ] Pattern Generator → Kandidaten in Scanner laden
- [ ] Scheduler → Job mit Portal erstellen
- [ ] Alle Features funktionieren parallel
- [ ] Keine Konflikte zwischen Features

---

## 🔍 BACKEND API TESTS

### Pattern Generator API
```bash
# Learn
curl -X POST http://localhost:8001/scanner/pattern/learn

# Generate
curl -X POST http://localhost:8001/scanner/pattern/generate \
  -H "Content-Type: application/json" \
  -d '{"strategy":"mixed","count":10}'

# Stats
curl http://localhost:8001/scanner/pattern/stats
```

**Erwartung**: Alle Requests geben JSON mit `"success": true` zurück

### Scheduler API
```bash
# Get Jobs
curl http://localhost:8001/scanner/scheduler/jobs

# Add Job
curl -X POST http://localhost:8001/scanner/scheduler/add \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Test Job",
    "portal_url":"http://test.com/c",
    "mac_list":["00:1A:79:00:00:01"],
    "schedule_time":"00:00",
    "repeat":"daily"
  }'

# Toggle Job
curl -X POST http://localhost:8001/scanner/scheduler/toggle \
  -H "Content-Type: application/json" \
  -d '{"job_id":"job_1","enabled":false}'

# Delete Job
curl -X POST http://localhost:8001/scanner/scheduler/delete \
  -H "Content-Type: application/json" \
  -d '{"job_id":"job_1"}'
```

**Erwartung**: Alle Requests geben JSON mit `"success": true` zurück

---

## 💾 DATA PERSISTENCE TESTS

### Test 1: Portal Persistence
```
1. Füge Portal hinzu
2. Schließe Browser
3. Öffne Browser neu
4. Gehe zu Portal Management
Erwartung: Portal ist noch da
```

### Test 2: Pattern Persistence
```
1. Learn from Found MACs
2. Stoppe Container
3. Starte Container neu
4. Gehe zu Pattern Generator
Erwartung: Statistics zeigen gelernte MACs
```

### Test 3: Scheduler Persistence
```
1. Füge Job hinzu
2. Stoppe Container
3. Starte Container neu
4. Gehe zu Scheduler
Erwartung: Job ist noch da
```

---

## 🐛 TROUBLESHOOTING

### Problem: Sortable.js lädt nicht
**Lösung**: Prüfe Internet-Verbindung, CDN erreichbar?

### Problem: Backend Routes geben 404
**Lösung**: Prüfe ob app-docker.py korrekt geladen wurde

### Problem: Scheduler startet nicht
**Lösung**: Prüfe Logs, `scanner_scheduler.py` vorhanden?

### Problem: Pattern Generator zeigt Fehler
**Lösung**: Prüfe ob `mac_pattern_generator.py` vorhanden

### Problem: localStorage funktioniert nicht
**Lösung**: Prüfe Browser-Einstellungen, Cookies erlaubt?

---

## 📊 PERFORMANCE TESTS

### Test 1: Page Load Time
```
Erwartung: <3 Sekunden
```

### Test 2: Tab Switch Time
```
Erwartung: <500ms
```

### Test 3: Portal Add Time
```
Erwartung: <100ms
```

### Test 4: Pattern Generation Time
```
Erwartung: <2 Sekunden für 100 MACs
```

### Test 5: Scheduler Job Add Time
```
Erwartung: <500ms
```

---

## ✅ FINAL CHECKLIST

### Pre-Deployment
- [x] Code vollständig
- [x] Tests bestanden
- [x] Dokumentation erstellt

### Deployment
- [ ] Docker Build erfolgreich
- [ ] Container läuft
- [ ] Logs zeigen keine Fehler

### Functional Tests
- [ ] Scanner-Seite lädt
- [ ] Portal Management funktioniert
- [ ] Pattern Generator funktioniert
- [ ] Scheduler funktioniert
- [ ] Integration funktioniert

### API Tests
- [ ] Pattern Generator API funktioniert
- [ ] Scheduler API funktioniert

### Persistence Tests
- [ ] Portal Persistence funktioniert
- [ ] Pattern Persistence funktioniert
- [ ] Scheduler Persistence funktioniert

### Performance Tests
- [ ] Page Load <3s
- [ ] Tab Switch <500ms
- [ ] Features responsive

---

## 🎉 DEPLOYMENT COMPLETE

Wenn alle Checkboxen markiert sind:

✅ **DEPLOYMENT ERFOLGREICH!**

Die neuen Features sind jetzt live und einsatzbereit!

---

## 📝 POST-DEPLOYMENT

### Monitoring
- Überwache Logs für Fehler
- Prüfe Scheduler läuft korrekt
- Prüfe Pattern Generator funktioniert

### User Feedback
- Sammle Feedback zu neuen Features
- Dokumentiere Bugs
- Plane Verbesserungen

### Backup
- Sichere `data/mac_patterns.json`
- Sichere `data/scheduled_jobs.json`
- Sichere Portal-Liste (localStorage)

---

**Viel Erfolg beim Deployment!** 🚀

