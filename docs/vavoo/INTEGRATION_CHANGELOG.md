# Vavoo Integration Changelog

## Übersicht
Vollständige Integration von Vavoo IPTV Proxy in MacReplayXC v3.0.0 als Single-Container-Lösung.

---

## Geänderte Dateien

### 1. **start.sh** (NEU)
**Zweck:** Startup-Script für beide Anwendungen

**Änderungen:**
- Startet Vavoo im Hintergrund auf Port 4323
- Startet MacReplayXC im Vordergrund auf Port 8001
- Extrahiert `PUBLIC_HOST` aus `HOST` Environment-Variable

**Wichtig für Updates:**
- Reihenfolge beibehalten: Vavoo zuerst (background), dann MacReplayXC (foreground)

---

### 2. **vavoo/vavoo2.py**
**Änderungen:**

#### a) Environment Variables (Zeilen 1-10)
```python
PORT = int(os.getenv("VAVOO_PORT", "4323"))
PUBLIC_HOST = os.getenv("VAVOO_PUBLIC_HOST", "")
PLAYLIST_DIR = "/app/data/vavoo_playlists"
```

#### b) public_port() Funktion (Zeile ~920)
```python
def public_port():
    return PORT
```

#### c) Static Route (Zeile ~1798)
```python
@app.route("/static/<path:filename>")
def serve_static(filename):
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(static_dir, filename)
```

#### d) CSS Link Injection (Zeile ~2717)
```html
</style>
<link rel="stylesheet" href="/static/macreplay-theme.css">
</head>
```

**Wichtig für Updates:**
- Environment-Variablen beibehalten
- Static Route nicht entfernen
- CSS Link im HTML-Head beibehalten

---

### 3. **vavoo/static/macreplay-theme.css** (NEU)
**Zweck:** Tabler Dark Theme für Vavoo

**Wichtig für Updates:**
- Bei Theme-Änderungen in MacReplayXC: CSS anpassen

---

### 4. **app-docker.py**
**Änderungen:**

#### Vavoo Route (Zeile ~9467)
```python
@app.route("/vavoo_page")
@login_required
def vavoo_page():
    return render_template("vavoo.html")
```

**Wichtig für Updates:**
- Route beibehalten
- `@login_required` nicht entfernen

---

### 5. **templates/base.html**
**Änderungen:**

#### Navigation Link (Zeile ~100-130)
```html
<li class="nav-item">
    <a class="nav-link" href="/vavoo_page">
        <i class="ti ti-broadcast me-1"></i>
        Vavoo
    </a>
</li>
```

**Wichtig für Updates:**
- Vavoo-Link beibehalten
- Icon: `ti-broadcast`

---

### 6. **templates/vavoo.html** (NEU)
**Zweck:** iFrame-Integration

```html
<iframe src="http://localhost:4323" 
        style="width: 100%; height: 85vh; border: none;">
</iframe>
```

**Wichtig für Updates:**
- iFrame src bleibt `localhost:4323` (Container-intern)

---

### 7. **Dockerfile**
**Änderungen:**
- `COPY vavoo/ vavoo/`
- `COPY start.sh .`
- `EXPOSE 4323`
- `CMD ["./start.sh"]`

---

### 8. **docker-compose.yml**
**Änderungen:**
- Port Mapping: `4323:4323`
- HOST Environment Variable

---

### 9. **templates/wiki.html**
**Änderungen:**
- Erweiterte Vavoo-Sektion mit Setup-Anleitung

---

## Update-Checkliste

### MacReplayXC Updates
- [ ] `start.sh` prüfen
- [ ] `app-docker.py` → `/vavoo_page` Route beibehalten
- [ ] `templates/base.html` → Navigation beibehalten
- [ ] `Dockerfile` → Vavoo-Zeilen beibehalten
- [ ] `docker-compose.yml` → Port 4323 beibehalten

### Vavoo Updates
- [ ] `vavoo/vavoo2.py` → Environment-Variablen beibehalten
- [ ] `vavoo/vavoo2.py` → Static Route beibehalten
- [ ] `vavoo/vavoo2.py` → CSS Link beibehalten
- [ ] `vavoo/static/macreplay-theme.css` → Theme beibehalten

---

**Erstellt:** 2026-02-06  
**Version:** MacReplayXC v3.0.0 + Vavoo Integration
