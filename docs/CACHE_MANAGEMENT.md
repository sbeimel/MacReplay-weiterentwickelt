# Cache Management

## Übersicht

MacReplayXC verwendet ein mehrstufiges Cache-System für optimale Performance:

- **Channel Cache**: Speichert Kanaldaten von Portalen
- **Lineup Cache**: HDHR-Lineup für Plex/Emby
- **Playlist Cache**: M3U-Playlist
- **EPG Cache**: XMLTV-Daten

## Cache-Modi

Der Channel Cache unterstützt 4 Modi (konfigurierbar in Settings):

### 1. lazy-ram (Standard) ⭐
- **Verhalten**: Cache on-demand, nur im RAM
- **Vorteil**: Minimaler Speicherverbrauch, keine Wartezeit beim Start
- **Nachteil**: Cache geht bei Neustart verloren
- **Neu-Erstellung**: **Automatisch** beim ersten Zugriff auf einen Kanal
- **Umfang**: Nur die **tatsächlich abgerufenen** Kanäle werden gecached
- **Portal-Setup**: **KEIN** Pre-Caching beim Hinzufügen
- **Ideal für**: Kleine Setups, wenige Portale, gelegentliche Nutzung

**Wie es funktioniert:**
```
1. Portal hinzufügen → Genre-Auswahl → Fertig (kein Pre-Cache!)
2. Benutzer öffnet Stream → Channel nicht im Cache
3. System lädt Channel von Portal-API
4. Channel wird im RAM gecached
5. Nächster Zugriff: Instant aus Cache
```

**Wichtig:** Nur **aktivierte Kanäle** (Genre-Auswahl) werden beim Zugriff gecached!

### 2. ram
- **Verhalten**: Pre-Cache beim Portal-Setup, nur im RAM
- **Vorteil**: Alle Kanäle sofort verfügbar, schneller Zugriff
- **Nachteil**: Cache geht bei Neustart verloren, höherer RAM-Verbrauch
- **Neu-Erstellung**: **Automatisch** beim Portal-Setup + manuell über "Rebuild Cache"
- **Umfang**: **Alle aktivierten Kanäle** (Genre-Auswahl) werden sofort gecached
- **Portal-Setup**: **JA** - Pre-Caching beim Hinzufügen
- **Ideal für**: Mittlere Setups, häufige Nutzung, schneller Start wichtig

**Wie es funktioniert:**
```
1. Portal hinzufügen → Genre-Auswahl
2. System lädt ALLE aktivierten Kanäle von ALLEN MACs
3. Alle Kanäle werden im RAM gecached (automatisch!)
4. Sofort verfügbar ohne Wartezeit
5. Nach Neustart: Cache weg → Rebuild nötig
```

### 3. disk
- **Verhalten**: Pre-Cache beim Portal-Setup, nur auf Disk
- **Vorteil**: Persistent über Neustarts, kein RAM-Verbrauch
- **Nachteil**: Langsamer als RAM (Disk I/O)
- **Neu-Erstellung**: **Automatisch** beim Portal-Setup + manuell über "Rebuild Cache"
- **Umfang**: **Alle aktivierten Kanäle** (Genre-Auswahl) werden auf Disk gespeichert
- **Portal-Setup**: **JA** - Pre-Caching beim Hinzufügen
- **Ideal für**: Systeme mit wenig RAM, viele Portale, Persistenz wichtig

**Wie es funktioniert:**
```
1. Portal hinzufügen → Genre-Auswahl
2. System lädt ALLE aktivierten Kanäle von ALLEN MACs
3. Alle Kanäle werden in SQLite-DB gespeichert (automatisch!)
4. Nach Neustart: Cache bleibt erhalten
```

### 4. hybrid (Empfohlen) ⭐
- **Verhalten**: Pre-Cache beim Portal-Setup, RAM + Disk
- **Vorteil**: Schnell + Persistent, beste Performance
- **Nachteil**: Höherer Speicherverbrauch (RAM + Disk)
- **Neu-Erstellung**: **Automatisch** beim Portal-Setup + manuell über "Rebuild Cache"
- **Umfang**: **Alle aktivierten Kanäle** (Genre-Auswahl) werden in RAM + Disk gecached
- **Portal-Setup**: **JA** - Pre-Caching beim Hinzufügen
- **Ideal für**: Produktiv-Systeme, viele Portale, maximale Performance

**Wie es funktioniert:**
```
1. Portal hinzufügen → Genre-Auswahl
2. System lädt ALLE aktivierten Kanäle von ALLEN MACs
3. Alle Kanäle werden in RAM UND Disk gespeichert (automatisch!)
4. Zugriff: Blitzschnell aus RAM
5. Nach Neustart: Lädt aus Disk in RAM
```

## Wichtig: Genre-Auswahl bestimmt Cache-Umfang

### Was wird gecached?

**NUR aktivierte Kanäle!**

Beim Hinzufügen eines Portals wählen Sie Genres aus:
```
Portal hinzufügen → Genre-Auswahl → z.B. "Entertainment", "News", "Sports"
```

**Gecached werden:**
- ✅ Alle Kanäle der **ausgewählten Genres**
- ❌ Kanäle **nicht ausgewählter** Genres werden NICHT gecached

**Beispiel:**
- Portal hat 1000 Kanäle in 20 Genres
- Sie wählen 3 Genres (150 Kanäle)
- **Nur diese 150 Kanäle** werden gecached!

### Genre-Auswahl ändern

**Nachträglich Genres hinzufügen/entfernen:**
```
Portals → Portal bearbeiten → "Genre Selection" → Genres ändern → Rebuild Cache
```

**Wichtig:** Nach Genre-Änderung **muss** "Rebuild Cache" ausgeführt werden!

## Cache-Modi im Vergleich

| Modus | Cache-Erstellung | Portal-Setup | Umfang | Persistenz | RAM | Disk | Ideal für |
|-------|------------------|--------------|--------|------------|-----|------|-----------|
| **lazy-ram** | Automatisch on-demand | ❌ Kein Pre-Cache | Nur abgerufene Kanäle | ❌ Nein | Minimal | - | Kleine Setups |
| **ram** | Automatisch + Manuell | ✅ Pre-Cache | Alle aktivierten Kanäle | ❌ Nein | Hoch | - | Mittlere Setups |
| **disk** | Automatisch + Manuell | ✅ Pre-Cache | Alle aktivierten Kanäle | ✅ Ja | Minimal | Hoch | Wenig RAM |
| **hybrid** | Automatisch + Manuell | ✅ Pre-Cache | Alle aktivierten Kanäle | ✅ Ja | Hoch | Hoch | Produktiv |

## Cache-Verwaltung

### Dashboard - Quick Actions

Im Dashboard gibt es zwei Buttons für Cache-Management:

#### 1. "Rebuild Cache" (Grün)
**Was macht es:**
- Lädt **alle** Kanäle von **allen** Portalen neu
- Aktualisiert die Datenbank mit neuen Kanälen
- Füllt den Cache mit aktuellen Daten
- Behält Customizations (Namen, Nummern, etc.)

**Wann verwenden:**
- Nach dem Hinzufügen neuer Portale
- Wenn neue Kanäle verfügbar sind
- Nach Änderungen an Portal-URLs
- Regelmäßige Wartung (z.B. wöchentlich)

**Dauer:** 2-10 Minuten (abhängig von Anzahl Portale/MACs)

**Fortschritt:** Live-Anzeige im Button + Toast-Benachrichtigung

#### 2. "Clear Cache" (Gelb)
**Was macht es:**
- Löscht **alle** Caches (RAM + Disk)
- Löscht **nicht** die Datenbank
- Nächster Zugriff lädt Daten neu

**Wann verwenden:**
- Bei Cache-Problemen
- Vor einem Rebuild
- Bei Speicherproblemen
- Nach Proxy-Änderungen

**Dauer:** < 1 Sekunde

### Automatische Cache-Erstellung

Der Cache wird **automatisch** neu erstellt in folgenden Situationen:

#### 1. Lazy Loading (lazy-ram Modus)
```
Benutzer öffnet Playlist → Cache leer → Lädt von Portal → Cached
```

#### 2. On-Demand (alle Modi)
```
Stream-Anfrage → Channel nicht im Cache → Lädt von Portal → Cached
```

#### 3. Beim Start (disk/hybrid Modus)
```
Container startet → Lädt Cache von Disk → Bereit
```

#### 4. Nach Portal-Änderungen
```
Portal hinzugefügt → Automatischer Refresh → Cache aktualisiert
```

### Cache-Statistiken

Das Dashboard zeigt Live-Statistiken:

- **Cache Mode**: Aktueller Modus (lazy-ram, ram, disk, hybrid)
- **RAM Entries**: Anzahl gecachter Portale im RAM
- **Disk Entries**: Anzahl gecachter Portale auf Disk
- **Total Channels**: Gesamtzahl gecachter Kanäle

**Auto-Update:** Alle 30 Sekunden

## Workflow-Beispiele

### Szenario 1: Neues Portal hinzufügen (lazy-ram)
```
1. Portals → "Add Portal" → Portal hinzufügen
2. Genre-Auswahl → Genres wählen → Speichern
3. Fertig! (Kein Pre-Cache)
4. Beim ersten Stream: Automatisches Caching (2-5 Sek)
```

### Szenario 2: Neues Portal hinzufügen (ram/disk/hybrid)
```
1. Portals → "Add Portal" → Portal hinzufügen
2. Genre-Auswahl → Genres wählen → Speichern
3. System cached automatisch alle aktivierten Kanäle (1-5 Min)
4. Fertig! Alle Kanäle sofort verfügbar
```

### Szenario 3: Cache-Probleme beheben
```
1. Dashboard → "Clear Cache" → Bestätigen
2. Dashboard → "Rebuild Cache" → Warten
3. Fertig! Cache neu erstellt
```

### Szenario 4: Regelmäßige Wartung
```
1. Wöchentlich: Dashboard → "Rebuild Cache"
2. Cache wird aktualisiert mit neuen Kanälen
3. Keine Downtime - alte Daten bleiben bis Rebuild fertig
```

### Szenario 5: Genre-Auswahl ändern
```
1. Portals → Portal bearbeiten → "Genre Selection"
2. Genres ändern (z.B. 3 → 5 Genres)
3. Dashboard → "Rebuild Cache" (wichtig!)
4. Neue Kanäle werden gecached
```

### Szenario 6: Lazy Loading (kein Eingriff nötig)
```
1. Nichts tun!
2. Cache wird automatisch beim ersten Zugriff erstellt
3. Kein manueller Eingriff nötig
```

## API-Endpunkte

### Cache löschen
```bash
POST /cache/clear
```

**Response:**
```json
{
  "success": true,
  "message": "Cache cleared successfully (150 entries)",
  "cleared_entries": 150
}
```

### Cache neu erstellen
```bash
POST /editor/refresh
```

**Response:**
```json
{
  "success": true,
  "message": "Channel refresh started"
}
```

**Progress abrufen:**
```bash
GET /editor/refresh/progress
```

**Response:**
```json
{
  "running": true,
  "current_portal": "Portal 1",
  "current_step": "Fetching channels from MAC 2/3",
  "portals_done": 1,
  "portals_total": 5,
  "started_at": "2026-02-06T12:00:00Z"
}
```

### Cache-Statistiken abrufen
```bash
GET /cache/stats
```

**Response:**
```json
{
  "success": true,
  "stats": {
    "mode": "hybrid",
    "cache_duration": null,
    "ram_entries": 5,
    "disk_entries": 5,
    "total_channels": 1250
  }
}
```

## Unterschied: Clear vs. Rebuild

### Clear Cache (Löschen)
- ❌ Löscht alle Cache-Daten
- ✅ Schnell (< 1 Sekunde)
- ✅ Befreit Speicher
- ❌ Nächster Zugriff langsam (muss neu laden)
- **Verwendung:** Problembehebung, Speicher freigeben

### Rebuild Cache (Neu erstellen)
- ✅ Lädt alle Daten neu von Portalen
- ✅ Aktualisiert Datenbank
- ✅ Findet neue Kanäle
- ❌ Langsam (2-10 Minuten)
- ✅ Cache sofort verfügbar nach Abschluss
- **Verwendung:** Regelmäßige Updates, neue Kanäle

### Empfohlener Workflow
```
1. Clear Cache (optional - nur bei Problemen)
2. Rebuild Cache (lädt alles neu)
3. Fertig!
```

Oder einfach:
```
Rebuild Cache (überschreibt alten Cache automatisch)
```

## Wann sollte der Cache gelöscht/neu erstellt werden?

### Rebuild Cache (Empfohlen)

**Regelmäßig:**
- ✅ Wöchentlich oder monatlich (je nach Bedarf)
- ✅ Nach Hinzufügen neuer Portale
- ✅ Wenn neue Kanäle erwartet werden
- ✅ Nach Portal-URL-Änderungen

**Bei Problemen:**
- ✅ Kanäle fehlen in der Liste
- ✅ Kanäle haben falsche Namen/Nummern
- ✅ EPG-Daten stimmen nicht

### Clear Cache (Nur bei Bedarf)

**Nur in diesen Fällen:**
- ❌ Bei schwerwiegenden Cache-Problemen
- ❌ Vor einem kompletten Rebuild
- ❌ Bei Speicherproblemen (RAM voll)
- ❌ Nach Proxy-Änderungen (wenn Streams nicht funktionieren)

**Nicht empfohlen:**
- ❌ Regelmäßiges Löschen (unnötig)
- ❌ Vor jedem Stream (verlangsamt Performance)
- ❌ "Zur Sicherheit" (bringt nichts)

### Automatisches Neu-Laden

In den meisten Fällen ist **kein manueller Eingriff** nötig:

**Lazy-RAM Modus (Standard):**
- Cache wird automatisch beim ersten Zugriff erstellt
- Kein Rebuild nötig
- Einfach Playlist öffnen → Cache wird erstellt

**Hybrid/Disk Modus:**
- Cache bleibt nach Neustart erhalten
- Rebuild nur für Updates nötig

## Cache-Lebensdauer

### Standard-Einstellung: Unbegrenzt

Der Cache läuft standardmäßig **unbegrenzt** (keine automatische Löschung).

**Vorteile:**
- Maximale Performance
- Keine unnötigen API-Anfragen an Portale
- Reduzierte Serverlast

**Konfiguration in Settings:**
- **Channel Cache Duration**: `unlimited` (Standard)
- Änderbar auf: 3600s (1h), 7200s (2h), 86400s (24h)

**Hinweis:** Bei unbegrenztem Cache ist **Rebuild Cache** die empfohlene Methode für Updates.

## Cache-Erstellung im Detail

### 1. Automatische Erstellung (Lazy Loading)

**Wann:** Beim ersten Zugriff auf einen Kanal/Portal

**Nur bei lazy-ram Modus!**

**Ablauf:**
```
1. Benutzer öffnet Playlist/Stream
2. System prüft Cache → Leer
3. System lädt von Portal-API
4. Daten werden gecached
5. Stream startet
```

**Dauer:** 2-5 Sekunden pro Kanal

**Vorteil:** Kein manueller Eingriff nötig

### 2. Automatische Erstellung (Portal-Setup)

**Wann:** Beim Hinzufügen eines Portals (Genre-Auswahl)

**Nur bei ram/disk/hybrid Modi!**

**Ablauf:**
```
1. Portal hinzufügen → Genre-Auswahl
2. System lädt ALLE aktivierten Kanäle von ALLEN MACs
3. Daten werden gecached (RAM/Disk je nach Modus)
4. Fertig! Alle Kanäle sofort verfügbar
```

**Dauer:** 1-5 Minuten (abhängig von Anzahl MACs/Kanäle)

**Vorteil:** Sofort verfügbar, keine Wartezeit beim ersten Stream

### 3. Manuelle Erstellung (Rebuild)

**Wann:** Über Dashboard → "Rebuild Cache"

**Für alle Modi verfügbar!**

**Ablauf:**
```
1. Benutzer klickt "Rebuild Cache"
2. System lädt von ALLEN Portalen
3. System lädt von ALLEN MACs pro Portal
4. Daten werden in Datenbank gespeichert
5. Cache wird gefüllt (RAM/Disk je nach Modus)
6. Fertig!
```

**Dauer:** 2-10 Minuten (abhängig von Anzahl Portale/MACs)

**Vorteil:** 
- Alle Kanäle sofort verfügbar
- Findet neue Kanäle
- Aktualisiert EPG-Zuordnungen

### 4. Pre-Cache (RAM/Disk/Hybrid Modi)

**Wann:** Beim Portal-Setup oder nach Rebuild

**Nur bei ram/disk/hybrid Modi!**

**Ablauf:**
```
1. Portal wird hinzugefügt
2. System lädt automatisch alle Kanäle
3. Cache wird sofort gefüllt
4. Keine Wartezeit beim ersten Zugriff
```

**Vorteil:** Instant-Start für Streams

## Rebuild vs. Refresh vs. Clear

### Rebuild Cache (Dashboard)
- **Was:** Lädt ALLE Kanäle von ALLEN Portalen neu
- **Wo:** Dashboard → "Rebuild Cache"
- **Dauer:** 2-10 Minuten
- **Effekt:** Cache + Datenbank aktualisiert
- **Verwendung:** Regelmäßige Updates

### Refresh Channels (Editor)
- **Was:** Lädt ALLE Kanäle von ALLEN Portalen neu
- **Wo:** Editor → "Refresh Channels"
- **Dauer:** 2-10 Minuten
- **Effekt:** Cache + Datenbank aktualisiert
- **Verwendung:** Gleich wie Rebuild (anderer Ort)

### Clear Cache (Dashboard)
- **Was:** Löscht Cache (nicht Datenbank)
- **Wo:** Dashboard → "Clear Cache"
- **Dauer:** < 1 Sekunde
- **Effekt:** Cache leer, Datenbank bleibt
- **Verwendung:** Problembehebung

**Hinweis:** Rebuild und Refresh sind identisch, nur an verschiedenen Stellen verfügbar.

## Troubleshooting

### Problem: Cache wird nicht gelöscht

**Lösung:**
1. Prüfen Sie die Logs: `/log`
2. Starten Sie den Container neu: `docker-compose restart`
3. Prüfen Sie Disk-Space: `df -h`

### Problem: Cache-Statistiken zeigen 0

**Lösung:**
1. Warten Sie 30 Sekunden (Auto-Refresh)
2. Laden Sie die Seite neu (F5)
3. Prüfen Sie, ob Portale aktiviert sind

### Problem: Disk-Cache wächst zu groß

**Lösung:**
1. Wechseln Sie zu `lazy-ram` Modus in Settings
2. Löschen Sie den Cache: Dashboard → "Clear Cache"
3. Löschen Sie die Disk-Cache-Datei: `rm /app/data/channel_cache.db`

## Best Practices

1. **Verwenden Sie `hybrid` Modus** für beste Performance + Persistenz
2. **Löschen Sie den Cache nur bei Bedarf** (siehe Szenarien oben)
3. **Überwachen Sie die Cache-Statistiken** im Dashboard
4. **Planen Sie regelmäßige Refreshes** über Editor (z.B. wöchentlich)
5. **Dokumentieren Sie Cache-Löschungen** in Ihren Wartungsprotokollen

## Weitere Informationen

- [EPG Management](EPG_IMPROVEMENTS_SUMMARY.md)
- [Proxy Support](PROXY_SUPPORT.md)
- [Docker Setup](DOCKER_PROXY_SETUP.md)


## Settings-Optionen im Detail

### Channel Cache Mode (Settings → Integrations & Advanced)

**Wo:** Settings → "Integrations & Advanced" → "Channel Cache Mode"

**Optionen:**

#### lazy-ram (Standard)
```
Beschreibung: On-Demand Caching (nur im RAM)
Empfohlen für: Kleine Setups, wenige Portale
RAM-Verbrauch: Minimal (nur abgerufene Kanäle)
Disk-Verbrauch: Keiner
Persistenz: Nein (Cache weg nach Neustart)
Rebuild nötig: Nein (automatisch)
```

**Verhalten:**
- Kanäle werden **nur** beim ersten Zugriff gecached
- Kein Pre-Caching beim Portal-Setup
- Schneller Start (keine Wartezeit)
- Ideal für gelegentliche Nutzung

#### ram
```
Beschreibung: Pre-Cache beim Setup (nur im RAM)
Empfohlen für: Mittlere Setups, häufige Nutzung
RAM-Verbrauch: Hoch (alle aktivierten Kanäle)
Disk-Verbrauch: Keiner
Persistenz: Nein (Cache weg nach Neustart)
Rebuild nötig: Ja (nach Neustart oder Genre-Änderung)
```

**Verhalten:**
- Alle aktivierten Kanäle werden beim Portal-Setup gecached
- Sofort verfügbar ohne Wartezeit
- Nach Neustart: Rebuild nötig

#### disk
```
Beschreibung: Pre-Cache beim Setup (nur auf Disk)
Empfohlen für: Systeme mit wenig RAM
RAM-Verbrauch: Minimal
Disk-Verbrauch: Hoch (alle aktivierten Kanäle)
Persistenz: Ja (Cache bleibt nach Neustart)
Rebuild nötig: Nur für Updates
```

**Verhalten:**
- Alle aktivierten Kanäle werden in SQLite-DB gespeichert
- Langsamer als RAM (Disk I/O)
- Nach Neustart: Cache bleibt erhalten

#### hybrid (Empfohlen)
```
Beschreibung: Pre-Cache beim Setup (RAM + Disk)
Empfohlen für: Produktiv-Systeme, viele Portale
RAM-Verbrauch: Hoch (alle aktivierten Kanäle)
Disk-Verbrauch: Hoch (alle aktivierten Kanäle)
Persistenz: Ja (Cache bleibt nach Neustart)
Rebuild nötig: Nur für Updates
```

**Verhalten:**
- Alle aktivierten Kanäle werden in RAM UND Disk gespeichert
- Blitzschneller Zugriff aus RAM
- Nach Neustart: Lädt aus Disk in RAM (schnell)
- Beste Performance + Persistenz

### Channel Cache Duration (Settings → Integrations & Advanced)

**Wo:** Settings → "Integrations & Advanced" → "Channel Cache Duration"

**Optionen:**

#### unlimited (Standard) ⭐
```
Beschreibung: Cache läuft unbegrenzt
Empfohlen für: Alle Modi
Verhalten: Cache wird nie automatisch gelöscht
Rebuild: Nur manuell über Dashboard
```

**Vorteil:**
- Maximale Performance
- Keine unnötigen API-Anfragen
- Reduzierte Serverlast

**Nachteil:**
- Veraltete Daten möglich (manueller Rebuild nötig)

#### 3600 (1 Stunde)
```
Beschreibung: Cache läuft 1 Stunde
Empfohlen für: Häufig wechselnde Kanäle
Verhalten: Cache wird nach 1h automatisch gelöscht
Rebuild: Automatisch beim nächsten Zugriff
```

#### 7200 (2 Stunden)
```
Beschreibung: Cache läuft 2 Stunden
Empfohlen für: Moderate Updates
Verhalten: Cache wird nach 2h automatisch gelöscht
Rebuild: Automatisch beim nächsten Zugriff
```

#### 86400 (24 Stunden)
```
Beschreibung: Cache läuft 24 Stunden
Empfohlen für: Tägliche Updates
Verhalten: Cache wird nach 24h automatisch gelöscht
Rebuild: Automatisch beim nächsten Zugriff
```

**Hinweis:** Bei zeitlich begrenztem Cache wird **lazy-ram** Modus empfohlen!

### Empfohlene Kombinationen

#### Setup 1: Kleine Installation (Standard)
```
Cache Mode: lazy-ram
Cache Duration: unlimited
Rebuild: Nicht nötig (automatisch)
```

#### Setup 2: Mittlere Installation
```
Cache Mode: hybrid
Cache Duration: unlimited
Rebuild: Wöchentlich manuell
```

#### Setup 3: Große Installation (Produktiv)
```
Cache Mode: hybrid
Cache Duration: unlimited
Rebuild: Täglich automatisch (via Cron/Hook)
```

#### Setup 4: Häufig wechselnde Kanäle
```
Cache Mode: lazy-ram
Cache Duration: 3600 (1h)
Rebuild: Automatisch
```


## Intelligentes MAC-Fallback (lazy-ram Optimierung)

### Problem

Bei **lazy-ram** Modus wird der Cache nur beim ersten Zugriff erstellt. Wenn ein Channel auf MAC1 nicht existiert, aber auf MAC2 vorhanden ist, würde der alte Code MAC1 cachen (leer) und MAC2 nie probieren.

### Lösung

**Neue Funktion: `find_channel_any_mac()`**

Diese Funktion probiert **alle MACs** nacheinander, bis der Channel gefunden wird:

```python
def find_channel_any_mac(portal_id, macs, channel_id, url, proxy):
    """
    Find channel across multiple MACs - tries each MAC until channel is found.
    
    Especially useful for lazy-ram mode where cache is built on-demand.
    """
    for mac in macs:
        channel = find_channel(portal_id, mac, channel_id, url, token, proxy)
        if channel:
            return (channel, mac)  # Gefunden!
    
    return (None, None)  # Nicht gefunden
```

### Ablauf

**Szenario: Portal mit 3 MACs, Channel nur auf MAC2**

#### Alter Code (Problem):
```
1. Versuche MAC1 → Channel nicht gefunden → Cache MAC1 (leer)
2. Versuche MAC2 → Channel gefunden → Stream startet
3. Nächster Zugriff: MAC1 im Cache (leer) → Fehler!
```

#### Neuer Code (Lösung):
```
1. find_channel_any_mac() probiert:
   - MAC1 → Nicht gefunden → Weiter
   - MAC2 → Gefunden! → Cache MAC2 mit Channel
2. Stream startet mit MAC2
3. Nächster Zugriff: MAC2 im Cache → Instant!
```

### Vorteile

**✅ Lazy-RAM Modus:**
- Findet Channel auch wenn er nur auf einer MAC existiert
- Cached automatisch die richtige MAC
- Keine leeren Caches mehr

**✅ Alle Modi:**
- Intelligenteres MAC-Fallback
- Bessere Fehlertoleranz
- Weniger fehlgeschlagene Streams

**✅ Performance:**
- Nur beim ersten Zugriff relevant
- Danach: Instant aus Cache
- Keine unnötigen API-Calls

### Verwendung

**Automatisch in Stream-Endpunkten:**

1. **HLS Streams** (`/hls/<portal>/<channel>/<file>`)
2. **Direct Streams** (`/play/<portal>/<channel>`)
3. **XC API Streams** (`/live/<user>/<pass>/<stream>`)

**Keine Konfiguration nötig!**

### Logging

**Erfolgreicher Fallback:**
```
[INFO] [find_channel_any_mac] Channel 12345 found on MAC 00:1A:79:XX:XX:XX
[INFO] Channel 12345 found on MAC 00:1A:79:XX:XX:XX (via cache)
```

**Channel nicht gefunden:**
```
[DEBUG] [find_channel_any_mac] Channel 12345 not found on MAC 00:1A:79:AA:AA:AA
[DEBUG] [find_channel_any_mac] Channel 12345 not found on MAC 00:1A:79:BB:BB:BB
[WARNING] [find_channel_any_mac] Channel 12345 not found on any MAC
```

### Beispiel

**Portal-Setup:**
- Portal: "Sky Germany"
- MAC1: `00:1A:79:AA:AA:AA` (Sport-Kanäle)
- MAC2: `00:1A:79:BB:BB:BB` (Entertainment-Kanäle)
- MAC3: `00:1A:79:CC:CC:CC` (News-Kanäle)

**Szenario 1: Sport-Kanal (nur auf MAC1)**
```
1. Benutzer öffnet "Sky Sport 1"
2. find_channel_any_mac() probiert:
   - MAC1 → Gefunden! ✅
3. Cache: MAC1 → "Sky Sport 1"
4. Stream startet
```

**Szenario 2: Entertainment-Kanal (nur auf MAC2)**
```
1. Benutzer öffnet "Sky Cinema"
2. find_channel_any_mac() probiert:
   - MAC1 → Nicht gefunden
   - MAC2 → Gefunden! ✅
3. Cache: MAC2 → "Sky Cinema"
4. Stream startet
```

**Szenario 3: Nächster Zugriff**
```
1. Benutzer öffnet "Sky Sport 1" erneut
2. Cache-Lookup: MAC1 → "Sky Sport 1" ✅
3. Instant! (keine API-Calls)
```

### Kompatibilität

**Funktioniert mit allen Cache-Modi:**
- ✅ **lazy-ram**: Hauptvorteil - intelligentes Caching
- ✅ **ram**: Zusätzliche Fehlertoleranz
- ✅ **disk**: Zusätzliche Fehlertoleranz
- ✅ **hybrid**: Zusätzliche Fehlertoleranz

**Rückwärtskompatibel:**
- Keine Breaking Changes
- Bestehende Setups funktionieren weiter
- Automatische Verbesserung

### Performance-Impact

**Erster Zugriff (lazy-ram):**
- Vorher: 1 API-Call (falsche MAC möglich)
- Nachher: 1-N API-Calls (bis Channel gefunden)
- Worst Case: +2-3 Sekunden (bei 3 MACs)

**Weitere Zugriffe:**
- Keine Änderung (aus Cache)
- Instant!

**Empfehlung:**
- Bei vielen MACs (>3): Verwenden Sie **ram/disk/hybrid** Modus
- Bei wenigen MACs (1-3): **lazy-ram** ist optimal
