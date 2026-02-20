# Docker "exec ./start.sh: no such file or directory" - Fix

## Problem

```
exec ./start.sh: no such file or directory
```

**Ursache:** Windows-Zeilenumbrüche (CRLF) in `start.sh` statt Unix (LF)

---

## ✅ Lösung 1: Python Entrypoint (Empfohlen)

**Bereits implementiert!** Das Dockerfile verwendet jetzt `entrypoint.py` statt `start.sh`.

### Vorteile:
- ✅ Keine Zeilenumbruch-Probleme
- ✅ Funktioniert auf Windows, Linux, Mac
- ✅ Kein Bash erforderlich
- ✅ Bessere Fehlerbehandlung

### Rebuild:
```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## ✅ Lösung 2: start.sh mit fixen Zeilenumbrüchen

**Auch implementiert!** Das Dockerfile konvertiert automatisch CRLF → LF.

### Im Dockerfile:
```dockerfile
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh
```

### Manuell umschalten:
```dockerfile
# In Dockerfile, letzte Zeile ändern:
CMD ["./start.sh"]  # Statt entrypoint.py
```

---

## ✅ Lösung 3: Lokale Datei-Konvertierung (Optional)

### Windows (Git Bash):
```bash
dos2unix start.sh
# oder
sed -i 's/\r$//' start.sh
```

### Windows (PowerShell):
```powershell
(Get-Content start.sh -Raw) -replace "`r`n", "`n" | Set-Content start.sh -NoNewline
```

### Linux/Mac:
```bash
dos2unix start.sh
# oder
sed -i 's/\r$//' start.sh
```

---

## 🔍 Diagnose

### Prüfe Zeilenumbrüche:
```bash
# Windows (PowerShell)
Get-Content start.sh -Raw | Format-Hex

# Linux/Mac
file start.sh
# Erwartete Ausgabe: "ASCII text" (nicht "ASCII text, with CRLF line terminators")
```

### Prüfe ob Datei existiert im Container:
```bash
docker-compose run --rm macreplayxc ls -la /app/start.sh
docker-compose run --rm macreplayxc cat /app/start.sh
```

---

## 📋 Aktueller Status

**✅ Problem behoben!**

Das Dockerfile verwendet jetzt:
1. **Python Entrypoint** (Standard) - Keine Zeilenumbruch-Probleme
2. **Automatische CRLF→LF Konvertierung** für start.sh (Fallback)

### Beide Optionen funktionieren:
```dockerfile
# Option 1 (Standard):
CMD ["python3", "entrypoint.py"]

# Option 2 (Alternative):
CMD ["./start.sh"]
```

---

## 🚀 Deployment

```bash
# 1. Stoppe Container
docker-compose down

# 2. Rebuild (mit --no-cache für sauberen Build)
docker-compose build --no-cache

# 3. Starte Container
docker-compose up -d

# 4. Prüfe Logs
docker-compose logs -f
```

**Erwartete Ausgabe:**
```
🚀 Starting MacReplayXC + Vavoo...
📡 Vavoo public host: 0.0.0.0:4323
📡 Starting Vavoo on port 4323...
✅ Vavoo started (PID: XX)
🎬 Starting MacReplayXC on port 8001...
[INFO] MacReplayXC v3.0.0 - Logging initialized
```

---

## 🔧 Troubleshooting

### Problem: Immer noch "no such file or directory"

**Lösung A: Prüfe .dockerignore**
```bash
# Stelle sicher, dass start.sh NICHT ignoriert wird
cat .dockerignore | grep start.sh
# Sollte NICHTS ausgeben
```

**Lösung B: Prüfe ob Datei kopiert wurde**
```bash
docker-compose build
docker-compose run --rm macreplayxc ls -la /app/
# Sollte start.sh und entrypoint.py zeigen
```

**Lösung C: Verwende Python Entrypoint**
```dockerfile
# In Dockerfile, letzte Zeile:
CMD ["python3", "entrypoint.py"]  # ✅ Funktioniert immer
```

---

## 💡 Warum passiert das?

**Windows vs. Unix Zeilenumbrüche:**

| System | Zeilenumbruch | Hex |
|--------|---------------|-----|
| Windows | CRLF (`\r\n`) | `0D 0A` |
| Unix/Linux | LF (`\n`) | `0A` |
| Mac (alt) | CR (`\r`) | `0D` |

**Problem:**
- Windows-Editor speichert mit CRLF
- Docker-Container ist Linux (erwartet LF)
- Bash interpretiert `\r` als Teil des Dateinamens
- `./start.sh\r` existiert nicht → Fehler

**Lösung:**
- Konvertiere CRLF → LF im Dockerfile
- Oder verwende Python (keine Zeilenumbruch-Probleme)

---

## ✅ Empfehlung

**Verwende Python Entrypoint:**
- Keine Zeilenumbruch-Probleme
- Plattform-unabhängig
- Bessere Fehlerbehandlung
- Einfacher zu debuggen

**Bereits aktiviert im Dockerfile!** 🎉

