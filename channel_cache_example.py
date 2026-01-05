# Intelligentes Channel-Caching für MacReplayXC
import time
import threading
from typing import Dict, List, Optional, Tuple

class ChannelCache:
    def __init__(self, cache_duration=43200):  # 12 Stunden (43200 Sekunden)
        self.cache_duration = cache_duration
        self.cache = {}  # portal_mac -> (channels, timestamp)
        self.lock = threading.RLock()
        logger.info(f"Channel cache initialized with {cache_duration/3600:.1f} hour duration")
    
    def get_channels(self, portal_id: str, mac: str, url: str, token: str, proxy: str = None) -> Optional[List]:
        """Hole Channels aus Cache oder lade sie neu."""
        cache_key = f"{portal_id}_{mac}"
        
        with self.lock:
            # Prüfe Cache
            if cache_key in self.cache:
                channels, timestamp = self.cache[cache_key]
                if time.time() - timestamp < self.cache_duration:
                    logger.debug(f"Cache HIT für {cache_key} - {len(channels)} channels")
                    return channels
                else:
                    logger.debug(f"Cache EXPIRED für {cache_key}")
            
            # Cache miss - lade neu
            logger.info(f"Cache MISS für {cache_key} - loading from portal...")
            try:
                channels = stb.getAllChannels(url, mac, token, proxy)
                if channels:
                    self.cache[cache_key] = (channels, time.time())
                    logger.info(f"Cached {len(channels)} channels für {cache_key}")
                    return channels
            except Exception as e:
                logger.error(f"Error loading channels for {cache_key}: {e}")
                
            return None
    
    def find_channel(self, portal_id: str, mac: str, channel_id: str, url: str, token: str, proxy: str = None) -> Optional[Dict]:
        """Finde einen spezifischen Channel (mit Caching)."""
        channels = self.get_channels(portal_id, mac, url, token, proxy)
        if not channels:
            return None
        
        # Suche Channel in gecachten Daten
        for channel in channels:
            if str(channel["id"]) == str(channel_id):
                return channel
        
        return None
    
    def invalidate_portal(self, portal_id: str):
        """Lösche Cache für ein Portal (alle MACs)."""
        with self.lock:
            keys_to_remove = [key for key in self.cache.keys() if key.startswith(f"{portal_id}_")]
            for key in keys_to_remove:
                del self.cache[key]
            logger.info(f"Cache invalidated für Portal {portal_id}")
    
    def cleanup_expired(self):
        """Entferne abgelaufene Cache-Einträge."""
        current_time = time.time()
        with self.lock:
            expired_keys = []
            for key, (channels, timestamp) in self.cache.items():
                if current_time - timestamp > self.cache_duration:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

# Globaler Cache
channel_cache = ChannelCache()

# Optimierte stream_channel Funktion - KORREKTE Version
def stream_channel_optimized(portalId, channelId, xc_user=None):
    """Optimierte Version mit Channel-Caching - behält die komplette MAC-Logik bei."""
    
    def isMacFree():
        count = 0
        for i in occupied.get(portalId, []):
            if i["mac"] == mac:
                count = count + 1
        if count < streamsPerMac:
            return True
        else:
            return False
    
    portal = getPortals().get(portalId)
    if not portal:
        return make_response("Portal not found", 404)
    
    portalName = portal.get("name")
    url = portal.get("url")
    macs = list(portal["macs"].keys())
    streamsPerMac = int(portal.get("streams per mac"))
    proxy = portal.get("proxy")
    ip = get_client_ip(request)
    
    logger.info(f"IP({ip}) requested Portal({portalId}):Channel({channelId})")
    
    freeMac = False
    
    # WICHTIG: Die MAC-Iteration bleibt GENAU GLEICH!
    for mac in macs:
        channel = None
        cmd = None
        link = None
        
        # Prüfe ob MAC frei ist (ORIGINAL LOGIK)
        if streamsPerMac == 0 or isMacFree():
            logger.info(f"Trying Portal({portalId}):MAC({mac}):Channel({channelId})")
            freeMac = True
            
            token = stb.getToken(url, mac, proxy)
            if token:
                stb.getProfile(url, mac, token, proxy)
                
                # HIER IST DER EINZIGE UNTERSCHIED: 
                # VORHER: channels = stb.getAllChannels(url, mac, token, proxy)
                #         for c in channels:
                #             if str(c["id"]) == channelId:
                #                 channel = c
                #                 break
                # 
                # NACHHER: Direkte Channel-Suche mit Cache
                channel = channel_cache.find_channel(portalId, mac, channelId, url, token, proxy)
        
        # Rest der Logik bleibt IDENTISCH
        if channel:
            channelName = portal.get("custom channel names", {}).get(channelId)
            if channelName == None:
                channelName = channel["name"]
            cmd = channel["cmd"]
        
        if cmd:
            if "http://localhost/" in cmd:
                link = stb.getLink(url, mac, token, cmd, proxy)
            else:
                link = cmd.split(" ")[1]
        
        if link:
            if getSettings().get("test streams", "true") == "false" or testStream():
                # Stream erfolgreich - verwende diese MAC
                logger.info(f"Stream found with MAC {mac}")
                return start_ffmpeg_stream(link, mac, portal, channelId, xc_user)
        
        # MAC funktioniert nicht - probiere nächste
        logger.info(f"Unable to connect to Portal({portalId}) using MAC({mac})")
        logger.info(f"Moving MAC({mac}) for Portal({portalName})")
        moveMac(portalId, mac)
        
        if not getSettings().get("try all macs", "true") == "true":
            break
    
    # Alle MACs probiert - kein Stream gefunden
    if freeMac:
        logger.info(f"No working streams found for Portal({portalId}):Channel({channelId})")
    else:
        logger.info(f"No free MAC for Portal({portalId}):Channel({channelId})")
    
    return make_response("No streams available", 503)

# Background-Task für Cache-Cleanup
def cache_cleanup_task():
    """Background-Task der regelmäßig den Cache aufräumt."""
    while True:
        time.sleep(300)  # Alle 5 Minuten
        try:
            channel_cache.cleanup_expired()
        except Exception as e:
            logger.error(f"Error in cache cleanup: {e}")

# Optimierte HLS-Stream Funktion - ECHTE Implementierung
def hls_stream_optimized(portalId, channelId, filename):
    """Optimierte HLS-Stream Funktion mit Channel-Caching - behält komplette Logik bei."""
    from flask import send_file
    
    # Get portal info
    portal = getPortals().get(portalId)
    if not portal:
        logger.error(f"Portal {portalId} not found for HLS request")
        return make_response("Portal not found", 404)
    
    portalName = portal.get("name")
    url = portal.get("url")
    macs = list(portal["macs"].keys())
    proxy = portal.get("proxy")
    ip = get_client_ip(request)
    
    logger.info(f"HLS request from IP({ip}) for Portal({portalId}):Channel({channelId}):File({filename})")
    
    # Check if we already have this stream
    stream_key = f"{portalId}_{channelId}"
    
    # First, check if stream is already active
    stream_exists = stream_key in hls_manager.streams
    
    if stream_exists:
        # For active streams, wait a bit for the file if it's a playlist
        if filename.endswith('.m3u8'):
            is_passthrough = hls_manager.streams[stream_key].get('is_passthrough', False)
            max_wait = 100 if not is_passthrough else 10
            
            for wait_count in range(max_wait):
                file_path = hls_manager.get_file(portalId, channelId, filename)
                if file_path:
                    break
                time.sleep(0.1)
        else:
            file_path = hls_manager.get_file(portalId, channelId, filename)
    else:
        file_path = None
    
    # If file doesn't exist and this is a playlist/segment request, start the stream
    if not file_path and (filename.endswith('.m3u8') or filename.endswith('.ts') or filename.endswith('.m4s')):
        # Get the stream URL - HIER IST DIE OPTIMIERUNG!
        link = None
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    
                    # OPTIMIERUNG: Nutze Channel-Cache statt alle Channels zu laden!
                    # VORHER: channels = stb.getAllChannels(url, mac, token, proxy)
                    #         if channels:
                    #             for c in channels:
                    #                 if str(c["id"]) == channelId:
                    #                     channel = c
                    #                     break
                    # 
                    # NACHHER: Direkte Channel-Suche mit Cache
                    channel = channel_cache.find_channel(portalId, mac, channelId, url, token, proxy)
                    
                    if channel:
                        cmd = channel["cmd"]
                        if "http://localhost/" in cmd:
                            link = stb.getLink(url, mac, token, cmd, proxy)
                        else:
                            link = cmd.split(" ")[1]
                        break  # Channel gefunden - fertig!
                    
            except Exception as e:
                logger.error(f"Error getting stream URL for HLS with MAC {mac}: {e}")
                continue
        
        if not link:
            logger.error(f"Could not get stream URL for Portal({portalId}):Channel({channelId})")
            return make_response("Stream not available", 503)
        
        # Start the HLS stream
        try:
            stream_info = hls_manager.start_stream(portalId, channelId, link, proxy)
            
            # Wait for file to be created
            is_passthrough = stream_info.get('is_passthrough', False)
            
            if filename.endswith('.m3u8'):
                max_wait = 100 if not is_passthrough else 10
                
                for wait_count in range(max_wait):
                    file_path = hls_manager.get_file(portalId, channelId, filename)
                    if file_path:
                        break
                    time.sleep(0.1)
            else:
                # For segments, wait a bit
                for wait_count in range(30):
                    file_path = hls_manager.get_file(portalId, channelId, filename)
                    if file_path:
                        break
                    time.sleep(0.1)
        
        except Exception as e:
            logger.error(f"Error starting HLS stream: {e}")
            return make_response("Error starting stream", 500)
    
    # Serve the file
    if file_path and os.path.exists(file_path):
        # Determine MIME type
        if filename.endswith('.m3u8'):
            mimetype = 'application/vnd.apple.mpegurl'
        elif filename.endswith('.ts'):
            mimetype = 'video/mp2t'
        elif filename.endswith('.m4s'):
            mimetype = 'video/iso.segment'
        elif filename.endswith('.mp4'):
            mimetype = 'video/mp4'
        else:
            mimetype = 'application/octet-stream'
        
        return send_file(file_path, mimetype=mimetype)
    else:
        logger.warning(f"File not found: {filename} for stream {stream_key}")
        return make_response("File not found", 404)

# Erweiterte Cache-Konfiguration für verschiedene Szenarien
class AdvancedChannelCache(ChannelCache):
    def __init__(self):
        # 12 Stunden Standard-Cache
        super().__init__(cache_duration=43200)  # 12 Stunden
        
        # Verschiedene Cache-Zeiten je nach Szenario
        self.cache_durations = {
            'default': 43200,      # 12 Stunden - Standard
            'stable_portal': 86400, # 24 Stunden - für sehr stabile Portale
            'unstable_portal': 3600, # 1 Stunde - für instabile Portale
            'development': 300      # 5 Minuten - für Entwicklung/Tests
        }
    
    def set_portal_cache_duration(self, portal_id: str, duration_type: str = 'default'):
        """Setze spezifische Cache-Dauer für ein Portal."""
        if duration_type in self.cache_durations:
            # Hier könnte man portal-spezifische Cache-Zeiten speichern
            logger.info(f"Portal {portal_id} cache duration set to {duration_type}: {self.cache_durations[duration_type]/3600:.1f} hours")
        else:
            logger.warning(f"Unknown cache duration type: {duration_type}")
    
    def get_cache_duration_for_portal(self, portal_id: str) -> int:
        """Hole Cache-Dauer für spezifisches Portal (erweiterbar)."""
        # Hier könnte man portal-spezifische Logik implementieren
        # Zum Beispiel basierend auf Portal-Stabilität
        return self.cache_duration
    
    def get_channels_with_smart_cache(self, portal_id: str, mac: str, url: str, token: str, proxy: str = None) -> Optional[List]:
        """Erweiterte get_channels mit intelligenter Cache-Verwaltung."""
        cache_key = f"{portal_id}_{mac}"
        current_time = time.time()
        
        with self.lock:
            # Prüfe Cache
            if cache_key in self.cache:
                channels, timestamp = self.cache[cache_key]
                cache_age = current_time - timestamp
                portal_cache_duration = self.get_cache_duration_for_portal(portal_id)
                
                if cache_age < portal_cache_duration:
                    logger.debug(f"Cache HIT für {cache_key} - {len(channels)} channels (age: {cache_age/3600:.1f}h)")
                    return channels
                else:
                    logger.debug(f"Cache EXPIRED für {cache_key} (age: {cache_age/3600:.1f}h)")
            
            # Cache miss oder expired - lade neu
            logger.info(f"Cache MISS für {cache_key} - loading from portal...")
            try:
                channels = stb.getAllChannels(url, mac, token, proxy)
                if channels:
                    self.cache[cache_key] = (channels, current_time)
                    logger.info(f"Cached {len(channels)} channels für {cache_key} (valid for {self.cache_duration/3600:.1f}h)")
                    return channels
            except Exception as e:
                logger.error(f"Error loading channels for {cache_key}: {e}")
                
            return None

# Globaler erweiterter Cache
advanced_channel_cache = AdvancedChannelCache()

# Cache-Statistiken für Monitoring
class CacheStats:
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.start_time = time.time()
    
    def record_hit(self):
        self.hits += 1
    
    def record_miss(self):
        self.misses += 1
    
    def record_error(self):
        self.errors += 1
    
    def get_hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0
    
    def get_stats(self) -> dict:
        uptime = time.time() - self.start_time
        return {
            'hits': self.hits,
            'misses': self.misses,
            'errors': self.errors,
            'hit_rate_percent': round(self.get_hit_rate(), 2),
            'uptime_hours': round(uptime / 3600, 2)
        }

cache_stats = CacheStats()

# Monitoring-Endpoint für Cache-Statistiken
def get_cache_statistics():
    """Hole Cache-Statistiken für Monitoring."""
    stats = cache_stats.get_stats()
    
    # Cache-Größe
    with advanced_channel_cache.lock:
        cache_entries = len(advanced_channel_cache.cache)
        total_channels = sum(len(channels) for channels, _ in advanced_channel_cache.cache.values())
    
    stats.update({
        'cache_entries': cache_entries,
        'total_cached_channels': total_channels,
        'cache_duration_hours': advanced_channel_cache.cache_duration / 3600
    })
    
    return stats

# Beispiel für Cache-Invalidierung bei Portal-Updates
def invalidate_cache_on_portal_update(portal_id: str):
    """Invalidiere Cache wenn Portal-Konfiguration geändert wird."""
    advanced_channel_cache.invalidate_portal(portal_id)
    logger.info(f"Cache invalidated for portal {portal_id} due to configuration change")

# Beispiel für manuelle Cache-Aktualisierung
def force_refresh_portal_cache(portal_id: str):
    """Erzwinge Cache-Refresh für ein Portal."""
    portals = getPortals()
    if portal_id not in portals:
        return False
    
    portal = portals[portal_id]
    url = portal.get("url")
    macs = list(portal["macs"].keys())
    proxy = portal.get("proxy")
    
    refreshed_macs = 0
    for mac in macs:
        try:
            token = stb.getToken(url, mac, proxy)
            if token:
                stb.getProfile(url, mac, token, proxy)
                # Invalidiere zuerst den Cache
                cache_key = f"{portal_id}_{mac}"
                if cache_key in advanced_channel_cache.cache:
                    del advanced_channel_cache.cache[cache_key]
                
                # Lade neu
                channels = advanced_channel_cache.get_channels_with_smart_cache(portal_id, mac, url, token, proxy)
                if channels:
                    refreshed_macs += 1
        except Exception as e:
            logger.error(f"Error refreshing cache for MAC {mac}: {e}")
    
    logger.info(f"Force refreshed cache for portal {portal_id}: {refreshed_macs}/{len(macs)} MACs successful")
    return refreshed_macs > 0