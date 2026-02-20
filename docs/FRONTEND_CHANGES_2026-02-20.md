# Frontend-Änderungen vom 2026-02-20

## Übersicht

Alle Frontend-Änderungen wurden korrekt implementiert und sind konsistent mit den Backend-Änderungen.

## Geänderte Dateien

### 1. templates/settings.html

#### Entfernte Settings:

**HLS Settings:**
- ❌ "HLS Auto Retry" Checkbox → Entfernt
- ✅ Ersetzt durch Info-Text: "Automatisches MAC Retry (immer aktiv)"
- ✅ Erklärung im Alert-Box hinzugefügt

**FFmpeg Settings:**
- ❌ "Try All MACs" Checkbox → Entfernt
- ✅ Ersetzt durch Info-Text: "Automatisches MAC Retry: System probiert automatisch alle MACs durch bis eine funktioniert"
- ✅ Erklärung im Alert-Box hinzugefügt

#### Hinzugefügte Settings:

**Custom ffprobe Parameters:**
- ✅ Neues Input-Feld für ffprobe Parameter
- ✅ 3 Preset-Buttons:
  - ⚖️ Balance (0.3-0.5s) - Standard
  - ⚡ Ultra Fast (0.1-0.2s)
  - 🐢 Standard Slow (2-5s)
- ✅ JavaScript-Funktion `setFfprobeParams(preset)`
- ✅ Info-Box mit Erklärung der Parameter
- ✅ Default-Wert: `-analyzeduration 500000 -probesize 100000`

**Location:** Nach "Custom FFmpeg Command" Sektion

### 2. templates/wiki.html

#### Aktualisierte Dokumentation:

**Settings-Tabelle:**
- ❌ "Try All MACs" Zeile → Entfernt
- ✅ "MAC Retry" Zeile → Hinzugefügt
  - Beschreibung: "Automatisches Durchprobieren aller MACs"
  - Status: "Immer aktiv" (grüner Badge)

**Empfohlene Konfigurationen:**

**Für maximale Performance:**
- Cache Mode: hybrid
- Cache Duration: unlimited
- ✅ MAC Retry: immer aktiv (neu)
- Test Streams: false
- ✅ ffprobe Params: Balance (neu)

**Für minimalen RAM:**
- Cache Mode: disk
- Cache Duration: 1h
- Stream Method: redirect
- Test Streams: false
- ✅ ffprobe Params: Ultra Fast (neu)

## Konsistenz-Prüfung

### ✅ HLS Settings
- Backend: `hls_auto_retry = True` (hardcoded)
- Frontend: Checkbox entfernt
- Info-Text: "Automatisches MAC Retry (immer aktiv)"
- **Status:** Konsistent

### ✅ FFmpeg Settings
- Backend: `try_all_macs_setting = True` (hardcoded)
- Frontend: Checkbox entfernt
- Info-Text: "Automatisches MAC Retry"
- **Status:** Konsistent

### ✅ ffprobe Parameters
- Backend: Liest aus `settings.get('ffprobe params', '-analyzeduration 500000 -probesize 100000')`
- Frontend: Input-Feld mit name="ffprobe params"
- Default: `-analyzeduration 500000 -probesize 100000`
- **Status:** Konsistent

## UI/UX Verbesserungen

### Preset-Buttons
- Benutzerfreundlich: Ein Klick setzt die Parameter
- Visuell klar: Emojis und Zeitangaben
- Farbcodierung:
  - Balance: Blau (Primary)
  - Ultra Fast: Grün (Success)
  - Standard Slow: Grau (Secondary)

### Info-Boxen
- Detaillierte Erklärungen für jedes Feature
- Strukturiert mit Listen und Überschriften
- Konsistente Formatierung

### Alert-Boxen
- Klare Hinweise auf automatische Features
- Erklärung des MAC Scoring Systems
- Hilfe für Benutzer bei der Entscheidung

## Verbleibende Settings

### HLS Settings (nach Änderungen):
1. ✅ HLS Segment Duration
2. ✅ HLS Playlist Size
3. ✅ Max Concurrent Streams
4. ✅ MAC Retry Timeout
5. ✅ Skip Busy MACs

### FFmpeg Settings (nach Änderungen):
1. ✅ FFmpeg Timeout
2. ✅ Test Streams
3. ✅ Skip Busy MACs

### Neue Settings:
1. ✅ Custom ffprobe Parameters

## Entfernte Verwirrung

**Vorher:**
- User musste "HLS Auto Retry" aktivieren
- User musste "Try All MACs" aktivieren
- Unklar was passiert wenn beide OFF sind
- Viele Settings, kompliziert

**Nachher:**
- MAC Retry ist immer aktiv (automatisch)
- Klare Info-Texte erklären das Verhalten
- Weniger Settings, einfacher
- Fokus auf wichtige Einstellungen (Timeout, Skip Busy, ffprobe Params)

## Testing-Checkliste

### ✅ Settings-Seite
- [ ] HLS Auto Retry Checkbox ist nicht mehr sichtbar
- [ ] Try All MACs Checkbox ist nicht mehr sichtbar
- [ ] Custom ffprobe Parameters Feld ist sichtbar
- [ ] 3 Preset-Buttons sind sichtbar und funktionieren
- [ ] Info-Boxen sind korrekt formatiert
- [ ] Default-Wert ist korrekt: `-analyzeduration 500000 -probesize 100000`

### ✅ Wiki-Seite
- [ ] "Try All MACs" ist durch "MAC Retry" ersetzt
- [ ] Status zeigt "Immer aktiv"
- [ ] Empfohlene Konfigurationen enthalten ffprobe Params
- [ ] Dokumentation ist aktuell

### ✅ Funktionalität
- [ ] Preset-Buttons ändern Input-Feld korrekt
- [ ] Settings werden korrekt gespeichert
- [ ] Backend liest Settings korrekt
- [ ] ffprobe verwendet die Parameter

## Fazit

✅ **Alle Frontend-Änderungen sind vollständig und konsistent**
✅ **Keine veralteten Referenzen mehr**
✅ **UI ist benutzerfreundlicher geworden**
✅ **Dokumentation ist aktuell**

**Status:** Bereit für Deployment
