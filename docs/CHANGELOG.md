# Änderungen (Changelog)

### [v3.0.0] - 06.02.2026 🎉

#### 🆕 Neue Features

**Advanced Channel Cache System**
- 4 Cache-Modi: lazy-ram, ram, disk, hybrid
- Bis zu 10x schnellere Channel-Zugriffe
- Persistent über Container-Neustarts (disk/hybrid)
- Intelligentes MAC-Fallback mit `find_channel_any_mac()`
- Konfigurierbare Cache-Duration (unlimited, 1h, 2h, 24h)

**Dashboard Cache-Management**
- Rebuild Cache Button (lädt alle Kanäle neu)
- Clear Cache Button (löscht kompletten Cache)
- Live Cache-Statistiken (RAM/Disk Entries, Total Channels)
- Auto-Update alle 30 Sekunden

**XC API Portal-Filterung mit Namen**
- Filterung nach Portal-ID ODER Portal-Name
- Case-insensitive Namenssuche
- Beispiel: `&portal_id=My%20Portal`

**MAC-Regionen-Erkennung**
- Automatische Flaggen-Anzeige (🇩🇪🇦🇹🇨🇭)
- Basierend auf Genre-Namen
- Anzeige in Portal-MAC-Tabelle

**XC API M3U Copy Button**
- Schnelles Kopieren der XC API URLs
- Zeigt beide Varianten (ID + Name)
- Automatische XC User Erkennung

**Feature Wiki**
- Neue Wiki-Seite mit allen Features
- Performance-Vergleichstabelle
- Links zu allen Dokumentationen
- Erreichbar über Navigation

#### ⚡ Performance-Optimierungen

**Python 3.13 Upgrade**
- Python: 3.11 → 3.13 (+5-15% Performance)
- Experimenteller JIT-Compiler (bis zu +30% bei rechenintensiven Tasks)
- Free-Threading Mode (No-GIL) für bessere Parallelisierung
- 7% kleinerer Memory Footprint
- Bessere Error Messages und Debugging

**Waitress Server**
- Threads: 24 → 48 (+100% Concurrent Requests)
- Channel Timeout: 2048s → 8192s (+400% für lange Streams)
- Buffer-Größe: 256KB → 1MB (+300%)
- Connection Limit: 1000 concurrent connections
- asyncore_use_poll: Bessere Performance als select()

**Fast JSON Parsing**
- orjson Support (10x schneller als standard json)
- ujson Fallback (5x schneller als standard json)
- Automatische Auswahl der schnellsten Bibliothek

**Aktualisierte Dependencies**
- Flask: 3.0.0 → 3.1.0
- Werkzeug: → 3.1.3 (neu)
- waitress: 3.0.0 → 3.0.2
- requests: 2.31.0 → 2.32.3
- urllib3: 2.0.7 → 2.2.3
- cryptography: 3.4.8 → 43.0.3
- pycryptodome: 3.15.0 → 3.21.0
- pytest: 7.4.0 → 8.3.4
- cloudscraper: 1.2.71 (Python 3.13 kompatibel)

#### 📚 Dokumentation

- `docs/CACHE_MANAGEMENT.md` (3.500+ Zeilen)
- `docs/XC_API_PORTAL_FILTERING.md` (500+ Zeilen)
- `docs/PERFORMANCE_OPTIMIZATIONS.md` (NEU - Performance-Guide)
- `EPG_IMPROVEMENTS_SUMMARY.md` (300+ Zeilen)
- `FEATURE_COMPARISON.md` (Detaillierter Vergleich)
- `ORIGINAL_ADVANTAGES.txt` (Was ist im Original besser)

#### 🔧 Verbesserungen

**EPG-System (9 Verbesserungen)**
- Raw XML Passthrough (alle Metadaten erhalten)
- ID-based Matching (custom_epg_id Priorität)
- M3U/XMLTV Alignment (100% Übereinstimmung)
- Variant Deduplication (HD/FHD/UHD teilen EPG)
- Portal EPG Enrichment (Kategorien, Regisseure, Schauspieler)
- (lang=) Cleanup (entfernt Sprach-Artefakte)
- Diagnostic Logging (EPG-Statistiken)

**Stream-Performance**
- Intelligentes MAC-Fallback
- Cache-optimierte Channel-Suche
- Automatische MAC-Auswahl
- Besseres Logging für Debugging

**Automatic Log Cleanup**
- Automatisches Löschen von Log-Dateien älter als 24 Stunden
- Läuft alle 6 Stunden im Hintergrund
- Verhindert Disk-Space-Probleme
- Keine manuelle Wartung mehr nötig
- Transparente Logging-Ausgaben

**Editor Performance**
- Entfernt unnötige `refresh_lineup()` Aufrufe beim Speichern
- Entfernt unnötige `refresh_xmltv()` Aufrufe bei Bulk-Operationen
- Lineup wird nur bei Bedarf geladen (lazy loading)
- EPG wird über "EPG Auto Refresh" Setting gesteuert
- Massiv schnelleres Speichern von Channel-Edits

**UI/UX**
- Erweiterte Settings-Seite mit Cache-Optionen
- Bessere Gruppierung und Hints
- Info-Cards mit Dokumentations-Links

#### 🐛 Bugfixes

- Syntax-Fehler behoben: `break`/`continue` außerhalb von Schleifen entfernt
- Wiki-Navigation hinzugefügt
- Channel-Cache Initialisierung nach `getSettings()` verschoben

#### 📊 Statistiken

- +1.216 Zeilen Code (+14,8%)
- +5.000 Zeilen Dokumentation
- 8 neue Features
- 3 verbesserte Features
- Bis zu 10x schnelleres JSON-Parsing
- +100% mehr Concurrent Requests

---

### [v2.3.1] - 14.12.2025

#### Neue Funktionen

*   **Proxy-Test-Tool**: Eigene Oberfläche hinzugefügt, um Proxy-Konfigurationen (HTTP, SOCKS5, Shadowsocks) direkt im Dashboard zu überprüfen.
*   **Dynamischer MAC-Status-Check**: Das MAC-Status-Modal behält nun seinen Zustand bei und aktualisiert den Inhalt dynamisch, ohne sich zu schließen und neu zu öffnen.
*   **Verbesserte Statusmeldung**: "Status aktualisieren" bietet nun sofortiges visuelles Feedback (Häkchen auf der Schaltfläche) für eine flüssigere Benutzererfahrung.

#### Verbesserungen

*   **Shadowsocks-Kompatibilität**: Verbesserte Validierung und Fehlerberichterstattung für Shadowsocks-Verbindungen. Spezifische Überprüfungen für `aes-256-cfb` und andere Verschlüsselungsmethoden hinzugefügt.
*   **MAC-Verfügbarkeitslogik**: Verbesserter Scoring-Algorithmus für MAC-Adressen, um den Status "Verfügbar", "Belegt" oder "Aktiv" basierend auf Watchdog-Timeouts und Stream-Limits genauer zu bestimmen.
*   **UI/UX**: Allgemeine Bereinigung und Verfeinerung der Modal-Interaktionen in der Portal-Ansicht.
*   **VOD-Modal Design**: Komplette Überarbeitung des VOD-Modals für einheitliches Design mit EPG und Editor.
*   **VOD Portal-Karten**: Hauptseite verwendet nun Portal-Card Design mit Statistik-Boxen (MACs, Kategorien, Ausgewählt %).
*   **VOD Kategorie-Grid**: Kompaktere Karten (180px min-width, 80px min-height) mit grünem Rand für ausgewählte Kategorien.
*   **VOD Preview-Button**: Immer sichtbares Auge-Icon zum Vorschauen von Kategorie-Inhalten ohne Auswahl zu ändern.
*   **VOD Sticky Filter**: Korrigierte Abstände und Margins der Sticky-Filterleiste, passende Hintergrundfarben für Light/Dark Mode.
*   **VOD Items laden**: Lädt nun bis zu 10.000 Items pro Kategorie (vorher auf 50 limitiert), "Load More" Button entfernt.

#### Interne Änderungen

*   **Aufräumarbeiten**: Veraltete Skripte `test_stream.sh` und `validate_fixes.py` entfernt.
*   **Refactoring**: Zentralisierung der Proxy-Verifizierungslogik in `app-docker.py`.
*   **CSS Bereinigung**: VOD-spezifische modal-content, card und alert Styles entfernt die Farbabweichungen verursachten.

---

### Version 2.2.1 HOTFIX (11. Dezember 2025)

**Problem:** Die Modals in `templates/vods.html` waren nicht richtig geschlossen:
1. vodModal fehlte das schließende `</div>` Tag
2. vodSettingsModal fehlte das schließende `</div>` Tag

**Lösung:** Beide fehlenden `</div>` Tags wurden hinzugefügt

---

### Version 2.2 (11. Dezember 2025)

#### Dashboard Live Log System
- **Real-time Log Monitoring**: AJAX-basiertes Live-Log mit konfigurierbaren Refresh-Intervallen (1s, 2s, 5s, 10s, Pausiert)
- **Live Countdown Timer**: Zeigt verbleibende Zeit bis zum nächsten Refresh
- **Badge-Style Controls**: Alle Log-Controls als interaktive Badges rechts in der Card
- **Vollständiger Light/Dark Mode**: Perfekte Darstellung in beiden Themes
- **Farbkodierte Log-Levels**: Error=Rot, Warning=Orange, Info=Blau, Debug=Grün
- **Auto-scroll Toggle**: Smart Auto-scrolling mit visueller Rückmeldung
- **Clear Function**: One-Click Log-Clearing mit Cache-Reset

#### Dashboard URL-Felder Enhancement
- **Professionelle M3U/XMLTV-Felder**: Mit Icons, farbigen Input-Groups und One-Click Copy
- **Enhanced Copy-Buttons**: Visuelle Bestätigung beim Kopieren
- **Theme-Support**: Korrekte Farben für Light/Dark Mode
- **Responsive Design**: Optimiert für alle Bildschirmgrößen

#### VOD-Seite Fixes
- **Footer-Problem behoben**: Footer erscheint jetzt unter Content statt ganz unten
- **Modal-Struktur optimiert**: Alle Modals korrekt in page-body positioniert
- **Dark Mode Fixes**: Grüne Checkboxen und korrekte Formular-Farben

#### Settings-System Verbesserungen
- **Public Access Toggle**: "Allow public access to /playlist.m3u and /xmltv" Einstellung hinzugefügt
- **Persistente Speicherung**: Settings überleben jetzt Server-Neustarts
- **Granulare Kontrolle**: Login-Pflicht für Playlist/XMLTV individuell steuerbar

#### JavaScript-Fehler behoben
- **Dashboard-Fehler**: "Cannot set properties of null" Error eliminiert
- **Datum-Handling**: "Invalid Date" Problem mit robusten Fallbacks gelöst
- **Performance**: Optimierte Timer-Verwaltung und Memory-Management

#### VOD & Series System
- **Komplettes VOD Management**: Movies und Series von allen Portalen
- **Grid-basierte Kategorie-Ansicht**: Visuelle Unterscheidung zwischen VOD (blau) und Series (orange)
- **Zwei-Level Navigation**: Kategorien → Items mit dynamischem Modal-System
- **Multi-Portal Support**: Kombiniert VOD-Inhalte von allen aktivierten Portalen
- **XC API Integration**: Vollständige Xtream Codes API Kompatibilität
- **Streaming-Optionen**:
  - **FFmpeg Processing** (Standard): Maximale Kompatibilität durch Transcoding
  - **Direct URL Mode**: Schnelleres Streaming mit direkten Portal-URLs
- **MAC Rotation**: Automatisches Load-Balancing über verfügbare MACs
- **VOD Settings**: Konfigurierbar über `/vods` Seite - probiert aus was besser funktioniert!

#### VOD Database Integration
- **Dedizierte SQLite DB**: Separate `vods.db` für VOD-spezifische Daten
- **Kategorie-Aktivierung**: Wie Editor/EPG können Kategorien aktiviert/deaktiviert werden
- **MAC Caching**: Merkt sich welche MAC für welchen Content funktioniert
- **Settings Persistence**: Stream-Methode und MAC-Rotation in DB gespeichert

#### XC API VOD Endpoints
```
/player_api.php?action=get_vod_categories     # VOD Kategorien
/player_api.php?action=get_series_categories  # Series Kategorien
/player_api.php?action=get_vod_streams        # Movies in Kategorie
/player_api.php?action=get_series             # Series in Kategorie
/movie/username/password/stream_id.mp4        # Movie Streaming
/series/username/password/stream_id.mp4       # Series Streaming
```

---

### Version 2.1 (10. Dezember 2025)

#### SFVIP Analysis & Portal Compatibility
- **MITM Proxy Verständnis**: Analyse wie SFVIP mit mitmproxy funktioniert
- **Cloudflare Bypass**: Erkenntnisse über Residential vs Datacenter IPs
- **Multiple Endpoints**: Erweiterte Portal-Kompatibilität durch alternative Pfade
- **GET/POST Fallback**: Robustere Portal-Verbindungen

#### UI/UX Verbesserungen
- **Modal Scrolling Fix**: Portal Edit Modal scrollt jetzt korrekt
- **Enhanced Bulk Edit UI**: 2x3 Grid Layout, bessere Übersicht
- **Rule Management**: Clear Saved Rules, Info-Anzeigen
- **Settings Persistence**: Checkboxen merken sich Einstellungen

#### XC API Database Integration (Game Changer!)
- **Problem gelöst**: XC API las aus Config-Dateien statt Datenbank
- **Sofortige Updates**: Bulk Edit Änderungen sofort in IPTV Playern sichtbar
- **Komplette Überarbeitung**: `xc_get_playlist()`, `xc_get_live_streams()`, `xc_get_live_categories()`
- **Performance**: Keine Portal-Abfragen mehr nötig für XC API

#### Advanced Bulk Search & Replace mit Persistenz
- **6 Smart Presets**: VIP, Emojis, Country Codes, Brackets, Clean Separators, Fix Spacing
- **Persistente Rules**: Automatisches Speichern in Datenbank, überleben Server-Restart
- **Undo/Redo System**: Vollständige History mit Backup vor jeder Änderung
- **Enhanced Country Code Removal**: Regex-basiert, erkennt `DE:`, `DE|`, `DE-`, `[DE]`, etc.
- **Preview-Funktion**: Zeigt Änderungen vor Anwendung

#### Real-Time Progress Tracking System
- **EPG Refresh Progress**: Detaillierte Fortschrittsanzeige mit Portal-Namen, Schritten und beweglicher Progress Bar
- **Channel Refresh Progress**: Live-Updates beim Laden der Kanäle mit Portal-Status
- **Threading-basiert**: Keine Blockierung der UI, Updates alle Sekunde
- **Auto-Reload**: Automatisches Neuladen nach Abschluss

#### Warum SFVIP bei dlta4k.com funktioniert:
1. **Residential IP**: SFVIP läuft auf Residential IP (nicht Datacenter/VPN)
2. **Browser Emulation**: Echte Browser-Headers und TLS-Fingerprint
3. **Proxy-Methode**: Kein direkter HTTP-Request, sondern Proxy-Interception
4. **Portal-Pfad**: Verwendet korrekten Pfad `/portal.php` (nicht `/c/portal.php`)

#### Implementierung:
- **cloudscraper**: Für Cloudflare-Bypass (soweit möglich)
- **Multiple Endpoints**: Alternative Portal-Pfade probieren
- **Enhanced Headers**: MAG-Device Fingerprinting
- **GET/POST Fallback**: Robustere Verbindungen

---

### Version 2.0 (08. Dezember 2025)

#### UI Redesign
- Komplett neues Grid-basiertes Design für Editor, EPG, Portals, XC Users, Dashboard
- Sticky Search Bars mit Glass-Effekt in allen Modals
- Dark/Light Mode mit korrekten Farben (#1a1a1a, #2a2a2a statt Blau)
- Grüner Akzent (#10b981) für aktive Elemente
- Keine Hover-Effekte mehr (weniger Ablenkung)
- Tabler Modal Dialogs statt Browser-Alerts

#### Portal Management
- Edit Modal komplett überarbeitet (Zwei-Spalten-Layout)
- MAC-Tabelle und Update-Textarea nebeneinander
- Genre Selection Modal mit Glass-Effect Search Bar
- Info Modal entfernt (redundant)

#### EPG Verbesserungen
- EPG Settings Modal für Fallback-Konfiguration
- Strikte Matching-Regeln (lieber kein EPG als falsches EPG)
- Custom EPG IDs werden bei Refresh berücksichtigt
- Direkte Datenbank-Updates statt JSON-Dateien

#### XC API
- Komplette Xtream Codes API Implementation
- User Management mit Connection-Limits
- Copy Playlist Button für schnelles Kopieren

#### Performance
- SQLite Database Caching für Kanäle
- Multi-MAC Support für Kanäle und EPG
- 5-Minuten Cache für EPG-Daten

---

### Version 1.0 (06. Dezember 2025)

#### Docker-Konfiguration
- Docker-Compose und Dockerfile von Unraid-spezifisch auf Standard-Docker umgestellt
- PUID/PGID von 99/100 auf 1000/1000 geändert
- Volume-Pfade von `/mnt/user/appdata/` auf relative Pfade (`./data`, `./logs`) angepasst
- Unraid-spezifische Labels und Netzwerk-Konfigurationen entfernt

#### Genre-Manager Feature
- Neuer **"Manage Genres"** Button im Editor hinzugefügt
- Modal mit Checkbox-Liste aller verfügbaren Genres
- Zeigt Statistik pro Genre (z.B. "5/20" für aktivierte/gesamt Sender)
- **"Select All" / "Deselect All"** Funktionen
- **Bulk-Aktivierung/-Deaktivierung** mehrerer Genres gleichzeitig

#### Technische Verbesserungen
- Doppelte DataTable-Initialisierung entfernt (behebt Fehler beim Laden)
- Änderungen werden korrekt in `enabledEdits` gespeichert
- Checkboxen in der Tabelle werden visuell aktualisiert
