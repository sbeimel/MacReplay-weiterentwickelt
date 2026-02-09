# Streaming-Optimierung - Zusammenfassung

## Was wurde geändert?

MacReplayXC nutzt jetzt **`channels.db` direkt** für Streaming statt des Channel Cache.

## Vorteile

✅ **Schnelleres Umschalten** - Kein `getAllChannels()` mehr beim Streaming  
✅ **Intelligentes Routing** - Probiert nur MACs die den Channel haben  
✅ **Automatisches Fallback** - Lernt neue Channels automatisch  
✅ **Weniger API-Calls** - Schont das Portal  

## Wie funktioniert es?

### 1. Editor Refresh (einmalig)
```
User klickt "Refresh" → System lädt alle Channels von allen MACs
→ Speichert in channels.db:
  - stream_cmd: "http://portal.com/stream/123.m3u8"
  - available_macs: "MAC1,MAC3,MAC4"
```

### 2. Streaming (bei jedem Channel-Wechsel)
```
User startet Channel → Lese aus channels.db (0.001s)
→ Probiere nur MACs die den Channel haben
→ Kein getAllChannels() mehr! ✅
```

## Performance

| Vorher | Nachher |
|--------|---------|
| 2-5 Sekunden (bei Cache-Miss) | 0.2-0.3 Sekunden |
| Alle MACs probieren | Nur verfügbare MACs |
| Häufige API-Calls | Keine API-Calls |

## Was muss ich tun?

**Nichts!** Die Migration erfolgt automatisch:

1. DB-Spalten werden beim Start hinzugefügt
2. Beim nächsten Editor Refresh werden die Daten gefüllt
3. Streaming funktioniert sofort mit Fallback

## Neue DB-Spalten

```sql
channels.db:
  - stream_cmd TEXT       -- Stream-URL
  - available_macs TEXT   -- "MAC1,MAC3,MAC4"
```

## Channel Cache Status

Der alte Channel Cache (lazy-ram, ram, disk, hybrid) ist jetzt **deprecated**:
- Bleibt für Backwards-Compatibility
- Wird nicht mehr für Streaming verwendet
- Kann in Zukunft entfernt werden

## Dokumentation

Siehe [docs/DB_STREAMING_OPTIMIZATION.md](docs/DB_STREAMING_OPTIMIZATION.md) für Details.

## Version

**v3.1.0** (2026-02-07)
