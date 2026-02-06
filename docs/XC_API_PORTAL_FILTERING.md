# XC API Portal Filtering

## Übersicht

Die XC API unterstützt Portal-Filterung über den `portal_id` Parameter. Sie können entweder die **Portal-ID** oder den **Portal-Namen** verwenden.

## Unterstützte Endpunkte

### M3U Playlist

**Basis-URL:**
```
http://your-server:8001/get.php
```

**Mit Portal-Filter:**
```
http://your-server:8001/get.php?username=USER&password=PASS&type=m3u_plus&output=ts&portal_id=PORTAL_ID
```

**ODER mit Portal-Name:**
```
http://your-server:8001/get.php?username=USER&password=PASS&type=m3u_plus&output=ts&portal_id=My Portal
```

## Parameter

| Parameter | Erforderlich | Beschreibung | Beispiel |
|-----------|--------------|--------------|----------|
| `username` | ✅ Ja | XC API Benutzername | `test` |
| `password` | ✅ Ja | XC API Passwort | `test123` |
| `type` | ❌ Nein | Playlist-Typ | `m3u_plus` (Standard) |
| `output` | ❌ Nein | Output-Format | `ts` oder `m3u8` |
| `portal_id` | ❌ Nein | Portal-ID oder Portal-Name | `portal_1` oder `My Portal` |

## Portal-Identifikation

### Methode 1: Portal-ID (Empfohlen)

Die Portal-ID ist die eindeutige ID, die beim Anlegen des Portals generiert wird.

**Wo finde ich die Portal-ID?**
- In der URL beim Bearbeiten eines Portals: `/portals?portal_id=portal_1`
- In der Datenbank: `MacReplayXC.json` → `portals` → Key

**Beispiel:**
```
http://your-server:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=portal_1
```

**Vorteile:**
- ✅ Eindeutig
- ✅ Schneller (keine Namensauflösung)
- ✅ Keine Probleme mit Sonderzeichen

### Methode 2: Portal-Name

Der Portal-Name ist der Name, den Sie beim Anlegen des Portals vergeben haben.

**Wo finde ich den Portal-Namen?**
- In der Portal-Liste: Portals → "Name" Spalte
- Beim Bearbeiten eines Portals: "Portal Name" Feld

**Beispiel:**
```
http://your-server:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=My%20Portal
```

**Wichtig:**
- ⚠️ Leerzeichen müssen URL-encoded werden: `My Portal` → `My%20Portal`
- ⚠️ Groß-/Kleinschreibung wird ignoriert: `my portal` = `My Portal`
- ⚠️ Bei mehreren Portalen mit gleichem Namen wird das erste gefunden

**Vorteile:**
- ✅ Lesbarer
- ✅ Einfacher zu merken

**Nachteile:**
- ❌ Muss URL-encoded werden
- ❌ Langsamer (Namensauflösung)
- ❌ Nicht eindeutig bei doppelten Namen

## Beispiele

### Beispiel 1: Alle Portale (kein Filter)

```bash
curl "http://localhost:8001/get.php?username=test&password=test&type=m3u_plus&output=ts"
```

**Ergebnis:** Playlist mit Kanälen von **allen** erlaubten Portalen

### Beispiel 2: Einzelnes Portal (Portal-ID)

```bash
curl "http://localhost:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=portal_1"
```

**Ergebnis:** Playlist mit Kanälen **nur** von Portal `portal_1`

### Beispiel 3: Einzelnes Portal (Portal-Name)

```bash
curl "http://localhost:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=Sky%20Germany"
```

**Ergebnis:** Playlist mit Kanälen **nur** von Portal "Sky Germany"

### Beispiel 4: Portal nicht gefunden

```bash
curl "http://localhost:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=NonExistent"
```

**Ergebnis:** Leere Playlist (keine Kanäle)

## Verwendung in IPTV-Playern

### VLC

**Netzwerkstream öffnen:**
```
http://your-server:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=portal_1
```

### Kodi (PVR IPTV Simple Client)

**M3U Playlist URL:**
```
http://your-server:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=My%20Portal
```

### TiviMate

**Playlist hinzufügen:**
- Typ: `Xtream Codes API`
- Server: `http://your-server:8001`
- Username: `test`
- Password: `test`
- Playlist URL: Manuell mit `portal_id` Parameter

**Hinweis:** TiviMate unterstützt keine direkten URL-Parameter. Verwenden Sie stattdessen die Portal-spezifische Route:
```
http://your-server:8001/portal/portal_1/get.php?username=test&password=test&type=m3u_plus&output=ts
```

### Plex

**Live TV & DVR → Tuner hinzufügen:**
```
http://your-server:8001/get.php?username=test&password=test&type=m3u_plus&output=ts&portal_id=portal_1
```

## Technische Details

### Namensauflösung

Die Namensauflösung erfolgt **case-insensitive** (Groß-/Kleinschreibung wird ignoriert):

```python
# Alle diese Varianten funktionieren:
portal_id=My Portal
portal_id=my portal
portal_id=MY PORTAL
portal_id=mY pOrTaL
```

### Priorität

1. **Exakte Portal-ID Match** (schnell)
2. **Portal-Name Match** (case-insensitive, langsamer)
3. **Nicht gefunden** → Leere Playlist

### Logging

Bei Verwendung des Portal-Namens wird ein Log-Eintrag erstellt:

```
[INFO] Resolved portal name 'My Portal' to portal ID 'portal_1'
```

Bei nicht gefundenem Portal:

```
[WARNING] Portal identifier 'NonExistent' not found (tried ID and Name)
```

## Best Practices

### Empfohlen ✅

1. **Verwenden Sie Portal-IDs** für maximale Performance
2. **URL-encode** alle Parameter (besonders bei Leerzeichen)
3. **Testen Sie** die URL im Browser vor der Verwendung in Playern
4. **Dokumentieren Sie** die Portal-IDs für Ihre Benutzer

### Nicht empfohlen ❌

1. ❌ Portal-Namen mit Sonderzeichen (z.B. `&`, `?`, `#`)
2. ❌ Sehr lange Portal-Namen (> 50 Zeichen)
3. ❌ Doppelte Portal-Namen (nicht eindeutig)
4. ❌ Portal-Namen ohne URL-Encoding

## Fehlerbehebung

### Problem: Leere Playlist

**Ursache:** Portal-ID/Name nicht gefunden

**Lösung:**
1. Prüfen Sie die Portal-ID in der Portal-Liste
2. Prüfen Sie die Groß-/Kleinschreibung (sollte egal sein, aber testen)
3. Prüfen Sie URL-Encoding (Leerzeichen = `%20`)
4. Prüfen Sie die Logs: `/log`

### Problem: Falsche Kanäle

**Ursache:** Falsches Portal ausgewählt

**Lösung:**
1. Prüfen Sie die Portal-ID/Name
2. Prüfen Sie, ob mehrere Portale den gleichen Namen haben
3. Verwenden Sie Portal-ID statt Name

### Problem: "XC API is disabled"

**Ursache:** XC API ist deaktiviert

**Lösung:**
1. Settings → "Xtream Codes API" → "Enable XC API" aktivieren
2. Speichern und neu versuchen

### Problem: "Invalid credentials"

**Ursache:** Falsche XC API Zugangsdaten

**Lösung:**
1. XC Users → Prüfen Sie Username/Password
2. Erstellen Sie ggf. einen neuen XC User
3. Prüfen Sie, ob der User Zugriff auf das Portal hat

## Weitere Informationen

- [XC API Dokumentation](README.md#xc-api-endpoints)
- [Portal Management](README.md#add-portal)
- [XC Users Management](README.md#xc-api-users)
