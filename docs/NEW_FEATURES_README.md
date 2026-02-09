# 🎉 Neue Scanner Features

**Version**: 2.5.0  
**Datum**: 2026-02-08

---

## 🆕 Was ist neu?

3 neue Features wurden zum MAC Scanner hinzugefügt:

### 1. 📋 Portal Management
Verwalte deine Portale mit Drag & Drop!

**Features**:
- Portal-Liste speichern
- Portale per Drag & Drop sortieren
- Portale per Drag & Drop in Scanner ziehen
- Kategorien: Active, Testing, Favorites
- Persistent über Browser-Neustarts

**Verwendung**:
1. Gehe zu Scanner → Portal Management Tab
2. Klicke "Add Portal"
3. Gebe Name, URL und optional Category ein
4. Portal erscheint in Liste
5. Ziehe Portal auf "Portal URL" Feld zum Verwenden

---

### 2. 🧠 Pattern Generator
Lerne von erfolgreichen MACs und generiere ähnliche!

**Features**:
- Patterns von gefundenen MACs lernen
- 4 Generierungs-Strategien: Mixed, Prefix, Sequential, Gap
- Statistics Dashboard
- Auto-Scan Option
- Kandidaten direkt in Scanner laden

**Verwendung**:
1. Gehe zu Scanner → Pattern Generator Tab
2. Klicke "Learn from Found MACs"
3. Wähle Strategy und Count
4. Klicke "Generate Candidates"
5. Klicke "Scan These MACs" oder aktiviere Auto-Scan

**Strategien**:
- **Mixed**: Kombination aller Strategien (empfohlen)
- **Prefix**: Verwendet häufige Prefixes (OUI)
- **Sequential**: Generiert sequentielle MACs
- **Gap**: Verwendet häufige Abstände zwischen MACs

---

### 3. ⏰ Scheduler
Automatische Scans zu geplanten Zeiten!

**Features**:
- Jobs mit Cron-like Scheduling
- Repeat: once, hourly, daily, weekly
- Enable/Disable Jobs
- Job Statistics (Success/Fail/Total)
- Next Run Time Anzeige

**Verwendung**:
1. Gehe zu Scanner → Scheduler Tab
2. Klicke "Add Job"
3. Gebe Name, Portal, MACs, Schedule, Repeat ein
4. Job erscheint in Liste
5. Toggle zum Aktivieren/Deaktivieren
6. Jobs laufen automatisch zur geplanten Zeit

**Schedule Format**:
- `00:00` = Mitternacht
- `12:00` = Mittag
- `18:30` = 18:30 Uhr

**Repeat Optionen**:
- `once` = Einmalig
- `hourly` = Jede Stunde
- `daily` = Jeden Tag
- `weekly` = Jede Woche

---

## 🎨 UI Übersicht

### Scanner Tabs (7 total)
1. **Scan** - Scan starten
2. **Settings** - Einstellungen
3. **Proxies** - Proxy-Verwaltung
4. **Found MACs** - Gefundene MACs
5. **Portal Management** ⭐ NEU
6. **Pattern Generator** ⭐ NEU
7. **Scheduler** ⭐ NEU

---

## 💡 Tipps & Tricks

### Portal Management
- Organisiere Portale nach Kategorien
- Markiere häufig verwendete als "Favorites"
- Nutze Drag & Drop für schnellen Zugriff

### Pattern Generator
- Sammle erst 50+ MACs, dann Patterns lernen
- "Mixed" Strategy liefert beste Ergebnisse
- Auto-Scan spart Zeit

### Scheduler
- Plane Scans für Nacht-Zeiten
- Verschiedene Portale zu verschiedenen Zeiten
- Überwache Success/Fail Statistics

---

## 🔧 Technische Details

### Datenspeicherung
- **Portal-Liste**: localStorage (Browser)
- **Patterns**: `data/mac_patterns.json` (Server)
- **Jobs**: `data/scheduled_jobs.json` (Server)

### Backend API
- Pattern Generator: `/scanner/pattern/*`
- Scheduler: `/scanner/scheduler/*`

### Externe Libraries
- Sortable.js für Drag & Drop

---

## 📊 Beispiele

### Portal Management
```
Portal 1: "Main Portal"
URL: http://portal.com/c
Category: Active

Portal 2: "Test Portal"
URL: http://test.com/stalker
Category: Testing
```

### Pattern Generator
```
Learned MACs: 150
Unique Prefixes: 10
Strategy: Mixed
Generated: 100 candidates
```

### Scheduler
```
Job: "Daily Scan"
Portal: http://portal.com/c
MACs: 00:1A:79:00:00:01, ...
Schedule: 00:00 (daily)
Status: ✓ 45 success | ✗ 2 failed
```

---

## ❓ FAQ

**Q: Wo werden Portale gespeichert?**  
A: Im Browser localStorage - persistent über Neustarts.

**Q: Wie viele Kandidaten kann ich generieren?**  
A: 10-1000 MACs pro Generation.

**Q: Können Jobs parallel laufen?**  
A: Ja, mehrere Jobs können gleichzeitig aktiv sein.

**Q: Was passiert wenn der Server neustartet?**  
A: Patterns und Jobs werden automatisch geladen.

**Q: Kann ich Portale zwischen Browsern teilen?**  
A: Nein, Portale sind browser-spezifisch (localStorage).

---

## 🐛 Troubleshooting

**Portal Management funktioniert nicht**:
- Prüfe Browser-Konsole auf Fehler
- Stelle sicher dass localStorage aktiviert ist
- Lösche Browser-Cache und versuche erneut

**Pattern Generator zeigt 0 MACs**:
- Erst MACs finden, dann "Learn" klicken
- Prüfe ob `data/mac_patterns.json` existiert

**Scheduler Jobs laufen nicht**:
- Prüfe ob Job aktiviert ist (Toggle)
- Prüfe Next Run Time
- Prüfe Server-Logs für Fehler

---

## 📝 Changelog

### Version 2.5.0 (2026-02-08)
- ✅ Portal Management mit Drag & Drop
- ✅ Pattern Generator UI
- ✅ Scheduler UI
- ✅ Sortable.js Integration
- ✅ 7 neue Backend Routes
- ✅ Auto-Initialisierung

---

## 🚀 Weitere Informationen

- **Vollständige Dokumentation**: `FRONTEND_FEATURES_IMPLEMENTATION_COMPLETE.md`
- **Implementation Details**: `ALL_FEATURES_IMPLEMENTED_2026-02-08.md`
- **Test Suite**: `test_new_features.py`

---

**Viel Spaß mit den neuen Features!** 🎉

