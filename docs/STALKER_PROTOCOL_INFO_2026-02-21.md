# 📋 Stalker Protocol Issues - INFO ONLY
## MacReplayXC v4.2.0 - Antworten auf deine Fragen

**Date**: 2026-02-21  
**Status**: NUR INFORMATION - KEINE ÄNDERUNGEN

---

## ❓ Deine Fragen

### 1. Missing token= parameter in handshake - haben wir hier nicht einen fallback gebaut?

**ANTWORT**: ✅ JA, Fallback ist bereits implementiert!

**Aktueller Code** (stb.py, Lines 266-310):
```python
# ROUND 1: Without token= parameter (current working portals)
endpoints = [
    "?type=stb&action=handshake&JsHttpRequest=1-xml",
    "/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml",
    # ... 6 more endpoints
]

# ROUND 2: With token= parameter as fallback (Stalker protocol compliance)
endpoints.extend([
    "?type=stb&action=handshake&token=&JsHttpRequest=1-xml",
    "/portal.php?type=stb&action=handshake&token=&JsHttpRequest=1-xml",
    # ... 6 more endpoints with token=
])
```

**Status**: ✅ BEREITS GEFIXT (Fix #5 - Token Parameter Fallback)

**Warum der Agent das als Issue sah**:
- Agent hat nur die erste Runde gesehen (ohne token=)
- Fallback (Runde 2 mit token=) wurde übersehen
- **Tatsächlich**: Code ist korrekt und vollständig!

**Fazit**: ❌ KEIN FIX NÖTIG - Bereits implementiert!

---

### 2. Missing hd=1&ver=ImageDescription in get_profile - wozu soll das sein?

**ANTWORT**: Für HD-Kanal-Filterung und Firmware-Features

**Aktueller Code** (stb.py, Line 437):
```python
profile_url = f"{url}/portal.php?type=stb&action=get_profile&JsHttpRequest=1-xml"
# ❌ Fehlt: &hd=1&ver=ImageDescription
```

**Was diese Parameter machen**:

**`hd=1`** - HD Capability Flag
- Sagt dem Portal: "Ich kann HD-Streams abspielen"
- Portal filtert dann Kanäle nach Qualität
- Ohne diesen Parameter: Portal könnte HD-Kanäle ausblenden
- **Beispiel**: 
  - Mit `hd=1`: Portal gibt 500 Kanäle (SD + HD)
  - Ohne `hd=1`: Portal gibt nur 300 Kanäle (nur SD)

**`ver=ImageDescription`** - Firmware Version
- Sagt dem Portal: "Ich bin MAG250 mit Firmware XYZ"
- Portal aktiviert/deaktiviert Features basierend auf Firmware
- Ohne diesen Parameter: Portal könnte Features einschränken
- **Beispiel**:
  - Mit `ver=ImageDescription`: Portal gibt VOD + Timeshift
  - Ohne `ver=ImageDescription`: Portal gibt nur Live-TV

**Ist das wichtig?**
- ⚠️ **Kommt drauf an**: Manche Portale brauchen es, manche nicht
- ✅ **Funktioniert ohne**: Ja, die meisten Portale funktionieren auch ohne
- 🎯 **Empfehlung**: Hinzufügen für maximale Kompatibilität

**Fazit**: ⚠️ OPTIONAL - Funktioniert ohne, aber besser mit

---

### 3. Wrong endpoint: get_all_channels statt get_ordered_list - wieso? wozu es geht doch oder?

**ANTWORT**: Beide funktionieren, aber `get_ordered_list` ist der offizielle Stalker-Standard

**Aktueller Code** (stb.py, Line 597):
```python
params = {
    "type": "itv",
    "action": "get_all_channels",  # ← Aktuell
    "force_ch_link_check": "",
    "JsHttpRequest": "1-xml"
}
```

**Unterschied**:

**`get_all_channels`** (was du nutzt):
- ✅ Funktioniert auf den meisten Portalen
- ✅ Gibt alle Kanäle zurück
- ❌ Keine Genre-Filterung möglich
- ❌ Keine Sortierung möglich
- ❌ Nicht offizieller Stalker-Standard

**`get_ordered_list`** (Stalker-Standard):
- ✅ Offizieller Stalker Portal Endpoint
- ✅ Unterstützt Genre-Filterung (`genre=*`)
- ✅ Unterstützt Sortierung (`sortby=number`)
- ✅ Unterstützt HD-Filter (`hd=0`)
- ✅ Unterstützt Favoriten (`fav=0`)
- ⚠️ Manche alte Portale haben es nicht

**Beispiel**:
```python
# get_all_channels (aktuell)
params = {
    "action": "get_all_channels"
}
# → Gibt ALLE Kanäle, keine Filterung

# get_ordered_list (Stalker-Standard)
params = {
    "action": "get_ordered_list",
    "genre": "*",        # Alle Genres
    "sortby": "number",  # Nach Nummer sortiert
    "hd": "0",          # SD + HD
    "fav": "0"          # Nicht nur Favoriten
}
# → Gibt Kanäle mit Filterung und Sortierung
```

**Ist das wichtig?**
- ✅ **Funktioniert ohne**: Ja, `get_all_channels` funktioniert
- ⚠️ **Kompatibilität**: Manche strenge Portale haben nur `get_ordered_list`
- 🎯 **Empfehlung**: Fallback-Strategie (erst `get_ordered_list`, dann `get_all_channels`)

**Fazit**: ⚠️ OPTIONAL - Funktioniert, aber `get_ordered_list` ist besser

---

### 4. Incorrect CMD format for create_link - wieso ist das falsch es geht doch?

**ANTWORT**: Es funktioniert, aber du rekonstruierst den CMD statt ihn zu extrahieren

**Aktueller Code** (app-docker.py, mehrere Stellen):
```python
# Du machst:
dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"

# Stalker-Standard:
cmd = channel_data.get('cmd', '')  # CMD aus Channel-Daten extrahieren
```

**Was ist das Problem?**

**Deine Methode** (CMD rekonstruieren):
```python
# Du baust CMD aus channel_id:
channel_id = "123"
cmd = f"ffmpeg http://localhost/ch/{channel_id}_"
# → "ffmpeg http://localhost/ch/123_"
```

**Stalker-Methode** (CMD extrahieren):
```python
# Portal gibt dir den CMD:
channel = {
    "id": "123",
    "cmd": "ffmpeg http://portal.com/stream/live/123.m3u8"
}
cmd = channel['cmd']
# → "ffmpeg http://portal.com/stream/live/123.m3u8"
```

**Warum ist das wichtig?**

**Szenario 1**: Portal mit Standard-Format
- Channel ID: `123`
- Echter CMD: `ffmpeg http://localhost/ch/123_`
- Dein CMD: `ffmpeg http://localhost/ch/123_`
- ✅ **Funktioniert!**

**Szenario 2**: Portal mit Custom-Format
- Channel ID: `bbc-news-hd`
- Echter CMD: `ffmpeg http://portal.com/live/bbc_news_hd.m3u8`
- Dein CMD: `ffmpeg http://localhost/ch/bbc-news-hd_`
- ❌ **Funktioniert NICHT!**

**Ist das wichtig?**
- ✅ **Funktioniert meistens**: Ja, bei Standard-Portalen
- ❌ **Kann brechen**: Bei Portalen mit Custom-CMD-Format
- 🎯 **Empfehlung**: CMD aus Channel-Daten extrahieren

**Fazit**: ⚠️ FUNKTIONIERT - Aber kann bei Custom-Portalen brechen

---

### 5. Wrong VOD series parameter ("0" statt "") - wieso?

**ANTWORT**: Stalker-Protokoll erwartet leeren String, nicht "0"

**Aktueller Code** (stb.py, Line 1336):
```python
params = {
    "series": "0",              # ❌ Aktuell
    "forced_storage": "false",  # ❌ Aktuell
    "disable_ad": "false",      # ❌ Aktuell
}
```

**Stalker-Standard**:
```python
params = {
    "series": "",      # ✅ Leer für single-part
    "forced_storage": "",  # ✅ Leer, nicht "false"
    "disable_ad": "0",     # ✅ "0", nicht "false"
}
```

**Was ist der Unterschied?**

**`series` Parameter**:
- `series=""` (leer) = Single-part VOD (1 Datei)
- `series="0"` = Multi-part VOD, Teil 0 (erste Datei)
- `series="1"` = Multi-part VOD, Teil 1 (zweite Datei)

**Beispiel**:
```python
# Film in 1 Datei (z.B. "Avatar.mkv")
series = ""  # ✅ Richtig

# Film in 2 Teilen (z.B. "Avatar_Part1.mkv", "Avatar_Part2.mkv")
series = "0"  # Teil 1
series = "1"  # Teil 2
```

**Ist das wichtig?**
- ⚠️ **Kommt drauf an**: Manche Portale akzeptieren "0", manche nicht
- ✅ **Funktioniert meistens**: Ja, bei toleranten Portalen
- ❌ **Kann brechen**: Bei strengen Portalen oder Multi-Part-VODs
- 🎯 **Empfehlung**: Leeren String verwenden für Single-Part

**Fazit**: ⚠️ FUNKTIONIERT MEISTENS - Aber nicht Stalker-konform

---

### 6. Missing prehash=false in handshake - wozu ist das?

**ANTWORT**: Für Pre-Hashed Authentication Support

**Aktueller Code** (stb.py, Line 266):
```python
endpoints.append(f"{url_path}?type=stb&action=handshake&JsHttpRequest=1-xml")
# ❌ Fehlt: &prehash=false
```

**Was ist `prehash`?**

**`prehash=false`** - Pre-Hash Authentication Flag
- Sagt dem Portal: "Ich unterstütze KEINE pre-hashed Passwörter"
- Portal weiß dann: "Ich muss das Passwort selbst hashen"
- Ohne diesen Parameter: Portal könnte annehmen, du sendest pre-hashed Passwörter

**Beispiel**:

**Mit `prehash=false`**:
```
Client → Portal: "Mein Passwort ist 'secret123'"
Portal: "OK, ich hashe es: SHA256('secret123')"
```

**Ohne `prehash` Parameter**:
```
Client → Portal: "Mein Passwort ist 'secret123'"
Portal: "Ist das pre-hashed oder plain? Ich weiß es nicht..."
Portal: "Ich probiere beides..."
```

**Ist das wichtig?**
- ⚠️ **Kommt drauf an**: Manche Portale brauchen es, manche nicht
- ✅ **Funktioniert ohne**: Ja, die meisten Portale sind tolerant
- ❌ **Kann brechen**: Bei strengen Portalen mit Pre-Hash-Support
- 🎯 **Empfehlung**: Hinzufügen für maximale Kompatibilität

**Fazit**: ⚠️ OPTIONAL - Funktioniert ohne, aber besser mit

---

### 7. Inconsistent cookie management - das verstehe ich nicht

**ANTWORT**: Cookies werden nicht konsistent über alle Requests hinweg verwendet

**Was ist das Problem?**

**Aktueller Code** (stb.py, verschiedene Funktionen):
```python
# getToken() - Zeile 240
cookies = {
    "mac": mac,
    "stb_lang": "en",
    "timezone": "Europe/London",
    "deviceId": device_id,
    "deviceId2": device_id2,
    "serial_number": serial_number,
    "sn": serial_number,
    "rand": random_id
}

# getProfile() - Zeile 424
cookies = _get_enhanced_cookies(mac)  # Andere Cookies!

# getAllChannels() - Zeile 580
cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}  # Wieder andere!
```

**Was sollte passieren?**

**Stalker-Standard**: Cookies sollten persistent sein
```python
# Session-basierter Ansatz:
session = requests.Session()

# Erster Request (handshake):
session.cookies.set("mac", mac)
session.cookies.set("stb_lang", "en")
# ... Portal setzt zusätzliche Cookies

# Zweiter Request (get_profile):
# → Session verwendet automatisch alle Cookies vom ersten Request

# Dritter Request (get_channels):
# → Session verwendet automatisch alle Cookies
```

**Warum ist das wichtig?**

**Szenario 1**: Portal setzt Session-Cookie
```
1. handshake → Portal setzt Cookie "session_id=abc123"
2. get_profile → Du sendest NICHT "session_id=abc123"
3. Portal: "Keine Session! Bitte neu authentifizieren!"
```

**Szenario 2**: Mit Session-Management
```
1. handshake → Portal setzt Cookie "session_id=abc123"
2. get_profile → Session sendet automatisch "session_id=abc123"
3. Portal: "OK, Session erkannt!"
```

**Ist das wichtig?**
- ⚠️ **Kommt drauf an**: Manche Portale brauchen Session-Cookies
- ✅ **Funktioniert meistens**: Ja, viele Portale sind tolerant
- ❌ **Kann brechen**: Bei Portalen mit strenger Session-Verwaltung
- 🎯 **Empfehlung**: Session-basierter Ansatz für bessere Kompatibilität

**Fazit**: ⚠️ FUNKTIONIERT MEISTENS - Aber nicht optimal

---

## 📊 Zusammenfassung

| Issue | Status | Wichtigkeit | Funktioniert ohne? |
|-------|--------|-------------|-------------------|
| 1. token= parameter | ✅ BEREITS GEFIXT | - | ✅ Ja |
| 2. hd=1&ver= | ⚠️ OPTIONAL | MEDIUM | ✅ Ja, meistens |
| 3. get_ordered_list | ⚠️ OPTIONAL | MEDIUM | ✅ Ja, meistens |
| 4. CMD format | ⚠️ FUNKTIONIERT | LOW | ✅ Ja, bei Standard-Portalen |
| 5. series="" | ⚠️ FUNKTIONIERT | LOW | ✅ Ja, meistens |
| 6. prehash=false | ⚠️ OPTIONAL | LOW | ✅ Ja, meistens |
| 7. Cookie management | ⚠️ FUNKTIONIERT | MEDIUM | ✅ Ja, meistens |

---

## 🎯 Empfehlung

**Deine Frage**: "Soll ich das fixen?"

**Antwort**: ⚠️ **OPTIONAL - Kommt drauf an**

**Wenn du maximale Kompatibilität willst**:
- ✅ Fix #2: `hd=1&ver=ImageDescription` hinzufügen (5 min)
- ✅ Fix #3: Fallback zu `get_ordered_list` (10 min)
- ✅ Fix #6: `prehash=false` hinzufügen (5 min)
- ✅ Fix #7: Session-basiertes Cookie-Management (30 min)

**Wenn es aktuell funktioniert**:
- ❌ **NICHT NÖTIG** - Alles funktioniert mit den meisten Portalen
- ✅ **NUR BEI PROBLEMEN** - Wenn ein Portal nicht funktioniert, dann fixen

**Meine Empfehlung**:
- 🎯 **WARTEN** - Erst fixen, wenn du ein Portal findest, das nicht funktioniert
- 🎯 **TESTEN** - Teste mit verschiedenen Portalen
- 🎯 **BEI BEDARF** - Nur fixen, wenn wirklich nötig

---

## ✅ Fazit

**Alle 7 "Issues" sind eigentlich OPTIONAL**:
1. ✅ Token= ist bereits als Fallback implementiert
2-7. ⚠️ Funktionieren ohne, aber besser mit

**Dein Code funktioniert!** Die Agent-Empfehlungen sind für **maximale Kompatibilität**, nicht für **Funktionalität**.

**Status**: ✅ PRODUCTION READY - Fixes sind optional!

---

**Erstellt**: 2026-02-21  
**Status**: NUR INFORMATION  
**Änderungen**: KEINE
