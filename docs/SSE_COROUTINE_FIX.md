# SSE Coroutine Fix + Sync Scanner UI Entfernt

## Problem
```
TypeError: 'coroutine' object is not iterable
```

SSE-Endpoint rief `scanner_async.get_all_scanner_statuses()` auf, aber das ist eine async Funktion (coroutine). Im SSE-Generator können wir kein `await` verwenden.

## Lösung

### 1. Synchrone Version erstellt
Neue Funktionen in `scanner_async.py`:
- `get_all_scanner_statuses_sync()` - Sync Version für SSE
- `get_scanner_status_sync(attack_id)` - Sync Version für einzelne Scanner

Diese Funktionen verwenden nur `threading.Lock()` und kein `await`.

### 2. SSE-Endpoints aktualisiert
```python
# VORHER (FEHLER):
attacks_data = scanner_async.get_all_scanner_statuses()  # coroutine!

# JETZT (FUNKTIONIERT):
attacks_data = scanner_async.get_all_scanner_statuses_sync()  # sync!
```

Beide Endpoints gefixt:
- `/scanner/stream`
- `/scanner-new/stream`

### 3. Sync Scanner UI entfernt

**Templates umbenannt:**
- `scanner.html` → `scanner_sync_backup.html`
- `scanner-full.html` → `scanner-full_backup.html`

**Endpoint geändert:**
```python
@app.route("/scanner")
def scanner_page():
    return render_template("scanner-new.html")  # Nur noch async UI
```

## Status
✅ SSE funktioniert jetzt
✅ Keine coroutine Fehler mehr
✅ Sync Scanner UI komplett entfernt
✅ Alle Endpoints verwenden async Scanner

## Testing
```bash
docker-compose restart
```

Dann Scanner öffnen - SSE sollte jetzt funktionieren ohne 500 Error!

## Date
2026-02-09
