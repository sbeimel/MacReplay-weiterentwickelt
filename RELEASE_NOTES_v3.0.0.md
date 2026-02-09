# MacReplayXC v3.0.0 Release Notes 🎉

**Release Date:** 06. Februar 2026

## 🚀 Major Release - Advanced Caching & Performance

Version 3.0.0 ist ein großes Update mit Fokus auf Performance, Caching und erweiterte Features.

---

## 🆕 Neue Features

### 1. Advanced Channel Cache System ⚡

Das Herzstück von v3.0.0 - ein vollständig neues 4-Modi Cache-System:

**Cache-Modi:**
- **lazy-ram** (Standard): On-demand Caching, minimaler RAM-Verbrauch
- **ram**: Pre-Cache beim Portal-Setup, alle Kanäle im RAM
- **disk**: Pre-Cache auf Disk, persistent über Neustarts
- **hybrid**: RAM + Disk, beste Performance + Persistenz

**Performance:**
- Bis zu **10x schnellere** Channel-Zugriffe
- Persistent über Container-Neustarts (disk/hybrid)
- Flexible Speicherverwaltung

**Konfiguration:**
- Settings → Channel Cache Mode
- Settings → Channel Cache Duration (unlimited/1h/2h/24h)

**Dokumentation:** `docs/CACHE_MANAGEMENT.md` (3.500+ Zeilen)

---

### 2. Intelligentes MAC-Fallback 🎯

Neue Funktion `find_channel_any_mac()` probiert automatisch alle MACs, bis der Channel gefunden wird.

**Problem gelöst:**
- Original: Wenn MAC1 Channel nicht hat, wird MAC1 trotzdem gecached (leer)
- v3.0.0: Probiert alle MACs, cached nur die richtige

**Vorteile:**
- Weniger fehlgeschlagene Streams
- Intelligenteres Caching (besonders bei lazy-ram)
- Bessere Fehlertoleranz

---

### 3. XC API Portal-Filterung mit Namen 🌍

Erweiterte Portal-Filterung - jetzt auch mit Portal-Namen!

**Vorher:**
```
/get.php?username=test&password=test&portal_id=portal_1
```

**Neu:**
```
/get.php?username=test&password=test&portal_id=My%20Portal
```

**Features:**
- Case-insensitive Namenssuche
- Automatische Namensauflösung
- Lesbarer und einfacher zu merken

**Dokumentation:** `docs/XC_API_PORTAL_FILTERING.md` (500+ Zeilen)

---

### 4. Dashboard Cache-Management 🗂️

Neue Dashboard-Funktionen für Cache-Verwaltung:

**Buttons:**
- **Rebuild Cache** (Grün): Lädt alle Kanäle neu von allen Portalen
- **Clear Cache** (Gelb): Löscht kompletten Cache

**Cache-Statistiken Card:**
- Cache Mode (lazy-ram/ram/disk/hybrid)
- RAM Entries (Anzahl gecachter Portale im RAM)
- Disk Entries (Anzahl gecachter Portale auf Disk)
- Total Channels (Gesamtzahl gecachter Kanäle)

**Auto-Update:** Alle 30 Sekunden

---

### 5. MAC-Regionen-Erkennung 🚩

Automatische Erkennung von Regionen basierend auf Genre-Namen:

**Flaggen:**
- 🇩🇪 Deutschland: `DE`, `GER`, `GERMAN`, `DEUTSCH`, `ALEMANGE`
- 🇦🇹 Österreich: `AT`, `AUSTRIA`, `ÖSTERREICH`
- 🇨🇭 Schweiz: `CH`, `SWITZERLAND`, `SCHWEIZ`, `SWISS`

**Anzeige:**
- Portals → Edit Portal → Current MACs → Spalte "Regions"
- Bis zu 3 Flaggen pro MAC

---

### 6. XC API M3U Copy Button 📋

Neuer Button in der Portals-Seite zum Kopieren der XC API M3U URL.

**Features:**
- Automatische XC User Erkennung
- Generiert URL mit Portal-ID
- Generiert URL mit Portal-Name
- Zeigt beide Varianten im Dialog
- Kopiert in Zwischenablage

**Button:** Portals → Portal → [🔗] Button (grün)

---

### 7. Feature Wiki 📚

Neue Wiki-Seite mit vollständiger Feature-Dokumentation:

**Inhalt:**
- Übersicht aller neuen Features
- Detaillierte Erklärungen
- Performance-Vergleichstabelle
- Links zu allen Dokumentationen

**Zugriff:** Navigation → Wiki

---

## 🔧 Verbesserte Features

### EPG-System (9 Verbesserungen)

1. **Raw XML Passthrough** - Alle Metadaten bleiben erhalten
2. **ID-based Matching** - custom_epg_id hat Priorität
3. **M3U/XMLTV Alignment** - 100% Übereinstimmung
4. **Variant Deduplication** - HD/FHD/UHD teilen EPG
5. **Portal EPG Enrichment** - Kategorien, Regisseure, Schauspieler
6. **(lang=) Cleanup** - Entfernt Sprach-Artefakte
7. **Diagnostic Logging** - EPG-Statistiken
8. **No Excess Channels** - Nur enabled Channels in XMLTV
9. **Code Cleanup** - Weniger Variablen, bessere Struktur

**Dokumentation:** `EPG_IMPROVEMENTS_SUMMARY.md` (300+ Zeilen)

---

### Stream-Performance

- Intelligentes MAC-Fallback
- Cache-optimierte Channel-Suche
- Automatische MAC-Auswahl basierend auf Channel-Verfügbarkeit
- Besseres Logging für Debugging

---

### UI/UX

- Cache-Statistiken im Dashboard
- Rebuild/Clear Cache Buttons
- MAC-Regionen-Flaggen
- XC API Copy Button
- Bessere Settings-Gruppierung
- Mehr Tooltips und Hints

---

## 📚 Neue Dokumentation

### 1. CACHE_MANAGEMENT.md (3.500+ Zeilen)
- Cache-Modi im Detail
- Settings-Optionen
- Workflow-Beispiele
- Troubleshooting
- Intelligentes MAC-Fallback

### 2. XC_API_PORTAL_FILTERING.md (500+ Zeilen)
- Portal-Filterung mit ID und Name
- Verwendung in IPTV-Playern
- Best Practices
- Fehlerbehebung

### 3. EPG_IMPROVEMENTS_SUMMARY.md (300+ Zeilen)
- 9 EPG-Verbesserungen dokumentiert
- Technische Details
- Testing-Empfehlungen

### 4. FEATURE_COMPARISON.md
- Detaillierter Vergleich mit Original
- Feature-Liste
- Performance-Messungen
- Empfehlungen

### 5. ORIGINAL_ADVANTAGES.txt
- Was ist im Original besser?
- 10 Bereiche analysiert
- Entscheidungshilfe

---

## 📈 Performance-Verbesserungen

### Cache-System

**Original:**
```
Erster Zugriff: 2-5 Sekunden (API-Call)
Zweiter Zugriff: 2-5 Sekunden (API-Call)
Dritter Zugriff: 2-5 Sekunden (API-Call)
```

**v3.0.0 (lazy-ram):**
```
Erster Zugriff: 2-5 Sekunden (API-Call + Cache)
Zweiter Zugriff: < 0.1 Sekunden (aus Cache)
Dritter Zugriff: < 0.1 Sekunden (aus Cache)
```

**v3.0.0 (hybrid):**
```
Erster Zugriff: < 0.1 Sekunden (aus Cache)
Nach Neustart: < 0.5 Sekunden (aus Disk → RAM)
Alle weiteren: < 0.1 Sekunden (aus RAM)
```

**Ergebnis: Bis zu 10x schnellere Channel-Zugriffe!**

---

## 🐛 Bugfixes

- Syntax-Fehler behoben: `break`/`continue` außerhalb von Schleifen entfernt
- Wiki-Navigation hinzugefügt
- Cache-Logik verbessert

---

## 📊 Statistiken

- **+1.216 Zeilen Code** (+14,8%)
- **+4.000 Zeilen Dokumentation**
- **8 neue Features**
- **3 verbesserte Features**
- **5 neue Dokumentations-Dateien**

---

## 🚀 Upgrade-Anleitung

### Docker (Empfohlen)

```bash
# Container stoppen
docker-compose down

# Neues Image pullen
docker pull registry.gitlab.com/un1x/macreplayxc:3.0.0

# Container starten
docker-compose up -d
```

### Manuell

```bash
# Repository aktualisieren
git pull

# Dependencies aktualisieren
pip install -r requirements.txt

# Anwendung starten
python app-docker.py
```

---

## ⚙️ Neue Einstellungen

Nach dem Update verfügbar unter **Settings**:

### Channel Cache
- **Cache Mode**: lazy-ram / ram / disk / hybrid
- **Cache Duration**: unlimited / 1h / 2h / 24h

**Empfehlung:**
- Produktiv-Systeme: `hybrid` + `unlimited`
- Entwicklung: `lazy-ram` + `1h`
- Minimaler RAM: `disk` + `unlimited`

---

## 🎯 Für wen ist v3.0.0?

### ✅ Ideal für:
- Produktiv-Umgebungen (hybrid Cache)
- Viele Portale/MACs (intelligentes Fallback)
- Performance-kritische Setups (Cache-System)
- Häufige Neustarts (disk/hybrid Persistenz)
- Mehrere Regionen (Flaggen-Erkennung)

### ⚠️ Nicht ideal für:
- Sehr einfache Setups (1 Portal, 1 MAC)
- Systeme mit < 256 MB RAM (bei ram/hybrid)
- Wenn Einfachheit wichtiger als Performance ist

---

## 📖 Weitere Informationen

- **Changelog:** `docs/CHANGELOG.md`
- **Cache-Dokumentation:** `docs/CACHE_MANAGEMENT.md`
- **Portal-Filterung:** `docs/XC_API_PORTAL_FILTERING.md`
- **EPG-Verbesserungen:** `EPG_IMPROVEMENTS_SUMMARY.md`
- **Feature-Vergleich:** `FEATURE_COMPARISON.md`
- **Wiki:** http://your-server:8001/wiki

---

## 🙏 Credits

- **Original:** Un1x
- **v3.0.0 Features:** StiniStinson
- **Community:** Alle Tester und Feedback-Geber

---

## 🐛 Bekannte Probleme

Keine bekannten kritischen Probleme in v3.0.0.

Bei Problemen bitte Issue erstellen mit:
- Log-Ausgabe (`docker-compose logs -f`)
- Cache-Modus und Settings
- Anzahl Portale/MACs

---

## 🔮 Roadmap

Geplant für v3.1.0:
- Web-UI für Cache-Verwaltung
- Cache-Statistiken-Graphen
- Automatische Cache-Optimierung
- Mehr Regionen-Flaggen

---

**Viel Spaß mit MacReplayXC v3.0.0!** 🎉
