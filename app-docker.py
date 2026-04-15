import os
import shutil
import time
import gzip
import io
import secrets
import requests
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import threading
from threading import Thread
import logging

# Fast JSON library (10x faster than standard json)
try:
    import orjson as json_lib
    JSON_LOADS = lambda x: json_lib.loads(x)
    JSON_DUMPS = lambda x: json_lib.dumps(x).decode('utf-8')
    logger_json = logging.getLogger("MacReplayXC")
    logger_json.info("Using orjson for fast JSON parsing (10x performance boost)")
except ImportError:
    try:
        import ujson as json_lib
        JSON_LOADS = json_lib.loads
        JSON_DUMPS = json_lib.dumps
        logger_json = logging.getLogger("MacReplayXC")
        logger_json.info("Using ujson for fast JSON parsing (5x performance boost)")
    except ImportError:
        import json as json_lib
        JSON_LOADS = json_lib.loads
        JSON_DUMPS = lambda x: json_lib.dumps(x, indent=4)
        logger_json = logging.getLogger("MacReplayXC")
        logger_json.info("Using standard json library (consider installing orjson for better performance)")

# Version
__version__ = "4.2.0"

logger = logging.getLogger("MacReplayXC")
logger.setLevel(logging.INFO)
logFormat = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Track recent redirects for learning (IP, portal, channel) -> (mac, timestamp)
recent_redirects = {}
redirect_lock = threading.Lock()

def cleanup_recent_redirects():
    """Periodically clean up old entries from recent_redirects dictionary.
    
    Removes entries older than 1 hour to prevent unbounded memory growth.
    This function runs in a background thread every 30 minutes.
    """
    global recent_redirects
    
    try:
        now = time.time()
        max_age = 3600  # 1 hour
        
        with redirect_lock:
            keys_to_delete = [
                k for k, (_, ts) in recent_redirects.items()
                if now - ts > max_age
            ]
            
            for k in keys_to_delete:
                del recent_redirects[k]
            
            if keys_to_delete:
                logger.info(f"[MEMORY CLEANUP] Removed {len(keys_to_delete)} old redirect entries (older than 1 hour)")
        
        # Schedule next cleanup in 30 minutes
        threading.Timer(1800, cleanup_recent_redirects).start()
        
    except Exception as e:
        logger.error(f"[MEMORY CLEANUP] Error during recent_redirects cleanup: {e}")
        # Try to schedule next cleanup anyway
        try:
            threading.Timer(1800, cleanup_recent_redirects).start()
        except:
            pass

# Docker-optimized paths
if os.getenv("CONFIG"):
    configFile = os.getenv("CONFIG")
    log_dir = os.path.dirname(configFile)
else:
    # Default paths for container
    log_dir = "/app/data"
    configFile = os.path.join(log_dir, "MacReplayXC.json")

# Create directories if they don't exist
os.makedirs(log_dir, exist_ok=True)
os.makedirs("/app/logs", exist_ok=True)

# Log file path for container
log_file_path = os.path.join("/app/logs", "MacReplayXC.log")

# Set up logging with rotation
from logging.handlers import RotatingFileHandler

# Rotating file handler: max 10 MB per file, keep 5 backup files
fileHandler = RotatingFileHandler(
    log_file_path,
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=5,  # Keep 5 old log files (MacReplayXC.log.1, .2, .3, .4, .5)
    encoding='utf-8'
)
fileHandler.setFormatter(logFormat)
logger.addHandler(fileHandler)

consoleFormat = logging.Formatter("[%(levelname)s] %(message)s")
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(consoleFormat)
logger.addHandler(consoleHandler)

# Ensure log file exists with initial entry
logger.info(f"MacReplayXC v{__version__} - Logging initialized with rotation (10MB x 5 files)")

# Log cleanup function
def cleanup_old_logs():
    """Delete log files older than 24 hours."""
    try:
        log_dir = "/app/logs"
        if not os.path.exists(log_dir):
            return
        
        now = time.time()
        cutoff_time = now - (24 * 60 * 60)  # 24 hours in seconds
        current_log = "MacReplayXC.log"  # Don't delete the current log file
        
        deleted_count = 0
        for filename in os.listdir(log_dir):
            # Skip current log file
            if filename == current_log:
                continue
                
            if filename.endswith('.log') or filename.endswith('.log.old'):
                filepath = os.path.join(log_dir, filename)
                try:
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < cutoff_time:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.info(f"Deleted old log file: {filename} (age: {(now - file_mtime) / 3600:.1f} hours)")
                except Exception as e:
                    logger.error(f"Error deleting log file {filename}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Log cleanup completed: {deleted_count} old log file(s) deleted")
    except Exception as e:
        logger.error(f"Error in log cleanup: {e}")

def schedule_log_cleanup():
    """Schedule periodic log cleanup every 6 hours."""
    cleanup_old_logs()  # Run immediately on startup
    threading.Timer(6 * 60 * 60, schedule_log_cleanup).start()  # Schedule next run in 6 hours


# ============================================================================
# Global MAC Scoring Function
# ============================================================================

def calculate_mac_score(success_count, fail_count, last_success_ts, consecutive_failures=0):
    """Calculate MAC reliability score (0-110+)
    
    Global function used by all streaming modes (FFmpeg, Proxy, HLS, Redirect).
    
    Optimized for IPTV with Failure Rate Acceleration:
    - Recency weighted higher (40 points) - "works now" > "worked often"
    - Soft start for new MACs (minimum 15 points) - prevents harsh punishment
    - Bonus for excellent MACs (<5% failure rate) - rewards reliability
    - Penalty for poor MACs (>15% failure rate) - punishes unreliability
    - Consecutive failure penalty (exponential) - avoids MACs with failure streaks
    
    Args:
        success_count (int): Number of successful streams
        fail_count (int): Number of failed streams
        last_success_ts (int): Unix timestamp of last successful stream
        consecutive_failures (int): Number of consecutive failures (default: 0)
        
    Returns:
        float: Score between 0 and 110+ (higher is better)
    """
    current_time = int(time.time())
    
    # 1. Success Rate (0-45 points with Failure Rate Acceleration)
    total = success_count + fail_count
    if total > 0:
        failure_rate = fail_count / total
        
        # Soft start: First 5 attempts get minimum 15 points
        if total <= 5:
            success_rate = max(15, (success_count / total) * 40)
        elif total <= 10:
            # Transition phase: Soft start bonus fades out gradually
            # This prevents sudden score drops when soft start ends
            soft_start_bonus = (10 - total) / 5 * 15  # 15 → 0 over 5 attempts
            base_rate = (success_count / total) * 40
            success_rate = base_rate + soft_start_bonus
            logger.debug(f"[SCORE] Transition phase: base={base_rate:.1f} + bonus={soft_start_bonus:.1f} = {success_rate:.1f}")
        else:
            base_success_rate = (success_count / total) * 40
            
            # Failure Rate Acceleration (only after 10+ attempts)
            if total >= 10:
                # PENALTY: High failure rate (>15%)
                if failure_rate > 0.15:
                    penalty = (failure_rate - 0.15) * 40
                    success_rate = max(0, base_success_rate - penalty)
                # BONUS: Low failure rate (<5%)
                elif failure_rate < 0.05:
                    bonus = min(5, (0.05 - failure_rate) * 100)  # Cap bonus at 5 points
                    success_rate = min(45, base_success_rate + bonus)  # Cap total at 45 points
                # NEUTRAL: Normal failure rate (5-15%)
                else:
                    success_rate = base_success_rate
            else:
                success_rate = base_success_rate
    else:
        success_rate = 25  # Neutral for untested
    
    # 2. Recency (0-40 points, increased from 30)
    # For IPTV: Recent success is more important than historical success
    if last_success_ts > 0:
        age_hours = (current_time - last_success_ts) / 3600
        if age_hours < 1:
            recency = 40
        elif age_hours < 24:
            recency = 30
        elif age_hours < 168:  # 1 week
            recency = 15
        else:
            recency = 5
    else:
        recency = 0  # Never successful
    
    # 3. Reliability Bonus (0-20 points, unchanged)
    if success_count >= 10:
        reliability = 20
    elif success_count >= 5:
        reliability = 10
    else:
        reliability = 0
    
    # 4. Consecutive Failure Penalty (exponential)
    # Heavily penalize MACs with failure streaks to avoid repeated attempts
    consecutive_penalty = 0
    if consecutive_failures > 0:
        # Exponential penalty: 5 * (2^n), capped at 30 points
        # 1 fail = -10, 2 fails = -20, 3 fails = -30 (max)
        consecutive_penalty = min(30, 5 * (2 ** min(consecutive_failures, 4)))
        logger.debug(f"[SCORE] Consecutive failure penalty: -{consecutive_penalty} (streak: {consecutive_failures})")
    
    total_score = success_rate + recency + reliability - consecutive_penalty
    return max(0, total_score)  # Never go below 0


# ============================================================================
# End of Global MAC Scoring Function
# ============================================================================


def parse_and_sort_macs(available_macs_raw):
    """Parse MACs from DB format and sort by score.
    
    Global function used by all streaming modes to parse MAC data from DB
    and sort them by reliability score.
    
    Args:
        available_macs_raw (str): Comma-separated MAC entries from DB
                                  Format: "MAC|limit|success|fail|last_ts,..."
    
    Returns:
        tuple: (available_macs, mac_limits, mac_stats)
            - available_macs (list): Sorted list of MAC addresses (highest score first)
            - mac_limits (dict): {mac: playback_limit}
            - mac_stats (dict): {mac: {'success': int, 'fail': int, 'last_ts': int, 'score': float}}
    """
    available_macs = []
    mac_limits = {}
    mac_stats = {}
    
    for mac_entry in available_macs_raw.split(','):
        parts = mac_entry.split('|')
        if len(parts) >= 6:
            # Format: MAC|limit|success|fail|last_ts|consecutive_failures
            mac = parts[0]
            available_macs.append(mac)
            mac_limits[mac] = int(parts[1])
            success_count = int(parts[2])
            fail_count = int(parts[3])
            last_ts = int(parts[4])
            consecutive_failures = int(parts[5])
            score = calculate_mac_score(success_count, fail_count, last_ts, consecutive_failures)
            mac_stats[mac] = {
                'success': success_count,
                'fail': fail_count,
                'last_ts': last_ts,
                'consecutive_failures': consecutive_failures,
                'score': score
            }
        elif len(parts) >= 5:
            # Format: MAC|limit|success|fail|last_ts (old format without consecutive_failures)
            mac = parts[0]
            available_macs.append(mac)
            mac_limits[mac] = int(parts[1])
            success_count = int(parts[2])
            fail_count = int(parts[3])
            last_ts = int(parts[4])
            score = calculate_mac_score(success_count, fail_count, last_ts, 0)
            mac_stats[mac] = {
                'success': success_count,
                'fail': fail_count,
                'last_ts': last_ts,
                'consecutive_failures': 0,
                'score': score
            }
        elif len(parts) == 2:
            # Format: MAC|limit (old format)
            mac = parts[0]
            available_macs.append(mac)
            mac_limits[mac] = int(parts[1])
            mac_stats[mac] = {
                'success': 0,
                'fail': 0,
                'last_ts': 0,
                'consecutive_failures': 0,
                'score': 25  # Neutral
            }
        else:
            # Format: MAC (very old) - assume it's a complete MAC address
            available_macs.append(mac_entry)
            mac_limits[mac_entry] = 1
            mac_stats[mac_entry] = {
                'success': 0,
                'fail': 0,
                'last_ts': 0,
                'consecutive_failures': 0,
                'score': 25  # Neutral
            }
    
    # CRITICAL: Sort MACs by score (highest first)
    available_macs.sort(key=lambda mac: mac_stats.get(mac, {}).get('score', 0), reverse=True)
    
    return available_macs, mac_limits, mac_stats


# ============================================================================
# End of Global Parse and Sort Function
# ============================================================================


# Docker-optimized ffmpeg paths (system-installed)
ffmpeg_path = "ffmpeg"
ffprobe_path = "ffprobe"

# Check if the binaries exist
import subprocess


# Channel Cache wird weiter unten definiert

def get_stream_url_with_auth(playlist_host, portal_id, channel_id):
    """
    Generate stream URL with embedded basic auth if needed.
    
    Args:
        playlist_host (str): Host for the playlist
        portal_id (str): Portal ID
        channel_id (str): Channel ID
        
    Returns:
        str: Stream URL with or without embedded auth
    """
    base_url = f"http://{playlist_host}/play/{portal_id}/{channel_id}"
    
    # Check if we should embed basic auth credentials
    settings = getSettings()
    
    # If public access is disabled, embed auth for VLC compatibility
    if settings.get("public playlist access", "true") == "false":
        
        # Try to get auth from current request context
        auth_user = None
        auth_pass = None
        
        try:
            if hasattr(request, 'authorization') and request.authorization:
                auth_user = request.authorization.username
                auth_pass = request.authorization.password
        except:
            # No request context or no authorization
            pass
        
        # If no auth from request, use default credentials
        if not auth_user:
            auth_user = settings.get("username", "admin")
            auth_pass = settings.get("password", "12345")
        
        # Embed basic auth in URL for VLC compatibility
        # Format: http://user:pass@host/path
        return f"http://{auth_user}:{auth_pass}@{playlist_host}/play/{portal_id}/{channel_id}"
    
    return base_url


def get_external_host_config():
    """
    Get external host configuration from environment variables.
    
    Returns:
        tuple: (external_host, external_scheme) or (None, None)
    """
    # Check if HOST contains a full URL (simple approach)
    host_env = os.getenv("HOST")
    if host_env and ("http://" in host_env or "https://" in host_env):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(host_env)
            if parsed.hostname:
                host_with_port = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
                scheme = parsed.scheme or "http"
                return host_with_port, scheme
        except Exception:
            pass
    
    # Fallback to None (use request.host)
    return None, None


def get_external_host_public_config():
    """
    Get public/external host configuration from environment variables.
    Used for generating external playlists accessible from the internet.
    
    Returns:
        tuple: (external_host, external_scheme) or (None, None)
    """
    # Check if HOST_EXTERNAL contains a full URL
    host_env = os.getenv("HOST_EXTERNAL")
    if host_env and ("http://" in host_env or "https://" in host_env):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(host_env)
            if parsed.hostname:
                host_with_port = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
                scheme = parsed.scheme or "http"
                return host_with_port, scheme
        except Exception:
            pass
    
    # Fallback to None
    return None, None


def extract_auth_credentials(request):
    """
    Extract authentication credentials from HTTP request.
    
    Supports both HTTP Basic Authentication and Query Parameters.
    Basic Auth takes precedence over Query Parameters.
    
    Args:
        request: Flask request object
        
    Returns:
        tuple: (username, password) or (None, None) if no credentials found
    """
    # Priority 1: HTTP Basic Authentication
    if hasattr(request, 'authorization') and request.authorization:
        auth = request.authorization
        if auth.username and auth.password:
            return (auth.username, auth.password)
    
    # Priority 2: Query Parameters
    username = request.args.get('username')
    password = request.args.get('password')
    
    if username and password:
        return (username, password)
    
    # No credentials found
    return (None, None)


def validate_authentication(username, password, settings=None, client_ip=None):
    """
    Validate authentication credentials against system settings.
    
    Args:
        username (str): Username to validate
        password (str): Password to validate
        settings (dict, optional): System settings. If None, will fetch current settings.
        client_ip (str, optional): Client IP address for logging
        
    Returns:
        tuple: (is_valid, error_message)
            - is_valid (bool): True if credentials are valid
            - error_message (str): Error message if validation fails, None if valid
    """
    if settings is None:
        settings = getSettings()
    
    # Get client IP for logging
    if client_ip is None:
        try:
            client_ip = get_client_ip()
        except:
            client_ip = "unknown"
    
    # Check if security is enabled
    security_enabled = settings.get("enable security", "false") == "true"
    
    # If security is disabled, allow access
    if not security_enabled:
        logger.debug(f"Authentication bypassed (security disabled) from IP: {client_ip}")
        return (True, None)
    
    # If security is enabled, credentials are required
    if not username or not password:
        logger.warning(f"Authentication attempt without credentials from IP: {client_ip}")
        return (False, "Authentication required")
    
    # Validate credentials against system settings
    system_username = settings.get("username", "admin")
    system_password = settings.get("password", "12345")
    
    # Use constant-time comparison to prevent timing attacks
    if not (secrets.compare_digest(username, system_username) and 
            secrets.compare_digest(password, system_password)):
        logger.warning(f"Authentication failed for user '{username}' from IP: {client_ip}")
        return (False, "Invalid credentials")
    
    # Authentication successful
    logger.info(f"Authentication successful for user '{username}' from IP: {client_ip}")
    return (True, None)


try:
    subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True)
    subprocess.run([ffprobe_path, "-version"], capture_output=True, check=True)
    logger.info("FFmpeg and FFprobe found and working")
except (subprocess.CalledProcessError, FileNotFoundError) as e:
    logger.error("CRITICAL: ffmpeg or ffprobe not found!")
    logger.error("FFmpeg is required for streaming. Please install FFmpeg.")
    raise RuntimeError("FFmpeg is required but not found. Please install FFmpeg and ensure it's in PATH.") from e

import flask
from flask import Flask, jsonify
import stb

# Use optimized JSON library (already imported at top)
# json_lib is either orjson, ujson, or standard json
import json  # Keep for compatibility, but prefer json_lib for performance-critical operations

import subprocess
import uuid
import xml.etree.cElementTree as ET
from flask import (
    Flask,
    render_template,
    redirect,
    request,
    Response,
    make_response,
    flash,
    send_file,
    stream_with_context,
)
from datetime import datetime, timezone
from functools import wraps
import secrets
import waitress
import sqlite3
import atexit
from utils import (
    validate_mac_address,
    validate_url,
    normalize_mac_address,
    sanitize_channel_name,
    get_client_ip,
    is_hls_url,
    validate_proxy_url,
    get_proxy_type,
    parse_proxy_url
)

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)

# HTTPS Reverse Proxy Support: ProxyFix Middleware
# Enables correct scheme/host detection when behind Caddy/Nginx/Traefik
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_proto=1,  # X-Forwarded-Proto → request.scheme (http/https)
    x_host=1,   # X-Forwarded-Host → request.host
    x_for=1     # X-Forwarded-For → request.remote_addr
)
logger.info("ProxyFix middleware enabled for reverse proxy support")

# In-memory cache for Macstrom hits (avoid re-fetching 10k entries per page)
_macstrom_hits_cache = {"hits": [], "url": None, "ts": 0}
# Rate Limiting (NEW in v4.2.0)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def is_localhost():
    """Check if request is from localhost - exempt from rate limiting."""
    remote_addr = request.remote_addr
    return remote_addr in ['127.0.0.1', '::1', 'localhost']

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],  # No default limits - only specific endpoints
    storage_uri="memory://",
    strategy="fixed-window"
)

# Exempt localhost from rate limiting using decorator
limiter.request_filter(is_localhost)

logger.info("Rate limiting enabled for specific endpoints only (login, refresh operations), localhost exempt")

# ============================================
# Vavoo Integration (Separate Container)
# ============================================
# Vavoo runs as separate Docker container on port 4323
# Accessible via iframe in /vavoo_page route
logger.info("Vavoo runs as separate container (vavoo:4323)")

# Docker-optimized host configuration
if os.getenv("HOST"):
    host = os.getenv("HOST")
else:
    host = "0.0.0.0:8001"
logger.info(f"MacReplayXC v{__version__} - Server started on http://{host}")

logger.info(f"Using config file: {configFile}")

# Database path for channel caching
dbPath = os.path.join(log_dir, "channels.db")
logger.info(f"Using database file: {dbPath}")

# VOD Database path for VOD/Series caching
vodsDbPath = os.path.join(log_dir, "vods.db")
logger.info(f"Using VOD database file: {vodsDbPath}")

# Thread-safe dictionaries with locks
occupied = {}
occupied_lock = threading.Lock()
config = {}
config_lock = threading.Lock()
mac_score_update_lock = threading.Lock()  # NEW: Lock for MAC score updates to prevent race conditions
cached_lineup = []
cached_playlist = None
last_playlist_host = None
cached_xmltv = None  # Deprecated - XMLTV now served from file for memory efficiency
last_updated = 0
hls_manager = None

# ============================================================================
# Token Cache - caches Stalker tokens per (portal_url, mac) to avoid
# repeated handshakes. TTL = token_cache_ttl setting (default 270s).
# Inspired by Macstrom's TokenCache implementation.
# ============================================================================
class TokenCache:
    """Thread-safe in-memory token cache keyed by (portal_url, mac)."""
    MAX_ENTRIES = 500  # Prevent unbounded memory growth

    def __init__(self):
        self._cache = {}  # (url, mac) -> {"token": str, "expires_at": float}
        self._lock = threading.Lock()

    def get(self, url, mac):
        """Return cached token if still valid, else None."""
        key = (url, mac)
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.time() < entry["expires_at"]:
                return entry["token"]
            elif entry:
                del self._cache[key]
        return None

    def set(self, url, mac, token, ttl_seconds=270):
        """Cache a token with TTL. Evicts expired entries if cache is full."""
        key = (url, mac)
        with self._lock:
            # Evict expired entries if at capacity
            if len(self._cache) >= self.MAX_ENTRIES:
                now = time.time()
                expired = [k for k, v in self._cache.items() if now >= v["expires_at"]]
                for k in expired:
                    del self._cache[k]
                # If still full after eviction, remove oldest entry
                if len(self._cache) >= self.MAX_ENTRIES:
                    oldest = min(self._cache.items(), key=lambda x: x[1]["expires_at"])
                    del self._cache[oldest[0]]
            self._cache[key] = {
                "token": token,
                "expires_at": time.time() + ttl_seconds
            }

    def invalidate(self, url, mac):
        """Remove a token from cache (e.g. on stream failure)."""
        key = (url, mac)
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        """Clear all cached tokens."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self):
        """Remove all expired entries. Called periodically."""
        with self._lock:
            now = time.time()
            expired = [k for k, v in self._cache.items() if now >= v["expires_at"]]
            for k in expired:
                del self._cache[k]
            return len(expired)

    def stats(self):
        """Return cache statistics."""
        with self._lock:
            now = time.time()
            valid = sum(1 for e in self._cache.values() if now < e["expires_at"])
            return {"total": len(self._cache), "valid": valid, "expired": len(self._cache) - valid}

token_cache = TokenCache()


def get_token_cached(url, mac, proxy=None):
    """
    Get token with caching. If enabled in settings, returns cached token if available.
    Falls back to fresh handshake on cache miss, when disabled, or if cached token fails.
    """
    settings = getSettings()
    cache_enabled = settings.get("token cache enabled", "true") == "true"

    if cache_enabled:
        cached = token_cache.get(url, mac)
        if cached:
            logger.debug(f"[TOKEN CACHE] Hit for MAC {mac}")
            return cached

    # Fresh handshake
    token = stb.getToken(url, mac, proxy)
    if token and cache_enabled:
        ttl = int(settings.get("token cache ttl", "270"))
        token_cache.set(url, mac, token, ttl)
        logger.debug(f"[TOKEN CACHE] Stored token for MAC {mac} (TTL: {ttl}s)")
    elif not token and cache_enabled:
        # Token failed - remove any stale cached entry
        token_cache.invalidate(url, mac)

    return token


def invalidate_token_cache(url, mac):
    """Invalidate cached token for a MAC (call on stream failure)."""
    token_cache.invalidate(url, mac)
    logger.debug(f"[TOKEN CACHE] Invalidated token for MAC {mac}")


def start_epg_auto_refresh_scheduler():
    """Start EPG auto-refresh scheduler if enabled in settings."""
    try:
        settings = getSettings()
        auto_refresh = settings.get("epg auto refresh", "manual")
        
        if auto_refresh == "manual":
            logger.info("EPG auto-refresh disabled (manual mode)")
            return
        
        refresh_days = int(settings.get("epg refresh interval days", "1"))
        refresh_seconds = refresh_days * 86400  # Convert days to seconds
        
        # Check when last refresh was
        last_refresh = float(settings.get("epg last refresh timestamp", "0"))
        current_time = time.time()
        
        if last_refresh > 0:
            time_since_last = current_time - last_refresh
            time_until_next = refresh_seconds - time_since_last
            
            if time_until_next <= 0:
                # Overdue - schedule immediately (with 60s delay to let server finish starting)
                logger.info(f"EPG auto-refresh: Last refresh was {time_since_last/3600:.1f} hours ago - scheduling immediate refresh")
                threading.Timer(60, epg_auto_refresh_task).start()
            else:
                # Schedule for remaining time
                logger.info(f"EPG auto-refresh enabled - next refresh in {time_until_next/3600:.1f} hours (interval: {refresh_days} day(s))")
                threading.Timer(time_until_next, epg_auto_refresh_task).start()
        else:
            # Never refreshed - schedule for full interval
            logger.info(f"EPG auto-refresh enabled - first refresh in {refresh_days} day(s)")
            threading.Timer(refresh_seconds, epg_auto_refresh_task).start()
        
    except Exception as e:
        logger.error(f"Error starting EPG auto-refresh scheduler: {e}")


def epg_auto_refresh_task():
    """Background task that runs EPG refresh and reschedules itself."""
    try:
        settings = getSettings()
        auto_refresh = settings.get("epg auto refresh", "manual")
        
        # Check if still enabled
        if auto_refresh == "manual":
            logger.info("EPG auto-refresh disabled - stopping scheduler")
            return
        
        refresh_days = int(settings.get("epg refresh interval days", "1"))
        refresh_seconds = refresh_days * 86400
        
        logger.info(f"EPG auto-refresh: Starting scheduled refresh (interval: {refresh_days} day(s))")
        
        # Run refresh in background thread
        global epg_refresh_progress
        if not epg_refresh_progress.get("running", False):
            _clear_epg_cache()
            global cached_xmltv
            cached_xmltv = None
            
            portals = getPortals()
            enabled_portals = [p for p in portals.values() if p.get("enabled") == "true"]
            
            epg_refresh_progress = {
                "running": True,
                "current_portal": "",
                "current_step": "Auto-refresh started...",
                "portals_done": 0,
                "portals_total": len(enabled_portals),
                "started_at": time.time()
            }
            
            # Save timestamp BEFORE starting refresh
            settings["epg last refresh timestamp"] = str(int(time.time()))
            saveSettings(settings)
            
            threading.Thread(target=refresh_xmltv_with_progress, daemon=True).start()
            logger.info("EPG auto-refresh: Refresh started successfully")
        else:
            logger.warning("EPG auto-refresh: Skipping - refresh already in progress")
        
        # Schedule next refresh
        threading.Timer(refresh_seconds, epg_auto_refresh_task).start()
        logger.info(f"EPG auto-refresh: Next refresh scheduled in {refresh_days} day(s)")
        
    except Exception as e:
        logger.error(f"Error in EPG auto-refresh task: {e}")
        # Try to reschedule even if error occurred
        try:
            settings = getSettings()
            refresh_days = int(settings.get("epg refresh interval days", "1"))
            refresh_seconds = refresh_days * 86400
            threading.Timer(refresh_seconds, epg_auto_refresh_task).start()
        except:
            pass


def cleanup_occupied_streams():
    """Automatically clean up old/expired streams from occupied dictionary to prevent memory leaks."""
    global occupied
    current_time = time.time()
    max_age = 1800  # 30 minutes (reduced from 2 hours for better memory management)
    
    try:
        cleaned_count = 0
        with occupied_lock:
            for portal_id in list(occupied.keys()):
                if portal_id not in occupied:
                    continue
                    
                streams = occupied[portal_id]
                # Keep only streams younger than max_age
                active_streams = [
                    s for s in streams 
                    if current_time - s.get("start time", 0) < max_age
                ]
                
                cleaned_count += len(streams) - len(active_streams)
                
                if active_streams:
                    occupied[portal_id] = active_streams
                else:
                    # Remove empty portal entries
                    del occupied[portal_id]
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} expired stream(s) from occupied dictionary (older than 30 minutes)")
        
    except Exception as e:
        logger.error(f"Error during occupied streams cleanup: {e}")
    
    # Schedule next cleanup in 3 minutes (reduced from 5 minutes)
    threading.Timer(180, cleanup_occupied_streams).start()


def cleanup_recent_redirects():
    """Automatically clean up old entries from recent_redirects dictionary to prevent memory leaks."""
    global recent_redirects
    current_time = time.time()
    max_age = 3600  # 1 hour
    
    try:
        cleaned_count = 0
        with redirect_lock:
            keys_to_delete = [
                k for k, (_, ts) in recent_redirects.items()
                if current_time - ts > max_age
            ]
            
            for k in keys_to_delete:
                del recent_redirects[k]
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old redirect(s) from recent_redirects dictionary (older than 1 hour)")
        
    except Exception as e:
        logger.error(f"Error during recent redirects cleanup: {e}")
    
    # Schedule next cleanup in 30 minutes
    threading.Timer(1800, cleanup_recent_redirects).start()


def update_mac_score_in_db(portal_id, channel_id, mac, is_success, duration=None):
    """
    Thread-safe function to update MAC score in database.
    Prevents race conditions when multiple streams update scores simultaneously.
    
    Args:
        portal_id (str): Portal ID
        channel_id (str): Channel ID
        mac (str): MAC address to update
        is_success (bool): True for success, False for failure
        duration (float): Optional stream duration in seconds
    """
    with mac_score_update_lock:
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get current stats
            cursor.execute('''
                SELECT available_macs FROM channels 
                WHERE portal = ? AND channel_id = ?
            ''', (portal_id, channel_id))
            
            row = cursor.fetchone()
            if not row or not row['available_macs']:
                logger.debug(f"[SCORE UPDATE] Channel {channel_id} not found in DB")
                return
            
            available_macs_raw = row['available_macs'].split(',')
            updated_macs = []
            mac_found = False
            
            for mac_entry in available_macs_raw:
                parts = mac_entry.split('|')
                if len(parts) >= 6:
                    entry_mac = parts[0]
                    if entry_mac == mac:
                        # Update this MAC's stats
                        mac_found = True
                        limit = int(parts[1])
                        success_count = int(parts[2])
                        fail_count = int(parts[3])
                        last_ts = int(parts[4])
                        consecutive_failures = int(parts[5])
                        
                        if is_success:
                            success_count += 1
                            last_ts = int(time.time())
                            consecutive_failures = 0  # Reset on success
                            duration_str = f", duration: {duration:.1f}s" if duration else ""
                            logger.info(f"[SCORE UPDATE] ✓ MAC {mac} success (now: {success_count} successes, streak reset{duration_str})")
                        else:
                            fail_count += 1
                            consecutive_failures += 1  # Increment on failure
                            duration_str = f", duration: {duration:.1f}s" if duration else ""
                            logger.info(f"[SCORE UPDATE] ✗ MAC {mac} fail (now: {fail_count} failures, streak: {consecutive_failures}{duration_str})")
                        
                        updated_macs.append(f"{entry_mac}|{limit}|{success_count}|{fail_count}|{last_ts}|{consecutive_failures}")
                    else:
                        updated_macs.append(mac_entry)
                elif len(parts) >= 5:
                    # Old format: MAC|limit|success|fail|last_ts (upgrade to new format)
                    entry_mac = parts[0]
                    if entry_mac == mac:
                        mac_found = True
                        limit = int(parts[1])
                        success_count = int(parts[2])
                        fail_count = int(parts[3])
                        last_ts = int(parts[4])
                        
                        if is_success:
                            success_count += 1
                            last_ts = int(time.time())
                            consecutive_failures = 0
                            duration_str = f", duration: {duration:.1f}s" if duration else ""
                            logger.info(f"[SCORE UPDATE] ✓ MAC {mac} success (now: {success_count} successes{duration_str})")
                        else:
                            fail_count += 1
                            consecutive_failures = 1  # Start tracking
                            duration_str = f", duration: {duration:.1f}s" if duration else ""
                            logger.info(f"[SCORE UPDATE] ✗ MAC {mac} fail (now: {fail_count} failures, streak: 1{duration_str})")
                        
                        updated_macs.append(f"{entry_mac}|{limit}|{success_count}|{fail_count}|{last_ts}|{consecutive_failures}")
                    else:
                        updated_macs.append(mac_entry)
                elif len(parts) == 2:
                    # Old format: MAC|limit
                    entry_mac = parts[0]
                    if entry_mac == mac:
                        mac_found = True
                        limit = int(parts[1])
                        if is_success:
                            updated_macs.append(f"{entry_mac}|{limit}|1|0|{int(time.time())}|0")
                            logger.info(f"[SCORE UPDATE] ✓ MAC {mac} success (first success)")
                        else:
                            updated_macs.append(f"{entry_mac}|{limit}|0|1|0|1")
                            logger.info(f"[SCORE UPDATE] ✗ MAC {mac} fail (first fail, streak: 1)")
                    else:
                        updated_macs.append(mac_entry)
                else:
                    updated_macs.append(mac_entry)
            
            if not mac_found:
                logger.debug(f"[SCORE UPDATE] MAC {mac} not in available_macs list, skipping")
                return
            
            # Update DB
            cursor.execute('''
                UPDATE channels SET available_macs = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (','.join(updated_macs), portal_id, channel_id))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"[SCORE UPDATE] Error updating MAC score: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass


def cleanup_recent_redirects():
    """Automatically clean up old entries from recent_redirects dictionary to prevent memory leaks."""
    global recent_redirects
    current_time = time.time()
    max_age = 3600  # 1 hour
    
    try:
        cleaned_count = 0
        with redirect_lock:
            keys_to_delete = [
                k for k, (_, ts) in recent_redirects.items()
                if current_time - ts > max_age
            ]
            for k in keys_to_delete:
                del recent_redirects[k]
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} old redirect(s) from recent_redirects dictionary (older than 1 hour)")
        
    except Exception as e:
        logger.error(f"Error during recent_redirects cleanup: {e}")
    
    # Schedule next cleanup in 30 minutes
    threading.Timer(1800, cleanup_recent_redirects).start()


def refresh_tokens_for_active_streams():
    """Refresh tokens for all active streams every 50 minutes to prevent expiration.
    
    Stalker tokens typically expire after ~1 hour. This function proactively
    refreshes tokens for streams older than 45 minutes, ensuring uninterrupted playback.
    Runs in a background thread every 50 minutes.
    """
    try:
        # Get all active streams (thread-safe)
        active_streams = []
        with occupied_lock:
            for portal_id, streams in occupied.items():
                for stream_info in streams:
                    mac = stream_info.get('mac')
                    start_time = stream_info.get('start time', 0)
                    stream_age = time.time() - start_time
                    
                    # Only refresh if stream is older than 45 minutes
                    if mac and stream_age > 2700:  # 45 minutes
                        active_streams.append({
                            'portal_id': portal_id,
                            'mac': mac,
                            'age': stream_age
                        })
        
        # Refresh tokens outside the lock
        if active_streams:
            logger.info(f"[TOKEN REFRESH] Found {len(active_streams)} active stream(s) needing token refresh")
            
            for stream in active_streams:
                try:
                    portal_id = stream['portal_id']
                    mac = stream['mac']
                    age_minutes = stream['age'] / 60
                    
                    # Get portal info
                    portals = getPortals()
                    portal = portals.get(portal_id)
                    if not portal:
                        continue
                    
                    url = portal.get('url')
                    proxy = portal.get('proxy')
                    
                    # Get fresh token
                    new_token = stb.getToken(url, mac, proxy)
                    if new_token:
                        logger.info(f"[TOKEN REFRESH] ✓ Refreshed token for Portal({portal_id}):MAC({mac}) (stream age: {age_minutes:.1f} min)")
                    else:
                        logger.warning(f"[TOKEN REFRESH] ✗ Failed to refresh token for Portal({portal_id}):MAC({mac})")
                
                except Exception as e:
                    logger.error(f"[TOKEN REFRESH] Error refreshing token for stream: {e}")
        else:
            logger.debug(f"[TOKEN REFRESH] No active streams needing refresh")
    
    except Exception as e:
        logger.error(f"[TOKEN REFRESH] Error in refresh loop: {e}")
    finally:
        # Always schedule next refresh in 50 minutes
        try:
            threading.Timer(3000, refresh_tokens_for_active_streams).start()
        except Exception as e:
            logger.error(f"[TOKEN REFRESH] Failed to schedule next refresh: {e}")


# ============================================
# Channel Cache REMOVED in v3.1.0
# ============================================
# Channel cache system has been replaced with direct channels.db access
# All streaming now reads stream_cmd and available_macs directly from channels.db
# This provides 30x faster streaming and persistent data across restarts

# EPG refresh progress tracking
epg_refresh_progress = {
    "running": False,
    "current_portal": "",
    "current_step": "",
    "portals_done": 0,
    "portals_total": 0,
    "started_at": None
}

# Editor refresh progress tracking
editor_refresh_progress = {
    "running": False,
    "current_portal": "",
    "current_step": "",
    "portals_done": 0,
    "portals_total": 0,
    "started_at": None
}

d_ffmpegcmd = [
    "-re",                      # Flag for real-time streaming
    "-http_proxy", "<proxy>",   # Proxy setting
    "-timeout", "<timeout>",    # Timeout setting
    "-i", "<url>",              # Input URL
    "-map", "0",                # Map all streams
    "-codec", "copy",           # Copy codec (no re-encoding)
    "-f", "mpegts",             # Output format
    "-flush_packets", "0",      # Disable flushing packets (optimized for faster output)
    "-fflags", "+nobuffer",     # No buffering for low latency
    "-flags", "low_delay",      # Low delay flag
    "-strict", "experimental",  # Use experimental features
    "-analyzeduration", "0",    # Skip analysis duration for faster startup
    "-probesize", "32",         # Set probe size to reduce input analysis time
    "-copyts",                  # Copy timestamps (avoid recalculating)
    "-threads", "12",           # Enable multi-threading (adjust thread count as needed)
    "pipe:"                     # Output to pipe
]

defaultSettings = {
    "stream method": "ffmpeg",
    "output format": "mpegts",
    "ffmpeg command": "-re -http_proxy <proxy> -timeout <timeout> -user_agent <user_agent> -i <url> -map 0 -codec copy -f mpegts -flush_packets 0 -fflags +nobuffer -flags low_delay -strict experimental -analyzeduration 0 -probesize 32 -copyts -threads 12 pipe:",
    "user agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3",
    "proxy buffer size": "4096",  # KB (4MB for smooth video streaming, prevents stuttering)
    "proxy connect timeout": "5",  # seconds
    "proxy read timeout": "30",  # seconds
    "hls segment type": "fmp4",
    "hls segment duration": "3",
    "hls playlist size": "8",
    "hls max streams": "10",
    "hls inactive timeout": "30",
    "hls connection timeout": "5",
    "hls auto retry": "false",
    "hls retry timeout": "6",
    "ffmpeg timeout": "5",
    "ffprobe params": "-analyzeduration 500000 -probesize 100000",  # Custom ffprobe parameters (Balance preset)
    "test streams": "true",
    "try all macs": "true",
    "try all macs on db miss": "true",
    "skip busy macs": "true",
    "token cache enabled": "true",  # Cache tokens per MAC to avoid repeated handshakes
    "token cache ttl": "270",  # Token cache TTL in seconds (watchdog_timeout * 0.9, default 300*0.9=270)
    "use channel genres": "true",
    "use channel numbers": "true",
    "sort playlist by channel genre": "false",
    "sort playlist by channel number": "true",
    "sort playlist by channel name": "false",
    "enable security": "false",
    "username": "admin",
    "password": "12345",
    "enable hdhr": "true",
    "hdhr name": "MacReplayXC",
    "hdhr id": str(uuid.uuid4().hex),
    "hdhr tuners": "10",
    "epg fallback enabled": "false",
    "epg fallback countries": "",
    "epg auto refresh": "manual",
    "epg refresh interval days": "1",
    "epg last refresh timestamp": "0",  # Unix timestamp of last EPG refresh
    "xc api enabled": "false",
    "xc vod proxy": "true",
    "public playlist access": "true",
    "use portal names as groups": "false",
}

defaultXCUser = {
    "username": "",
    "password": "",
    "enabled": "true",
    "max_connections": "1",
    "allowed_portals": [],  # Empty = all portals
    "created_at": "",
    "expires_at": "",  # Empty = never expires
    "active_connections": {},  # device_id -> {portal_id, channel_id, started_at, ip}
}

defaultPortal = {
    "enabled": "true",
    "name": "",
    "url": "",
    "macs": {},
    "streams per mac": "1",
    "epg offset": "0",
    "proxy": "",
    "portal prefix": "",
    "enabled channels": [],
    "selected genres": [],
    "custom channel names": {},
    "custom channel numbers": {},
    "custom genres": {},
    "custom epg ids": {},
    "fallback channels": {},
    "mac_has_de": {},
}


def monitor_ffmpeg_hls_output(process, timeout_seconds=5):
    """
    Monitor FFmpeg stderr for HLS segment creation.
    Returns True as soon as FFmpeg starts writing segments, False on error or timeout.
    
    This is inspired by macattack-r's approach: instead of polling the filesystem,
    we listen to FFmpeg's output to know immediately when streaming starts.
    """
    import select
    import sys
    
    start_time = time.time()
    segment_detected = False
    
    try:
        # Make stderr non-blocking on Unix systems
        if hasattr(select, 'poll'):
            poller = select.poll()
            poller.register(process.stderr, select.POLLIN)
        
        while time.time() - start_time < timeout_seconds:
            # Check if process is still running
            if process.poll() is not None:
                logger.warning(f"[HLS MONITOR] FFmpeg process ended prematurely (exit code: {process.returncode})")
                return False
            
            # Try to read a line from stderr
            try:
                # Use select on Unix, simple readline on Windows
                if hasattr(select, 'poll'):
                    # Unix: non-blocking poll
                    events = poller.poll(100)  # 100ms timeout
                    if events:
                        line = process.stderr.readline()
                    else:
                        continue
                else:
                    # Windows: blocking readline with short timeout
                    line = process.stderr.readline()
                
                if not line:
                    time.sleep(0.05)
                    continue
                
                line_lower = line.lower()
                
                # Success: FFmpeg is writing segments
                if "opening" in line_lower and (".ts" in line_lower or ".m4s" in line_lower or "seg_" in line_lower):
                    elapsed = time.time() - start_time
                    logger.info(f"[HLS MONITOR] ✓ FFmpeg started writing segments after {elapsed:.2f}s")
                    segment_detected = True
                    # Wait a bit more to ensure playlist is written
                    time.sleep(0.5)
                    return True
                
                # Also detect playlist creation
                if "opening" in line_lower and ".m3u8" in line_lower:
                    elapsed = time.time() - start_time
                    logger.info(f"[HLS MONITOR] ✓ FFmpeg created playlist after {elapsed:.2f}s")
                    segment_detected = True
                    # Wait a bit more to ensure file is flushed
                    time.sleep(0.3)
                    return True
                
                # Error detection
                if any(err in line_lower for err in ["error", "failed", "invalid", "connection refused", "403 forbidden", "404 not found"]):
                    logger.warning(f"[HLS MONITOR] ✗ FFmpeg error detected: {line.strip()}")
                    return False
                
            except Exception as e:
                logger.debug(f"[HLS MONITOR] Error reading stderr: {e}")
                time.sleep(0.05)
                continue
        
        # Timeout reached
        logger.warning(f"[HLS MONITOR] ✗ Timeout after {timeout_seconds}s, no segment output detected")
        return False
        
    except Exception as e:
        logger.error(f"[HLS MONITOR] Exception in monitor: {e}")
        return False


class HLSStreamManager:
    """Manages HLS streams with shared access and automatic cleanup."""
    
    def __init__(self, max_streams=10, inactive_timeout=30):
        self.streams = {}  # Key: "portalId_channelId", Value: stream info dict
        self.max_streams = max_streams
        self.inactive_timeout = 120  # 2 minutes (increased from 30 seconds for better stability)
        self.lock = threading.Lock()
        self.monitor_thread = None
        self.running = False
        logger.info(f"HLS Stream Manager initialized with max_streams={max_streams}, inactive_timeout={self.inactive_timeout}s")
        
    def start_monitoring(self):
        """Start the background monitoring thread."""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("HLS Stream Manager monitoring started")
    
    def _monitor_loop(self):
        """Background thread that monitors and cleans up inactive streams."""
        while self.running:
            try:
                time.sleep(10)  # Check every 10 seconds
                self._cleanup_inactive_streams()
            except Exception as e:
                logger.error(f"Error in HLS monitor loop: {e}")
    
    def _cleanup_inactive_streams(self):
        """Clean up streams that have been inactive or crashed."""
        current_time = time.time()
        streams_to_remove = []
        
        with self.lock:
            for stream_key, stream_info in self.streams.items():
                is_passthrough = stream_info.get('is_passthrough', False)
                
                # Skip process checks for passthrough streams
                if not is_passthrough:
                    # Check if process has crashed
                    try:
                        if stream_info['process'].poll() is not None:
                            returncode = stream_info['process'].returncode
                            if returncode != 0:
                                logger.error(f"FFmpeg process crashed for {stream_key} (exit code: {returncode})")
                            else:
                                logger.info(f"FFmpeg process ended normally for {stream_key}")
                            streams_to_remove.append(stream_key)
                            continue
                    except Exception as e:
                        logger.error(f"Error checking process status for {stream_key}: {e}")
                        streams_to_remove.append(stream_key)
                        continue
                
                # Check if stream is inactive
                inactive_time = current_time - stream_info['last_accessed']
                if inactive_time > self.inactive_timeout:
                    stream_type = "passthrough" if is_passthrough else "FFmpeg"
                    logger.info(f"Cleaning up inactive {stream_type} stream {stream_key} (idle for {inactive_time:.1f}s)")
                    streams_to_remove.append(stream_key)
        
        # Clean up streams outside the lock to avoid blocking
        for stream_key in streams_to_remove:
            try:
                self._stop_stream(stream_key)
            except Exception as e:
                logger.error(f"Error stopping stream {stream_key}: {e}")
    
    def _stop_stream(self, stream_key):
        """Stop a stream and clean up its resources."""
        with self.lock:
            if stream_key not in self.streams:
                logger.debug(f"Stream {stream_key} already removed")
                return
            
            stream_info = self.streams[stream_key]
            is_passthrough = stream_info.get('is_passthrough', False)
            
            # Terminate FFmpeg process (skip for passthrough streams)
            if not is_passthrough and stream_info.get('process'):
                try:
                    if stream_info['process'].poll() is None:
                        logger.debug(f"Terminating FFmpeg process for {stream_key}")
                        stream_info['process'].terminate()
                        try:
                            stream_info['process'].wait(timeout=5)
                            logger.debug(f"FFmpeg process terminated gracefully for {stream_key}")
                        except subprocess.TimeoutExpired:
                            logger.warning(f"FFmpeg process did not terminate, killing for {stream_key}")
                            stream_info['process'].kill()
                            stream_info['process'].wait(timeout=2)
                except Exception as e:
                    logger.error(f"Error terminating FFmpeg process for {stream_key}: {e}")
                    try:
                        stream_info['process'].kill()
                    except Exception as kill_error:
                        logger.error(f"Error killing FFmpeg process for {stream_key}: {kill_error}")
            
            # Clean up temp directory and HLS segments
            try:
                temp_dir = stream_info.get('temp_dir')
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.info(f"[HLS CLEANUP] Removed temp directory and segments: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temp dir for {stream_key}: {e}")
            
            # Additional cleanup: Check for orphaned HLS directories in /dev/shm
            try:
                portal_id = stream_info.get('portal_id')
                channel_id = stream_info.get('channel_id')
                if portal_id and channel_id:
                    # Clean up any orphaned directories matching this stream
                    shm_path = '/dev/shm'
                    if os.path.exists(shm_path):
                        pattern = f"MacReplayXC_hls_{portal_id}_{channel_id}_"
                        for item in os.listdir(shm_path):
                            if item.startswith(pattern):
                                orphan_path = os.path.join(shm_path, item)
                                try:
                                    shutil.rmtree(orphan_path, ignore_errors=True)
                                    logger.info(f"[HLS CLEANUP] Removed orphaned directory: {orphan_path}")
                                except Exception as cleanup_error:
                                    logger.debug(f"Could not remove orphaned dir {orphan_path}: {cleanup_error}")
            except Exception as e:
                logger.debug(f"Error during orphaned directory cleanup for {stream_key}: {e}")
            
            # Remove from active streams
            del self.streams[stream_key]
            logger.info(f"Stream {stream_key} stopped and cleaned up")
    
    def stop_stream(self, portal_id, channel_id):
        """Stop a specific HLS stream."""
        stream_key = f"{portal_id}_{channel_id}"
        
        with self.lock:
            if stream_key not in self.streams:
                logger.debug(f"Stream {stream_key} not found, nothing to stop")
                return
            
            stream_info = self.streams[stream_key]
            
            # Kill FFmpeg process
            if stream_info.get('process'):
                try:
                    stream_info['process'].kill()
                    logger.debug(f"Killed FFmpeg process for {stream_key}")
                except Exception as e:
                    logger.error(f"Error killing FFmpeg for {stream_key}: {e}")
            
            # Clean up temp directory and HLS segments
            try:
                temp_dir = stream_info.get('temp_dir')
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.info(f"[HLS CLEANUP] Removed temp directory and segments: {temp_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up temp dir for {stream_key}: {e}")
            
            # Additional cleanup: Check for orphaned HLS directories in /dev/shm
            try:
                shm_path = '/dev/shm'
                if os.path.exists(shm_path):
                    pattern = f"MacReplayXC_hls_{portal_id}_{channel_id}_"
                    for item in os.listdir(shm_path):
                        if item.startswith(pattern):
                            orphan_path = os.path.join(shm_path, item)
                            try:
                                shutil.rmtree(orphan_path, ignore_errors=True)
                                logger.info(f"[HLS CLEANUP] Removed orphaned directory: {orphan_path}")
                            except Exception as cleanup_error:
                                logger.debug(f"Could not remove orphaned dir {orphan_path}: {cleanup_error}")
            except Exception as e:
                logger.debug(f"Error during orphaned directory cleanup for {stream_key}: {e}")
            
            # Remove from active streams
            del self.streams[stream_key]
            logger.info(f"Stream {stream_key} stopped")
    
    def start_stream(self, portal_id, channel_id, stream_url, proxy=None):
        """Start or reuse an HLS stream for a channel."""
        import tempfile
        
        stream_key = f"{portal_id}_{channel_id}"
        
        with self.lock:
            # Check if stream already exists
            if stream_key in self.streams:
                self.streams[stream_key]['last_accessed'] = time.time()
                logger.info(f"Reusing existing HLS stream for {stream_key}")
                return self.streams[stream_key]
            
            # Check concurrency limit
            if len(self.streams) >= self.max_streams:
                logger.error(f"Max concurrent streams ({self.max_streams}) reached")
                raise Exception(f"Maximum concurrent streams ({self.max_streams}) reached")
            
            # Get HLS settings
            settings = getSettings()
            segment_type = settings.get("hls segment type", "mpegts")
            
            # Safe conversions for HLS settings (support floats for segment duration)
            segment_duration_str = settings.get("hls segment duration", "4")
            try:
                segment_duration = str(float(segment_duration_str)) if segment_duration_str and segment_duration_str != "false" else "4"
            except (ValueError, TypeError):
                segment_duration = "4"
            
            playlist_size_str = settings.get("hls playlist size", "6")
            try:
                playlist_size = str(int(playlist_size_str)) if playlist_size_str and playlist_size_str != "false" else "6"
            except (ValueError, TypeError):
                playlist_size = "6"
            
            # Safe int conversion for HLS connection timeout (separate from FFmpeg timeout)
            hls_timeout_str = settings.get("hls connection timeout", "3")
            try:
                timeout = int(hls_timeout_str) * 1000000 if hls_timeout_str and hls_timeout_str != "false" else 3000000
            except (ValueError, TypeError):
                timeout = 3000000
            
            # Detect if source is already HLS
            is_source_hls = is_hls_url(stream_url)
            
            # Create temp directory for HLS segments
            # Try to use /dev/shm (RAM disk) first, fallback to /tmp
            import os
            if os.path.exists('/dev/shm') and os.access('/dev/shm', os.W_OK):
                temp_base = '/dev/shm'
                logger.debug(f"[HLS] Using RAM disk (/dev/shm) for segments")
            else:
                temp_base = tempfile.gettempdir()
                logger.debug(f"[HLS] Using temp directory ({temp_base}) for segments")
            
            temp_dir = tempfile.mkdtemp(prefix=f"MacReplayXC_hls_{stream_key}_", dir=temp_base)
            playlist_path = os.path.join(temp_dir, "stream.m3u8")
            master_playlist_path = os.path.join(temp_dir, "master.m3u8")
            logger.info(f"[HLS] Created temp directory: {temp_dir}")
            logger.info(f"[HLS] Playlist path: {playlist_path}")
            
            # If source is already HLS, create a passthrough
            if is_source_hls:
                logger.info(f"Creating HLS passthrough for {stream_key}")
                
                stream_info = {
                    'process': None,
                    'temp_dir': temp_dir,
                    'playlist_path': playlist_path,
                    'master_playlist_path': master_playlist_path,
                    'last_accessed': time.time(),
                    'portal_id': portal_id,
                    'channel_id': channel_id,
                    'stream_url': stream_url,
                    'is_passthrough': True
                }
                
                # Create master playlist that points to the source
                with open(master_playlist_path, 'w') as f:
                    f.write("#EXTM3U\n")
                    f.write("#EXT-X-VERSION:7\n")
                    f.write(f'#EXT-X-STREAM-INF:BANDWIDTH=15000000,CODECS="avc1.640028,mp4a.40.2"\n')
                    f.write(stream_url + "\n")
                
                self.streams[stream_key] = stream_info
                logger.info(f"HLS passthrough ready for {stream_key}")
                return stream_info
            
            # Set segment pattern based on segment type
            if segment_type == "fmp4":
                segment_pattern = os.path.join(temp_dir, "seg_%03d.m4s")
                init_filename = "init.mp4"
            else:
                segment_pattern = os.path.join(temp_dir, "seg_%03d.ts")
                init_filename = None
            
            # Build FFmpeg command for HLS
            user_agent = str(getSettings().get("user agent", "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3"))
            
            ffmpeg_cmd = [
                "ffmpeg",
                "-v", "info",  # Add verbose logging to see codec info
                "-user_agent", user_agent,  # STB emulation
                "-fflags", "+genpts+discardcorrupt",
                "-flags", "low_delay",
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "15",
            ]
            
            if proxy:
                ffmpeg_cmd.extend(["-http_proxy", proxy])
            
            ffmpeg_cmd.extend(["-timeout", str(timeout)])
            
            ffmpeg_cmd.extend([
                "-i", stream_url,
                "-map", "0:v?",  # Map video if available
                "-map", "0:a?",  # Map audio if available
                "-c", "copy",    # Copy everything
                "-copyts",
                "-f", "hls",
                "-hls_time", segment_duration,
                "-hls_list_size", playlist_size,
                "-hls_flags", "independent_segments+omit_endlist+delete_segments",
                "-hls_delete_threshold", "10",  # Keep 10 extra segments (~30s buffer at 3s/segment)
                "-hls_segment_type", segment_type,
                "-hls_segment_filename", segment_pattern,
                "-hls_allow_cache", "0",
                "-start_number", "0"
            ])
            
            if segment_type == "fmp4":
                ffmpeg_cmd.extend(["-hls_fmp4_init_filename", init_filename])
            
            ffmpeg_cmd.append(playlist_path)
            
            # Start FFmpeg process with guaranteed cleanup
            process = None
            try:
                logger.info(f"[HLS] Starting FFmpeg process for {stream_key}")
                logger.info(f"[HLS] FFmpeg command: {' '.join(ffmpeg_cmd)}")
                
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
                
                # Store stream info
                stream_info = {
                    'process': process,
                    'temp_dir': temp_dir,
                    'playlist_path': playlist_path,
                    'master_playlist_path': master_playlist_path,
                    'last_accessed': time.time(),
                    'portal_id': portal_id,
                    'channel_id': channel_id,
                    'stream_url': stream_url,
                    'is_passthrough': False
                }
                
                self.streams[stream_key] = stream_info
                logger.info(f"[HLS] FFmpeg stream started for {stream_key}")
                return stream_info
                
            except Exception as e:
                logger.error(f"[HLS] Error starting FFmpeg for {stream_key}: {e}")
                
                # CRITICAL: Ensure FFmpeg process is killed on error
                if process:
                    try:
                        logger.warning(f"[HLS] Killing FFmpeg process due to error")
                        process.kill()
                        process.wait(timeout=2)
                    except Exception as kill_error:
                        logger.error(f"[HLS] Error killing FFmpeg process: {kill_error}")
                
                # Clean up temp directory
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"[HLS] Cleaned up temp directory after error")
                except Exception as cleanup_error:
                    logger.debug(f"[HLS] Error cleaning temp dir: {cleanup_error}")
                
                raise
    
    def get_file(self, portal_id, channel_id, filename):
        """Get a file path for a stream."""
        stream_key = f"{portal_id}_{channel_id}"
        
        with self.lock:
            if stream_key not in self.streams:
                logger.debug(f"[HLS] Stream {stream_key} not found in active streams")
                return None
            
            stream_info = self.streams[stream_key]
            stream_info['last_accessed'] = time.time()
            
            # Handle master playlist
            if filename == "master.m3u8":
                path = stream_info['master_playlist_path']
                exists = os.path.exists(path)
                logger.debug(f"[HLS] Checking master playlist: {path} (exists: {exists})")
                if exists:
                    return path
                return None
            
            # Handle stream playlist
            if filename == "stream.m3u8":
                path = stream_info['playlist_path']
                exists = os.path.exists(path)
                logger.debug(f"[HLS] Checking stream playlist: {path} (exists: {exists})")
                if exists:
                    return path
                # List directory contents for debugging
                temp_dir = stream_info['temp_dir']
                if os.path.exists(temp_dir):
                    files = os.listdir(temp_dir)
                    logger.debug(f"[HLS] Temp dir contents: {files}")
                else:
                    logger.warning(f"[HLS] Temp dir does not exist: {temp_dir}")
                return None
            
            # Handle segments
            file_path = os.path.join(stream_info['temp_dir'], filename)
            exists = os.path.exists(file_path)
            logger.debug(f"[HLS] Checking segment: {file_path} (exists: {exists})")
            if exists:
                return file_path
            
            return None


def loadConfig():
    try:
        with open(configFile) as f:
            data = json.load(f)
        logger.info(f"Config loaded from {configFile}")
    except FileNotFoundError:
        logger.warning("No existing config found. Creating a new one")
        data = {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}. Creating new config.")
        data = {}
    except Exception as e:
        logger.error(f"Error loading config: {e}. Creating new config.")
        data = {}

    data.setdefault("portals", {})
    data.setdefault("settings", {})

    settings = data["settings"]
    settingsOut = {}

    for setting, default in defaultSettings.items():
        value = settings.get(setting)
        if not value or type(default) != type(value):
            value = default
        settingsOut[setting] = value

    # Preserve extra keys not in defaultSettings (e.g. macstrom_url, macstrom_api_key)
    for key, value in settings.items():
        if key not in settingsOut:
            settingsOut[key] = value

    data["settings"] = settingsOut

    portals = data["portals"]
    portalsOut = {}

    for portal in portals:
        portalsOut[portal] = {}
        for setting, default in defaultPortal.items():
            value = portals[portal].get(setting)
            if not value or type(default) != type(value):
                value = default
            portalsOut[portal][setting] = value

    data["portals"] = portalsOut

    with open(configFile, "w") as f:
        json.dump(data, f, indent=4)

    return data

def getPortals():
    global config
    with config_lock:
        if not config:
            config = loadConfig()
        return config["portals"]

def savePortals(portals):
    try:
        with config_lock:
            with open(configFile, "w") as f:
                config["portals"] = portals
                json.dump(config, f, indent=4)
        logger.debug(f"Portals saved to {configFile}")
        
        # ENTFERNT: Aggressive Cache-Invalidierung bei jeder Portal-Speicherung
        # Cache wird nur bei echten Konfiguration-Änderungen invalidiert (manuell)
            
    except Exception as e:
        logger.error(f"Error saving portals: {e}")
        raise

def getSettings():
    global config
    with config_lock:
        if not config:
            config = loadConfig()
        return config["settings"]

def saveSettings(settings):
    try:
        with config_lock:
            with open(configFile, "w") as f:
                config["settings"] = settings
                json.dump(config, f, indent=4)
        logger.debug(f"Settings saved to {configFile}")
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise


# Channel Cache DEPRECATED - Using channels.db directly now
# channel_cache = init_channel_cache()
# logger.info(f"Channel cache initialized: mode={channel_cache.mode}, duration={channel_cache.cache_duration or 'unlimited'}")


def get_db_connection():
    """Get a database connection with increased timeout for concurrent access."""
    conn = sqlite3.connect(dbPath, timeout=30.0)  # 30 second timeout for locks
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database and create tables if they don't exist."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                portal TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                portal_name TEXT,
                name TEXT,
                number TEXT,
                genre TEXT,
                logo TEXT,
                enabled INTEGER DEFAULT 0,
                custom_name TEXT,
                custom_number TEXT,
                custom_genre TEXT,
                custom_epg_id TEXT,
                fallback_channel TEXT,
                has_portal_epg INTEGER DEFAULT 0,
                stream_cmd TEXT,
                available_macs TEXT,
                PRIMARY KEY (portal, channel_id)
            )
        ''')
        
        # Add columns if they don't exist (migration)
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN has_portal_epg INTEGER DEFAULT 0')
            logger.info("Added has_portal_epg column to database")
        except:
            pass  # Column already exists
        
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN stream_cmd TEXT')
            logger.info("Added stream_cmd column to database")
        except:
            pass  # Column already exists
        
        try:
            cursor.execute('ALTER TABLE channels ADD COLUMN available_macs TEXT')
            logger.info("Added available_macs column to database")
        except:
            pass  # Column already exists
        
        # Create indexes for better query performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_channels_enabled 
            ON channels(enabled)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_channels_name 
            ON channels(name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_channels_portal 
            ON channels(portal)
        ''')
        
        # Create table for selected genres per portal
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portal_genres (
                portal TEXT NOT NULL,
                genre TEXT NOT NULL,
                PRIMARY KEY (portal, genre)
            )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def get_vod_db_connection():
    """Get a VOD database connection."""
    conn = sqlite3.connect(vodsDbPath)
    conn.row_factory = sqlite3.Row
    return conn


def init_vod_db():
    """Initialize the VOD database and create tables if they don't exist."""
    conn = None
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # VOD Categories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vod_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_id TEXT NOT NULL,
                category_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content_type TEXT NOT NULL,
                item_count INTEGER DEFAULT 0,
                working_mac TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portal_id, category_id, content_type)
            )
        ''')
        
        # VOD Items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vod_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_id TEXT NOT NULL,
                category_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                content_type TEXT NOT NULL,
                name TEXT NOT NULL,
                year TEXT,
                description TEXT,
                genre TEXT,
                duration TEXT,
                rating TEXT,
                poster_url TEXT,
                cmd TEXT NOT NULL,
                working_macs TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portal_id, item_id, content_type)
            )
        ''')
        
        # Series Episodes table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS series_episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_id TEXT NOT NULL,
                series_id TEXT NOT NULL,
                season_number INTEGER NOT NULL,
                episode_number INTEGER NOT NULL,
                title TEXT,
                cmd TEXT NOT NULL,
                working_macs TEXT,
                UNIQUE(portal_id, series_id, season_number, episode_number)
            )
        ''')
        
        # User Selections table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vod_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portal_id TEXT NOT NULL,
                category_key TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                UNIQUE(portal_id, category_key)
            )
        ''')
        
        # VOD Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vod_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')
        
        # Create indexes for performance
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_vod_categories_portal 
            ON vod_categories(portal_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_vod_items_portal_category 
            ON vod_items(portal_id, category_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_vod_items_name 
            ON vod_items(name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_series_episodes_series 
            ON series_episodes(portal_id, series_id)
        ''')
        
        # Insert default settings if not exist
        cursor.execute('''
            INSERT OR IGNORE INTO vod_settings (key, value) VALUES ('stream_type', 'ffmpeg')
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO vod_settings (key, value) VALUES ('mac_rotation', 'true')
        ''')
        
        conn.commit()
        logger.info("VOD database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing VOD database: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def refresh_channels_cache_with_progress(portal_ids=None):
    """Wrapper for refresh_channels_cache with progress tracking."""
    global editor_refresh_progress
    try:
        return refresh_channels_cache(portal_ids=portal_ids)
    finally:
        editor_refresh_progress["running"] = False
        editor_refresh_progress["current_step"] = "Completed"

def refresh_channels_cache(portal_ids=None):
    """Refresh the channels cache from STB portals - respects genre filtering.
    
    Args:
        portal_ids: Optional list of portal IDs to refresh. If None, refreshes all portals.
    """
    global editor_refresh_progress
    
    logger.info("Starting channel cache refresh...")
    editor_refresh_progress["current_step"] = "Clearing old cache data..."
    
    conn = get_db_connection()
    cursor = conn.cursor()

    if portal_ids:
        # Only clear cache for the specific portals being refreshed
        cleared_count = 0
        for pid in portal_ids:
            cursor.execute('UPDATE channels SET stream_cmd = NULL, available_macs = NULL WHERE portal = ?', (pid,))
            cleared_count += cursor.rowcount
        logger.info(f"Cleared cache data for {len(portal_ids)} specific portal(s) ({cleared_count} rows)")
    else:
        # Full refresh — clear all
        cursor.execute('UPDATE channels SET stream_cmd = NULL, available_macs = NULL')
        cleared_count = cursor.rowcount
        logger.info(f"Cleared cache data from {cleared_count} channels")
    conn.commit()
    
    editor_refresh_progress["current_step"] = "Loading portals..."
    
    portals = getPortals()
    
    total_channels = 0
    portal_index = 0
    
    for portal_id in portals:
        # Skip portals not in the requested list (if a list was given)
        if portal_ids is not None and portal_id not in portal_ids:
            continue

        portal = portals[portal_id]
        if portal["enabled"] == "true":
            portal_index += 1
            portal_name = portal["name"]
            url = portal["url"]
            macs = list(portal["macs"].keys())
            proxy = portal["proxy"]
            
            # Get selected genres for this portal from database (primary source)
            selected_genres = []
            try:
                cursor.execute('SELECT genre FROM portal_genres WHERE portal = ?', (portal_id,))
                selected_genres = [row['genre'] for row in cursor.fetchall()]
                if selected_genres:
                    logger.info(f"Loaded {len(selected_genres)} genres from database for portal {portal_name}")
                else:
                    logger.info(f"No genres in database for portal {portal_name}")
                    
                    # Fallback: Check JSON config for migration/backup
                    json_genres = portal.get("selected genres", [])
                    if json_genres:
                        logger.info(f"Found {len(json_genres)} genres in JSON config - migrating to database")
                        selected_genres = json_genres
                        
                        # Sync to database
                        try:
                            for genre in selected_genres:
                                cursor.execute('INSERT INTO portal_genres (portal, genre) VALUES (?, ?)', (portal_id, genre))
                            conn.commit()
                            logger.info(f"Migrated {len(selected_genres)} genres from JSON to database")
                        except Exception as sync_error:
                            logger.error(f"Error syncing genres to database: {sync_error}")
                    else:
                        logger.info(f"No genre filter - will cache ALL channels")
            except Exception as e:
                logger.error(f"Error loading genres from database: {e}")
                selected_genres = []
            
            # Update progress
            editor_refresh_progress["current_portal"] = portal_name
            editor_refresh_progress["current_step"] = f"Starting {portal_name}..."
            editor_refresh_progress["portals_done"] = portal_index - 1
            
            logger.info(f"Fetching channels for portal: {portal_name} from {len(macs)} MACs")
            if selected_genres:
                logger.info(f"Selected genres ({len(selected_genres)}): {selected_genres}")
            editor_refresh_progress["current_step"] = f"{portal_name}: Found {len(macs)} MAC(s)"
            
            # Fetch from ALL MACs and merge
            all_channels_map = {}  # channel_id -> channel data
            all_genres_dict = {}  # genre_id -> genre_name
            channel_macs_map = {}  # channel_id -> [mac1, mac2, ...]
            mac_playback_limits = {}  # mac -> playback_limit
            
            mac_index = 0
            for mac in macs:
                mac_index += 1
                logger.info(f"Trying MAC: {mac}")
                editor_refresh_progress["current_step"] = f"{portal_name}: Fetching from MAC {mac_index}/{len(macs)}"
                try:
                    token = stb.getToken(url, mac, proxy)
                    if token:
                        profile = stb.getProfile(url, mac, token, proxy)
                        playback_limit = profile.get('playback_limit', 1) if profile else 1
                        mac_playback_limits[mac] = playback_limit
                        logger.info(f"MAC {mac}: playback_limit = {playback_limit}")
                        
                        editor_refresh_progress["current_step"] = f"{portal_name}: Getting channels from MAC {mac_index}/{len(macs)}"
                        mac_channels = stb.getAllChannels(url, mac, token, proxy)
                        editor_refresh_progress["current_step"] = f"{portal_name}: Getting genres from MAC {mac_index}/{len(macs)}"
                        mac_genres = stb.getGenreNames(url, mac, token, proxy)
                        
                        if mac_channels:
                            # Merge channels - add new ones and track which MACs have them
                            for channel in mac_channels:
                                channel_id = str(channel["id"])
                                if channel_id not in all_channels_map:
                                    all_channels_map[channel_id] = channel
                                    channel_macs_map[channel_id] = []
                                
                                # Track which MAC has this channel
                                if mac not in channel_macs_map[channel_id]:
                                    channel_macs_map[channel_id].append(mac)
                                    
                            logger.info(f"MAC {mac}: Added {len(mac_channels)} channels (total: {len(all_channels_map)})")
                            editor_refresh_progress["current_step"] = f"{portal_name}: MAC {mac_index}/{len(macs)} - {len(all_channels_map)} channels"
                        
                        if mac_genres:
                            all_genres_dict.update(mac_genres)
                            logger.info(f"MAC {mac}: Added genres (total: {len(all_genres_dict)})")
                            editor_refresh_progress["current_step"] = f"{portal_name}: MAC {mac_index}/{len(macs)} - {len(all_genres_dict)} genres"
                            
                except Exception as e:
                    logger.error(f"Error fetching from MAC {mac}: {e}")
                    continue
            
            if all_channels_map and all_genres_dict:
                logger.info(f"Processing {len(all_channels_map)} total channels for {portal_name}")
                editor_refresh_progress["current_step"] = f"{portal_name}: Updating cache data..."
                
                # Delete old channels for this portal first (clean slate)
                cursor.execute('DELETE FROM channels WHERE portal = ?', (portal_id,))
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"Deleted {deleted_count} old channels for portal {portal_name}")
                
                # Insert ONLY channels with selected genres
                inserted_count = 0
                skipped_count = 0
                
                for channel_id, channel in all_channels_map.items():
                    genre_id = str(channel.get("tv_genre_id", ""))
                    genre = str(all_genres_dict.get(genre_id, "")).strip()  # Remove whitespace
                    
                    # Skip if genre not selected
                    if selected_genres:
                        # Normalize selected genres (strip whitespace)
                        selected_genres_normalized = [g.strip() for g in selected_genres]
                        
                        if genre not in selected_genres_normalized:
                            # Genres are selected but this channel's genre is not selected - skip
                            if skipped_count < 5:  # Log first 5 skipped channels for debugging
                                logger.debug(f"Skipping channel '{channel.get('name', '')}' - genre '{genre}' not in {selected_genres_normalized}")
                            skipped_count += 1
                            continue
                    
                    # Get stream_cmd and available_macs with playback_limits and initial scores
                    stream_cmd = str(channel.get("cmd", ""))
                    macs_for_channel = channel_macs_map.get(channel_id, [])
                    # Format: "MAC|limit|success|fail|last_ts" (initial: 0|0|0)
                    available_macs = ",".join([f"{mac}|{mac_playback_limits.get(mac, 1)}|0|0|0" for mac in macs_for_channel])
                    
                    # Insert channel (all channels are new since we deleted old ones)
                    channel_name = str(channel.get("name", ""))
                    channel_number = str(channel.get("number", ""))
                    logo = str(channel.get("logo", ""))
                    is_enabled = 1  # Enable by default since genre is selected
                    
                    cursor.execute('''
                        INSERT INTO channels (
                            portal, channel_id, portal_name, name, number, genre, logo,
                            enabled, custom_name, custom_number, custom_genre, 
                            custom_epg_id, fallback_channel, has_portal_epg,
                            stream_cmd, available_macs
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', '', 0, ?, ?)
                    ''', (
                        portal_id, channel_id, portal_name, channel_name, channel_number,
                        genre, logo, is_enabled, stream_cmd, available_macs
                    ))
                    inserted_count += 1
                    
                    total_channels += 1
                
                conn.commit()
                logger.info(f"Inserted {inserted_count} channels for {portal_name}")
                logger.info(f"Skipped {skipped_count} channels (genres not selected)")
                editor_refresh_progress["current_step"] = f"{portal_name}: Completed - {inserted_count} channels cached"
                editor_refresh_progress["portals_done"] = portal_index
            else:
                logger.error(f"Failed to fetch channels for portal: {portal_name}")
                editor_refresh_progress["current_step"] = f"{portal_name}: Error - failed to fetch channels"
                editor_refresh_progress["portals_done"] = portal_index
    
    # Run VACUUM to reclaim disk space
    editor_refresh_progress["current_step"] = "Optimizing database (VACUUM)..."
    logger.info("Running VACUUM to reclaim disk space...")
    cursor.execute("VACUUM")
    conn.commit()
    logger.info("VACUUM completed")
    
    # Count actual cached channels (with stream_cmd)
    cursor.execute('SELECT COUNT(*) FROM channels WHERE stream_cmd IS NOT NULL')
    cached_count = cursor.fetchone()[0]
    
    # Count total channels in DB (including those without stream_cmd)
    cursor.execute('SELECT COUNT(*) FROM channels')
    total_in_db = cursor.fetchone()[0]
    
    conn.close()
    logger.info(f"Channel cache refresh complete. Channels with stream data: {cached_count} (total channels processed: {total_channels}, total in DB: {total_in_db})")
    editor_refresh_progress["current_step"] = f"Completed! {cached_count} channels cached from {portal_index} portals"
    
    # Regenerate playlist after cache refresh
    generate_playlist()
    
    return total_channels


# ============================================
# XC API User Management
# ============================================

def getXCUsers():
    """Get all XC API users."""
    with config_lock:
        return config.get("xc_users", {})


def saveXCUsers(users):
    """Save XC API users."""
    try:
        with config_lock:
            with open(configFile, "w") as f:
                config["xc_users"] = users
                json.dump(config, f, indent=4)
        logger.debug(f"XC users saved to {configFile}")
    except Exception as e:
        logger.error(f"Error saving XC users: {e}")
        raise


def validateXCUser(username, password):
    """Validate XC API user credentials."""
    users = getXCUsers()
    user_id = f"{username}_{password}"
    
    if user_id not in users:
        return None, "Invalid credentials"
    
    user = users[user_id]
    
    if user.get("enabled") != "true":
        return None, "User disabled"
    
    # Check expiry
    expires_at = user.get("expires_at", "")
    if expires_at:
        try:
            expiry_date = datetime.strptime(expires_at, "%Y-%m-%d")
            if datetime.now() > expiry_date:
                return None, "User expired"
        except:
            pass
    
    return user_id, user


def checkXCConnectionLimit(user_id, device_id):
    """Check if user can start a new connection."""
    users = getXCUsers()
    if user_id not in users:
        return False, "User not found"
    
    user = users[user_id]
    max_connections = int(user.get("max_connections", 1))
    active_connections = user.get("active_connections", {})
    
    # Clean up old connections (older than 60 seconds without activity)
    current_time = time.time()
    cleaned_connections = {}
    modified = False
    for dev_id, conn in active_connections.items():
        if current_time - conn.get("last_activity", 0) < 60:
            cleaned_connections[dev_id] = conn
        else:
            modified = True
    
    # Save if we cleaned up any connections
    if modified:
        user["active_connections"] = cleaned_connections
        saveXCUsers(users)
    
    # If this device already has a connection, allow it
    if device_id in cleaned_connections:
        return True, "Existing connection"
    
    # Check if under limit
    if len(cleaned_connections) >= max_connections:
        return False, f"Connection limit reached ({max_connections})"
    
    return True, "OK"


def registerXCConnection(user_id, device_id, portal_id, channel_id, ip):
    """Register a new XC API connection."""
    users = getXCUsers()
    if user_id not in users:
        return False
    
    if "active_connections" not in users[user_id]:
        users[user_id]["active_connections"] = {}
    
    users[user_id]["active_connections"][device_id] = {
        "portal_id": portal_id,
        "channel_id": channel_id,
        "started_at": time.time(),
        "last_activity": time.time(),
        "ip": ip
    }
    
    saveXCUsers(users)
    return True


def updateXCConnectionActivity(user_id, device_id):
    """Update last activity time for a connection."""
    users = getXCUsers()
    if user_id in users and device_id in users[user_id].get("active_connections", {}):
        users[user_id]["active_connections"][device_id]["last_activity"] = time.time()
        saveXCUsers(users)


def unregisterXCConnection(user_id, device_id):
    """Unregister an XC API connection."""
    users = getXCUsers()
    if user_id in users and device_id in users[user_id].get("active_connections", {}):
        del users[user_id]["active_connections"][device_id]
        saveXCUsers(users)


def cleanupOldXCConnections():
    """Cleanup connections older than 5 minutes without activity."""
    users = getXCUsers()
    current_time = time.time()
    timeout = 300  # 5 minutes
    
    modified = False
    # Create a copy to avoid RuntimeError if dictionary changes during iteration
    for user_id, user in list(users.items()):
        active_connections = user.get("active_connections", {})
        to_remove = []
        
        for device_id, conn_info in active_connections.items():
            last_activity = conn_info.get("last_activity", 0)
            if current_time - last_activity > timeout:
                to_remove.append(device_id)
        
        for device_id in to_remove:
            del active_connections[device_id]
            modified = True
    
    if modified:
        saveXCUsers(users)


def authorise(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        settings = getSettings()
        security = settings["enable security"]
        
        # If security is disabled, allow access
        if security == "false":
            return f(*args, **kwargs)
        
        # Check if user is logged in via session
        if flask.session.get("authenticated"):
            return f(*args, **kwargs)
        
        # Not authenticated, redirect to login page
        return redirect("/login", code=302)
    
    return decorated


def xc_auth_only(f):
    """Decorator for XC API routes - only allows XC API authentication, no HTTP Basic Auth fallback."""
    @wraps(f)
    def decorated(*args, **kwargs):
        settings = getSettings()
        
        if settings.get("xc api enabled") != "true":
            return flask.jsonify({"user_info": {"auth": 0, "message": "XC API disabled"}}), 403
        
        xc_username = request.args.get("username") or kwargs.get("username")
        xc_password = request.args.get("password") or kwargs.get("password")
        
        if not xc_username or not xc_password:
            return flask.jsonify({"user_info": {"auth": 0, "message": "Missing credentials"}}), 401
        
        user_id, user = validateXCUser(xc_username, xc_password)
        if not user:
            logger.debug(f"Auth failed: {xc_username}")
            return flask.jsonify({"user_info": {"auth": 0, "message": user_id}}), 401
        
        return f(*args, **kwargs)
    
    return decorated


def xc_auth_optional(f):
    """Decorator that allows both XC API auth and HTTP Basic Auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        settings = getSettings()
        
        # If security is disabled, allow access
        if settings.get("enable security") == "false":
            return f(*args, **kwargs)
        
        # Check if XC API is enabled and this is an XC API request
        if settings.get("xc api enabled") == "true":
            # Try XC API authentication first (from URL params or path)
            xc_username = request.args.get("username") or kwargs.get("username")
            xc_password = request.args.get("password") or kwargs.get("password")
            
            if xc_username and xc_password:
                user_id, user = validateXCUser(xc_username, xc_password)
                if user_id:
                    # XC API auth successful, allow access
                    return f(*args, **kwargs)
        
        # Fall back to HTTP Basic Auth
        auth = request.authorization
        username = settings["username"]
        password = settings["password"]
        
        if auth and auth.username == username and auth.password == password:
            return f(*args, **kwargs)
        
        return make_response(
            "Could not verify your login!",
            401,
            {"WWW-Authenticate": 'Basic realm="Login Required"'},
        )

    return decorated

def moveMac(portalId, mac):
    portals = getPortals()
    url = portals[portalId].get("url", "")
    macs = portals[portalId]["macs"]
    x = macs[mac]
    del macs[mac]
    macs[mac] = x
    portals[portalId]["macs"] = macs
    savePortals(portals)
    # Invalidate cached token for this MAC since it failed
    if url:
        invalidate_token_cache(url, mac)

@app.route("/data/<path:filename>", methods=["GET"])
def block_data_access(filename):
    """Block direct access to data files."""
    return "Access denied", 403


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    """Login page."""
    if request.method == "POST":
        settings = getSettings()
        username = request.form.get("username")
        password = request.form.get("password")
        
        if username == settings["username"] and password == settings["password"]:
            flask.session["authenticated"] = True
            flask.session.permanent = True
            return redirect("/dashboard", code=302)
        else:
            return render_template("login.html", error="Invalid credentials")
    
    # If already authenticated, redirect to dashboard
    if flask.session.get("authenticated"):
        return redirect("/dashboard", code=302)
    
    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    """Logout."""
    flask.session.clear()
    return redirect("/login", code=302)


# ============================================================================
# VOD/Series Routes
# ============================================================================

# Global VOD refresh state
vod_refresh_state = {
    "running": False,
    "portals_total": 0,
    "portals_done": 0,
    "current_portal": "",
    "current_step": ""
}

# MAC rotation state per portal
vod_mac_rotation_state = {}


def get_next_mac_for_portal(portal_id, macs):
    """Get next MAC in rotation for a portal."""
    global vod_mac_rotation_state
    
    if not macs:
        return None
    
    if portal_id not in vod_mac_rotation_state:
        vod_mac_rotation_state[portal_id] = 0
    
    current_index = vod_mac_rotation_state[portal_id]
    mac = macs[current_index % len(macs)]
    
    # Advance to next MAC for next request
    vod_mac_rotation_state[portal_id] = (current_index + 1) % len(macs)
    
    return mac


def try_get_vod_link_with_fallback(url, macs, cmd, content_type, proxy, series_id=None, season_id=None, episode_id=None):
    """Try to get VOD link with MAC fallback on failure."""
    working_mac = None
    link = None
    
    for mac in macs:
        try:
            token = stb.getToken(url, mac, proxy)
            if not token:
                continue
            
            if content_type == 'series' and series_id:
                link = stb.getSeriesLink(url, mac, token, cmd, series_id, season_id, episode_id, proxy)
            else:
                link = stb.getVodLink(url, mac, token, cmd, proxy)
            
            if link:
                working_mac = mac
                break
        except Exception as e:
            logger.debug(f"MAC {mac} failed for VOD link: {e}")
            continue
    
    return link, working_mac


@app.route("/api/vods", methods=["GET"])
@app.route("/vods", methods=["GET"])
@authorise
def vods_page():
    """Render VOD page."""
    return render_template("vods.html")


@app.route("/vods/portals", methods=["GET"])
@authorise
def vods_portals():
    """Get all portals with VOD/Series category counts."""
    conn = None
    try:
        portals = getPortals()
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        result = []
        for portal_id, portal in portals.items():
            if portal.get("enabled") != "true":
                continue
            
            # Get cached category counts
            cursor.execute('''
                SELECT content_type, COUNT(*) as count 
                FROM vod_categories 
                WHERE portal_id = ? 
                GROUP BY content_type
            ''', (portal_id,))
            
            cached_counts = {row['content_type']: row['count'] for row in cursor.fetchall()}
            
            # Get selected categories count
            cursor.execute('''
                SELECT COUNT(*) as count 
                FROM vod_selections 
                WHERE portal_id = ? AND enabled = 1
            ''', (portal_id,))
            selected_count = cursor.fetchone()['count']
            
            result.append({
                "id": portal_id,
                "name": portal.get("name", portal_id),
                "macs": len(portal.get("macs", {})),
                "vod_categories": cached_counts.get("vod", 0),
                "series_categories": cached_counts.get("series", 0),
                "cached_vod_categories": cached_counts.get("vod", 0),
                "cached_series_categories": cached_counts.get("series", 0),
                "selected_categories": selected_count,
                "has_cache": (cached_counts.get("vod", 0) + cached_counts.get("series", 0)) > 0
            })
        
        return jsonify({"success": True, "portals": result})
    except Exception as e:
        logger.error(f"Error getting VOD portals: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/categories/<portal_id>", methods=["GET"])
@authorise
def vods_categories(portal_id):
    """Get VOD/Series categories for a portal from cache."""
    conn = None
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT category_id, title, content_type, item_count, working_mac
            FROM vod_categories
            WHERE portal_id = ?
            ORDER BY content_type, title
        ''', (portal_id,))
        
        categories = []
        for row in cursor.fetchall():
            categories.append({
                "category_id": row['category_id'],
                "title": row['title'],
                "type": row['content_type'],
                "item_count": row['item_count'],
                "working_mac": row['working_mac'] or "N/A"
            })
        
        return jsonify({"success": True, "categories": categories})
    except Exception as e:
        logger.error(f"Error getting VOD categories: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/items/<portal_id>/<content_type>/<category_id>", methods=["GET"])
@authorise
def vods_items(portal_id, content_type, category_id):
    """Get VOD/Series items for a category from cache."""
    conn = None
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute('''
            SELECT COUNT(*) as total
            FROM vod_items
            WHERE portal_id = ? AND category_id = ? AND content_type = ?
        ''', (portal_id, category_id, content_type))
        total = cursor.fetchone()['total']
        
        # Get items with pagination
        offset = (page - 1) * per_page
        cursor.execute('''
            SELECT item_id, name, year, description, genre, duration, rating, poster_url, cmd, working_macs
            FROM vod_items
            WHERE portal_id = ? AND category_id = ? AND content_type = ?
            ORDER BY name
            LIMIT ? OFFSET ?
        ''', (portal_id, category_id, content_type, per_page, offset))
        
        items = []
        for row in cursor.fetchall():
            items.append({
                "id": row['item_id'],
                "name": row['name'],
                "year": row['year'],
                "description": row['description'],
                "genre": row['genre'],
                "duration": row['duration'],
                "rating": row['rating'],
                "screenshot_uri": row['poster_url'],
                "cmd": row['cmd'],
                "working_mac": row['working_macs'].split(',')[0] if row['working_macs'] else None
            })
        
        return jsonify({
            "success": True, 
            "items": items, 
            "total": total,
            "page": page,
            "has_more": (page * per_page) < total
        })
    except Exception as e:
        logger.error(f"Error getting VOD items: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/selection/<portal_id>", methods=["GET"])
@authorise
def vods_selection_get(portal_id):
    """Get selected categories for a portal."""
    conn = None
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT category_key FROM vod_selections
            WHERE portal_id = ? AND enabled = 1
        ''', (portal_id,))
        
        selected = [row['category_key'] for row in cursor.fetchall()]
        
        return jsonify({"success": True, "selected_categories": selected})
    except Exception as e:
        logger.error(f"Error getting VOD selection: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


# Global state for VOD items loading progress
vod_items_load_state = {
    "running": False,
    "portal_id": None,
    "categories_total": 0,
    "categories_done": 0,
    "current_category": "",
    "items_loaded": 0
}


@app.route("/vods/save-selection", methods=["POST"])
@authorise
def vods_selection_save():
    """Save selected categories for a portal and start loading items in background."""
    global vod_items_load_state
    
    try:
        data = request.get_json()
        portal_id = data.get('portal_id')
        selected_categories = data.get('selected_categories', [])
        load_items = data.get('load_items', True)  # Default to loading items
        
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Clear existing selections
        cursor.execute('DELETE FROM vod_selections WHERE portal_id = ?', (portal_id,))
        
        # Insert new selections
        for category_key in selected_categories:
            cursor.execute('''
                INSERT INTO vod_selections (portal_id, category_key, enabled)
                VALUES (?, ?, 1)
            ''', (portal_id, category_key))
        
        conn.commit()
        conn.close()
        
        # Start loading items in background if requested
        if load_items and selected_categories and not vod_items_load_state["running"]:
            def load_items_background():
                global vod_items_load_state
                try:
                    vod_items_load_state["running"] = True
                    vod_items_load_state["portal_id"] = portal_id
                    vod_items_load_state["categories_total"] = len(selected_categories)
                    vod_items_load_state["categories_done"] = 0
                    vod_items_load_state["items_loaded"] = 0
                    
                    portals = getPortals()
                    portal = portals.get(portal_id)
                    
                    if not portal:
                        logger.error(f"Portal {portal_id} not found for items loading")
                        return
                    
                    url = portal.get("url")
                    macs = list(portal.get("macs", {}).keys())
                    proxy = portal.get("proxy")
                    
                    if not macs:
                        logger.error(f"No MACs for portal {portal_id}")
                        return
                    
                    # Get working MACs for each category from database
                    conn = get_vod_db_connection()
                    cursor = conn.cursor()
                    
                    # Build a map of category -> working_macs
                    category_macs = {}
                    for category_key in selected_categories:
                        parts = category_key.split('_', 1)
                        if len(parts) != 2:
                            continue
                        content_type = parts[0]
                        category_id = parts[1]
                        
                        cursor.execute('''
                            SELECT working_mac FROM vod_categories 
                            WHERE portal_id = ? AND category_id = ? AND content_type = ?
                        ''', (portal_id, category_id, content_type))
                        row = cursor.fetchone()
                        if row and row['working_mac']:
                            # working_mac can be comma-separated list
                            category_macs[category_key] = row['working_mac'].split(',')
                        else:
                            category_macs[category_key] = macs  # Fallback to all MACs
                    
                    # Cache tokens for MACs
                    mac_tokens = {}
                    
                    for category_key in selected_categories:
                        # Parse category key (format: "vod_123" or "series_456")
                        parts = category_key.split('_', 1)
                        if len(parts) != 2:
                            continue
                        
                        content_type = parts[0]
                        category_id = parts[1]
                        
                        # Skip "all" category (category_id = "*")
                        if category_id == "*":
                            logger.debug(f"Skipping 'all' category: {category_key}")
                            continue
                        
                        vod_items_load_state["current_category"] = f"{content_type}: {category_id}"
                        
                        # Get working MACs for this category
                        cat_macs = category_macs.get(category_key, macs)
                        
                        # Try each MAC until we get items
                        category_items = 0
                        logger.info(f"Loading items for {category_key} (type={content_type}, id={category_id}), trying {len(cat_macs)} MACs")
                        
                        for mac in cat_macs:
                            # Get or create token for this MAC
                            if mac not in mac_tokens:
                                try:
                                    token = stb.getToken(url, mac, proxy)
                                    if token:
                                        mac_tokens[mac] = token
                                        logger.info(f"Got token for MAC {mac[:15]}...")
                                    else:
                                        logger.warning(f"No token returned for MAC {mac[:15]}...")
                                        continue
                                except Exception as e:
                                    logger.warning(f"Failed to get token for MAC {mac[:15]}...: {e}")
                                    continue
                            
                            if mac not in mac_tokens:
                                continue
                            
                            token = mac_tokens[mac]
                            
                            # Load items for this category with this MAC
                            page = 1
                            mac_items = 0
                            
                            while True:
                                try:
                                    logger.debug(f"Fetching {content_type} items for category {category_id}, page {page}, MAC {mac[:15]}...")
                                    if content_type == 'series':
                                        result = stb.getSeriesItems(url, mac, token, category_id, page, proxy)
                                    else:
                                        result = stb.getVodItems(url, mac, token, category_id, page, proxy)
                                    
                                    if not result:
                                        logger.debug(f"No result returned for category {category_id}")
                                        break
                                    
                                    items = result.get('items', [])
                                    if not items:
                                        logger.debug(f"Empty items list for category {category_id}")
                                        break
                                    
                                    logger.info(f"Got {len(items)} items for category {category_id}, page {page}")
                                    
                                    # Save items to database
                                    for item in items:
                                        item_id = str(item.get('id', ''))
                                        name = item.get('name', '')
                                        year = item.get('year', '')
                                        description = item.get('description', '')
                                        genre = item.get('genre_str', '')
                                        duration = item.get('time', '')
                                        rating = item.get('rating_imdb', '')
                                        poster_url = item.get('screenshot_uri', '')
                                        cmd = item.get('cmd', '')
                                        
                                        cursor.execute('''
                                            INSERT OR REPLACE INTO vod_items 
                                            (portal_id, category_id, item_id, content_type, name, year, description, 
                                             genre, duration, rating, poster_url, cmd, working_macs)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        ''', (portal_id, category_id, item_id, content_type, name, year, description,
                                              genre, duration, rating, poster_url, cmd, mac))
                                        
                                        mac_items += 1
                                        category_items += 1
                                        vod_items_load_state["items_loaded"] += 1
                                    
                                    conn.commit()
                                    
                                    # Check if there are more pages
                                    total = int(result.get('total', 0))
                                    if mac_items >= total or len(items) < 14:
                                        logger.debug(f"Finished loading category {category_id}: {mac_items} items (total: {total})")
                                        break
                                    
                                    page += 1
                                    
                                except Exception as e:
                                    logger.error(f"Error loading items for category {category_key} with MAC {mac[:15]}...: {e}")
                                    import traceback
                                    logger.error(traceback.format_exc())
                                    break
                            
                            # If we got items with this MAC, don't try other MACs
                            if mac_items > 0:
                                logger.info(f"Successfully loaded {mac_items} items for category {category_key} with MAC {mac[:15]}...")
                                break
                            else:
                                logger.debug(f"No items found for category {category_key} with MAC {mac[:15]}..., trying next MAC")
                        
                        vod_items_load_state["categories_done"] += 1
                        if category_items == 0:
                            logger.warning(f"No items loaded for category {category_key} after trying all MACs")
                        else:
                            logger.info(f"Loaded {category_items} items for category {category_key}")
                            # Update item_count in vod_categories table
                            cursor.execute('''
                                UPDATE vod_categories SET item_count = ?
                                WHERE portal_id = ? AND category_id = ? AND content_type = ?
                            ''', (category_items, portal_id, category_id, content_type))
                            conn.commit()
                    
                    conn.close()
                    logger.info(f"Finished loading {vod_items_load_state['items_loaded']} items for portal {portal_id}")
                    
                except Exception as e:
                    logger.error(f"Error in background items loading: {e}")
                finally:
                    vod_items_load_state["running"] = False
            
            # Start background thread
            threading.Thread(target=load_items_background, daemon=True).start()
        
        return jsonify({
            "success": True, 
            "count": len(selected_categories),
            "loading_items": load_items and len(selected_categories) > 0
        })
    except Exception as e:
        logger.error(f"Error saving VOD selection: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/vods/items-load/progress", methods=["GET"])
@authorise
def vods_items_load_progress():
    """Get VOD items loading progress."""
    return jsonify(vod_items_load_state)


@app.route("/vods/settings", methods=["GET"])
@authorise
def vods_settings_get():
    """Get VOD settings."""
    conn = None
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT key, value FROM vod_settings')
        settings = {row['key']: row['value'] for row in cursor.fetchall()}
        
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        logger.error(f"Error getting VOD settings: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/settings", methods=["POST"])
@authorise
def vods_settings_save():
    """Save VOD settings."""
    conn = None
    try:
        data = request.get_json()
        
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        for key, value in data.items():
            cursor.execute('''
                INSERT OR REPLACE INTO vod_settings (key, value) VALUES (?, ?)
            ''', (key, str(value)))
        
        conn.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving VOD settings: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/refresh", methods=["POST"])
@authorise
def vods_refresh():
    """Start VOD cache refresh in background - tests ALL MACs and merges categories."""
    global vod_refresh_state
    
    if vod_refresh_state["running"]:
        return jsonify({"success": False, "error": "Refresh already in progress"})
    
    def refresh_vod_cache():
        global vod_refresh_state
        try:
            vod_refresh_state["running"] = True
            portals = getPortals()
            enabled_portals = {k: v for k, v in portals.items() if v.get("enabled") == "true"}
            
            vod_refresh_state["portals_total"] = len(enabled_portals)
            vod_refresh_state["portals_done"] = 0
            
            for portal_id, portal in enabled_portals.items():
                vod_refresh_state["current_portal"] = portal.get("name", portal_id)
                vod_refresh_state["current_step"] = "Testing MACs..."
                
                url = portal.get("url")
                macs = list(portal.get("macs", {}).keys())
                proxy = portal.get("proxy")
                
                if not macs:
                    vod_refresh_state["portals_done"] += 1
                    continue
                
                conn = get_vod_db_connection()
                cursor = conn.cursor()
                
                # Track all categories by key to merge from multiple MACs
                all_vod_categories = {}
                all_series_categories = {}
                working_macs_count = 0
                
                # Helper function to extract item count from category
                def get_item_count(cat):
                    for field in ['censored', 'count', 'cnt', 'total', 'items_count', 'num', 'number']:
                        val = cat.get(field)
                        if val is not None:
                            try:
                                return int(val)
                            except (ValueError, TypeError):
                                pass
                    return 0
                
                # Test ALL MACs and merge their categories
                for mac_idx, mac in enumerate(macs):
                    vod_refresh_state["current_step"] = f"Testing MAC {mac_idx + 1}/{len(macs)}..."
                    try:
                        token = stb.getToken(url, mac, proxy)
                        if not token:
                            continue
                        
                        working_macs_count += 1
                        
                        # Get VOD categories from this MAC
                        vod_refresh_state["current_step"] = f"MAC {mac_idx + 1}: Loading VOD categories..."
                        vod_cats = stb.getVodCategories(url, mac, token, proxy)
                        if vod_cats:
                            for cat in vod_cats:
                                cat_id = str(cat.get('id', ''))
                                title = cat.get('title', '')
                                item_count = get_item_count(cat)
                                
                                # Skip "all" category (id = "*")
                                if cat_id == "*" or not cat_id:
                                    continue
                                
                                if cat_id not in all_vod_categories:
                                    all_vod_categories[cat_id] = {
                                        "title": title,
                                        "item_count": item_count,
                                        "working_macs": [mac]
                                    }
                                else:
                                    if mac not in all_vod_categories[cat_id]["working_macs"]:
                                        all_vod_categories[cat_id]["working_macs"].append(mac)
                                    if item_count > all_vod_categories[cat_id]["item_count"]:
                                        all_vod_categories[cat_id]["item_count"] = item_count
                        
                        # Get Series categories from this MAC
                        vod_refresh_state["current_step"] = f"MAC {mac_idx + 1}: Loading Series categories..."
                        series_cats = stb.getSeriesCategories(url, mac, token, proxy)
                        if series_cats:
                            for cat in series_cats:
                                cat_id = str(cat.get('id', ''))
                                title = cat.get('title', '')
                                item_count = get_item_count(cat)
                                
                                # Skip "all" category (id = "*")
                                if cat_id == "*" or not cat_id:
                                    continue
                                
                                if cat_id not in all_series_categories:
                                    all_series_categories[cat_id] = {
                                        "title": title,
                                        "item_count": item_count,
                                        "working_macs": [mac]
                                    }
                                else:
                                    if mac not in all_series_categories[cat_id]["working_macs"]:
                                        all_series_categories[cat_id]["working_macs"].append(mac)
                                    if item_count > all_series_categories[cat_id]["item_count"]:
                                        all_series_categories[cat_id]["item_count"] = item_count
                                        
                    except Exception as e:
                        logger.debug(f"MAC {mac} failed: {e}")
                        continue
                
                if working_macs_count == 0:
                    logger.warning(f"No working MAC for portal {portal_id}")
                    conn.close()
                    vod_refresh_state["portals_done"] += 1
                    continue
                
                # Save merged VOD categories to database
                vod_refresh_state["current_step"] = "Saving categories..."
                for cat_id, cat_data in all_vod_categories.items():
                    working_macs_str = ','.join(cat_data["working_macs"])
                    cursor.execute('''
                        INSERT OR REPLACE INTO vod_categories 
                        (portal_id, category_id, title, content_type, item_count, working_mac)
                        VALUES (?, ?, ?, 'vod', ?, ?)
                    ''', (portal_id, cat_id, cat_data["title"], cat_data["item_count"], working_macs_str))
                
                # Save merged Series categories to database
                for cat_id, cat_data in all_series_categories.items():
                    working_macs_str = ','.join(cat_data["working_macs"])
                    cursor.execute('''
                        INSERT OR REPLACE INTO vod_categories 
                        (portal_id, category_id, title, content_type, item_count, working_mac)
                        VALUES (?, ?, ?, 'series', ?, ?)
                    ''', (portal_id, cat_id, cat_data["title"], cat_data["item_count"], working_macs_str))
                
                conn.commit()
                conn.close()
                
                logger.info(f"Portal {portal_id}: {len(all_vod_categories)} VOD, {len(all_series_categories)} Series categories from {working_macs_count} MACs")
                vod_refresh_state["portals_done"] += 1
            
            vod_refresh_state["current_step"] = "Completed!"
            
        except Exception as e:
            logger.error(f"Error in VOD refresh: {e}")
        finally:
            vod_refresh_state["running"] = False
    
    # Start refresh in background thread
    threading.Thread(target=refresh_vod_cache, daemon=True).start()
    
    return jsonify({"success": True, "message": "VOD refresh started"})


@app.route("/vods/refresh/progress", methods=["GET"])
@authorise
def vods_refresh_progress():
    """Get VOD refresh progress."""
    return jsonify(vod_refresh_state)


@app.route("/vods/load-categories", methods=["POST"])
@authorise
def vods_load_categories():
    """Load categories for a single portal on-demand - tests ALL MACs and merges categories."""
    conn = None
    try:
        data = request.get_json()
        portal_id = data.get('portal_id')
        
        portals = getPortals()
        portal = portals.get(portal_id)
        
        if not portal:
            return jsonify({"success": False, "error": "Portal not found"})
        
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        if not macs:
            return jsonify({"success": False, "error": "No MACs configured"})
        
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Track all categories by key (category_id + content_type) to merge from multiple MACs
        all_vod_categories = {}  # key: category_id, value: {data, working_macs: []}
        all_series_categories = {}
        working_macs_count = 0
        
        # Helper function to extract item count from category - tries multiple field names
        def get_item_count(cat):
            # Try various possible field names for item count
            for field in ['censored', 'count', 'cnt', 'total', 'items_count', 'num', 'number']:
                val = cat.get(field)
                if val is not None:
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        pass
            return 0
        
        # Test ALL MACs and merge their categories
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if not token:
                    continue
                    
                working_macs_count += 1
                logger.info(f"Loading categories from MAC {mac} for portal {portal_id}")
                
                # Get VOD categories from this MAC
                vod_cats = stb.getVodCategories(url, mac, token, proxy)
                if vod_cats:
                    for cat in vod_cats:
                        cat_id = str(cat.get('id', ''))
                        title = cat.get('title', '')
                        item_count = get_item_count(cat)
                        
                        # Skip "all" category (id = "*")
                        if cat_id == "*" or not cat_id:
                            continue
                        
                        # Log first category to debug field names
                        if cat_id and not all_vod_categories:
                            logger.debug(f"VOD category fields: {list(cat.keys())}")
                        
                        if cat_id not in all_vod_categories:
                            all_vod_categories[cat_id] = {
                                "category_id": cat_id,
                                "title": title,
                                "item_count": item_count,
                                "working_macs": [mac]
                            }
                        else:
                            # Category exists, add this MAC to working_macs
                            if mac not in all_vod_categories[cat_id]["working_macs"]:
                                all_vod_categories[cat_id]["working_macs"].append(mac)
                            # Update item_count if higher
                            if item_count > all_vod_categories[cat_id]["item_count"]:
                                all_vod_categories[cat_id]["item_count"] = item_count
                
                # Get Series categories from this MAC
                series_cats = stb.getSeriesCategories(url, mac, token, proxy)
                if series_cats:
                    for cat in series_cats:
                        cat_id = str(cat.get('id', ''))
                        title = cat.get('title', '')
                        item_count = get_item_count(cat)
                        
                        # Skip "all" category (id = "*")
                        if cat_id == "*" or not cat_id:
                            continue
                        
                        # Log first category to debug field names
                        if cat_id and not all_series_categories:
                            logger.debug(f"Series category fields: {list(cat.keys())}")
                        
                        if cat_id not in all_series_categories:
                            all_series_categories[cat_id] = {
                                "category_id": cat_id,
                                "title": title,
                                "item_count": item_count,
                                "working_macs": [mac]
                            }
                        else:
                            # Category exists, add this MAC to working_macs
                            if mac not in all_series_categories[cat_id]["working_macs"]:
                                all_series_categories[cat_id]["working_macs"].append(mac)
                            # Update item_count if higher
                            if item_count > all_series_categories[cat_id]["item_count"]:
                                all_series_categories[cat_id]["item_count"] = item_count
                                
            except Exception as e:
                logger.warning(f"Error loading categories from MAC {mac}: {e}")
                continue
        
        if working_macs_count == 0:
            return jsonify({"success": False, "error": "Could not authenticate with any MAC"})
        
        categories = []
        
        # Save VOD categories to database
        for cat_id, cat_data in all_vod_categories.items():
            working_macs_str = ','.join(cat_data["working_macs"])
            cursor.execute('''
                INSERT OR REPLACE INTO vod_categories 
                (portal_id, category_id, title, content_type, item_count, working_mac)
                VALUES (?, ?, ?, 'vod', ?, ?)
            ''', (portal_id, cat_id, cat_data["title"], cat_data["item_count"], working_macs_str))
            
            categories.append({
                "category_id": cat_id,
                "title": cat_data["title"],
                "type": "vod",
                "item_count": cat_data["item_count"],
                "working_mac": working_macs_str
            })
        
        # Save Series categories to database
        for cat_id, cat_data in all_series_categories.items():
            working_macs_str = ','.join(cat_data["working_macs"])
            cursor.execute('''
                INSERT OR REPLACE INTO vod_categories 
                (portal_id, category_id, title, content_type, item_count, working_mac)
                VALUES (?, ?, ?, 'series', ?, ?)
            ''', (portal_id, cat_id, cat_data["title"], cat_data["item_count"], working_macs_str))
            
            categories.append({
                "category_id": cat_id,
                "title": cat_data["title"],
                "type": "series",
                "item_count": cat_data["item_count"],
                "working_mac": working_macs_str
            })
        
        conn.commit()
        
        logger.info(f"Loaded {len(all_vod_categories)} VOD and {len(all_series_categories)} Series categories from {working_macs_count} MACs for portal {portal_id}")
        
        return jsonify({
            "success": True, 
            "categories": categories,
            "macs_tested": len(macs),
            "macs_working": working_macs_count
        })
    except Exception as e:
        logger.error(f"Error loading categories: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/stream", methods=["POST"])
@authorise
def vods_stream():
    """Get stream URL for VOD item."""
    conn = None
    try:
        data = request.get_json()
        portal_id = data.get('portal_id')
        content_type = data.get('content_type', 'vod')
        cmd = data.get('cmd')
        series_id = data.get('series_id')
        season_id = data.get('season_id')
        episode_id = data.get('episode_id')
        
        if not portal_id or not cmd:
            return jsonify({"success": False, "error": "Missing portal_id or cmd"})
        
        portals = getPortals()
        portal = portals.get(portal_id)
        
        if not portal:
            return jsonify({"success": False, "error": "Portal not found"})
        
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        if not macs:
            return jsonify({"success": False, "error": "No MACs configured"})
        
        # Get VOD settings
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM vod_settings')
        settings = {row['key']: row['value'] for row in cursor.fetchall()}
        
        stream_type = settings.get('stream_type', 'ffmpeg')
        mac_rotation = settings.get('mac_rotation', 'true') == 'true'
        
        # Select MAC based on rotation setting
        if mac_rotation:
            selected_mac = get_next_mac_for_portal(portal_id, macs)
            macs_to_try = [selected_mac] + [m for m in macs if m != selected_mac]
        else:
            macs_to_try = macs
        
        # Get stream link with fallback
        link, working_mac = try_get_vod_link_with_fallback(
            url, macs_to_try, cmd, content_type, proxy,
            series_id, season_id, episode_id
        )
        
        if not link:
            return jsonify({"success": False, "error": "Could not get stream URL"})
        
        # Return based on stream type
        if stream_type == 'direct':
            return jsonify({
                "success": True,
                "stream_url": link,
                "stream_type": "direct",
                "working_mac": working_mac
            })
        else:
            # FFmpeg - return internal play URL
            return jsonify({
                "success": True,
                "stream_url": link,
                "stream_type": "ffmpeg",
                "working_mac": working_mac
            })
    except Exception as e:
        logger.error(f"Error getting VOD stream: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/items/load", methods=["POST"])
@authorise
def vods_load_items():
    """Load items for a category on-demand and cache them."""
    conn = None
    try:
        data = request.get_json()
        portal_id = data.get('portal_id')
        category_id = data.get('category_id')
        content_type = data.get('content_type', 'vod')
        
        portals = getPortals()
        portal = portals.get(portal_id)
        
        if not portal:
            return jsonify({"success": False, "error": "Portal not found"})
        
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        if not macs:
            return jsonify({"success": False, "error": "No MACs configured"})
        
        # Try each MAC until one works
        working_mac = None
        token = None
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    working_mac = mac
                    break
            except:
                continue
        
        if not token:
            return jsonify({"success": False, "error": "Could not authenticate"})
        
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        all_items = []
        page = 1
        
        while True:
            if content_type == 'series':
                result = stb.getSeriesItems(url, working_mac, token, category_id, page, proxy)
            else:
                result = stb.getVodItems(url, working_mac, token, category_id, page, proxy)
            
            if not result or not result.get('items'):
                break
            
            items = result['items']
            all_items.extend(items)
            
            # Save items to database
            for item in items:
                item_id = str(item.get('id', ''))
                name = item.get('name', '')
                year = item.get('year', '')
                description = item.get('description', '')
                genre = item.get('genre_str', '')
                duration = item.get('time', '')
                rating = item.get('rating_imdb', '')
                poster_url = item.get('screenshot_uri', '')
                cmd = item.get('cmd', '')
                
                cursor.execute('''
                    INSERT OR REPLACE INTO vod_items 
                    (portal_id, category_id, item_id, content_type, name, year, description, 
                     genre, duration, rating, poster_url, cmd, working_macs)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (portal_id, category_id, item_id, content_type, name, year, description,
                      genre, duration, rating, poster_url, cmd, working_mac))
            
            # Check if there are more pages
            total = result.get('total', 0)
            if len(all_items) >= total or len(items) < 14:
                break
            
            page += 1
        
        conn.commit()
        
        return jsonify({
            "success": True,
            "items_loaded": len(all_items),
            "category_id": category_id
        })
    except Exception as e:
        logger.error(f"Error loading VOD items: {e}")
        return jsonify({"success": False, "error": str(e)})
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/vods/debug/test-api", methods=["POST"])
@authorise
def vods_debug_test_api():
    """Debug endpoint to test VOD API directly and return raw response."""
    try:
        data = request.get_json()
        portal_id = data.get('portal_id')
        category_id = data.get('category_id')
        content_type = data.get('content_type', 'vod')
        
        portals = getPortals()
        portal = portals.get(portal_id)
        
        if not portal:
            return jsonify({"success": False, "error": "Portal not found"})
        
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        if not macs:
            return jsonify({"success": False, "error": "No MACs configured"})
        
        # Try first MAC
        mac = macs[0]
        token = stb.getToken(url, mac, proxy)
        
        if not token:
            return jsonify({"success": False, "error": f"Could not get token for MAC {mac}"})
        
        # Make direct API call
        import requests as req
        
        proxies = {"http": proxy, "https": proxy} if proxy else None
        cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Authorization": "Bearer " + token,
        }
        
        # Build params matching macvod.py exactly
        params = {
            "type": content_type if content_type == "series" else "vod",
            "action": "get_ordered_list",
            "movie_id": "0",
            "season_id": "0",
            "episode_id": "0",
            "row": "0",
            "JsHttpRequest": "1-xml",
            "category": str(category_id),
            "sortby": "added",
            "fav": "0",
            "hd": "0",
            "not_ended": "0",
            "abc": "*",
            "genre": "*",
            "years": "*",
            "search": "",
            "p": "1"
        }
        
        response = req.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        
        return jsonify({
            "success": True,
            "portal_id": portal_id,
            "portal_url": url,
            "mac": mac,
            "category_id": category_id,
            "content_type": content_type,
            "request_url": response.url,
            "status_code": response.status_code,
            "response_text": response.text[:2000] if len(response.text) > 2000 else response.text,
            "response_json": response.json() if response.status_code == 200 else None
        })
    except Exception as e:
        logger.error(f"Error in VOD debug: {e}")
        import traceback
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()})


@app.route("/vods/play/<portal_id>/<content_type>", methods=["POST"])
@authorise
def vods_play(portal_id, content_type):
    """Get playback URL for VOD/Series item by calling create_link API.
    
    Tests each MAC to find one that has access to the content.
    """
    try:
        data = request.get_json()
        cmd = data.get('cmd')
        episode_num = data.get('episode_num', '0')  # Episode number for series
        season_num = data.get('season_num', '0')
        test_stream = data.get('test_stream', True)  # Test stream by default
        
        if not cmd:
            return jsonify({"success": False, "error": "No cmd provided"})
        
        portals = getPortals()
        portal = portals.get(portal_id)
        
        if not portal:
            return jsonify({"success": False, "error": "Portal not found"})
        
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        if not macs:
            return jsonify({"success": False, "error": "No MACs configured"})
        
        # Get VOD settings for stream testing
        settings = getSettings()
        should_test = settings.get("test streams", "true") == "true" and test_stream
        
        failed_macs = []
        
        # Try each MAC until we get a working link
        for mac in macs:
            try:
                logger.info(f"Trying MAC {mac} for {content_type} content...")
                token = stb.getToken(url, mac, proxy)
                if not token:
                    logger.warning(f"MAC {mac}: Failed to get token")
                    failed_macs.append({"mac": mac, "reason": "No token"})
                    continue
                
                # Call create_link API
                if content_type == 'series':
                    # For series, episode_num is passed as the 'series' parameter
                    link = stb.getSeriesLink(url, mac, token, cmd, episode_num, season_num, episode_num, proxy)
                else:
                    link = stb.getVodLink(url, mac, token, cmd, proxy)
                
                if not link:
                    logger.warning(f"MAC {mac}: No link returned from API")
                    failed_macs.append({"mac": mac, "reason": "No link from API"})
                    continue
                
                # Test if the stream is accessible
                if should_test:
                    logger.info(f"Testing stream link from MAC {mac}...")
                    if stb.testStreamLink(link, proxy, timeout=5):
                        logger.info(f"MAC {mac}: Stream test PASSED - {link[:50]}...")
                        return jsonify({
                            "success": True,
                            "url": link,
                            "mac": mac,
                            "tested": True
                        })
                    else:
                        logger.warning(f"MAC {mac}: Stream test FAILED - {link[:50]}...")
                        failed_macs.append({"mac": mac, "reason": "Stream test failed"})
                        continue
                else:
                    # Return without testing
                    logger.info(f"Got play link for {content_type} (untested): {link[:50]}...")
                    return jsonify({
                        "success": True,
                        "url": link,
                        "mac": mac,
                        "tested": False
                    })
                    
            except Exception as e:
                logger.warning(f"Error getting play link with MAC {mac}: {e}")
                failed_macs.append({"mac": mac, "reason": str(e)})
                continue
        
        # All MACs failed
        error_msg = f"Could not get working stream from any MAC. Tried {len(macs)} MAC(s)."
        if failed_macs:
            reasons = [f"{m['mac'][:10]}...: {m['reason']}" for m in failed_macs[:3]]
            error_msg += f" Reasons: {'; '.join(reasons)}"
        
        return jsonify({"success": False, "error": error_msg, "failed_macs": failed_macs})
    except Exception as e:
        logger.error(f"Error in VOD play: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/vods/series/<portal_id>/<series_id>/episodes", methods=["GET"])
@authorise
def vods_series_episodes(portal_id, series_id):
    """Get episodes for a series."""
    try:
        portals = getPortals()
        portal = portals.get(portal_id)
        
        if not portal:
            return jsonify({"success": False, "error": "Portal not found"})
        
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        if not macs:
            return jsonify({"success": False, "error": "No MACs configured"})
        
        # Try each MAC until we get episodes
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if not token:
                    continue
                
                # Get series info with episodes
                series_info = stb.getSeriesInfo(url, mac, token, series_id, proxy)
                
                if series_info:
                    logger.info(f"Got series info for {series_id}")
                    return jsonify({
                        "success": True,
                        "series_info": series_info,
                        "mac": mac
                    })
            except Exception as e:
                logger.warning(f"Error getting series info with MAC {mac}: {e}")
                continue
        
        return jsonify({"success": False, "error": "Could not get series info from any MAC"})
    except Exception as e:
        logger.error(f"Error getting series episodes: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/", methods=["GET"])
@authorise
def home():
    return redirect("/dashboard", code=302)

@app.route("/portals", methods=["GET"])
@authorise
def portals():
    # Check if we should show genre modal
    show_genre_modal = flask.session.pop('show_genre_modal', False)
    genre_modal_portal_id = flask.session.pop('genre_modal_portal_id', None)
    genre_modal_portal_name = flask.session.pop('genre_modal_portal_name', None)
    
    return render_template("portals.html", 
                         portals=getPortals(),
                         settings=getSettings(),
                         show_genre_modal=show_genre_modal,
                         genre_modal_portal_id=genre_modal_portal_id,
                         genre_modal_portal_name=genre_modal_portal_name)

@app.route("/portal/test-macs", methods=["POST"])
@authorise
def portal_test_macs():
    """Test MAC addresses for a portal."""
    try:
        data = request.json
        url = data.get('url')
        macs = data.get('macs', [])
        proxy = data.get('proxy', '')
        
        if not url:
            return flask.jsonify({"error": "No URL provided"}), 400
        
        if not validate_url(url):
            return flask.jsonify({"error": "Invalid URL format"}), 400
        
        if not macs:
            return flask.jsonify({"error": "No MAC addresses provided"}), 400
        
        # Validate MAC addresses
        invalid_macs = [mac for mac in macs if not validate_mac_address(mac)]
        if invalid_macs:
            return flask.jsonify({"error": f"Invalid MAC address format: {', '.join(invalid_macs)}"}), 400
        
        # Ensure URL ends with .php
        if not url.endswith(".php"):
            url = stb.getUrl(url, proxy)
            if not url:
                return flask.jsonify({"error": "Invalid portal URL"}), 400
        
        results = []
        
        for mac in macs:
            mac = mac.strip()
            if not mac:
                continue
            
            result = {
                "mac": mac,
                "valid": False,
                "expiry": None
            }
            
            try:
                logger.info(f"Testing MAC: {mac}")
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    expiry = stb.getExpires(url, mac, token, proxy)
                    if expiry:
                        result["valid"] = True
                        result["expiry"] = expiry
                        logger.info(f"MAC {mac} is valid, expires: {expiry}")
                    else:
                        logger.warning(f"MAC {mac} got token but no expiry")
                else:
                    logger.warning(f"MAC {mac} failed to get token")
            except Exception as e:
                logger.error(f"Error testing MAC {mac}: {e}")
            
            results.append(result)
        
        return flask.jsonify({"results": results})
    except Exception as e:
        logger.error(f"Error in portal_test_macs: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/portal/add", methods=["POST"])
@authorise
def portalsAdd():
    id = uuid.uuid4().hex
    enabled = "true"
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    
    # Validate inputs
    if not name:
        flash("Portal name is required", "danger")
        return redirect("/portals", code=302)
    
    if not url or not validate_url(url):
        flash("Valid portal URL is required", "danger")
        return redirect("/portals", code=302)
    
    # Support newline-separated MACs
    macs_text = request.form.get("macs", "")
    macs = [m.strip() for m in macs_text.split('\n') if m.strip()]
    macs = list(set(macs))  # Remove duplicates
    
    # Validate MAC addresses
    invalid_macs = [mac for mac in macs if not validate_mac_address(mac)]
    if invalid_macs:
        flash(f"Invalid MAC address format: {', '.join(invalid_macs)}", "danger")
        return redirect("/portals", code=302)
    
    if not macs:
        flash("At least one MAC address is required", "danger")
        return redirect("/portals", code=302)
    
    streamsPerMac = request.form.get("streams per mac", "1")
    epgOffset = request.form.get("epg offset", "0")
    proxy = request.form.get("proxy", "").strip()
    portalPrefix = request.form.get("portal prefix", "").strip()
    
    # Validate proxy if provided
    if proxy and not validate_proxy_url(proxy):
        proxy_type = get_proxy_type(proxy)
        flash(f"Invalid proxy format. Detected type: {proxy_type}. Use: http://host:port, socks5://host:port, ss://method:password@host:port, etc.", "danger")
        return redirect("/portals", code=302)

    if not url.endswith(".php"):
        url = stb.getUrl(url, proxy)
        if not url:
            logger.error("Error getting URL for Portal({})".format(name))
            flash("Error getting URL for Portal({})".format(name), "danger")
            return redirect("/portals", code=302)

    macsd = {}

    for mac in macs:
        token = stb.getToken(url, mac, proxy)
        if token:
            stb.getProfile(url, mac, token, proxy)
            expiry = stb.getExpires(url, mac, token, proxy)
            if expiry:
                macsd[mac] = expiry
                logger.info(
                    "Successfully tested MAC({}) for Portal({})".format(mac, name)
                )
                flash(
                    "Successfully tested MAC({}) for Portal({})".format(mac, name),
                    "success",
                )
                continue

        logger.error("Error testing MAC({}) for Portal({})".format(mac, name))
        flash("Error testing MAC({}) for Portal({})".format(mac, name), "danger")

    if len(macsd) > 0:
        portal = {
            "enabled": enabled,
            "name": name,
            "url": url,
            "macs": macsd,
            "streams per mac": streamsPerMac,
            "epg offset": epgOffset,
            "proxy": proxy,
            "portal prefix": portalPrefix,
        }

        for setting, default in defaultPortal.items():
            if not portal.get(setting):
                portal[setting] = default

        portals = getPortals()
        portals[id] = portal
        savePortals(portals)
        logger.info("Portal({}) added!".format(portal["name"]))
        
        # Automatically refresh channels.db for new portal
        try:
            logger.info(f"Auto-refreshing channels.db for new portal: {name}")
            
            # Fetch channels from ALL MACs and save to DB
            all_channels_map = {}
            all_genres_dict = {}
            channel_macs_map = {}
            mac_playback_limits = {}
            mac_has_de = {}  # Store DE content detection per MAC
            
            # Region detection patterns
            de_patterns = ['DE', 'GER', 'GERMAN', 'DEUTSCH', 'ALEMANGE', 'DEUTSCHLAND', 'GERMANY']
            
            for mac in macsd.keys():
                try:
                    token = stb.getToken(url, mac, proxy)
                    if token:
                        profile = stb.getProfile(url, mac, token, proxy)
                        playback_limit = profile.get('playback_limit', 1) if profile else 1
                        mac_playback_limits[mac] = playback_limit
                        logger.info(f"MAC {mac}: playback_limit = {playback_limit}")
                        
                        mac_channels = stb.getAllChannels(url, mac, token, proxy)
                        mac_genres = stb.getGenreNames(url, mac, token, proxy)
                        
                        # Detect DE content in genres
                        has_de = False
                        if mac_genres:
                            for genre_id, genre_name in mac_genres.items():
                                genre_upper = genre_name.upper()
                                if any(pattern in genre_upper for pattern in de_patterns):
                                    has_de = True
                                    break
                        mac_has_de[mac] = has_de
                        logger.info(f"[PORTAL ADD] MAC {mac} has DE content: {has_de}")
                        
                        if mac_channels:
                            for channel in mac_channels:
                                channel_id = str(channel["id"])
                                if channel_id not in all_channels_map:
                                    all_channels_map[channel_id] = channel
                                    channel_macs_map[channel_id] = []
                                if mac not in channel_macs_map[channel_id]:
                                    channel_macs_map[channel_id].append(mac)
                        
                        if mac_genres:
                            all_genres_dict.update(mac_genres)
                except Exception as e:
                    logger.error(f"Error fetching from MAC {mac}: {e}")
                    mac_has_de[mac] = False
            
            # Save DE detection results to portal config
            portals = getPortals()
            portals[id]["mac_has_de"] = mac_has_de
            savePortals(portals)
            logger.info(f"Saved DE detection results for {len(mac_has_de)} MACs")
            
            # DON'T save channels to DB yet - wait for genre selection
            # User will select genres in the modal, then channels will be inserted
            logger.info(f"Portal added with {len(all_channels_map)} channels. Waiting for genre selection...")
        except Exception as e:
            logger.error(f"Error auto-refreshing channels.db: {e}")
        
        # Store portal ID in session for genre selection modal
        flask.session['show_genre_modal'] = True
        flask.session['genre_modal_portal_id'] = id
        flask.session['genre_modal_portal_name'] = name
        return redirect("/portals", code=302)

    else:
        logger.error(
            "None of the MACs tested OK for Portal({}). Adding not successfull".format(
                name
            )
        )

    return redirect("/portals", code=302)

@app.route("/portal/update", methods=["POST"])
@authorise
def portalUpdate():
    id = request.form["id"]
    enabled = request.form.get("enabled", "false")
    name = request.form["name"]
    url = request.form["url"]
    # Support newline-separated MACs
    macs_text = request.form["macs"]
    newmacs = [m.strip() for m in macs_text.split('\n') if m.strip()]
    newmacs = list(set(newmacs))  # Remove duplicates
    streamsPerMac = request.form["streams per mac"]
    epgOffset = request.form["epg offset"]
    proxy = request.form["proxy"].strip()
    portalPrefix = request.form.get("portal prefix", "").strip()
    retest = request.form.get("retest", None)
    
    # Validate proxy if provided
    if proxy and not validate_proxy_url(proxy):
        proxy_type = get_proxy_type(proxy)
        flash(f"Invalid proxy format. Detected type: {proxy_type}. Use: http://host:port, socks5://host:port, ss://method:password@host:port, etc.", "danger")
        return redirect("/portals", code=302)

    if not url.endswith(".php"):
        url = stb.getUrl(url, proxy)
        if not url:
            logger.error("Error getting URL for Portal({})".format(name))
            flash("Error getting URL for Portal({})".format(name), "danger")
            return redirect("/portals", code=302)

    portals = getPortals()
    oldmacs = portals[id]["macs"]
    macsout = {}
    deadmacs = []

    for mac in newmacs:
        if retest or mac not in oldmacs.keys():
            token = stb.getToken(url, mac, proxy)
            if token:
                stb.getProfile(url, mac, token, proxy)
                expiry = stb.getExpires(url, mac, token, proxy)
                if expiry:
                    macsout[mac] = expiry
                    logger.info(
                        "Successfully tested MAC({}) for Portal({})".format(mac, name)
                    )
                    flash(
                        "Successfully tested MAC({}) for Portal({})".format(mac, name),
                        "success",
                    )

            if mac not in list(macsout.keys()):
                deadmacs.append(mac)

        if mac in oldmacs.keys() and mac not in deadmacs:
            macsout[mac] = oldmacs[mac]

        if mac not in macsout.keys():
            logger.error("Error testing MAC({}) for Portal({})".format(mac, name))
            flash("Error testing MAC({}) for Portal({})".format(mac, name), "danger")

    if len(macsout) > 0:
        portals[id]["enabled"] = enabled
        portals[id]["name"] = name
        portals[id]["url"] = url
        portals[id]["macs"] = macsout
        portals[id]["streams per mac"] = streamsPerMac
        portals[id]["epg offset"] = epgOffset
        portals[id]["proxy"] = proxy
        portals[id]["portal prefix"] = portalPrefix
        savePortals(portals)
        logger.info("Portal({}) updated!".format(name))
        flash("Portal({}) updated!".format(name), "success")
        
        # Auto-refresh channels.db if MACs changed
        if retest or set(macsout.keys()) != set(oldmacs.keys()):
            try:
                logger.info(f"Auto-refreshing channels.db for updated portal: {name}")
                
                # Determine which MACs are new (not in oldmacs)
                new_macs = set(macsout.keys()) - set(oldmacs.keys())
                existing_macs = set(macsout.keys()) & set(oldmacs.keys())
                
                logger.info(f"New MACs: {len(new_macs)}, Existing MACs: {len(existing_macs)}")
                
                macs_to_fetch = list(new_macs)
                
                # If retest=true but no new MACs, skip channel fetching entirely
                all_channels_map = {}
                all_genres_dict = {}
                channel_macs_map = {}
                mac_playback_limits = {}
                mac_has_de = {}

                if retest and not new_macs:
                    logger.info(f"Re-test with no new MACs - skipping channel fetch (use 'Alle Channels neu laden' to force)")
                    portals = getPortals()
                    savePortals(portals)
                    flash("Portal updated. MACs verified. Use 'Alle Channels neu laden' to refresh channel list.", "info")
                elif macs_to_fetch:                    # Fetch channels only for new MACs
                    de_patterns = ['DE', 'GER', 'GERMAN', 'DEUTSCH', 'ALEMANGE', 'DEUTSCHLAND', 'GERMANY']
                    
                    for mac in macs_to_fetch:
                        try:
                            token = stb.getToken(url, mac, proxy)
                            if token:
                                profile = stb.getProfile(url, mac, token, proxy)
                                playback_limit = profile.get("playback_limit", 1) if profile else 1
                                mac_playback_limits[mac] = playback_limit
                                logger.info(f"[PORTAL EDIT] MAC {mac} has playback_limit: {playback_limit}")
                                
                                mac_channels = stb.getAllChannels(url, mac, token, proxy)
                                mac_genres = stb.getGenreNames(url, mac, token, proxy)
                                
                                has_de = False
                                if mac_genres:
                                    for genre_id, genre_name in mac_genres.items():
                                        genre_upper = genre_name.upper()
                                        if any(pattern in genre_upper for pattern in de_patterns):
                                            has_de = True
                                            break
                                mac_has_de[mac] = has_de
                                logger.info(f"[PORTAL EDIT] MAC {mac} has DE content: {has_de}")
                                
                                if mac_channels:
                                    for channel in mac_channels:
                                        channel_id = str(channel["id"])
                                        if channel_id not in all_channels_map:
                                            all_channels_map[channel_id] = channel
                                            channel_macs_map[channel_id] = []
                                        if mac not in channel_macs_map[channel_id]:
                                            channel_macs_map[channel_id].append(mac)
                                
                                if mac_genres:
                                    all_genres_dict.update(mac_genres)
                        except Exception as e:
                            logger.error(f"Error fetching from MAC {mac}: {e}")
                            mac_has_de[mac] = False
                    
                    # Save DE detection results
                    portals = getPortals()
                    if "mac_has_de" not in portals[id]:
                        portals[id]["mac_has_de"] = {}
                    portals[id]["mac_has_de"].update(mac_has_de)
                    savePortals(portals)
                    
                    # Add new MAC's channels to existing DB entries
                    if all_channels_map:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        for channel_id, channel in all_channels_map.items():
                            stream_cmd = str(channel.get("cmd", ""))
                            macs_with_limits = []
                            for mac in channel_macs_map.get(channel_id, []):
                                limit = mac_playback_limits.get(mac, 1)
                                macs_with_limits.append(f"{mac}|{limit}|0|0|0")
                            new_macs_str = ",".join(macs_with_limits)
                            
                            # Check if channel already exists - if so, append new MACs
                            cursor.execute('SELECT available_macs FROM channels WHERE portal = ? AND channel_id = ?', (id, channel_id))
                            existing = cursor.fetchone()
                            if existing and existing['available_macs']:
                                # Append new MACs to existing
                                combined = existing['available_macs'] + "," + new_macs_str
                                cursor.execute('UPDATE channels SET available_macs = ?, stream_cmd = ? WHERE portal = ? AND channel_id = ?',
                                             (combined, stream_cmd, id, channel_id))
                            else:
                                # Channel doesn't exist yet - will be handled by full refresh
                                pass
                        
                        conn.commit()
                        conn.close()
                        logger.info(f"Updated {len(all_channels_map)} channels with new MAC data")
                else:
                    logger.info(f"No new MACs to fetch channels for")
                
                # Update channels.db — only if all_channels_map was populated
                if all_channels_map:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    for channel_id, channel in all_channels_map.items():
                        stream_cmd = str(channel.get("cmd", ""))
                        # Format available_macs with playback_limit: "MAC:limit,MAC:limit"
                        macs_with_limits = []
                        for mac in channel_macs_map.get(channel_id, []):
                            limit = mac_playback_limits.get(mac, 1)
                            macs_with_limits.append(f"{mac}|{limit}|0|0|0")  # Format: MAC|limit|success|fail|last_ts
                        available_macs = ",".join(macs_with_limits)
                        
                        cursor.execute('''
                            UPDATE channels 
                            SET stream_cmd = ?, available_macs = ?
                            WHERE portal = ? AND channel_id = ?
                        ''', (stream_cmd, available_macs, id, channel_id))
                    
                    conn.commit()
                    conn.close()
                    logger.info(f"Auto-refresh: Updated {len(all_channels_map)} channels in DB for portal {name}")
            except Exception as e:
                logger.error(f"Error auto-refreshing channels.db: {e}")

    else:
        logger.error(
            "None of the MACs tested OK for Portal({}). Adding not successfull".format(
                name
            )
        )

    return redirect("/portals", code=302)

@app.route("/portal/genre-selection", methods=["GET"])
@authorise
def portal_genre_selection():
    """Show genre selection page after adding a portal."""
    # Check for query parameters first (for direct links from portal page)
    portal_id = request.args.get('portal_id')
    portal_name = request.args.get('portal_name')
    
    # If not in query params, check session (for new portal flow)
    if not portal_id:
        portal_id = flask.session.get('new_portal_id')
        portal_name = flask.session.get('new_portal_name')
    else:
        # Store in session for subsequent API calls
        flask.session['new_portal_id'] = portal_id
        flask.session['new_portal_name'] = portal_name
    
    if not portal_id:
        return redirect("/portals", code=302)
    
    return render_template("genre_selection.html", portal_id=portal_id, portal_name=portal_name)


@app.route("/portal/load-genres", methods=["POST"])
@authorise
def portal_load_genres():
    """Load genres for a specific portal - uses database cache if available."""
    try:
        portal_id = request.json.get('portal_id')
        force_refresh = request.json.get('force_refresh', False)
        
        if not portal_id:
            return flask.jsonify({"error": "No portal ID provided"}), 400
        
        portals = getPortals()
        portal = portals.get(portal_id)
        if not portal:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        portal_name = portal["name"]
        
        # Check if we have cached data in database (unless force refresh)
        if not force_refresh:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Check if we have any channels for this portal in DB
                cursor.execute('SELECT COUNT(*) as count FROM channels WHERE portal = ?', (portal_id,))
                row = cursor.fetchone()
                channel_count = row['count'] if row else 0
                
                if channel_count > 0:
                    logger.info(f"Loading genres from database cache for portal {portal_id} ({channel_count} channels)")
                    
                    # Get genre counts from database
                    cursor.execute('''
                        SELECT genre, COUNT(*) as count
                        FROM channels
                        WHERE portal = ? AND genre IS NOT NULL AND genre != ''
                        GROUP BY genre
                        ORDER BY genre
                    ''', (portal_id,))
                    
                    genres = [{"name": row['genre'], "count": row['count']} for row in cursor.fetchall()]
                    
                    # Get previously selected genres from database
                    cursor.execute('SELECT genre FROM portal_genres WHERE portal = ?', (portal_id,))
                    enabled_genres = [row['genre'] for row in cursor.fetchall()]
                    
                    # Fallback to JSON config if database is empty
                    if not enabled_genres:
                        enabled_genres = portal.get("selected genres", [])
                    
                    conn.close()
                    
                    logger.info(f"Loaded {len(genres)} genres from database cache")
                    return flask.jsonify({
                        "genres": genres,
                        "total_channels": channel_count,
                        "enabled_genres": enabled_genres,
                        "from_cache": True
                    })
                
                conn.close()
            except Exception as e:
                logger.error(f"Error loading from database cache: {e}")
        
        # Fetch from portal (first time or force refresh)
        logger.info(f"Fetching genres from portal {portal_id} (force_refresh={force_refresh})")
        
        url = portal["url"]
        macs = list(portal["macs"].keys())
        proxy = portal["proxy"]
        
        all_channels_map = {}  # channel_id -> channel data
        all_genres_dict = {}  # genre_id -> genre_name
        
        logger.info(f"Loading channels from {len(macs)} MACs for portal {portal_id}")
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    mac_channels = stb.getAllChannels(url, mac, token, proxy)
                    mac_genres = stb.getGenreNames(url, mac, token, proxy)
                    
                    if mac_channels:
                        for channel in mac_channels:
                            channel_id = str(channel["id"])
                            if channel_id not in all_channels_map:
                                all_channels_map[channel_id] = channel
                        logger.info(f"MAC {mac}: Added {len(mac_channels)} channels (total now: {len(all_channels_map)})")
                    
                    if mac_genres:
                        all_genres_dict.update(mac_genres)
                        logger.info(f"MAC {mac}: Added genres (total now: {len(all_genres_dict)})")
                        
            except Exception as e:
                logger.error(f"Error fetching from MAC {mac}: {e}")
                continue
        
        if not all_channels_map or not all_genres_dict:
            return flask.jsonify({"error": "Failed to fetch channels from any MAC"}), 500
        
        logger.info(f"Total channels loaded from all MACs: {len(all_channels_map)}")
        
        # DON'T save to database yet - wait for genre selection
        # Channels will be inserted when user selects genres
        logger.info(f"Loaded {len(all_channels_map)} channels. Waiting for genre selection to save to DB...")
        
        # Count channels per genre
        genre_counts = {}
        for channel_id, channel in all_channels_map.items():
            genre_id = str(channel.get("tv_genre_id", ""))
            genre_name = all_genres_dict.get(genre_id, "Unknown")
            
            if genre_name not in genre_counts:
                genre_counts[genre_name] = 0
            genre_counts[genre_name] += 1
        
        # Get previously selected genres from database
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT genre FROM portal_genres WHERE portal = ?', (portal_id,))
            enabled_genres = [row['genre'] for row in cursor.fetchall()]
            conn.close()
            
            # Fallback to JSON config if database is empty
            if not enabled_genres:
                enabled_genres = portal.get("selected genres", [])
        except Exception as e:
            logger.error(f"Error loading selected genres from database: {e}")
            enabled_genres = portal.get("selected genres", [])
        
        logger.info(f"Portal {portal_id}: {len(all_channels_map)} total channels, {len(genre_counts)} genres, {len(enabled_genres)} selected")
        
        # Sort genres by name
        genres = sorted([{"name": name, "count": count} for name, count in genre_counts.items()], key=lambda x: x['name'])
        
        return flask.jsonify({
            "genres": genres, 
            "total_channels": len(all_channels_map),
            "enabled_genres": enabled_genres,
            "from_cache": False
        })
    except Exception as e:
        logger.error(f"Error loading genres: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/portal/mac-regions", methods=["POST"])
@authorise
def portal_mac_regions():
    """Get cached DE content detection for each MAC from portal config."""
    try:
        portal_id = request.json.get('portal_id')
        
        if not portal_id:
            return flask.jsonify({"error": "No portal ID provided"}), 400
        
        portals = getPortals()
        portal = portals.get(portal_id)
        if not portal:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        # Get cached DE detection results from portal config
        mac_has_de = portal.get("mac_has_de", {})
        
        # Convert to old format for compatibility (list with 'de' if True)
        mac_regions = {}
        for mac, has_de in mac_has_de.items():
            if has_de:
                mac_regions[mac] = ['de']
            else:
                mac_regions[mac] = []
        
        logger.info(f"Returning cached DE detection for {len(mac_regions)} MACs")
        return flask.jsonify({"mac_regions": mac_regions})
        
    except Exception as e:
        logger.error(f"Error getting MAC regions: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/portal/mac-scores", methods=["POST"])
@authorise
def portal_mac_scores():
    """Get average reliability scores for each MAC from channel data."""
    try:
        portal_id = request.json.get('portal_id')
        
        if not portal_id:
            return flask.jsonify({"error": "No portal ID provided"}), 400
        
        portals = getPortals()
        portal = portals.get(portal_id)
        if not portal:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        # Get all channels for this portal from DB
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT available_macs 
            FROM channels 
            WHERE portal = ? AND available_macs IS NOT NULL AND available_macs != ''
        ''', (portal_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Calculate average score per MAC
        mac_stats = {}  # {mac: {'total_score': float, 'count': int, 'success': int, 'fail': int}}
        
        # Use global calculate_mac_score function
        
        for row in rows:
            available_macs_raw = row['available_macs'].split(',')
            
            for mac_entry in available_macs_raw:
                parts = mac_entry.split('|')
                if len(parts) >= 5:  # MAC|limit|success|fail|last_ts
                    # Format: MAC|limit|success|fail|last_ts
                    mac = parts[0]
                    success_count = int(parts[2])
                    fail_count = int(parts[3])
                    last_ts = int(parts[4])
                    
                    score = calculate_mac_score(success_count, fail_count, last_ts)
                    
                    if mac not in mac_stats:
                        mac_stats[mac] = {'total_score': 0, 'count': 0, 'success': 0, 'fail': 0}
                    
                    mac_stats[mac]['total_score'] += score
                    mac_stats[mac]['count'] += 1
                    mac_stats[mac]['success'] += success_count
                    mac_stats[mac]['fail'] += fail_count
        
        # Calculate averages
        mac_scores = {}
        for mac, stats in mac_stats.items():
            if stats['count'] > 0:
                avg_score = stats['total_score'] / stats['count']
                mac_scores[mac] = {
                    'score': round(avg_score, 1),
                    'success': stats['success'],
                    'fail': stats['fail'],
                    'channels': stats['count']
                }
            else:
                mac_scores[mac] = {
                    'score': 25.0,  # Neutral
                    'success': 0,
                    'fail': 0,
                    'channels': 0
                }
        
        return flask.jsonify({"mac_scores": mac_scores})
        
    except Exception as e:
        logger.error(f"Error getting MAC scores: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/portal/save-genre-selection", methods=["POST"])
@authorise
def portal_save_genre_selection():
    """Save genre selection and enable channels - fetches from ALL MACs."""
    try:
        portal_id = request.json.get('portal_id')
        selected_genres = request.json.get('selected_genres', [])
        auto_sync = request.json.get('auto_sync', False)
        
        if not portal_id:
            return flask.jsonify({"error": "No portal ID provided"}), 400
        
        portals = getPortals()
        portal = portals.get(portal_id)
        if not portal:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        # Fetch channels from ALL MACs and merge
        url = portal["url"]
        macs = list(portal["macs"].keys())
        proxy = portal["proxy"]
        portal_name = portal["name"]
        
        all_channels_map = {}  # channel_id -> channel data
        all_genres_dict = {}  # genre_id -> genre_name
        channel_macs_map = {}  # channel_id -> [mac1, mac2, ...]
        mac_playback_limits = {}  # Store playback_limit per MAC
        
        logger.info(f"Saving genre selection: fetching from {len(macs)} MACs for portal {portal_name}")
        
        # Track channels per MAC for pre-caching
        mac_channels_dict = {}  # mac -> channels list
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    profile = stb.getProfile(url, mac, token, proxy)
                    # Get playback_limit from profile
                    if profile:
                        playback_limit = profile.get("playback_limit", 1)
                        mac_playback_limits[mac] = playback_limit
                        logger.info(f"[GENRE SELECTION] MAC {mac} has playback_limit: {playback_limit}")
                    
                    mac_channels = stb.getAllChannels(url, mac, token, proxy)
                    mac_genres = stb.getGenreNames(url, mac, token, proxy)
                    
                    if mac_channels:
                        # Store for pre-caching
                        mac_channels_dict[mac] = mac_channels
                        
                        # Merge channels and track which MACs have them
                        for channel in mac_channels:
                            channel_id = str(channel["id"])
                            if channel_id not in all_channels_map:
                                all_channels_map[channel_id] = channel
                                channel_macs_map[channel_id] = []
                            
                            # Track which MAC has this channel
                            if mac not in channel_macs_map[channel_id]:
                                channel_macs_map[channel_id].append(mac)
                                
                        logger.info(f"MAC {mac}: Added {len(mac_channels)} channels (total: {len(all_channels_map)})")
                    
                    if mac_genres:
                        all_genres_dict.update(mac_genres)
                        
            except Exception as e:
                logger.error(f"Error fetching from MAC {mac}: {e}")
                continue
        
        if not all_channels_map or not all_genres_dict:
            return flask.jsonify({"error": "Failed to fetch channels from any MAC"}), 500
        
        # Save enabled channels to portal configuration
        enabled_channels = []
        enabled_count = 0
        total_count = len(all_channels_map)
        
        logger.info(f"Selected genres: {selected_genres}")
        logger.info(f"Processing {total_count} total channels from all MACs")
        
        for channel_id, channel in all_channels_map.items():
            genre_id = str(channel.get("tv_genre_id", ""))
            genre = all_genres_dict.get(genre_id, "")
            
            # Enable channel if its genre is selected
            if genre in selected_genres:
                enabled_channels.append(channel_id)
                enabled_count += 1
        
        logger.info(f"Enabled {enabled_count} channels out of {total_count}")
        logger.info(f"First 10 enabled channel IDs: {enabled_channels[:10]}")
        
        # Update portal configuration
        portals = getPortals()
        if portal_id in portals:
            portals[portal_id]["enabled channels"] = enabled_channels
            portals[portal_id]["selected genres"] = selected_genres  # Save selected genres
            savePortals(portals)
            logger.info(f"Saved to portal config. Verifying...")
            
            # Verify it was saved
            portals_verify = getPortals()
            saved_count = len(portals_verify[portal_id].get("enabled channels", []))
            saved_genres = portals_verify[portal_id].get("selected genres", [])
            logger.info(f"Verification: {saved_count} channels in 'enabled channels' list")
            logger.info(f"Verification: {len(saved_genres)} genres in 'selected genres' list")
            
            # Insert/Update channels in database
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # First, delete all existing channels for this portal
                cursor.execute('DELETE FROM channels WHERE portal = ?', (portal_id,))
                logger.info(f"Deleted existing channels for portal {portal_id}")
                
                # Insert ONLY channels with selected genres into database
                inserted_count = 0
                skipped_count = 0
                for channel_id, channel in all_channels_map.items():
                    channel_name = str(channel.get("name", ""))
                    channel_number = str(channel.get("number", ""))
                    genre_id = str(channel.get("tv_genre_id", ""))
                    genre = all_genres_dict.get(genre_id, "")
                    logo = str(channel.get("logo", ""))
                    
                    # ONLY cache channels with selected genres
                    if genre not in selected_genres:
                        skipped_count += 1
                        continue  # Skip this channel
                    
                    # This channel has a selected genre - cache it
                    is_enabled = 1 if channel_id in enabled_channels else 0
                    
                    # Get stream_cmd and available_macs with playback_limit
                    stream_cmd = str(channel.get("cmd", ""))
                    # Format available_macs with playback_limit: "MAC:limit,MAC:limit"
                    macs_with_limits = []
                    for mac in channel_macs_map.get(channel_id, []):
                        limit = mac_playback_limits.get(mac, 1)
                        macs_with_limits.append(f"{mac}|{limit}|0|0|0")  # Format: MAC|limit|success|fail|last_ts
                    available_macs = ",".join(macs_with_limits)
                    
                    cursor.execute('''
                        INSERT INTO channels (
                            portal, channel_id, portal_name, name, number, genre, logo,
                            enabled, custom_name, custom_number, custom_genre, 
                            custom_epg_id, fallback_channel, has_portal_epg,
                            stream_cmd, available_macs
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', '', '', '', '', 0, ?, ?)
                    ''', (
                        portal_id, channel_id, portal_name, channel_name, channel_number,
                        genre, logo, is_enabled, stream_cmd, available_macs
                    ))
                    inserted_count += 1
                
                # Save selected genres to database
                cursor.execute('DELETE FROM portal_genres WHERE portal = ?', (portal_id,))
                for genre in selected_genres:
                    cursor.execute('INSERT INTO portal_genres (portal, genre) VALUES (?, ?)', (portal_id, genre))
                
                conn.commit()
                
                # Run VACUUM to reclaim disk space after deleting old channels
                logger.info("Running VACUUM to reclaim disk space...")
                cursor.execute("VACUUM")
                conn.commit()
                logger.info("VACUUM completed")
                
                conn.close()
                logger.info(f"Inserted {inserted_count} channels into database (only selected genres)")
                logger.info(f"Skipped {skipped_count} channels (genres not selected)")
                logger.info(f"Saved {len(selected_genres)} selected genres to database")
            except Exception as e:
                logger.error(f"Error inserting channels into database: {e}")
        else:
            logger.error(f"Portal {portal_id} not found in portals!")
        
        # Clear session
        flask.session.pop('new_portal_id', None)
        flask.session.pop('new_portal_name', None)
        
        # Auto-regenerate playlist after genre selection
        logger.info("Auto-regenerating playlist after genre selection...")
        generate_playlist()
        
        logger.info(f"Saved {enabled_count}/{total_count} channels for portal {portal_name}")
        return flask.jsonify({
            "success": True, 
            "enabled_count": enabled_count, 
            "total_count": total_count
        })
    except Exception as e:
        logger.error(f"Error saving genre selection: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/portal/remove", methods=["POST"])
@authorise
def portalRemove():
    id = request.form["deleteId"]
    portals = getPortals()
    name = portals[id]["name"]
    
    # Delete all channels for this portal from the database
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM channels WHERE portal = ?', (id,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        logger.info("Deleted {} channels for portal ({}) from database".format(deleted_count, name))
    except Exception as e:
        logger.error("Error deleting channels from database: {}".format(e))
    
    # Delete portal from config
    del portals[id]
    savePortals(portals)
    
    # Regenerate playlist after portal removal
    generate_playlist()
    
    logger.info("Portal ({}) removed!".format(name))
    flash("Portal ({}) removed!".format(name), "success")
    return redirect("/portals", code=302)


def apply_portal_prefix(channel_name, genre, portal_prefix):
    """Apply portal prefix to genre only (for group-title organization)."""
    if portal_prefix and genre:
        genre = f"[{portal_prefix}] {genre}"
    return channel_name, genre


def generate_portal_m3u(portal_id):
    """Generate M3U playlist content for a specific portal."""
    logger.info(f"Generating M3U for portal: {portal_id}")
    
    # Use external host configuration
    external_host, external_scheme = get_external_host_config()
    # Use request.host only if we're in a request context
    try:
        playlist_host = external_host or request.host or "0.0.0.0:8001"
    except RuntimeError:
        # Not in request context
        playlist_host = external_host or "0.0.0.0:8001"
    
    channels = []
    
    # Get enabled channels from database for specific portal
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
                   number, custom_number, custom_epg_id
            FROM channels 
            WHERE enabled = 1 AND portal = ?
            ORDER BY channel_id
        ''', (portal_id,))
        db_channels = cursor.fetchall()
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
    
    # Get portal info
    portals = getPortals()
    
    # Check if portal exists and is enabled
    if portal_id not in portals:
        logger.warning(f"Portal {portal_id} not found")
        return None
        
    if portals[portal_id].get("enabled") != "true":
        logger.warning(f"Portal {portal_id} is disabled")
        return "#EXTM3U \n"  # Return empty playlist for disabled portals
    
    # Get portal prefix
    portal_prefix = portals[portal_id].get("portal prefix", "").strip()
    
    for channel in db_channels:
        channel_id = str(channel['channel_id'])
        
        # Use custom values if available, otherwise use original values
        channel_name = channel['custom_name'] if channel['custom_name'] else (channel['name'] or "Unknown Channel")
        genre = channel['custom_genre'] if channel['custom_genre'] else (channel['genre'] or "")
        channel_number = channel['custom_number'] if channel['custom_number'] else (channel['number'] or "")
        epg_id = channel['custom_epg_id'] if channel['custom_epg_id'] else channel_name
        
        # Determine group-title based on settings
        if getSettings().get("use portal names as groups", "false") == "true":
            # Use portal name as group
            group_title = portals[portal_id].get("name", portal_id)
        else:
            # Use genre with optional portal prefix
            if portal_prefix and genre:
                group_title = f"[{portal_prefix}] {genre}"
            else:
                group_title = genre
        
        # Build M3U entry - escape quotes in attributes
        def escape_quotes(text):
            return str(text).replace('"', '&quot;') if text else ""
        
        m3u_entry = "#EXTINF:-1"
        m3u_entry += ' tvg-id="' + escape_quotes(epg_id) + '"'
        
        if getSettings().get("use channel numbers", "true") == "true" and channel_number:
            m3u_entry += ' tvg-chno="' + escape_quotes(channel_number) + '"'
        
        if getSettings().get("use channel genres", "true") == "true" and group_title:
            m3u_entry += ' group-title="' + escape_quotes(group_title) + '"'
        
        m3u_entry += ',' + str(channel_name) + "\n"
        m3u_entry += "http://" + playlist_host + "/play/" + portal_id + "/" + channel_id
        
        channels.append(m3u_entry)

    # Sort channels based on settings (same logic as main playlist)
    if getSettings().get("sort playlist by channel name", "true") == "true":
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0] if "," in k else "")
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            def get_channel_number(k):
                try:
                    if 'tvg-chno="' in k:
                        return int(k.split('tvg-chno="')[1].split('"')[0])
                    return 999999  # Put channels without numbers at the end
                except (ValueError, IndexError):
                    return 999999
            channels.sort(key=get_channel_number)
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            def get_genre(k):
                try:
                    if 'group-title="' in k:
                        return k.split('group-title="')[1].split('"')[0]
                    return "zzz"  # Put channels without genre at the end
                except IndexError:
                    return "zzz"
            channels.sort(key=get_genre)

    playlist = "#EXTM3U \n"
    if channels:
        playlist = playlist + "\n".join(channels)

    logger.info(f"Generated M3U for portal {portal_id} with {len(channels)} channels")
    return playlist


def generate_portal_m3u_with_auth(portal_id, username=None, password=None):
    """
    Generate M3U playlist content for a specific portal with authentication-aware stream URLs.
    
    Args:
        portal_id (str): Portal ID
        username (str): Username for embedding in stream URLs (if security enabled)
        password (str): Password for embedding in stream URLs (if security enabled)
        
    Returns:
        str: M3U playlist content with authentication-aware stream URLs
    """
    logger.info(f"Generating M3U with auth for portal: {portal_id}")
    
    # Use external host configuration
    external_host, external_scheme = get_external_host_config()
    # Use request.host only if we're in a request context
    try:
        playlist_host = external_host or request.host or "0.0.0.0:8001"
    except RuntimeError:
        # Not in request context
        playlist_host = external_host or "0.0.0.0:8001"
    
    channels = []
    
    # Get enabled channels from database for specific portal
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
                   number, custom_number, custom_epg_id
            FROM channels 
            WHERE enabled = 1 AND portal = ?
            ORDER BY channel_id
        ''', (portal_id,))
        db_channels = cursor.fetchall()
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
    
    # Get portal info
    portals = getPortals()
    
    # Check if portal exists and is enabled
    if portal_id not in portals:
        logger.warning(f"Portal {portal_id} not found")
        return None
        
    if portals[portal_id].get("enabled") != "true":
        logger.warning(f"Portal {portal_id} is disabled")
        return "#EXTM3U \n"  # Return empty playlist for disabled portals
    
    # Get settings to determine if we should embed auth in stream URLs
    settings = getSettings()
    security_enabled = settings.get("enable security", "false") == "true"
    
    # Get portal prefix
    portal_prefix = portals[portal_id].get("portal prefix", "").strip()
    
    for channel in db_channels:
        channel_id = str(channel['channel_id'])
        
        # Use custom values if available, otherwise use original values
        channel_name = channel['custom_name'] if channel['custom_name'] else (channel['name'] or "Unknown Channel")
        genre = channel['custom_genre'] if channel['custom_genre'] else (channel['genre'] or "")
        channel_number = channel['custom_number'] if channel['custom_number'] else (channel['number'] or "")
        epg_id = channel['custom_epg_id'] if channel['custom_epg_id'] else channel_name
        
        # Determine group-title based on settings
        if getSettings().get("use portal names as groups", "false") == "true":
            # Use portal name as group
            group_title = portals[portal_id].get("name", portal_id)
        else:
            # Use genre with optional portal prefix
            if portal_prefix and genre:
                group_title = f"[{portal_prefix}] {genre}"
            else:
                group_title = genre
        
        # Build M3U entry - escape quotes in attributes
        def escape_quotes(text):
            return str(text).replace('"', '&quot;') if text else ""
        
        m3u_entry = "#EXTINF:-1"
        m3u_entry += ' tvg-id="' + escape_quotes(epg_id) + '"'
        
        if getSettings().get("use channel numbers", "true") == "true" and channel_number:
            m3u_entry += ' tvg-chno="' + escape_quotes(channel_number) + '"'
        
        if getSettings().get("use channel genres", "true") == "true" and group_title:
            m3u_entry += ' group-title="' + escape_quotes(group_title) + '"'
        
        m3u_entry += ',' + str(channel_name) + "\n"
        
        # Generate stream URL with embedded auth if security is enabled and credentials provided
        if security_enabled and username and password:
            # Embed Basic Auth in stream URL for maximum player compatibility
            stream_url = f"http://{username}:{password}@{playlist_host}/play/{portal_id}/{channel_id}"
        else:
            # Standard stream URL without embedded auth
            stream_url = f"http://{playlist_host}/play/{portal_id}/{channel_id}"
        
        m3u_entry += stream_url
        
        channels.append(m3u_entry)

    # Sort channels based on settings (same logic as main playlist)
    if getSettings().get("sort playlist by channel name", "true") == "true":
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0] if "," in k else "")
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            def get_channel_number(k):
                try:
                    if 'tvg-chno="' in k:
                        return int(k.split('tvg-chno="')[1].split('"')[0])
                    return 999999  # Put channels without numbers at the end
                except (ValueError, IndexError):
                    return 999999
            channels.sort(key=get_channel_number)
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            def get_genre(k):
                try:
                    if 'group-title="' in k:
                        return k.split('group-title="')[1].split('"')[0]
                    return "zzz"  # Put channels without genre at the end
                except IndexError:
                    return "zzz"
            channels.sort(key=get_genre)

    playlist = "#EXTM3U \n"
    if channels:
        playlist = playlist + "\n".join(channels)

    logger.info(f"Generated M3U with auth for portal {portal_id} with {len(channels)} channels")
    return playlist


def generate_portal_filename(portal_name):
    """Generate a safe filename for portal M3U download."""
    import re
    # Remove or replace unsafe characters
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', portal_name)
    # Remove extra spaces and trim
    safe_name = re.sub(r'\s+', '_', safe_name.strip())
    # Ensure it's not empty
    if not safe_name:
        safe_name = "portal"
    return f"{safe_name}.m3u"


@app.route("/api/portal/<portal_id>/mac-status", methods=["GET"])
@authorise
def portal_mac_status(portal_id):
    """Check MAC address status for a portal."""
    try:
        portals = getPortals()
        
        if portal_id not in portals:
            return flask.jsonify({"success": False, "error": "Portal not found"}), 404
        
        portal = portals[portal_id]
        portal_url = portal["url"]
        macs = portal.get("macs", [])
        
        if not macs:
            return flask.jsonify({"success": False, "error": "No MAC addresses configured"}), 400
        
        # Import MAC status checker
        import requests
        import json
        from datetime import datetime
        
        def check_single_mac_status(portal_url, mac_address):
            """Check status of a single MAC address"""
            try:
                # Ensure portal URL ends with portal.php
                if not portal_url.endswith('/portal.php'):
                    if portal_url.endswith('/'):
                        portal_url_clean = portal_url + 'portal.php'
                    else:
                        portal_url_clean = portal_url + '/portal.php'
                else:
                    portal_url_clean = portal_url
                
                session = requests.Session()
                headers = {
                    'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3',
                    'X-User-Agent': f'Model: MAG250; Link: WiFi; MAC: {mac_address}',
                    'Cookie': f'mac={mac_address}; stb_lang=en'
                }
                
                # Get authentication token
                token_response = session.get(
                    f'{portal_url_clean}?type=stb&action=handshake&JsHttpRequest=1-xml',
                    headers=headers,
                    timeout=10
                )
                
                if token_response.status_code != 200:
                    return {
                        'success': False,
                        'mac': mac_address,
                        'error': f'Token request failed: HTTP {token_response.status_code}'
                    }
                
                try:
                    token_data = token_response.json()
                    token = token_data.get('js', {}).get('token')
                    if not token:
                        return {
                            'success': False,
                            'mac': mac_address,
                            'error': 'No token received from portal'
                        }
                except json.JSONDecodeError:
                    return {
                        'success': False,
                        'mac': mac_address,
                        'error': 'Invalid JSON response for token'
                    }
                
                # Get profile information
                profile_response = session.get(
                    f'{portal_url_clean}?type=stb&action=get_profile&JsHttpRequest=1-xml',
                    headers=headers,
                    timeout=10
                )
                
                if profile_response.status_code != 200:
                    return {
                        'success': False,
                        'mac': mac_address,
                        'error': f'Profile request failed: HTTP {profile_response.status_code}'
                    }
                
                try:
                    profile_data = profile_response.json()
                    profile = profile_data.get('js', {})
                except json.JSONDecodeError:
                    return {
                        'success': False,
                        'mac': mac_address,
                        'error': 'Invalid JSON response for profile'
                    }
                
                # Get account information
                account_response = session.get(
                    f'{portal_url_clean}?type=account_info&action=get_main_info&JsHttpRequest=1-xml',
                    headers=headers,
                    timeout=10
                )
                
                account_info = {}
                if account_response.status_code == 200:
                    try:
                        account_data = account_response.json()
                        account_info = account_data.get('js', {})
                    except json.JSONDecodeError:
                        pass
                
                # Extract key information
                watchdog_timeout = profile.get('watchdog_timeout')
                playback_limit = profile.get('playback_limit', 1)
                account_status = profile.get('status', 0)
                is_blocked = profile.get('blocked', '0') != '0'
                expires = account_info.get('phone', '')  # This seems to contain expiry date
                
                return {
                    'success': True,
                    'mac': mac_address,
                    'watchdog_timeout': watchdog_timeout,
                    'playback_limit': playback_limit,
                    'account_active': account_status == 1,
                    'is_blocked': is_blocked,
                    'expires': expires,
                    'token': token
                }
                
            except requests.exceptions.Timeout:
                return {
                    'success': False,
                    'mac': mac_address,
                    'error': 'Request timeout'
                }
            except requests.exceptions.ConnectionError as e:
                return {
                    'success': False,
                    'mac': mac_address,
                    'error': f'Connection error: {str(e)}'
                }
            except Exception as e:
                return {
                    'success': False,
                    'mac': mac_address,
                    'error': f'Unexpected error: {str(e)}'
                }
        
        # Use the enhanced stb.py functions for better MAC status checking
        import stb
        
        # Get MAC status summary using the smart system
        mac_list = list(macs.keys()) if isinstance(macs, dict) else macs
        mac_summary = stb.getMacStatusSummary(portal_url, mac_list, portal.get('proxy'))
        
        # Convert to the expected format
        mac_statuses = []
        portal_info = {}
        
        for mac_info in mac_summary:
            status = mac_info['status']
            if status['success']:
                # Add the enhanced information
                enhanced_status = {
                    'success': True,
                    'mac': status['mac'],
                    'watchdog_timeout': status.get('watchdog_timeout'),
                    'playback_limit': status.get('playback_limit', 1),
                    'account_active': status.get('account_active', False),
                    'is_blocked': status.get('is_blocked', False),
                    'expires': status.get('expires', ''),
                    'token': status.get('token', ''),
                    # New enhanced fields
                    'is_internally_used': status.get('is_internally_used', False),
                    'streams_used': status.get('streams_used', 0),
                    'max_streams': status.get('max_streams', 1),
                    'usage_ratio': status.get('usage_ratio', 0.0),
                    'internal_usage': status.get('internal_usage')
                }
                mac_statuses.append(enhanced_status)
                
                # Extract portal info from first successful response
                if not portal_info:
                    portal_info = {
                        'playback_limit': status.get('playback_limit', 1)
                    }
            else:
                # Keep failed status as is
                mac_statuses.append(status)
        
        return flask.jsonify({
            "success": True,
            "portal_id": portal_id,
            "portal_name": portal["name"],
            "portal_info": portal_info,
            "mac_statuses": mac_statuses,
            "checked_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error checking MAC status for portal {portal_id}: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500


@app.route("/portal/download-m3u/<portal_id>", methods=["GET"])
def portal_download_m3u(portal_id):
    """Legacy portal M3U download with configurable access control."""
    settings = getSettings()
    public_access = settings.get("public playlist access", "true") == "true"
    
    if public_access:
        # Public access enabled - no authentication required
        return _portal_download_m3u(portal_id)
    else:
        # Public access disabled - require Basic Auth
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            # No Basic Auth provided - return 401 with WWW-Authenticate header
            response = Response(
                'Authentication required\n'
                'Please provide Basic Auth credentials in the URL:\n'
                'http://username:password@host/portal/download-m3u/portal_id',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Legacy M3U"'}
            )
            return response
        
        # Validate Basic Auth credentials
        system_username = settings.get("username", "admin")
        system_password = settings.get("password", "12345")
        
        if auth.username != system_username or auth.password != system_password:
            logger.warning(f"Invalid Basic Auth credentials for legacy M3U: {auth.username}")
            response = Response(
                'Invalid credentials\n'
                'Please check your username and password.',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Legacy M3U"'}
            )
            return response
        
        # Authentication successful
        logger.info(f"Basic Auth successful for legacy M3U: {auth.username}")
        return _portal_download_m3u(portal_id)

def _portal_download_m3u(portal_id):
    """Download M3U playlist for a specific portal."""
    try:
        # Get portal info
        portals = getPortals()
        
        if portal_id not in portals:
            logger.warning(f"Portal download requested for non-existent portal: {portal_id}")
            return Response("Portal not found", status=404)
        
        portal = portals[portal_id]
        portal_name = portal.get("name", "Unknown Portal")
        
        # Generate M3U content
        m3u_content = generate_portal_m3u(portal_id)
        
        if m3u_content is None:
            logger.error(f"Failed to generate M3U for portal: {portal_id}")
            return Response("Error generating M3U", status=500)
        
        # Generate filename
        filename = generate_portal_filename(portal_name)
        
        # Create response with proper headers
        response = Response(m3u_content, mimetype="text/plain")
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        
        logger.info(f"M3U download served for portal: {portal_name} ({portal_id})")
        return response
        
    except Exception as e:
        logger.error(f"Error in portal M3U download for {portal_id}: {e}")
        return Response("Internal server error", status=500)


@app.route("/portal/<portal_id>/playlist.m3u", methods=["GET"])
def portal_specific_m3u(portal_id):
    """Portal-specific M3U with configurable access control."""
    settings = getSettings()
    public_access = settings.get("public playlist access", "true") == "true"
    
    if public_access:
        # Public access enabled - no authentication required
        return _portal_specific_m3u(portal_id)
    else:
        # Public access disabled - require Basic Auth
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            # No Basic Auth provided - return 401 with WWW-Authenticate header
            response = Response(
                'Authentication required\n'
                'Please provide Basic Auth credentials in the URL:\n'
                'http://username:password@host/portal/portal_id/playlist.m3u',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Portal M3U"'}
            )
            return response
        
        # Validate Basic Auth credentials
        system_username = settings.get("username", "admin")
        system_password = settings.get("password", "12345")
        
        if auth.username != system_username or auth.password != system_password:
            logger.warning(f"Invalid Basic Auth credentials for portal M3U: {auth.username}")
            response = Response(
                'Invalid credentials\n'
                'Please check your username and password.',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Portal M3U"'}
            )
            return response
        
        # Authentication successful
        logger.info(f"Basic Auth successful for portal M3U: {auth.username}")
        return _portal_specific_m3u(portal_id)

def _portal_specific_m3u(portal_id):
    """
    Portal-specific M3U route handler with Basic Auth and Query Parameter support.
    
    Supports authentication via:
    1. HTTP Basic Auth: http://user:pass@host/portal/portal_id/playlist.m3u
    2. Query Parameters: http://host/portal/portal_id/playlist.m3u?username=user&password=pass
    
    Basic Auth takes precedence over Query Parameters.
    """
    try:
        # Extract authentication credentials
        username, password = extract_auth_credentials(request)
        
        # Get system settings
        settings = getSettings()
        security_enabled = settings.get("enable security", "false") == "true"
        public_access_enabled = settings.get("public playlist access", "true") == "true"
        
        # Validate portal exists and is enabled
        portals = getPortals()
        
        if portal_id not in portals:
            logger.warning(f"Portal-specific M3U requested for non-existent portal: {portal_id}")
            return Response("Portal not found", status=404)
        
        portal = portals[portal_id]
        
        if portal.get("enabled") != "true":
            logger.warning(f"Portal-specific M3U requested for disabled portal: {portal_id}")
            return Response("Portal not found", status=404)
        
        # Validate authentication only if public access is disabled
        if not public_access_enabled:
            is_valid, error_message = validate_authentication(username, password, settings)
            if not is_valid:
                logger.warning(f"Portal-specific M3U requested with invalid credentials for portal: {portal_id}")
                return Response(error_message, status=401)
        else:
            logger.debug(f"Portal-specific M3U access granted (public access enabled) for portal: {portal_id}")
        
        # Generate M3U content with authentication-aware stream URLs
        m3u_content = generate_portal_m3u_with_auth(portal_id, username, password)
        
        if m3u_content is None:
            logger.error(f"Failed to generate M3U for portal: {portal_id}")
            return Response("Error generating M3U", status=500)
        
        # Create response with proper headers for M3U file download
        response = Response(m3u_content, mimetype="application/x-mpegURL")
        response.headers["Content-Disposition"] = f"attachment; filename=portal_{portal_id}_playlist.m3u"
        response.headers["Content-Type"] = "application/x-mpegURL; charset=utf-8"
        
        portal_name = portal.get("name", "Unknown Portal")
        logger.info(f"Portal-specific M3U served for portal: {portal_name} ({portal_id})")
        return response
        
    except Exception as e:
        logger.error(f"Error in portal-specific M3U for {portal_id}: {e}")
        return Response("Internal server error", status=500)


@app.route("/editor", methods=["GET"])
@authorise
def editor():
    return render_template("editor.html")
    
@app.route("/editor_data", methods=["GET"])
@authorise
def editor_data():
    """Get channel data from database cache."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get only enabled channels from database
        cursor.execute('''
            SELECT 
                portal, channel_id, portal_name, name, number, genre,
                custom_name, custom_number, custom_genre, custom_epg_id, fallback_channel
            FROM channels
            WHERE enabled = 1
            ORDER BY portal_name, CAST(COALESCE(NULLIF(custom_number, ''), number) AS INTEGER)
        ''')
        
        channels = []
        # Use external host configuration
        external_host, external_scheme = get_external_host_config()
        request_host = external_host or request.host
        request_scheme = external_scheme if external_host else request.scheme
        
        for row in cursor.fetchall():
            channels.append({
                "portal": row['portal'],
                "portalName": row['portal_name'] or '',
                "enabled": True,  # All returned channels are enabled
                "channelNumber": row['number'] or '',
                "customChannelNumber": row['custom_number'] or '',
                "channelName": row['name'] or '',
                "customChannelName": row['custom_name'] or '',
                "genre": row['genre'] or '',
                "customGenre": row['custom_genre'] or '',
                "channelId": row['channel_id'],
                "customEpgId": row['custom_epg_id'] or '',
                "fallbackChannel": row['fallback_channel'] or '',
                "link": f"{request_scheme}://{request_host}/play/{row['portal']}/{row['channel_id']}?web=true",
            })
        
        logger.info(f"Returned {len(channels)} enabled channels from database cache")
        return flask.jsonify({"data": channels})
        
    except Exception as e:
        logger.error(f"Error in editor_data: {e}")
        return flask.jsonify({"data": [], "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.route("/editor/portals", methods=["GET"])
@authorise
def editor_portals():
    """Get list of unique portals for filter dropdown."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT portal_name
            FROM channels
            WHERE portal_name IS NOT NULL AND portal_name != ''
            ORDER BY portal_name
        """)
        
        portals = [row['portal_name'] for row in cursor.fetchall()]
        
        logger.info(f"Returning {len(portals)} portals from database")
        return flask.jsonify({"portals": portals})
    except Exception as e:
        logger.error(f"Error in editor_portals: {e}")
        return flask.jsonify({"portals": [], "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/genres", methods=["GET"])
@authorise
def editor_genres():
    """Get list of unique genres for filter dropdown."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT COALESCE(NULLIF(custom_genre, ''), genre) as genre
            FROM channels
            WHERE COALESCE(NULLIF(custom_genre, ''), genre) IS NOT NULL 
                AND COALESCE(NULLIF(custom_genre, ''), genre) != ''
                AND COALESCE(NULLIF(custom_genre, ''), genre) != 'None'
            ORDER BY genre
        """)
        
        genres = [row['genre'] for row in cursor.fetchall()]
        
        logger.info(f"Returning {len(genres)} genres from database")
        return flask.jsonify({"genres": genres})
    except Exception as e:
        logger.error(f"Error in editor_genres: {e}")
        return flask.jsonify({"genres": [], "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/portal-stats", methods=["GET"])
@authorise
def editor_portal_stats():
    """Get portal statistics with all channels (enabled and disabled)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all portals with their stats
        cursor.execute("""
            SELECT 
                portal,
                portal_name,
                COUNT(*) as total_channels,
                SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) as enabled_channels,
                COUNT(DISTINCT COALESCE(NULLIF(custom_genre, ''), genre)) as total_genres
            FROM channels
            GROUP BY portal, portal_name
            ORDER BY portal_name
        """)
        
        portals = []
        for row in cursor.fetchall():
            # Get genre stats for this portal
            cursor.execute("""
                SELECT 
                    COALESCE(NULLIF(custom_genre, ''), genre) as genre,
                    COUNT(*) as total,
                    SUM(CASE WHEN enabled = 1 THEN 1 ELSE 0 END) as enabled
                FROM channels
                WHERE portal = ?
                GROUP BY COALESCE(NULLIF(custom_genre, ''), genre)
            """, (row['portal'],))
            
            genres_with_enabled = sum(1 for g in cursor.fetchall() if g['enabled'] > 0)
            
            portals.append({
                "id": row['portal'],
                "name": row['portal_name'] or row['portal'],
                "total_channels": row['total_channels'],
                "enabled_channels": row['enabled_channels'],
                "total_genres": row['total_genres'],
                "enabled_genres": genres_with_enabled
            })
        
        logger.info(f"Returning {len(portals)} portal stats")
        return flask.jsonify({"portals": portals})
    except Exception as e:
        logger.error(f"Error in editor_portal_stats: {e}")
        return flask.jsonify({"portals": [], "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/portal-channels/<portal_id>", methods=["GET"])
@authorise
def editor_portal_channels(portal_id):
    """Get all channels for a specific portal (enabled and disabled)."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Use external host configuration
        external_host, external_scheme = get_external_host_config()
        request_host = external_host or request.host
        request_scheme = external_scheme if external_host else request.scheme
        
        cursor.execute("""
            SELECT 
                portal, channel_id, portal_name, name, number, genre, logo,
                custom_name, custom_number, custom_genre, custom_epg_id, 
                fallback_channel, enabled
            FROM channels
            WHERE portal = ? OR portal_name = ?
            ORDER BY COALESCE(NULLIF(custom_genre, ''), genre), 
                     CAST(COALESCE(NULLIF(custom_number, ''), number) AS INTEGER)
        """, (portal_id, portal_id))
        
        channels = []
        for row in cursor.fetchall():
            channels.append({
                "portal": row['portal'],
                "portalName": row['portal_name'] or '',
                "channelId": row['channel_id'],
                "channelName": row['name'] or '',
                "customChannelName": row['custom_name'] or '',
                "channelNumber": row['number'] or '',
                "customChannelNumber": row['custom_number'] or '',
                "genre": row['genre'] or '',
                "customGenre": row['custom_genre'] or '',
                "customEpgId": row['custom_epg_id'] or '',
                "fallbackChannel": row['fallback_channel'] or '',
                "enabled": bool(row['enabled']),
                "logo": row['logo'] or '',
                "link": f"{request_scheme}://{request_host}/play/{row['portal']}/{row['channel_id']}?web=true",
            })
        
        # Info message about genre filtering
        if len(channels) == 0:
            logger.warning(f"No channels found for portal {portal_id} - may need to select more genres")
        else:
            logger.info(f"Returning {len(channels)} channels for portal {portal_id} (only selected genres)")
        
        return flask.jsonify({"channels": channels})
    except Exception as e:
        logger.error(f"Error in editor_portal_channels: {e}")
        return flask.jsonify({"channels": [], "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/save", methods=["POST"])
@authorise
def editorSave():
    global last_playlist_host
    # Force M3U playlist regeneration
    last_playlist_host = None
    # Lineup is lazy-loaded on /lineup.json request (no need to refresh here)
    
    enabledEdits = json.loads(request.form["enabledEdits"])
    numberEdits = json.loads(request.form["numberEdits"])
    nameEdits = json.loads(request.form["nameEdits"])
    genreEdits = json.loads(request.form["genreEdits"])
    epgEdits = json.loads(request.form["epgEdits"])
    fallbackEdits = json.loads(request.form["fallbackEdits"])
    
    # Update SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Process enabled/disabled edits
        for edit in enabledEdits:
            portal = edit["portal"]
            channel_id = edit["channel id"]
            enabled = 1 if edit["enabled"] else 0
            
            cursor.execute('''
                UPDATE channels 
                SET enabled = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (enabled, portal, channel_id))
        
        # Process custom number edits
        for edit in numberEdits:
            portal = edit["portal"]
            channel_id = edit["channel id"]
            custom_number = edit["custom number"]
            
            cursor.execute('''
                UPDATE channels 
                SET custom_number = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (custom_number, portal, channel_id))
        
        # Process custom name edits
        for edit in nameEdits:
            portal = edit["portal"]
            channel_id = edit["channel id"]
            custom_name = edit["custom name"]
            
            cursor.execute('''
                UPDATE channels 
                SET custom_name = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (custom_name, portal, channel_id))
        
        # Process custom genre edits
        for edit in genreEdits:
            portal = edit["portal"]
            channel_id = edit["channel id"]
            custom_genre = edit["custom genre"]
            
            cursor.execute('''
                UPDATE channels 
                SET custom_genre = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (custom_genre, portal, channel_id))
        
        # Process custom EPG ID edits
        for edit in epgEdits:
            portal = edit["portal"]
            channel_id = edit["channel id"]
            custom_epg_id = edit["custom epg id"]
            
            cursor.execute('''
                UPDATE channels 
                SET custom_epg_id = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (custom_epg_id, portal, channel_id))
        
        # Process fallback channel edits
        for edit in fallbackEdits:
            portal = edit["portal"]
            channel_id = edit["channel id"]
            fallback_channel = edit["channel name"]
            
            cursor.execute('''
                UPDATE channels 
                SET fallback_channel = ? 
                WHERE portal = ? AND channel_id = ?
            ''', (fallback_channel, portal, channel_id))
        
        conn.commit()
        logger.info("Channel edits saved to database!")
        
        # Auto-regenerate playlist after editor changes
        logger.info("Auto-regenerating playlist after editor changes...")
        generate_playlist()
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error saving channel edits: {e}")
        flash(f"Error saving changes: {e}", "danger")
        return redirect("/editor", code=302)
    finally:
        conn.close()
    
    flash("Playlist config saved!", "success")
    return redirect("/editor", code=302)


@app.route("/editor/bulk-edit", methods=["POST"])
@authorise
def editor_bulk_edit():
    """Apply bulk search & replace to channel names and genres."""
    try:
        data = request.get_json()
        rules = data.get('rules', [])
        apply_to_names = data.get('apply_to_names', True)
        apply_to_genres = data.get('apply_to_genres', False)
        case_sensitive = data.get('case_sensitive', False)
        use_regex = data.get('use_regex', False)
        
        if not rules:
            return flask.jsonify({"success": False, "error": "No rules provided"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create tables for history and saved rules
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bulk_edit_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                rules TEXT NOT NULL,
                apply_to_names INTEGER NOT NULL,
                apply_to_genres INTEGER NOT NULL,
                channels_backup TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bulk_edit_saved_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_text TEXT NOT NULL,
                replace_text TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_used TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Get all channels and save as backup
        cursor.execute('SELECT portal, channel_id, name, custom_name, genre, custom_genre FROM channels')
        channels = cursor.fetchall()
        
        import json
        channels_backup = json.dumps([dict(ch) for ch in channels])
        
        # Save to history
        cursor.execute('''
            INSERT INTO bulk_edit_history (timestamp, rules, apply_to_names, apply_to_genres, channels_backup)
            VALUES (datetime('now'), ?, ?, ?, ?)
        ''', (json.dumps(rules), 1 if apply_to_names else 0, 1 if apply_to_genres else 0, channels_backup))
        
        # Save individual rules for persistence
        for rule in rules:
            search_text = rule['search']
            replace_text = rule['replace']
            
            # Check if rule already exists
            cursor.execute('''
                SELECT id FROM bulk_edit_saved_rules 
                WHERE search_text = ? AND replace_text = ?
            ''', (search_text, replace_text))
            
            if cursor.fetchone():
                # Update last_used timestamp
                cursor.execute('''
                    UPDATE bulk_edit_saved_rules 
                    SET last_used = datetime('now')
                    WHERE search_text = ? AND replace_text = ?
                ''', (search_text, replace_text))
            else:
                # Insert new rule
                cursor.execute('''
                    INSERT INTO bulk_edit_saved_rules (search_text, replace_text)
                    VALUES (?, ?)
                ''', (search_text, replace_text))
        
        # Keep only last 10 history entries
        cursor.execute('''
            DELETE FROM bulk_edit_history 
            WHERE id NOT IN (
                SELECT id FROM bulk_edit_history 
                ORDER BY id DESC 
                LIMIT 10
            )
        ''')
        
        conn.commit()
        
        # Re-fetch channels for processing (cursor was used for history operations)
        cursor.execute('SELECT portal, channel_id, name, custom_name, genre, custom_genre FROM channels')
        channels = cursor.fetchall()
        
        updated_count = 0
        
        for channel in channels:
            portal = channel['portal']
            channel_id = channel['channel_id']
            original_name = channel['custom_name'] or channel['name']
            original_genre = channel['custom_genre'] or channel['genre']
            
            new_name = original_name
            new_genre = original_genre
            
            # Apply rules to name
            if apply_to_names and original_name:
                for rule in rules:
                    search = rule['search']
                    replace = rule['replace']
                    
                    if use_regex:
                        import re
                        flags = 0 if case_sensitive else re.IGNORECASE
                        try:
                            new_name = re.sub(search, replace, new_name, flags=flags)
                        except re.error as e:
                            logger.error(f"Regex error: {e}")
                            continue
                    else:
                        if case_sensitive:
                            new_name = new_name.replace(search, replace)
                        else:
                            # Case-insensitive replace
                            import re
                            pattern = re.compile(re.escape(search), re.IGNORECASE)
                            new_name = pattern.sub(replace, new_name)
            
            # Apply rules to genre
            if apply_to_genres and original_genre:
                for rule in rules:
                    search = rule['search']
                    replace = rule['replace']
                    
                    if use_regex:
                        import re
                        flags = 0 if case_sensitive else re.IGNORECASE
                        try:
                            new_genre = re.sub(search, replace, new_genre, flags=flags)
                        except re.error as e:
                            logger.error(f"Regex error: {e}")
                            continue
                    else:
                        if case_sensitive:
                            new_genre = new_genre.replace(search, replace)
                        else:
                            import re
                            pattern = re.compile(re.escape(search), re.IGNORECASE)
                            new_genre = pattern.sub(replace, new_genre)
            
            # Clean up whitespace
            new_name = ' '.join(new_name.split()).strip()
            new_genre = ' '.join(new_genre.split()).strip()
            
            # Update if changed
            if new_name != original_name or new_genre != original_genre:
                if apply_to_names and new_name != original_name:
                    cursor.execute('''
                        UPDATE channels 
                        SET custom_name = ? 
                        WHERE portal = ? AND channel_id = ?
                    ''', (new_name, portal, channel_id))
                
                if apply_to_genres and new_genre != original_genre:
                    cursor.execute('''
                        UPDATE channels 
                        SET custom_genre = ? 
                        WHERE portal = ? AND channel_id = ?
                    ''', (new_genre, portal, channel_id))
                
                updated_count += 1
        
        conn.commit()
        conn.close()
        
        # Regenerate playlist after bulk edit
        generate_playlist()
        
        logger.info(f"Bulk edit applied: {updated_count} channels updated")
        
        return flask.jsonify({
            "success": True,
            "updated": updated_count
        })
        
    except Exception as e:
        logger.error(f"Error in bulk edit: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500


@app.route("/editor/bulk-edit/undo", methods=["POST"])
@authorise
def editor_bulk_edit_undo():
    """Undo the last bulk edit operation."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the last history entry
        cursor.execute('''
            SELECT id, channels_backup FROM bulk_edit_history 
            ORDER BY id DESC 
            LIMIT 1
        ''')
        history = cursor.fetchone()
        
        if not history:
            return flask.jsonify({"success": False, "error": "No history to undo"}), 400
        
        import json
        channels_backup = json.loads(history['channels_backup'])
        
        # Restore channels from backup
        for channel in channels_backup:
            cursor.execute('''
                UPDATE channels 
                SET custom_name = ?, custom_genre = ?
                WHERE portal = ? AND channel_id = ?
            ''', (channel['custom_name'], channel['custom_genre'], 
                  channel['portal'], channel['channel_id']))
        
        # Delete the history entry
        cursor.execute('DELETE FROM bulk_edit_history WHERE id = ?', (history['id'],))
        
        conn.commit()
        
        # Regenerate playlist after undo
        generate_playlist()
        
        logger.info("Bulk edit undone successfully")
        
        return flask.jsonify({
            "success": True,
            "message": "Last bulk edit undone successfully"
        })
        
    except Exception as e:
        logger.error(f"Error undoing bulk edit: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/bulk-edit/history", methods=["GET"])
@authorise
def editor_bulk_edit_history():
    """Get bulk edit history."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, timestamp, rules FROM bulk_edit_history 
            ORDER BY id DESC 
            LIMIT 10
        ''')
        history = cursor.fetchall()
        
        import json
        history_list = []
        for entry in history:
            rules = json.loads(entry['rules'])
            history_list.append({
                'id': entry['id'],
                'timestamp': entry['timestamp'],
                'rules': rules
            })
        
        return flask.jsonify({
            "success": True,
            "history": history_list
        })
        
    except Exception as e:
        logger.error(f"Error getting bulk edit history: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/bulk-edit/saved-rules", methods=["GET"])
@authorise
def editor_bulk_edit_saved_rules():
    """Get saved bulk edit rules."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT search_text, replace_text, last_used 
            FROM bulk_edit_saved_rules 
            ORDER BY last_used DESC 
            LIMIT 50
        ''')
        rules = cursor.fetchall()
        
        rules_list = []
        for rule in rules:
            rules_list.append({
                'search': rule['search_text'],
                'replace': rule['replace_text'],
                'last_used': rule['last_used']
            })
        
        return flask.jsonify({
            "success": True,
            "rules": rules_list
        })
        
    except Exception as e:
        logger.error(f"Error getting saved rules: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/bulk-edit/clear-saved-rules", methods=["POST"])
@authorise
def editor_bulk_edit_clear_saved_rules():
    """Clear all saved bulk edit rules."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM bulk_edit_saved_rules')
        conn.commit()
        
        logger.info("Cleared all saved bulk edit rules")
        
        return flask.jsonify({
            "success": True,
            "message": "All saved rules cleared"
        })
        
    except Exception as e:
        logger.error(f"Error clearing saved rules: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/reset-all", methods=["POST"])
@authorise
def editor_reset_all_customizations():
    """Reset all custom names and genres to original values."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE channels 
            SET custom_name = NULL,
                custom_genre = NULL
        ''')
        
        conn.commit()
        
        # Regenerate playlist after reset
        generate_playlist()
        
        logger.info("All customizations reset to original values")
        
        return flask.jsonify({
            "success": True,
            "message": "All customizations reset successfully"
        })
        
    except Exception as e:
        logger.error(f"Error resetting customizations: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


@app.route("/editor/reset", methods=["POST"])
@authorise
def editorReset():
    """Reset all channel customizations in the database."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE channels 
            SET enabled = 0,
                custom_name = '',
                custom_number = '',
                custom_genre = '',
                custom_epg_id = '',
                fallback_channel = ''
        ''')
        
        conn.commit()
        logger.info("All channel customizations reset!")
        
        # Regenerate playlist after reset
        generate_playlist()
        
        flash("Playlist reset!", "success")
        
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Error resetting channels: {e}")
        flash(f"Error resetting: {e}", "danger")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
    
    return redirect("/editor", code=302)


@app.route("/editor/refresh", methods=["POST"])
@authorise
def editor_refresh():
    """Manually trigger a refresh of the channel cache."""
    try:
        global editor_refresh_progress
        
        if editor_refresh_progress["running"]:
            return flask.jsonify({"error": "Channel refresh already in progress"}), 400
        
        # Initialize progress
        portals = getPortals()
        enabled_portals = [p for p in portals.values() if p.get("enabled") == "true"]
        
        editor_refresh_progress = {
            "running": True,
            "current_portal": "",
            "current_step": "Starting...",
            "portals_done": 0,
            "portals_total": len(enabled_portals),
            "started_at": time.time()
        }
        
        threading.Thread(target=refresh_channels_cache_with_progress, daemon=True).start()
        return flask.jsonify({"success": True, "message": "Channel refresh started"})
    except Exception as e:
        logger.error(f"Error starting channel refresh: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/editor/refresh/progress", methods=["GET"])
@authorise
def editor_refresh_progress_status():
    """Get channel refresh progress."""
    return flask.jsonify(editor_refresh_progress)


@app.route("/editor/deactivate-duplicates", methods=["POST"])
@authorise
def editor_deactivate_duplicates():
    """Deactivate duplicate enabled channels, keeping only the first occurrence."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Find all duplicate channels (using ROW_NUMBER to identify which to keep)
        find_duplicates_query = """
            WITH ranked_channels AS (
                SELECT 
                    portal,
                    channel_id,
                    COALESCE(NULLIF(custom_name, ''), name) as effective_name,
                    ROW_NUMBER() OVER (
                        PARTITION BY COALESCE(NULLIF(custom_name, ''), name) 
                        ORDER BY portal, channel_id
                    ) as row_num
                FROM channels
                WHERE enabled = 1
            )
            SELECT portal, channel_id, effective_name, row_num
            FROM ranked_channels
            WHERE effective_name IN (
                SELECT effective_name
                FROM ranked_channels
                GROUP BY effective_name
                HAVING COUNT(*) > 1
            )
            AND row_num > 1
            ORDER BY effective_name, row_num
        """
        
        cursor.execute(find_duplicates_query)
        duplicates_to_deactivate = cursor.fetchall()
        
        # Deactivate the duplicate channels
        deactivated_count = 0
        for dup in duplicates_to_deactivate:
            cursor.execute("""
                UPDATE channels
                SET enabled = 0
                WHERE portal = ? AND channel_id = ?
            """, (dup['portal'], dup['channel_id']))
            deactivated_count += 1
        
        conn.commit()
        
        # Regenerate playlist after deactivating duplicates
        generate_playlist()
        
        logger.info(f"Deactivated {deactivated_count} duplicate channels")
        
        return flask.jsonify({
            "success": True,
            "deactivated": deactivated_count,
            "message": f"Deactivated {deactivated_count} duplicate channels"
        })
        
    except Exception as e:
        logger.error(f"Error in editor_deactivate_duplicates: {e}")
        return flask.jsonify({
            "success": False,
            "deactivated": 0,
            "error": str(e)
        }), 500
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

@app.route("/settings", methods=["GET"])
@authorise
def settings():
    settings = getSettings()
    return render_template(
        "settings.html", settings=settings, defaultSettings=defaultSettings
    )


@app.route("/wiki", methods=["GET"])
@authorise
def wiki():
    """Feature wiki page showing new features and improvements."""
    return render_template("wiki.html")


@app.route("/macstrom-import", methods=["GET"])
@authorise
def macstrom_import_page():
    """Macstrom import page."""
    settings = getSettings()
    return render_template("macstrom_import.html",
                           portals=getPortals(),
                           macstrom_url=settings.get("macstrom_url", ""),
                           macstrom_api_key=settings.get("macstrom_api_key", ""))


@app.route("/macstrom-import/save-connection", methods=["POST"])
@authorise
def macstrom_save_connection():
    """Save Macstrom connection settings."""
    data = request.json
    settings = getSettings()
    settings["macstrom_url"] = data.get("url", "").strip()
    settings["macstrom_api_key"] = data.get("api_key", "").strip()
    saveSettings(settings)
    return flask.jsonify({"success": True})


@app.route("/macstrom-import/fetch", methods=["POST"])
@authorise
def macstrom_fetch_hits():
    """Fetch saved hits from Macstrom API with server-side cache and pagination."""
    import requests as req_lib
    global _macstrom_hits_cache

    data = request.json
    url = data.get("url", "").strip().rstrip("/")
    api_key = data.get("api_key", "").strip()
    page_size = int(data.get("page_size", 500))
    page = int(data.get("page", 0))
    force_refresh = data.get("refresh", False)

    if not url or not api_key:
        return flask.jsonify({"error": "URL und API Key erforderlich"}), 400

    # Use cache if same URL and not older than 5 minutes, unless forced
    cache_age = time.time() - _macstrom_hits_cache["ts"]
    if force_refresh or _macstrom_hits_cache["url"] != url or cache_age > 300:
        try:
            resp = req_lib.get(
                f"{url}/api/hits",
                headers={"X-Api-Key": api_key},
                timeout=60
            )
            if resp.status_code == 401:
                return flask.jsonify({"error": "Ungültiger API Key"}), 401
            if resp.status_code != 200:
                return flask.jsonify({"error": f"Macstrom antwortete mit Status {resp.status_code}"}), 502

            raw_hits = resp.json()
            now = int(time.time())
            normalized = []
            for h in raw_hits:
                cats = h.get("categories", {})
                live = cats.get("live", 0)
                movies = cats.get("movies", 0)
                series = cats.get("series", 0)
                expiry_epoch = h.get("expiry_epoch")

                # portal_url: Macstrom uses "portal" field
                portal_url = h.get("portal_url") or h.get("portal", "")

                # Detect DE content from portal name or genres
                genres_str = str(h.get("genres", "")).upper()
                portal_name_str = str(h.get("portal_name", "")).upper()
                has_de = any(p in genres_str or p in portal_name_str for p in ["DE", "GER", "GERMAN", "DEUTSCH", "DEUTSCHLAND"])

                days = ((expiry_epoch - now) / 86400) if expiry_epoch else 0
                is_dead = h.get("validation_state") in ["invalid", "failed", "retest_failed"]
                if is_dead:
                    score = 5
                elif days < 0:
                    score = 10
                else:
                    base = 30 if h.get("validation_state") == "valid" else 20
                    exp = min(25, (max(0, days) + 1) ** 0.5 / 27 * 25) if expiry_epoch else 0
                    ch = min(25, ((live + movies + series + 1) ** 0.5) / 71 * 25)
                    st = 10 if h.get("stream_test_result") == "pass" else (-5 if h.get("stream_test_result") == "fail" else 0)
                    conn = {0: 0, 1: 2, 2: 5, 3: 7}.get(h.get("playback_limit", 0), 10)
                    score = max(0, min(100, int(base + exp + ch + st + conn)))

                normalized.append({
                    "id": h.get("id"),
                    "portal_name": h.get("portal_name", "Unknown"),
                    "portal_url": portal_url,
                    "mac": h.get("mac", ""),
                    "expiry": h.get("expiry", ""),
                    "expiry_epoch": expiry_epoch,
                    "categories_live": live,
                    "categories_movies": movies,
                    "categories_series": series,
                    "playback_limit": h.get("playback_limit"),
                    "validation_state": h.get("validation_state", "unchecked"),
                    "stream_test_result": h.get("stream_test_result"),
                    "proxy": h.get("proxy", ""),
                    "score": score,
                })

            _macstrom_hits_cache = {"hits": normalized, "url": url, "ts": time.time()}
            logger.info(f"Fetched and cached {len(normalized)} hits from Macstrom at {url}")

        except req_lib.exceptions.ConnectionError:
            return flask.jsonify({"error": f"Verbindung zu {url} fehlgeschlagen"}), 502
        except req_lib.exceptions.Timeout:
            return flask.jsonify({"error": "Timeout beim Verbinden mit Macstrom"}), 504
        except Exception as e:
            logger.error(f"Error fetching from Macstrom: {e}")
            return flask.jsonify({"error": str(e)}), 500

    all_hits = _macstrom_hits_cache["hits"]
    total = len(all_hits)
    start = page * page_size
    end = start + page_size
    page_hits = all_hits[start:end]

    return flask.jsonify({
        "hits": page_hits,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
        "cached": not force_refresh and _macstrom_hits_cache["url"] == url,
    })


@app.route("/macstrom-import/already-imported", methods=["GET"])
@authorise
def macstrom_already_imported():
    """Return set of MAC addresses already present in MacReplay portals."""
    portals = getPortals()
    imported_macs = set()
    for portal in portals.values():
        for mac in portal.get("macs", {}).keys():
            imported_macs.add(mac.upper())
    return flask.jsonify({"macs": list(imported_macs)})


@app.route("/macstrom-import/import", methods=["POST"])
@authorise
def macstrom_import_hits():
    """Import selected hits from Macstrom into MacReplay portals."""
    data = request.json
    hits = data.get("hits", [])
    target_portal_id = data.get("target_portal_id")  # None = create new portals
    streams_per_mac = int(data.get("streams_per_mac", 1))

    if not hits:
        return flask.jsonify({"error": "Keine MACs ausgewählt"}), 400

    portals = getPortals()
    imported = 0
    skipped = 0
    portals_created = 0
    portals_updated = 0
    details = []

    # Group hits by portal_name + portal_url
    portal_groups = {}
    for h in hits:
        key = (h.get("portal_name", "Unknown"), h.get("portal_url", ""))
        if key not in portal_groups:
            portal_groups[key] = []
        portal_groups[key].append(h)

    for (portal_name, portal_url), group_hits in portal_groups.items():
        if target_portal_id:
            # Add to existing portal
            portal_id = target_portal_id
            if portal_id not in portals:
                details.append({"portal_name": portal_name, "mac": "*", "success": False, "message": "Ziel-Portal nicht gefunden"})
                skipped += len(group_hits)
                continue
            portal = portals[portal_id]
            portal_url_to_use = portal.get("url", portal_url)
            is_new_portal = False
        else:
            # Find existing portal by URL or create new one
            existing_id = None
            for pid, p in portals.items():
                if p.get("url", "").rstrip("/") == portal_url.rstrip("/"):
                    existing_id = pid
                    break

            if existing_id:
                portal_id = existing_id
                portal = portals[portal_id]
                portal_url_to_use = portal.get("url", portal_url)
                is_new_portal = False
            else:
                # Create new portal
                portal_id = uuid.uuid4().hex
                portal_url_to_use = portal_url
                portal = {
                    "enabled": "true",
                    "name": portal_name,
                    "url": portal_url,
                    "macs": {},
                    "streams per mac": str(streams_per_mac),
                    "epg offset": "0",
                    "proxy": "",
                    "portal prefix": "",
                }
                for setting, default in defaultPortal.items():
                    if setting not in portal:
                        portal[setting] = default
                portals[portal_id] = portal
                portals_created += 1
                is_new_portal = True

        # Add each MAC directly using Macstrom data (no live handshake needed)
        for h in group_hits:
            mac = h.get("mac", "")
            if not mac:
                skipped += 1
                continue

            # Skip if MAC already exists in portal
            if mac in portals[portal_id].get("macs", {}):
                details.append({"portal_name": portal_name, "mac": mac, "success": False, "message": "Bereits vorhanden"})
                skipped += 1
                continue

            # Use expiry from Macstrom directly
            expiry = h.get("expiry", "")
            portals[portal_id]["macs"][mac] = expiry
            imported += 1
            if not is_new_portal:
                portals_updated += 1
            details.append({"portal_name": portal_name, "mac": mac, "success": True, "message": f"Importiert (Ablauf: {expiry or 'unbekannt'})"})

    # Save portals — channel fetch happens when user selects genres
    if imported > 0:
        savePortals(portals)
        logger.info(f"Macstrom import: {imported} MACs imported, {skipped} skipped, {portals_created} portals created")

    return flask.jsonify({
        "imported": imported,
        "skipped": skipped,
        "portals_created": portals_created,
        "portals_updated": portals_updated,
        "details": details[:50]  # Limit details to 50 entries
    })


@app.route("/proxy-test", methods=["GET"])
@authorise
def proxy_test_page():
    """Proxy test page."""
    return render_template("proxy_test.html")


@app.route("/settings/save", methods=["POST"])
@authorise
def save():
    settings = {}

    for setting, _ in defaultSettings.items():
        if setting == "public playlist access":
            # Special handling for inverted checkbox logic
            # If checkbox is checked, it means "secure" (false for public access)
            # If checkbox is not checked, it means "public" (true for public access)
            checkbox_value = request.form.get(setting)
            if checkbox_value == "false":  # Checkbox is checked (secure mode)
                settings[setting] = "false"  # No public access
            else:  # Checkbox is not checked (public mode)
                settings[setting] = "true"   # Allow public access
        else:
            value = request.form.get(setting, "false")
            settings[setting] = value

    saveSettings(settings)
    logger.info("Settings saved!")
    
    # EPG refresh is controlled by EPG Auto Refresh setting
    # Use Dashboard "Refresh EPG" button for manual refresh
    
    flash("Settings saved!", "success")
    return redirect("/settings", code=302)


# ============================================
# XC Users Management Routes
# ============================================

@app.route("/xc-users", methods=["GET"])
@authorise
def xc_users_page():
    """XC Users management page."""
    return render_template("xc_users.html", settings=getSettings())


@app.route("/xc-users/list", methods=["GET"])
@authorise
def xc_users_list():
    """Get list of XC users."""
    users = getXCUsers()
    user_list = []
    
    # Create a copy to avoid RuntimeError if dictionary changes during iteration
    for user_id, user in list(users.items()):
        active_cons = len(user.get("active_connections", {}))
        user_list.append({
            "id": user_id,
            "username": user.get("username"),
            "password": user.get("password"),
            "enabled": user.get("enabled") == "true",
            "max_connections": user.get("max_connections"),
            "active_connections": active_cons,
            "allowed_portals": user.get("allowed_portals", []),
            "created_at": user.get("created_at"),
            "expires_at": user.get("expires_at")
        })
    
    return flask.jsonify({"users": user_list})


@app.route("/xc-users/add", methods=["POST"])
@authorise
def xc_users_add():
    """Add new XC user."""
    try:
        data = request.json
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        
        if not username or not password:
            return flask.jsonify({"error": "Username and password required"}), 400
        
        users = getXCUsers()
        user_id = f"{username}_{password}"
        
        if user_id in users:
            return flask.jsonify({"error": "User already exists"}), 400
        
        users[user_id] = {
            "username": username,
            "password": password,
            "enabled": "true",
            "max_connections": str(data.get("max_connections", 1)),
            "allowed_portals": data.get("allowed_portals", []),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "expires_at": data.get("expires_at", ""),
            "active_connections": {}
        }
        
        saveXCUsers(users)
        logger.info(f"XC user created: {username}")
        return flask.jsonify({"success": True, "user_id": user_id})
    except Exception as e:
        logger.error(f"Error adding XC user: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/xc-users/update", methods=["POST"])
@authorise
def xc_users_update():
    """Update XC user."""
    try:
        data = request.json
        user_id = data.get("user_id")
        
        if not user_id:
            return flask.jsonify({"error": "User ID required"}), 400
        
        users = getXCUsers()
        if user_id not in users:
            return flask.jsonify({"error": "User not found"}), 404
        
        users[user_id]["enabled"] = "true" if data.get("enabled") else "false"
        users[user_id]["max_connections"] = str(data.get("max_connections", 1))
        users[user_id]["allowed_portals"] = data.get("allowed_portals", [])
        users[user_id]["expires_at"] = data.get("expires_at", "")
        
        saveXCUsers(users)
        logger.info(f"XC user updated: {user_id}")
        return flask.jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error updating XC user: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/xc-users/delete", methods=["POST"])
@authorise
def xc_users_delete():
    """Delete XC user."""
    try:
        data = request.json
        user_id = data.get("user_id")
        
        if not user_id:
            return flask.jsonify({"error": "User ID required"}), 400
        
        users = getXCUsers()
        if user_id not in users:
            return flask.jsonify({"error": "User not found"}), 404
        
        username = users[user_id].get("username")
        del users[user_id]
        saveXCUsers(users)
        
        logger.info(f"XC user deleted: {username}")
        return flask.jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting XC user: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/xc-users/kick", methods=["POST"])
@authorise
def xc_users_kick():
    """Kick active connection."""
    try:
        data = request.json
        user_id = data.get("user_id")
        device_id = data.get("device_id")
        
        if not user_id or not device_id:
            return flask.jsonify({"error": "User ID and device ID required"}), 400
        
        unregisterXCConnection(user_id, device_id)
        logger.info(f"Kicked connection: {user_id}/{device_id}")
        return flask.jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error kicking connection: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/playlist.m3u", methods=["GET"])
def playlist():
    """Main M3U playlist with support for both session-based and Basic Auth."""
    settings = getSettings()
    public_access = settings.get("public playlist access", "true") == "true"
    
    if public_access:
        # Public access enabled - no authentication required
        return _playlist()
    else:
        # Public access disabled - check for authentication
        
        # First check if user is logged in via session (existing logic)
        if flask.session.get("authenticated"):
            return _playlist()
        
        # If no session, try Basic Auth
        auth = request.authorization
        if auth and auth.username and auth.password:
            # Validate Basic Auth credentials
            system_username = settings.get("username", "admin")
            system_password = settings.get("password", "12345")
            
            if auth.username == system_username and auth.password == system_password:
                # Basic Auth successful - generate playlist with embedded auth
                logger.info(f"Basic Auth successful for main playlist: {auth.username}")
                return _playlist_with_auth(auth.username, auth.password)
            else:
                logger.warning(f"Invalid Basic Auth credentials for main playlist: {auth.username}")
        
        # No valid authentication - check if this is a Basic Auth request
        if auth:
            # Basic Auth was attempted but failed
            response = Response(
                'Invalid credentials\n'
                'Please check your username and password.',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Main Playlist"'}
            )
            return response
        else:
            # No Basic Auth provided - use existing session-based auth (redirect to login)
            return authorise(lambda: _playlist())()

def _playlist():
    global cached_playlist, last_playlist_host
    
    logger.info("Playlist Requested")
    
    # Use external host configuration
    external_host, external_scheme = get_external_host_config()
    # Use request.host only if we're in a request context
    try:
        current_host = external_host or request.host or "0.0.0.0:8001"
    except RuntimeError:
        # Not in request context (e.g., called from generate_playlist)
        current_host = external_host or "0.0.0.0:8001"
    
    # Try to read from file first
    playlist_file = os.path.join(log_dir, "playlist.m3u")
    if os.path.exists(playlist_file):
        # Check if host changed - if so, regenerate
        if last_playlist_host and last_playlist_host != current_host:
            logger.info(f"Regenerating playlist due to host change: {last_playlist_host} -> {current_host}")
            last_playlist_host = current_host
            generate_playlist()
        
        # Serve from file
        try:
            with open(playlist_file, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype="text/plain")
        except Exception as e:
            logger.error(f"Error reading playlist file: {e}")
            # Fallback to RAM cache
            if cached_playlist:
                return Response(cached_playlist, mimetype="text/plain")
    
    # File doesn't exist - generate it
    logger.info("Playlist file not found - generating...")
    last_playlist_host = current_host
    generate_playlist()
    
    # Try to read the newly generated file
    if os.path.exists(playlist_file):
        try:
            with open(playlist_file, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype="text/plain")
        except Exception as e:
            logger.error(f"Error reading newly generated playlist file: {e}")
    
    # Final fallback to RAM cache
    if cached_playlist:
        return Response(cached_playlist, mimetype="text/plain")
    else:
        return Response("#EXTM3U\n", mimetype="text/plain")


@app.route("/playlist_external.m3u", methods=["GET"])
def playlist_external():
    """External M3U playlist with public URLs (uses HOST_EXTERNAL)."""
    settings = getSettings()
    public_access = settings.get("public playlist access", "true") == "true"
    
    if public_access:
        # Public access enabled - no authentication required
        return _playlist_external()
    else:
        # Public access disabled - check for authentication
        
        # First check if user is logged in via session
        if flask.session.get("authenticated"):
            return _playlist_external()
        
        # If no session, try Basic Auth
        auth = request.authorization
        if auth and auth.username and auth.password:
            # Validate Basic Auth credentials
            system_username = settings.get("username", "admin")
            system_password = settings.get("password", "12345")
            
            if auth.username == system_username and auth.password == system_password:
                return _playlist_external()
            else:
                return Response("Invalid credentials", 401, {"WWW-Authenticate": 'Basic realm="Login Required"'})
        else:
            # No Basic Auth provided - use existing session-based auth
            return authorise(lambda: _playlist_external())()


def _playlist_external():
    """Internal function to serve external playlist."""
    logger.info("External Playlist Requested")
    
    # Check if HOST_EXTERNAL is configured
    external_host_public, external_scheme_public = get_external_host_public_config()
    if not external_host_public:
        logger.warning("HOST_EXTERNAL not configured - returning regular playlist")
        return _playlist()
    
    # Try to read from file
    playlist_file_external = os.path.join(log_dir, "playlist_external.m3u")
    if os.path.exists(playlist_file_external):
        try:
            with open(playlist_file_external, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype="text/plain")
        except Exception as e:
            logger.error(f"Error reading external playlist file: {e}")
    
    # File doesn't exist - generate it
    logger.info("External playlist file not found - generating...")
    generate_playlist()
    
    # Try to read the newly generated file
    if os.path.exists(playlist_file_external):
        try:
            with open(playlist_file_external, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype="text/plain")
        except Exception as e:
            logger.error(f"Error reading newly generated external playlist file: {e}")
    
    # Fallback to regular playlist
    logger.warning("External playlist not available - falling back to regular playlist")
    return _playlist()


def _playlist_with_auth(username, password):
    """Generate playlist with embedded Basic Auth credentials in stream URLs."""
    logger.info("Playlist with Basic Auth Requested")
    
    # Use external host configuration or request host
    external_host, external_scheme = get_external_host_config()
    if external_host:
        playlist_host = external_host
    else:
        # Use the actual request host (e.g., your-domain.com:8001)
        playlist_host = request.host or "0.0.0.0:8001"
    
    channels = []
    
    # Get enabled channels from database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
               number, custom_number, custom_epg_id
        FROM channels 
        WHERE enabled = 1
        ORDER BY portal, channel_id
    ''')
    db_channels = cursor.fetchall()
    conn.close()
    
    # Get portal info
    portals = getPortals()
    
    for channel in db_channels:
        portal_id = channel['portal']
        channel_id = str(channel['channel_id'])
        
        # Check if portal is enabled
        if portal_id not in portals or portals[portal_id].get("enabled") != "true":
            continue
        
        # Use custom values if available, otherwise use original values
        channel_name = channel['custom_name'] if channel['custom_name'] else (channel['name'] or "Unknown Channel")
        genre = channel['custom_genre'] if channel['custom_genre'] else (channel['genre'] or "")
        channel_number = channel['custom_number'] if channel['custom_number'] else (channel['number'] or "")
        epg_id = channel['custom_epg_id'] if channel['custom_epg_id'] else channel_name
        
        # Use portal name or genre as group-title based on settings
        portal_name = portals[portal_id].get("name", portal_id)
        
        # Check if we should use portal names as groups
        if getSettings().get("use portal names as groups", "false") == "true":
            group_title = portal_name
        else:
            # Use genre (with optional portal prefix)
            portal_prefix = portals[portal_id].get("portal prefix", "").strip()
            if portal_prefix and genre:
                group_title = f"[{portal_prefix}] {genre}"
            else:
                group_title = genre
        
        # Build M3U entry - escape quotes in attributes
        def escape_quotes(text):
            return str(text).replace('"', '&quot;') if text else ""
        
        m3u_entry = "#EXTINF:-1"
        m3u_entry += ' tvg-id="' + escape_quotes(epg_id) + '"'
        
        if getSettings().get("use channel numbers", "true") == "true" and channel_number:
            m3u_entry += ' tvg-chno="' + escape_quotes(channel_number) + '"'
        
        # Use group-title based on settings
        if getSettings().get("use channel genres", "true") == "true" and group_title:
            m3u_entry += ' group-title="' + escape_quotes(group_title) + '"'
        
        m3u_entry += ',' + str(channel_name) + "\n"
        # Embed Basic Auth credentials in stream URL
        m3u_entry += f"http://{username}:{password}@{playlist_host}/play/{portal_id}/{channel_id}"
        
        channels.append(m3u_entry)

    # Sort channels based on settings (same logic as generate_playlist)
    if getSettings().get("sort playlist by channel name", "true") == "true":
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0] if "," in k else "")
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            def get_channel_number(k):
                try:
                    if 'tvg-chno="' in k:
                        return int(k.split('tvg-chno="')[1].split('"')[0])
                    return 999999  # Put channels without numbers at the end
                except (ValueError, IndexError):
                    return 999999
            channels.sort(key=get_channel_number)
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            def get_genre(k):
                try:
                    if 'group-title="' in k:
                        return k.split('group-title="')[1].split('"')[0]
                    return "zzz"  # Put channels without genre at the end
                except IndexError:
                    return "zzz"
            channels.sort(key=get_genre)

    playlist = "#EXTM3U \n"
    if channels:
        playlist = playlist + "\n".join(channels)

    logger.info("Playlist with Basic Auth generated.")
    return Response(playlist, mimetype="text/plain")

@app.route("/update_playlistm3u", methods=["POST"])
@authorise
def update_playlistm3u():
    try:
        # First, clean up orphaned channels from deleted portals
        cleanup_orphaned_channels()
        
        # Then generate the playlist
        generate_playlist()
        logger.info("Playlist updated via dashboard")
        return Response("Playlist updated successfully", status=200)
    except Exception as e:
        logger.error(f"Error updating playlist: {e}")
        return Response(f"Error updating playlist: {str(e)}", status=500)

def cleanup_orphaned_channels():
    """Remove channels from database that belong to portals that no longer exist."""
    conn = None
    try:
        portals = getPortals()
        valid_portal_ids = set(portals.keys())
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all unique portal IDs from the database
        cursor.execute('SELECT DISTINCT portal FROM channels')
        db_portal_ids = set(row[0] for row in cursor.fetchall())
        
        # Find orphaned portal IDs (in DB but not in config)
        orphaned_ids = db_portal_ids - valid_portal_ids
        
        if orphaned_ids:
            for portal_id in orphaned_ids:
                cursor.execute('DELETE FROM channels WHERE portal = ?', (portal_id,))
                deleted = cursor.rowcount
                logger.info(f"Cleaned up {deleted} orphaned channels from deleted portal: {portal_id}")
            
            conn.commit()
        
    except Exception as e:
        logger.error(f"Error cleaning up orphaned channels: {e}")
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

def generate_playlist():
    global cached_playlist
    logger.info("Generating playlist.m3u from database...")

    # Use external host configuration
    external_host, external_scheme = get_external_host_config()
    # Use request.host only if we're in a request context
    try:
        playlist_host = external_host or request.host or "0.0.0.0:8001"
    except RuntimeError:
        # Not in request context (e.g., called from dashboard button)
        playlist_host = external_host or "0.0.0.0:8001"
    
    # Check if we should also generate an external playlist
    external_host_public, external_scheme_public = get_external_host_public_config()
    generate_external = external_host_public is not None
    
    channels = []
    channels_external = [] if generate_external else None
    
    # Get enabled channels from database
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
                   number, custom_number, custom_epg_id
            FROM channels 
            WHERE enabled = 1
        ORDER BY portal, channel_id
    ''')
        db_channels = cursor.fetchall()
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
    
    # Get portal info
    portals = getPortals()
    
    for channel in db_channels:
        portal_id = channel['portal']
        channel_id = str(channel['channel_id'])
        
        # Check if portal is enabled
        if portal_id not in portals or portals[portal_id].get("enabled") != "true":
            continue
        
        # Use custom values if available, otherwise use original values
        channel_name = channel['custom_name'] if channel['custom_name'] else (channel['name'] or "Unknown Channel")
        genre = channel['custom_genre'] if channel['custom_genre'] else (channel['genre'] or "")
        channel_number = channel['custom_number'] if channel['custom_number'] else (channel['number'] or "")
        epg_id = channel['custom_epg_id'] if channel['custom_epg_id'] else channel_name
        
        # Determine group-title based on settings
        if getSettings().get("use portal names as groups", "false") == "true":
            # Use portal name as group
            group_title = portals[portal_id].get("name", portal_id)
        else:
            # Use genre with optional portal prefix
            portal_prefix = portals[portal_id].get("portal prefix", "").strip()
            if portal_prefix and genre:
                group_title = f"[{portal_prefix}] {genre}"
            else:
                group_title = genre
        
        # Build M3U entry - escape quotes in attributes
        def escape_quotes(text):
            return str(text).replace('"', '&quot;') if text else ""
        
        m3u_entry = "#EXTINF:-1"
        m3u_entry += ' tvg-id="' + escape_quotes(epg_id) + '"'
        
        if getSettings().get("use channel numbers", "true") == "true" and channel_number:
            m3u_entry += ' tvg-chno="' + escape_quotes(channel_number) + '"'
        
        if getSettings().get("use channel genres", "true") == "true" and group_title:
            m3u_entry += ' group-title="' + escape_quotes(group_title) + '"'
        
        m3u_entry += ',' + str(channel_name) + "\n"
        m3u_entry += "http://" + playlist_host + "/play/" + portal_id + "/" + channel_id
        
        channels.append(m3u_entry)
        
        # Generate external playlist entry if HOST_EXTERNAL is set
        if generate_external:
            m3u_entry_ext = "#EXTINF:-1"
            m3u_entry_ext += ' tvg-id="' + escape_quotes(epg_id) + '"'
            
            if getSettings().get("use channel numbers", "true") == "true" and channel_number:
                m3u_entry_ext += ' tvg-chno="' + escape_quotes(channel_number) + '"'
            
            if getSettings().get("use channel genres", "true") == "true" and group_title:
                m3u_entry_ext += ' group-title="' + escape_quotes(group_title) + '"'
            
            m3u_entry_ext += ',' + str(channel_name) + "\n"
            m3u_entry_ext += "http://" + external_host_public + "/play/" + portal_id + "/" + channel_id
            
            channels_external.append(m3u_entry_ext)

    # Sort channels based on settings
    if getSettings().get("sort playlist by channel name", "true") == "true":
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0] if "," in k else "")
        if generate_external:
            channels_external.sort(key=lambda k: k.split(",")[1].split("\n")[0] if "," in k else "")
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            def get_channel_number(k):
                try:
                    if 'tvg-chno="' in k:
                        return int(k.split('tvg-chno="')[1].split('"')[0])
                    return 999999  # Put channels without numbers at the end
                except (ValueError, IndexError):
                    return 999999
            channels.sort(key=get_channel_number)
            if generate_external:
                channels_external.sort(key=get_channel_number)
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            def get_genre(k):
                try:
                    if 'group-title="' in k:
                        return k.split('group-title="')[1].split('"')[0]
                    return "zzz"  # Put channels without genre at the end
                except IndexError:
                    return "zzz"
            channels.sort(key=get_genre)
            if generate_external:
                channels_external.sort(key=get_genre)

    playlist = "#EXTM3U \n"
    if channels:
        playlist = playlist + "\n".join(channels)

    # Write to file instead of RAM cache
    playlist_file = os.path.join(log_dir, "playlist.m3u")
    try:
        with open(playlist_file, "w", encoding="utf-8") as f:
            f.write(playlist)
        logger.info(f"Playlist generated and saved to file ({len(channels)} channels)")
    except Exception as e:
        logger.error(f"Error writing playlist file: {e}")
        # Fallback to RAM cache if file write fails
        cached_playlist = playlist
    
    # Generate external playlist if HOST_EXTERNAL is set
    if generate_external:
        playlist_external = "#EXTM3U \n"
        if channels_external:
            playlist_external = playlist_external + "\n".join(channels_external)
        
        playlist_file_external = os.path.join(log_dir, "playlist_external.m3u")
        try:
            with open(playlist_file_external, "w", encoding="utf-8") as f:
                f.write(playlist_external)
            logger.info(f"External playlist generated and saved to file ({len(channels_external)} channels)")
        except Exception as e:
            logger.error(f"Error writing external playlist file: {e}")
    
    # Also update RAM cache for backward compatibility
    cached_playlist = playlist
    
def normalize_channel_name(name):
    """Normalize channel name for better matching."""
    import re
    if not name:
        return ""
    # Convert to lowercase
    name = name.lower().strip()
    # Remove common suffixes/prefixes
    name = re.sub(r'\s*(hd|sd|fhd|uhd|4k)\s*$', '', name, flags=re.IGNORECASE)
    # Remove special characters but keep spaces
    name = re.sub(r'[^\w\s]', '', name)
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def find_best_epg_match(channel_name, fallback_data):
    """Find best EPG match using normalized names with VERY strict matching rules.
    Returns None if no confident match is found - better no EPG than wrong EPG."""
    if not channel_name or not fallback_data:
        return None
    
    normalized_search = normalize_channel_name(channel_name)
    if not normalized_search:
        return None
    
    # Try exact match first - this is the only 100% confident match
    for fb_name, fb_data in fallback_data.items():
        if normalize_channel_name(fb_name) == normalized_search:
            return fb_data['channel_id']
    
    # Try substring match - but ONLY if it's a very strong match (80% similarity)
    for fb_name, fb_data in fallback_data.items():
        normalized_fb = normalize_channel_name(fb_name)
        # Increased threshold to 80% to be more conservative
        if normalized_search in normalized_fb:
            if len(normalized_search) >= len(normalized_fb) * 0.8:
                return fb_data['channel_id']
        elif normalized_fb in normalized_search:
            if len(normalized_fb) >= len(normalized_search) * 0.8:
                return fb_data['channel_id']
    
    # Word-by-word matching is now DISABLED by default
    # It causes too many false positives
    # If you want to enable it, uncomment the code below and adjust thresholds
    
    # # Try word-by-word match with VERY strict requirements
    # search_words = set(normalized_search.split())
    # # Filter out common words that shouldn't be used for matching
    # common_words = {'tv', 'hd', 'sd', 'channel', 'de', 'nl', 'uk', 'us', 'plus', 'one', 'two', 'drei', 'vier'}
    # search_words = search_words - common_words
    # 
    # if not search_words or len(search_words) < 2:
    #     return None  # Need at least 2 meaningful words to match
    # 
    # best_match = None
    # best_score = 0
    # best_ratio = 0
    # 
    # for fb_name, fb_data in fallback_data.items():
    #     fb_words = set(normalize_channel_name(fb_name).split()) - common_words
    #     if not fb_words or len(fb_words) < 2:
    #         continue
    #     
    #     # Count matching words
    #     matching_words = search_words & fb_words
    #     match_ratio = len(matching_words) / max(len(search_words), len(fb_words))
    #     
    #     # Require at least 75% of words to match (increased from 50%)
    #     # AND at least 2 matching words
    #     if match_ratio >= 0.75 and len(matching_words) >= 2 and len(matching_words) > best_score:
    #         best_score = len(matching_words)
    #         best_ratio = match_ratio
    #         best_match = fb_data['channel_id']
    # 
    # # Only return if we have a very strong match
    # if best_score >= 2 and best_ratio >= 0.75:
    #     return best_match
    
    # No confident match found - return None (better no EPG than wrong EPG)
    return None


def fetch_epgshare_fallback(countries):
    """Fetch EPG data from epgshare01.online for specified countries.
    
    IMPROVEMENT #1: Raw XML Passthrough - Preserves all metadata from fallback EPG
    (icons, categories, credits, ratings, episode numbers, etc.)
    """
    fallback_programmes = {}
    base_url = "https://epgshare01.online/epgshare01/"
    
    # Country code mapping
    country_files = {
        "DE": "epg_ripper_DE1.xml.gz",
        "AT": "epg_ripper_AT1.xml.gz",
        "CH": "epg_ripper_CH1.xml.gz",
        "NL": "epg_ripper_NL1.xml.gz",
        "BE": "epg_ripper_BE2.xml.gz",
        "UK": "epg_ripper_UK1.xml.gz",
        "US": "epg_ripper_US2.xml.gz",
        "FR": "epg_ripper_FR1.xml.gz",
        "ES": "epg_ripper_ES1.xml.gz",
        "IT": "epg_ripper_IT1.xml.gz",
        "PL": "epg_ripper_PL1.xml.gz",
        "TR": "epg_ripper_TR1.xml.gz",
        "PT": "epg_ripper_PT1.xml.gz",
        "SE": "epg_ripper_SE1.xml.gz",
        "NO": "epg_ripper_NO1.xml.gz",
        "DK": "epg_ripper_DK1.xml.gz",
        "FI": "epg_ripper_FI1.xml.gz",
        "GR": "epg_ripper_GR1.xml.gz",
        "RO": "epg_ripper_RO1.xml.gz",
        "HU": "epg_ripper_HU1.xml.gz",
        "CZ": "epg_ripper_CZ1.xml.gz",
        "SK": "epg_ripper_SK1.xml.gz",
        "HR": "epg_ripper_HR1.xml.gz",
        "RS": "epg_ripper_RS1.xml.gz",
        "BG": "epg_ripper_BG1.xml.gz",
        "AU": "epg_ripper_AU1.xml.gz",
        "NZ": "epg_ripper_NZ1.xml.gz",
        "CA": "epg_ripper_CA2.xml.gz",
        "BR": "epg_ripper_BR1.xml.gz",
        "MX": "epg_ripper_MX1.xml.gz",
        "AR": "epg_ripper_AR1.xml.gz",
        "JP": "epg_ripper_JP1.xml.gz",
        "KR": "epg_ripper_KR1.xml.gz",
        "IN": "epg_ripper_IN1.xml.gz",
        "IL": "epg_ripper_IL1.xml.gz",
        "ZA": "epg_ripper_ZA1.xml.gz",
        "IE": "epg_ripper_IE1.xml.gz",
    }
    
    for country in countries:
        country = country.strip().upper()
        if country not in country_files:
            logger.warning(f"No EPG fallback available for country: {country}")
            continue
        
        try:
            url = base_url + country_files[country]
            logger.info(f"Fetching EPG fallback for {country} from {url}")
            
            response = requests.get(url, timeout=60)
            if response.status_code == 200:
                # Decompress gzip
                with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
                    xml_content = f.read().decode('utf-8')
                
                # Parse XML
                root = ET.fromstring(xml_content)
                
                # Extract channel mappings and programmes
                for channel in root.findall('channel'):
                    channel_id = channel.get('id', '')
                    display_name = channel.find('display-name')
                    if display_name is not None and display_name.text:
                        # Store by display name (lowercase for matching)
                        name_key = display_name.text.lower().strip()
                        if name_key not in fallback_programmes:
                            fallback_programmes[name_key] = {
                                'channel_id': channel_id,
                                'programmes': []
                            }
                
                for programme in root.findall('programme'):
                    channel_id = programme.get('channel', '')
                    # Find matching channel name
                    for name_key, data in fallback_programmes.items():
                        if data['channel_id'] == channel_id:
                            # IMPROVEMENT #1: Store raw XML element instead of just title/desc
                            # This preserves ALL metadata (icons, categories, credits, ratings, etc.)
                            data['programmes'].append({
                                'start': programme.get('start', ''),
                                'stop': programme.get('stop', ''),
                                'xml_element': programme  # Store entire XML element for passthrough
                            })
                            break
                
                logger.info(f"Loaded {len([p for d in fallback_programmes.values() for p in d['programmes']])} programmes from {country}")
                
                # Don't delete root - we need the XML elements
                del xml_content
                
        except Exception as e:
            logger.error(f"Error fetching EPG fallback for {country}: {e}")
    
    return fallback_programmes


def refresh_xmltv_with_progress():
    """Wrapper for refresh_xmltv with progress tracking."""
    global epg_refresh_progress
    try:
        refresh_xmltv()
    finally:
        epg_refresh_progress["running"] = False
        epg_refresh_progress["current_step"] = "Completed"

def refresh_xmltv():
    """Refresh XMLTV data with ALL 9 EPG IMPROVEMENTS implemented."""
    import gc
    import re
    global epg_refresh_progress
    
    settings = getSettings()
    logger.info("Refreshing XMLTV with EPG improvements...")

    # Docker-optimized cache paths
    cache_dir = "/app/data"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "epg.xml")

    day_before_yesterday = datetime.utcnow() - timedelta(days=2)
    day_before_yesterday_str = day_before_yesterday.strftime("%Y%m%d%H%M%S") + " +0000"

    # IMPROVEMENT #7: (lang=) Cleanup regex
    lang_cleanup_regex = re.compile(r'\s*\(lang=[^)]+\)\s*')

    # Check if EPG fallback is enabled
    epg_refresh_progress["current_step"] = "Loading EPG settings..."
    epg_fallback_enabled = settings.get("epg fallback enabled", "false") == "true"
    epg_fallback_countries = settings.get("epg fallback countries", "").split(",")
    epg_fallback_countries = [c.strip() for c in epg_fallback_countries if c.strip()]
    
    fallback_epg = {}
    if epg_fallback_enabled and epg_fallback_countries:
        epg_refresh_progress["current_step"] = f"Fetching fallback EPG for {', '.join(epg_fallback_countries)}..."
        logger.info(f"EPG fallback enabled for countries: {epg_fallback_countries}")
        fallback_epg = fetch_epgshare_fallback(epg_fallback_countries)
        logger.info(f"Loaded fallback EPG for {len(fallback_epg)} channels")
        epg_refresh_progress["current_step"] = f"Loaded fallback EPG for {len(fallback_epg)} channels"

    # IMPROVEMENT #8: Diagnostic counters
    epg_stats = {
        "portal_epg_count": 0,
        "fallback_epg_count": 0,
        "no_epg_count": 0,  # Channels without EPG (skipped, no dummy)
        "total_channels": 0
    }

    # Build XMLTV directly without caching old programmes (memory optimization)
    channels_xml = ET.Element("tv")
    portals = getPortals()
    programme_count = 0

    # IMPROVEMENT #3: M3U/XMLTV Alignment - Load database channels for 100% match
    # Get all enabled channels from database
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT portal, channel_id, name, custom_name, number, custom_number, 
                   genre, custom_genre, logo, custom_epg_id
            FROM channels 
            WHERE enabled = 1
        ''')
        db_channels = {}
        for row in cursor.fetchall():
            portal_id = row['portal']
            channel_id = row['channel_id']
            if portal_id not in db_channels:
                db_channels[portal_id] = {}
            db_channels[portal_id][channel_id] = {
                'name': row['custom_name'] or row['name'],
                'number': row['custom_number'] or row['number'],
                'genre': row['custom_genre'] or row['genre'],
                'logo': row['logo'],
                'custom_epg_id': row['custom_epg_id']
            }
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

    # IMPROVEMENT #5: Variant Deduplication - Track base channel names
    # Map to deduplicate HD/FHD/UHD variants
    variant_map = {}  # base_name -> {epg_id, channels: [list of variant channel_ids]}

    portal_index = 0
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            portal_index += 1
            portal_name = portals[portal]["name"]
            portal_epg_offset = int(portals[portal]["epg offset"])
            
            # Update progress - show current portal being processed
            epg_refresh_progress["current_portal"] = portal_name
            epg_refresh_progress["current_step"] = f"Starting {portal_name}..."
            epg_refresh_progress["portals_done"] = portal_index - 1  # Show as "processing X of Y"
            
            logger.info(f"Fetching EPG | Portal: {portal_name} | offset: {portal_epg_offset} |")

            # IMPROVEMENT #3 & #9: Use database channels instead of JSON config
            portal_db_channels = db_channels.get(portal, {})
            if len(portal_db_channels) == 0:
                logger.warning(f"No enabled channels in database for portal {portal_name}")
                continue

            url = portals[portal]["url"]
            macs = list(portals[portal]["macs"].keys())
            proxy = portals[portal]["proxy"]

            # OPTIMIZATION: Sort MACs by how many enabled channels they cover
            # MAC that appears in most channels' available_macs should be tried first
            try:
                conn_temp = get_db_connection()
                cursor_temp = conn_temp.cursor()
                
                mac_coverage = {}
                for mac in macs:
                    # Count how many enabled channels have this MAC in their available_macs
                    cursor_temp.execute('''
                        SELECT COUNT(*) FROM channels 
                        WHERE portal = ? AND enabled = 1 
                        AND available_macs LIKE ?
                    ''', (portal, f'%{mac}%'))
                    count = cursor_temp.fetchone()[0]
                    mac_coverage[mac] = count
                
                conn_temp.close()
                
                # Sort MACs by coverage (descending - more channels = better for EPG)
                if mac_coverage:
                    macs = sorted(macs, key=lambda m: mac_coverage.get(m, 0), reverse=True)
                    logger.info(f"Sorted MACs by channel coverage: {[(m, mac_coverage.get(m, 0)) for m in macs[:3]]}")
            except Exception as e:
                logger.warning(f"Could not sort MACs by coverage: {e}")
                # Continue with original MAC order

            # Fetch EPG only (channels already in database) - try MACs until all enabled channels have EPG
            merged_epg = {}  # channelId -> [programmes]
            
            # Get list of enabled channel IDs that need EPG
            enabled_channel_ids = set(portal_db_channels.keys())
            
            # Try MACs until we have EPG for all enabled channels (or run out of MACs)
            for mac_index, mac in enumerate(macs, 1):
                try:
                    epg_refresh_progress["current_step"] = f"{portal_name}: Trying MAC {mac_index}/{len(macs)} ({mac})"
                    token = stb.getToken(url, mac, proxy)
                    if not token:
                        logger.warning(f"MAC {mac}: Failed to get token, trying next MAC")
                        continue
                    
                    stb.getProfile(url, mac, token, proxy)
                    
                    # OPTIMIZATION: Skip getAllChannels - we already have channels in database
                    # Only fetch EPG data
                    epg_refresh_progress["current_step"] = f"{portal_name}: Fetching EPG from MAC {mac}"
                    mac_epg = stb.getEpg(url, mac, token, 24, proxy)
                    
                    # Merge EPG (only add missing channels or better data)
                    if mac_epg:
                        new_epg_count = 0
                        for ch_id, programmes in mac_epg.items():
                            # Only add if we don't have EPG for this channel yet, or if new data is better
                            if ch_id not in merged_epg or len(programmes) > len(merged_epg.get(ch_id, [])):
                                merged_epg[ch_id] = programmes
                                if ch_id in enabled_channel_ids:
                                    new_epg_count += 1
                        logger.info(f"MAC {mac}: Got EPG for {len(mac_epg)} channels ({new_epg_count} new for enabled channels)")
                    else:
                        logger.warning(f"MAC {mac}: No EPG data returned")
                    
                    # Check how many enabled channels have EPG now
                    enabled_with_epg = sum(1 for ch_id in enabled_channel_ids if ch_id in merged_epg)
                    coverage_pct = (enabled_with_epg / len(enabled_channel_ids) * 100) if enabled_channel_ids else 0
                    
                    logger.info(f"EPG coverage: {enabled_with_epg}/{len(enabled_channel_ids)} enabled channels ({coverage_pct:.1f}%)")
                    epg_refresh_progress["current_step"] = f"{portal_name}: EPG coverage {coverage_pct:.1f}% ({enabled_with_epg}/{len(enabled_channel_ids)})"
                    
                    # If we have EPG for all enabled channels, we're done
                    if enabled_with_epg == len(enabled_channel_ids):
                        logger.info(f"Successfully got EPG for all enabled channels from {mac_index} MAC(s)")
                        break
                    
                    # If still missing EPG, try next MAC
                    if enabled_with_epg < len(enabled_channel_ids):
                        logger.info(f"Still missing EPG for {len(enabled_channel_ids) - enabled_with_epg} channels, trying next MAC")
                        continue
                        
                except Exception as e:
                    logger.error(f"Error fetching EPG for MAC {mac}: {e}")
                    epg_refresh_progress["current_step"] = f"{portal_name}: MAC {mac_index}/{len(macs)} failed, trying next"
                    continue
            
            # Final coverage report
            enabled_with_epg = sum(1 for ch_id in enabled_channel_ids if ch_id in merged_epg)
            if enabled_with_epg < len(enabled_channel_ids):
                logger.warning(f"Portal {portal_name}: EPG incomplete - {enabled_with_epg}/{len(enabled_channel_ids)} enabled channels have EPG")
            else:
                logger.info(f"Portal {portal_name}: EPG complete - all {enabled_with_epg} enabled channels have EPG")
            
            logger.info(f"Portal {portal_name}: EPG for {len(merged_epg)} channels")
            
            # UPDATE DATABASE: Set custom_epg_id for channels with EPG data
            # This is needed for EPG statistics to work correctly
            try:
                conn_update = get_db_connection()
                cursor_update = conn_update.cursor()
                
                if merged_epg:
                    # Update custom_epg_id for channels that have EPG
                    for channelId in merged_epg.keys():
                        if channelId in portal_db_channels:
                            # Calculate EPG ID the same way as in XMLTV generation
                            db_data = portal_db_channels[channelId]
                            channelNumber = db_data['number'] or "0"
                            epg_id = db_data['custom_epg_id'] or channelNumber
                            
                            # Only update if epg_id is not empty
                            if epg_id and epg_id != "0":
                                cursor_update.execute('''
                                    UPDATE channels 
                                    SET custom_epg_id = ? 
                                    WHERE portal = ? AND channel_id = ?
                                ''', (epg_id, portal, channelId))
                            else:
                                # Use channel_id as fallback EPG ID
                                cursor_update.execute('''
                                    UPDATE channels 
                                    SET custom_epg_id = ? 
                                    WHERE portal = ? AND channel_id = ?
                                ''', (channelId, portal, channelId))
                
                # Clear custom_epg_id for channels that DON'T have EPG (for accurate statistics)
                # This runs even if merged_epg is empty (portal has no EPG at all)
                channels_without_epg = set(portal_db_channels.keys()) - set(merged_epg.keys())
                for channelId in channels_without_epg:
                    cursor_update.execute('''
                        UPDATE channels 
                        SET custom_epg_id = NULL 
                        WHERE portal = ? AND channel_id = ?
                    ''', (portal, channelId))
                
                conn_update.commit()
                conn_update.close()
                logger.debug(f"Updated custom_epg_id for {len(merged_epg)} channels (cleared {len(channels_without_epg)} without EPG)")
            except Exception as e:
                logger.error(f"Error updating custom_epg_id in database: {e}")
            
            epg_refresh_progress["current_step"] = f"{portal_name}: Processing {len(portal_db_channels)} enabled channels..."

            if merged_epg:
                    # OPTIMIZATION: Skip genre fetching - genres already in database
                    # No need to fetch genres again, we have them in db_channel_data
                    
                    # IMPROVEMENT #4: Only include channels that are in database (enabled)
                    processed_channels = 0
                    total_enabled = len(portal_db_channels)
                    
                    for channelId, db_channel_data in portal_db_channels.items():
                        try:
                            processed_channels += 1
                            epg_stats["total_channels"] += 1
                            
                            if processed_channels % 10 == 0:
                                epg_refresh_progress["current_step"] = f"{portal_name}: Processing ({processed_channels}/{total_enabled} channels)"
                            
                            # IMPROVEMENT #3: Use database data for channel info
                            channelName = db_channel_data['name']
                            channelNumber = db_channel_data['number'] or "0"
                            
                            # IMPROVEMENT #2: ID-based matching - Use custom_epg_id from database first
                            epgId = db_channel_data['custom_epg_id'] or channelNumber
                            
                            # IMPROVEMENT #5: Variant deduplication - normalize channel name
                            # Remove quality indicators and special unicode characters
                            base_name = re.sub(r'\s*(HD\+?|FHD|QHD|UHD|4K|8K|RAW|HEVC|ULTRA|SD|ᵘˡᵗʳᵃ|ʰᵉᵛᶜ|ᴴᴰ|ᶠʰᵈ|ʳᵃʷ|ᵁᴴᴰ|ᴴᴱⱽᶜ|4ᴷ|4ᵏ)\s*$', '', channelName, flags=re.IGNORECASE).strip()
                            
                            # Check if this is a variant of an existing channel
                            is_variant = False
                            if base_name in variant_map and base_name != channelName:
                                # This is a variant - use the same EPG ID as the base channel
                                epgId = variant_map[base_name]['epg_id']
                                variant_map[base_name]['channels'].append(channelId)
                                is_variant = True
                            else:
                                # This is the base channel or first variant
                                variant_map[base_name] = {
                                    'epg_id': epgId,
                                    'channels': [channelId]
                                }
                            
                            # IMPROVEMENT #4: Only add channel element if not a variant (avoid duplicates)
                            if not is_variant:
                                channelEle = ET.SubElement(channels_xml, "channel", id=epgId)
                                ET.SubElement(channelEle, "display-name").text = channelName
                                logo = db_channel_data.get('logo')
                                if logo:
                                    ET.SubElement(channelEle, "icon", src=logo)

                            # Get EPG data for this channel (channel metadata is already in db_channel_data)
                            channel_epg = merged_epg.get(channelId, [])
                            
                            # Skip adding programmes if this is a variant (EPG already added for base channel)
                            if is_variant:
                                continue
                            
                            if not channel_epg:
                                # Try fallback EPG if enabled
                                fallback_used = False
                                if epg_fallback_enabled and fallback_epg:
                                    # IMPROVEMENT #2: Try matching by custom_epg_id first, then channel name
                                    matched_fb_id = None
                                    
                                    # First try: Match by custom_epg_id
                                    if db_channel_data['custom_epg_id']:
                                        for fb_name, data in fallback_epg.items():
                                            if data['channel_id'] == db_channel_data['custom_epg_id']:
                                                matched_fb_id = data['channel_id']
                                                break
                                    
                                    # Second try: Match by channel name
                                    if not matched_fb_id:
                                        matched_fb_id = find_best_epg_match(channelName, fallback_epg)
                                    
                                    if matched_fb_id:
                                        fb_data = None
                                        for fb_name, data in fallback_epg.items():
                                            if data['channel_id'] == matched_fb_id:
                                                fb_data = data
                                                break
                                        
                                        if fb_data and fb_data.get('programmes'):
                                            for p in fb_data['programmes'][:50]:
                                                try:
                                                    # Filter out old programmes (older than 2 days)
                                                    if p.get('start', '') <= day_before_yesterday_str:
                                                        continue
                                                    
                                                    # IMPROVEMENT #1: Raw XML passthrough - copy entire XML element
                                                    xml_elem = p.get('xml_element')
                                                    if xml_elem is not None:
                                                        # Create new programme element with our channel ID
                                                        programmeEle = ET.SubElement(
                                                            channels_xml, "programme",
                                                            start=p['start'], stop=p['stop'], channel=epgId
                                                        )
                                                        # Copy all child elements from fallback (title, desc, category, credits, etc.)
                                                        for child in xml_elem:
                                                            # IMPROVEMENT #7: Clean (lang=) artifacts from title
                                                            if child.tag == 'title' and child.text:
                                                                cleaned_title = lang_cleanup_regex.sub('', child.text).strip()
                                                                title_elem = ET.SubElement(programmeEle, child.tag, child.attrib)
                                                                title_elem.text = cleaned_title
                                                            else:
                                                                # Copy element as-is with all attributes and text
                                                                new_child = ET.SubElement(programmeEle, child.tag, child.attrib)
                                                                new_child.text = child.text
                                                                new_child.tail = child.tail
                                                        programme_count += 1
                                                        fallback_used = True
                                                except Exception as e:
                                                    pass
                                            if fallback_used:
                                                epg_stats["fallback_epg_count"] += 1
                                                logger.debug(f"Used fallback EPG for {channelName}")
                                
                                if not fallback_used:
                                    # No EPG available - skip dummy EPG (channel will have no programmes)
                                    epg_stats["no_epg_count"] += 1
                                    # Don't create dummy EPG - just count it for statistics
                            else:
                                # Portal EPG available
                                epg_stats["portal_epg_count"] += 1
                                for p in channel_epg:
                                    try:
                                        start_ts = p.get("start_timestamp")
                                        stop_ts = p.get("stop_timestamp")
                                        if not start_ts or not stop_ts:
                                            continue
                                            
                                        start_time = datetime.utcfromtimestamp(start_ts) + timedelta(hours=portal_epg_offset)
                                        stop_time = datetime.utcfromtimestamp(stop_ts) + timedelta(hours=portal_epg_offset)
                                        start = start_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                        stop = stop_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                        
                                        if start <= day_before_yesterday_str:
                                            continue
                                            
                                        programmeEle = ET.SubElement(
                                            channels_xml, "programme", start=start, stop=stop, channel=epgId
                                        )
                                        
                                        # IMPROVEMENT #7: Clean (lang=) artifacts from title
                                        title = p.get("name", "")
                                        if title:
                                            title = lang_cleanup_regex.sub('', title).strip()
                                        ET.SubElement(programmeEle, "title").text = title
                                        
                                        desc = p.get("descr", "")
                                        if desc:
                                            ET.SubElement(programmeEle, "desc").text = desc
                                        
                                        # IMPROVEMENT #6: Portal EPG enrichment - add category
                                        # Genre is already in db_channel_data
                                        genre = db_channel_data.get('genre', '')
                                        if genre:
                                            ET.SubElement(programmeEle, "category").text = genre
                                        
                                        # Add director if available
                                        director = p.get("director", "")
                                        if director:
                                            credits_elem = ET.SubElement(programmeEle, "credits")
                                            ET.SubElement(credits_elem, "director").text = director
                                        
                                        # Add actors if available
                                        actors = p.get("actors", "")
                                        if actors:
                                            if "credits" not in [child.tag for child in programmeEle]:
                                                credits_elem = ET.SubElement(programmeEle, "credits")
                                            else:
                                                credits_elem = programmeEle.find("credits")
                                            # Split actors by comma and add each
                                            for actor in actors.split(","):
                                                actor = actor.strip()
                                                if actor:
                                                    ET.SubElement(credits_elem, "actor").text = actor
                                        
                                        programme_count += 1
                                    except Exception as e:
                                        logger.error(f"Error processing programme: {e}")
                        except Exception as e:
                            logger.error(f"Error processing channel {channelId}: {e}")
                    
                    epg_refresh_progress["current_step"] = f"{portal_name}: Completed - {programme_count} total programmes"
                    epg_refresh_progress["portals_done"] = portal_index
                    del merged_epg
                    gc.collect()
            else:
                logger.error(f"Error making XMLTV for {portal_name}, skipping")
                epg_refresh_progress["current_step"] = f"{portal_name}: Error - skipping"
                epg_refresh_progress["portals_done"] = portal_index

    # IMPROVEMENT #8: Diagnostic logging at INFO level
    logger.info(f"EPG Statistics:")
    logger.info(f"  Total channels: {epg_stats['total_channels']}")
    logger.info(f"  Portal EPG: {epg_stats['portal_epg_count']} channels")
    logger.info(f"  Fallback EPG: {epg_stats['fallback_epg_count']} channels")
    logger.info(f"  No EPG: {epg_stats['no_epg_count']} channels (skipped)")

    epg_refresh_progress["current_step"] = "Generating XMLTV file..."
    # Generate XML string without minidom (much more memory efficient)
    rough_string = ET.tostring(channels_xml, encoding="unicode")
    
    # Simple formatting without minidom
    formatted_xmltv = '<?xml version="1.0" encoding="UTF-8"?>\n' + rough_string

    epg_refresh_progress["current_step"] = f"Writing XMLTV cache ({programme_count} programmes)..."
    # Write to cache file
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(formatted_xmltv)
        logger.info(f"XMLTV cache updated with {programme_count} programmes.")
        epg_refresh_progress["current_step"] = f"XMLTV cache updated with {programme_count} programmes"
    except Exception as e:
        logger.error(f"Error writing XMLTV cache: {e}")
        epg_refresh_progress["current_step"] = f"Error writing cache: {str(e)}"

    epg_refresh_progress["current_step"] = "Finalizing..."
    # Update global cache - only track timestamp, not the data
    global last_updated
    last_updated = time.time()
    
    logger.info(f"XMLTV refresh completed - {programme_count} programmes written to file")
    logger.info(f"Memory optimization: XMLTV served from file instead of RAM")
    
    # Clean up
    del channels_xml
    del rough_string
    del fallback_epg
    gc.collect()
    
    epg_refresh_progress["current_step"] = f"Completed! {programme_count} programmes from {portal_index} portals"
    
@app.route("/xmltv", methods=["GET"])
def xmltv():
    """XMLTV EPG with support for both session-based and Basic Auth."""
    settings = getSettings()
    public_access = settings.get("public playlist access", "true") == "true"
    
    if public_access:
        # Public access enabled - no authentication required
        return _xmltv()
    else:
        # Public access disabled - check for authentication
        
        # First check if user is logged in via session (existing logic)
        if flask.session.get("authenticated"):
            return _xmltv()
        
        # If no session, try Basic Auth
        auth = request.authorization
        if auth and auth.username and auth.password:
            # Validate Basic Auth credentials
            system_username = settings.get("username", "admin")
            system_password = settings.get("password", "12345")
            
            if auth.username == system_username and auth.password == system_password:
                # Basic Auth successful
                logger.info(f"Basic Auth successful for XMLTV: {auth.username}")
                return _xmltv()
            else:
                logger.warning(f"Invalid Basic Auth credentials for XMLTV: {auth.username}")
        
        # No valid authentication - check if this is a Basic Auth request
        if auth:
            # Basic Auth was attempted but failed
            response = Response(
                'Invalid credentials\n'
                'Please check your username and password.',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC XMLTV"'}
            )
            return response
        else:
            # No Basic Auth provided - use existing session-based auth (redirect to login)
            return authorise(lambda: _xmltv())()

def _xmltv():
    """Serve XMLTV from file - refresh handled by scheduler or manual button."""
    global last_updated
    logger.info("Guide Requested")
    
    cache_file = os.path.join(log_dir, "epg.xml")
    settings = getSettings()
    
    # Check if file exists
    if os.path.exists(cache_file):
        # Serve existing file (refresh is handled by scheduler if auto-refresh enabled)
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return Response(f.read(), mimetype="text/xml")
        except Exception as e:
            logger.error(f"Error reading XMLTV cache file: {e}")
            return Response("Error reading XMLTV file", status=500, mimetype="text/plain")
    else:
        # File doesn't exist
        auto_refresh = settings.get("epg auto refresh", "manual")
        
        if auto_refresh == "manual":
            # Manual mode: Don't create file automatically - user must press Refresh button
            logger.warning("XMLTV file not found and auto-refresh is disabled. Please use 'Refresh EPG' button in dashboard.")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n<!-- EPG not available. Please click "Refresh EPG" button in the dashboard to generate EPG data. -->\n</tv>',
                mimetype="text/xml"
            )
        else:
            # Auto mode: Create file on first request (scheduler will handle future updates)
            logger.info("XMLTV cache file missing - creating initial file (auto-refresh enabled)")
            refresh_xmltv()
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return Response(f.read(), mimetype="text/xml")
            except Exception as e:
                logger.error(f"Error reading XMLTV after refresh: {e}")
                return Response("Error generating XMLTV", status=500, mimetype="text/plain")

# ============================================
# EPG Routes - with caching to prevent memory leaks
# ============================================

# EPG cache to prevent repeated API calls
_epg_cache = {
    "portal_status": None,
    "portal_status_time": 0,
    "channels": None,
    "channels_time": 0,
    "programs": None,
    "programs_time": 0
}
_EPG_CACHE_TTL = 300  # 5 minutes cache


def _clear_epg_cache():
    """Clear EPG cache."""
    global _epg_cache
    _epg_cache = {
        "portal_status": None,
        "portal_status_time": 0,
        "channels": None,
        "channels_time": 0,
        "programs": None,
        "programs_time": 0
    }


@app.route("/epg", methods=["GET"])
@authorise
def epg_page():
    """EPG status page showing portal EPG information."""
    return render_template("epg.html", settings=getSettings())


@app.route("/epg/portal-status", methods=["GET"])
@authorise
def epg_portal_status():
    """Get EPG status for all portals from database - NO portal queries."""
    global _epg_cache
    
    # First, clean up orphaned channels from deleted portals
    cleanup_orphaned_channels()
    
    # Clear cache to ensure fresh data after cleanup
    _epg_cache["portal_status"] = None
    
    try:
        # Get valid portal IDs from config
        portals = getPortals()
        valid_portal_ids = set(portals.keys())
        
        # Get portal info from database only - no API queries
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get channel counts and EPG status per portal from database
        cursor.execute('''
            SELECT 
                portal,
                portal_name,
                COUNT(*) as channel_count,
                SUM(CASE WHEN custom_epg_id IS NOT NULL AND custom_epg_id != '' THEN 1 ELSE 0 END) as epg_channel_count
            FROM channels
            WHERE enabled = 1
            GROUP BY portal, portal_name
            ORDER BY portal_name
        ''')
        
        portal_status = []
        for row in cursor.fetchall():
            # Only include portals that still exist in config
            if row['portal'] in valid_portal_ids:
                portal_info = {
                    "id": row['portal'],
                    "name": row['portal_name'] or 'Unknown',
                    "has_epg": row['epg_channel_count'] > 0,
                    "epg_url": None,  # Not needed for display
                    "epg_type": "database",
                    "channel_count": row['channel_count'],
                    "epg_channel_count": row['epg_channel_count']
                }
                portal_status.append(portal_info)
        
        conn.close()
        
        # Cache the result
        _epg_cache["portal_status"] = portal_status
        _epg_cache["portal_status_time"] = time.time()
        
        logger.info(f"Returned EPG status for {len(portal_status)} portals from database")
        return flask.jsonify(portal_status)
    except Exception as e:
        logger.error(f"Error getting portal EPG status: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/settings", methods=["GET"])
@authorise
def epg_settings():
    """Get EPG fallback settings."""
    settings = getSettings()
    return flask.jsonify({
        "epg_fallback_enabled": settings.get("epg fallback enabled", "false") == "true",
        "epg_fallback_countries": settings.get("epg fallback countries", "")
    })


@app.route("/epg/settings", methods=["POST"])
@authorise
def epg_settings_save():
    """Save EPG fallback settings."""
    try:
        data = request.json
        settings = getSettings()
        
        settings["epg fallback enabled"] = "true" if data.get("epg_fallback_enabled") else "false"
        settings["epg fallback countries"] = data.get("epg_fallback_countries", "")
        
        saveSettings(settings)
        _clear_epg_cache()
        
        return flask.jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving EPG settings: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/channels", methods=["GET"])
@authorise
def epg_channels():
    """Get all enabled channels with their EPG mapping status from database - NO portal queries."""
    global _epg_cache
    
    # Return cached data if still valid
    if _epg_cache["channels"] and (time.time() - _epg_cache["channels_time"]) < _EPG_CACHE_TTL:
        return flask.jsonify({"channels": _epg_cache["channels"]})
    
    try:
        # Get channels from database ONLY - no portal queries
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                portal, channel_id, portal_name, name, number, logo, genre,
                custom_name, custom_genre, custom_epg_id, has_portal_epg
            FROM channels
            WHERE enabled = 1
            ORDER BY portal_name, CAST(COALESCE(NULLIF(custom_number, ''), number) AS INTEGER)
        ''')
        
        channels = []
        
        for row in cursor.fetchall():
            channel_name = row['custom_name'] if row['custom_name'] else row['name']
            channel_genre = row['custom_genre'] if row['custom_genre'] else row['genre']
            epg_id = row['custom_epg_id'] if row['custom_epg_id'] else ''
            
            # Try to get has_portal_epg, default to 0 if column doesn't exist yet
            try:
                has_portal_epg = bool(row['has_portal_epg'])
            except (KeyError, IndexError):
                has_portal_epg = False
            
            # has_epg = True if custom_epg_id is set OR has portal EPG
            has_epg = bool(epg_id) or has_portal_epg
            
            channels.append({
                "portal_id": row['portal'],
                "portal_name": row['portal_name'] or '',
                "channel_id": row['channel_id'],
                "channel_name": channel_name,
                "channel_number": row['number'] or '',
                "channel_genre": channel_genre or '',
                "epg_id": epg_id,
                "has_epg": has_epg,
                "has_portal_epg": has_portal_epg,  # Now from database!
                "logo": row['logo'] or ''
            })
        
        conn.close()
        
        # Cache the result
        _epg_cache["channels"] = channels
        _epg_cache["channels_time"] = time.time()
        
        logger.info(f"Returned {len(channels)} channels for EPG page from database")
        return flask.jsonify({"channels": channels})
    except Exception as e:
        logger.error(f"Error getting EPG channels: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/fallback-channels", methods=["GET"])
@authorise
def epg_fallback_channels():
    """Get available channels from epgshare01 fallback for matching."""
    settings = getSettings()
    countries = settings.get("epg fallback countries", "").split(",")
    countries = [c.strip() for c in countries if c.strip()]
    
    if not countries:
        return flask.jsonify({"channels": [], "message": "No fallback countries configured"})
    
    try:
        fallback_data = fetch_epgshare_fallback(countries)
        channels = list(fallback_data.keys())
        return flask.jsonify({"channels": sorted(channels), "count": len(channels)})
    except Exception as e:
        logger.error(f"Error fetching fallback channels: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/apply-fallback", methods=["POST"])
@authorise
def epg_apply_fallback():
    """Apply fallback EPG ID to a channel based on name matching - uses database."""
    try:
        data = request.json
        portal_id = data.get("portal_id")
        channel_id = data.get("channel_id")
        channel_name = data.get("channel_name", "")
        fallback_name = data.get("fallback_name", "")  # Optional: specific fallback channel name
        
        if not portal_id or not channel_id:
            return flask.jsonify({"error": "Missing portal_id or channel_id"}), 400
        
        # Get fallback data
        settings = getSettings()
        countries = settings.get("epg fallback countries", "").split(",")
        countries = [c.strip() for c in countries if c.strip()]
        
        if not countries:
            return flask.jsonify({"error": "No fallback countries configured"}), 400
        
        fallback_data = fetch_epgshare_fallback(countries)
        
        # Use improved matching function
        search_name = fallback_name or channel_name
        matched_epg_id = find_best_epg_match(search_name, fallback_data)
        
        if not matched_epg_id:
            logger.warning(f"No fallback match found for '{search_name}'")
            return flask.jsonify({
                "error": f"No fallback match found for '{search_name}'", 
                "available": list(fallback_data.keys())[:20]
            }), 404
        
        # Update database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE channels 
            SET custom_epg_id = ? 
            WHERE portal = ? AND channel_id = ?
        ''', (matched_epg_id, portal_id, channel_id))
        
        conn.commit()
        conn.close()
        
        # Clear caches
        global cached_xmltv
        cached_xmltv = None
        _clear_epg_cache()
        
        logger.info(f"Applied fallback EPG ID '{matched_epg_id}' to channel '{channel_name}'")
        return flask.jsonify({"success": True, "epg_id": matched_epg_id})
    except Exception as e:
        logger.error(f"Error applying fallback: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/apply-fallback-all", methods=["POST"])
@authorise
def epg_apply_fallback_all():
    """Apply fallback EPG to all channels without portal EPG - optimized for database."""
    try:
        data = request.json
        channels = data.get("channels", [])
        
        if not channels:
            return flask.jsonify({"error": "No channels provided"}), 400
        
        # Filter to only channels without portal EPG (has_portal_epg = False)
        # This should significantly reduce the number of channels to process
        channels_without_portal_epg = [ch for ch in channels if not ch.get("has_portal_epg", False)]
        
        logger.info(f"Received {len(channels)} channels, {len(channels_without_portal_epg)} without portal EPG")
        
        # Use the filtered list for processing
        channels = channels_without_portal_epg
        
        if not channels:
            return flask.jsonify({
                "success": True,
                "matched": 0,
                "total": 0,
                "message": "No channels without portal EPG found"
            })
        
        # Increased limit since we're now only processing channels without portal EPG
        if len(channels) > 5000:
            return flask.jsonify({
                "error": f"Too many channels without portal EPG ({len(channels)}). Please apply fallback manually to specific channels."
            }), 400
        
        # Get fallback data
        settings = getSettings()
        countries = settings.get("epg fallback countries", "").split(",")
        countries = [c.strip() for c in countries if c.strip()]
        
        if not countries:
            return flask.jsonify({"error": "No fallback countries configured. Configure in EPG Fallback tab."}), 400
        
        logger.info(f"Fetching fallback EPG for countries: {countries}")
        fallback_data = fetch_epgshare_fallback(countries)
        
        if not fallback_data:
            return flask.jsonify({"error": "Failed to fetch fallback data"}), 500
        
        # Update database directly for better performance
        conn = get_db_connection()
        cursor = conn.cursor()
        
        matched_count = 0
        total_count = len(channels)
        
        for channel in channels:
            portal_id = channel.get("portal_id")
            channel_id = channel.get("channel_id")
            channel_name = channel.get("channel_name", "")
            
            if not portal_id or not channel_id:
                continue
            
            # Try to find matching channel using improved matching
            matched_epg_id = find_best_epg_match(channel_name, fallback_data)
            
            if matched_epg_id:
                # Update database
                cursor.execute('''
                    UPDATE channels 
                    SET custom_epg_id = ? 
                    WHERE portal = ? AND channel_id = ?
                ''', (matched_epg_id, portal_id, channel_id))
                
                matched_count += 1
                if matched_count % 100 == 0:
                    logger.info(f"Matched {matched_count}/{total_count} channels...")
        
        conn.commit()
        conn.close()
        
        # Clear caches
        global cached_xmltv
        cached_xmltv = None
        _clear_epg_cache()
        
        logger.info(f"Applied fallback to {matched_count}/{total_count} channels")
        return flask.jsonify({
            "success": True,
            "matched": matched_count,
            "total": total_count,
            "message": f"Applied fallback to {matched_count} out of {total_count} channels"
        })
    except Exception as e:
        logger.error(f"Error applying fallback to all: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/save-mapping", methods=["POST"])
@authorise
def epg_save_mapping():
    """Save EPG ID mapping for a channel - uses database."""
    try:
        data = request.json
        portal_id = data.get("portal_id")
        channel_id = data.get("channel_id")
        epg_id = data.get("epg_id", "")
        
        if not portal_id or not channel_id:
            return flask.jsonify({"error": "Missing portal_id or channel_id"}), 400
        
        # Update database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE channels 
            SET custom_epg_id = ? 
            WHERE portal = ? AND channel_id = ?
        ''', (epg_id, portal_id, channel_id))
        
        conn.commit()
        conn.close()
        
        # Clear caches
        global cached_xmltv
        cached_xmltv = None
        _clear_epg_cache()
        
        logger.info(f"Saved EPG mapping for channel {channel_id}: {epg_id}")
        return flask.jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving EPG mapping: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/refresh", methods=["POST"])
@authorise
def epg_refresh():
    """Force refresh EPG cache."""
    try:
        global epg_refresh_progress
        
        if epg_refresh_progress["running"]:
            return flask.jsonify({"error": "EPG refresh already in progress"}), 400
        
        _clear_epg_cache()
        global cached_xmltv
        cached_xmltv = None
        
        # Initialize progress
        portals = getPortals()
        enabled_portals = [p for p in portals.values() if p.get("enabled") == "true"]
        
        epg_refresh_progress = {
            "running": True,
            "current_portal": "",
            "current_step": "Starting...",
            "portals_done": 0,
            "portals_total": len(enabled_portals),
            "started_at": time.time()
        }
        
        # Save timestamp for manual refresh too
        settings = getSettings()
        settings["epg last refresh timestamp"] = str(int(time.time()))
        saveSettings(settings)
        
        threading.Thread(target=refresh_xmltv_with_progress, daemon=True).start()
        return flask.jsonify({"success": True, "message": "EPG refresh started"})
    except Exception as e:
        logger.error(f"Error refreshing EPG: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/refresh/progress", methods=["GET"])
@authorise
def epg_refresh_progress_status():
    """Get EPG refresh progress."""
    return flask.jsonify(epg_refresh_progress)


# ============================================
# Xtream Codes API Routes
# ============================================

@app.route("/get.php", methods=["GET"])
@app.route("/get", methods=["GET"])
@xc_auth_only
def xc_get_playlist():
    """XC API M3U playlist endpoint with optional portal filtering."""
    return xc_get_playlist_impl()


@app.route("/portal/<portal_id>/get.php", methods=["GET"])
@xc_auth_only
def xc_get_portal_playlist(portal_id):
    """Route-based XC API M3U playlist endpoint for specific portal."""
    return xc_get_playlist_impl(route_portal_id=portal_id)


def xc_get_playlist_impl(route_portal_id=None):
    """XC API M3U playlist endpoint with optional portal filtering."""
    settings = getSettings()
    if settings.get("xc api enabled") != "true":
        return "XC API is disabled", 403
    
    username = request.args.get("username")
    password = request.args.get("password")
    output = request.args.get("output", "m3u8")
    playlist_type = request.args.get("type", "m3u_plus")
    
    # NEW: Portal filtering support via portal_id parameter (ID or Name)
    portal_id_filter = request.args.get("portal_id")
    
    # If portal_id_filter is provided, try to resolve it (could be ID or Name)
    if portal_id_filter:
        portal_id_filter = resolve_portal_identifier(portal_id_filter)
    
    if not username or not password:
        return "Missing credentials", 401
    
    user_id, user = validateXCUser(username, password)
    if not user_id:
        return "Invalid credentials", 401
    
    # Generate M3U playlist with optional portal filtering
    m3u_content = generate_xc_m3u_with_portal_filter(user, portal_id_filter)
    
    return Response(m3u_content, mimetype="application/x-mpegURL")


def resolve_portal_identifier(identifier):
    """
    Resolve portal identifier - accepts both Portal ID and Portal Name.
    
    Args:
        identifier (str): Portal ID or Portal Name
        
    Returns:
        str: Portal ID (or original identifier if not found)
    """
    if not identifier:
        return None
    
    portals = getPortals()
    
    # First, check if it's a direct Portal ID match
    if identifier in portals:
        return identifier
    
    # Second, try to find by Portal Name (case-insensitive)
    identifier_lower = identifier.lower()
    for portal_id, portal in portals.items():
        portal_name = portal.get("name", "").lower()
        if portal_name == identifier_lower:
            logger.info(f"Resolved portal name '{identifier}' to portal ID '{portal_id}'")
            return portal_id
    
    # Not found - return original (will be filtered out later)
    logger.warning(f"Portal identifier '{identifier}' not found (tried ID and Name)")
    return identifier


def generate_xc_m3u_with_portal_filter(user, portal_id_filter=None):
    """
    Generate XC API M3U playlist content with optional portal filtering.
    
    Args:
        user (dict): XC API user object with allowed_portals
        portal_id_filter (str, optional): Portal ID to filter by
        
    Returns:
        str: M3U playlist content
    """
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    m3u_content = "#EXTM3U\n"
    
    # Get enabled channels from database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
               number, custom_number, custom_epg_id, logo
        FROM channels 
        WHERE enabled = 1
        ORDER BY portal, channel_id
    ''')
    db_channels = cursor.fetchall()
    conn.close()
    
    # Use external host configuration (same as main playlist)
    external_host, external_scheme = get_external_host_config()
    if external_host:
        # Use configured external host
        scheme = external_scheme or "http"
        host = external_host
    else:
        # Fallback to request headers (handles reverse proxy correctly)
        scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
        host = request.headers.get('X-Forwarded-Host', request.host)
    
    # Create a copy to avoid RuntimeError if dictionary changes during iteration
    for portal_id, portal in list(portals.items()):
        if portal.get("enabled") != "true":
            continue
        if allowed_portals and portal_id not in allowed_portals:
            continue
        
        # NEW: Portal filtering - if portal_id_filter is specified, only include that portal
        if portal_id_filter and portal_id != portal_id_filter:
            continue
        
        # Get channels for this portal from database
        portal_channels = [ch for ch in db_channels if ch['portal'] == portal_id]
        if not portal_channels:
            continue
        
        for db_channel in portal_channels:
            channel_id = str(db_channel['channel_id'])
            
            # Use custom values if available, otherwise use original values
            channel_name = db_channel['custom_name'] if db_channel['custom_name'] else (db_channel['name'] or "Unknown Channel")
            genre = db_channel['custom_genre'] if db_channel['custom_genre'] else (db_channel['genre'] or "")
            channel_number = db_channel['custom_number'] if db_channel['custom_number'] else (db_channel['number'] or "")
            epg_id = db_channel['custom_epg_id'] if db_channel['custom_epg_id'] else channel_name
            logo = db_channel['logo'] or ""
            
            # Determine group-title based on settings
            if getSettings().get("use portal names as groups", "false") == "true":
                # Use portal name as group
                group_title = portal.get("name", portal_id)
            else:
                # Use genre with optional portal prefix
                portal_prefix = portal.get("portal prefix", "").strip()
                if portal_prefix and genre:
                    group_title = f"[{portal_prefix}] {genre}"
                else:
                    group_title = genre
            
            stream_id = f"{portal_id}_{channel_id}"
            # Standard XC API URL format for maximum compatibility
            # Add .ts extension for better IPTV client compatibility
            stream_url = f"{scheme}://{host}/{request.args.get('username')}/{request.args.get('password')}/{stream_id}.ts"
            
            # Escape quotes in attributes
            def escape_quotes(text):
                return str(text).replace('"', '&quot;') if text else ""
            
            m3u_content += f'#EXTINF:-1 tvg-id="{escape_quotes(epg_id)}" tvg-name="{escape_quotes(channel_name)}" tvg-logo="{escape_quotes(logo)}" group-title="{escape_quotes(group_title)}",{channel_name}\n'
            m3u_content += f'{stream_url}\n'
    
    return m3u_content


@app.route("/player_api.php", methods=["GET"])
@xc_auth_only
def xc_api():
    """Xtream Codes API endpoint."""
    settings = getSettings()
    if settings.get("xc api enabled") != "true":
        return flask.jsonify({
            "user_info": {
                "auth": 0,
                "message": "XC API is disabled"
            }
        })
    
    username = request.args.get("username")
    password = request.args.get("password")
    action = request.args.get("action")
    
    if not username or not password:
        return flask.jsonify({
            "user_info": {
                "auth": 0,
                "message": "Missing credentials"
            }
        })
    
    user_id, user = validateXCUser(username, password)
    if not user_id:
        return flask.jsonify({
            "user_info": {
                "auth": 0,
                "message": user_id  # user_id contains error message
            }
        })
    
    # Handle different actions
    if action == "get_live_streams":
        return xc_get_live_streams(user)
    elif action == "get_live_categories":
        return xc_get_live_categories(user)
    elif action == "get_vod_streams":
        return xc_get_vod_streams(user)
    elif action == "get_series":
        return xc_get_series(user)
    elif action == "get_vod_categories":
        return xc_get_vod_categories(user)
    elif action == "get_series_categories":
        return xc_get_series_categories(user)
    elif action == "get_series_info":
        series_id = request.args.get("series_id")
        if series_id:
            return xc_get_series_info(user, series_id)
        return flask.jsonify({"info": {}, "episodes": {}})
    elif action == "get_vod_info":
        vod_id = request.args.get("vod_id")
        if vod_id:
            return xc_get_vod_info(user, vod_id)
        return flask.jsonify({"info": {}, "movie_data": {}})
    else:
        # Default: return user info
        return xc_get_user_info(user_id, user)


def xc_get_user_info(user_id, user):
    """Get XC user info."""
    active_cons = len(user.get("active_connections", {}))
    max_cons = int(user.get("max_connections", 1))
    
    expires_at = user.get("expires_at", "")
    exp_date = None
    if expires_at:
        try:
            exp_date = datetime.strptime(expires_at, "%Y-%m-%d")
        except:
            pass
    
    # Get correct host from headers (handles reverse proxy)
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.headers.get('X-Forwarded-Host', request.host)
    base_url = f"{scheme}://{host}"
    
    # Extract port
    port = "80"
    if ':' in host:
        port = host.split(':')[1]
    elif scheme == "https":
        port = "443"
    
    return flask.jsonify({
        "user_info": {
            "username": user.get("username"),
            "password": user.get("password"),
            "message": "",
            "auth": 1,
            "status": "Active",
            "exp_date": exp_date.strftime("%s") if exp_date else None,
            "is_trial": "0",
            "active_cons": str(active_cons),
            "created_at": user.get("created_at", ""),
            "max_connections": str(max_cons),
            "allowed_output_formats": ["m3u8", "ts"]
        },
        "server_info": {
            "url": base_url,
            "port": port,
            "https_port": "443" if scheme == "https" else "",
            "server_protocol": scheme,
            "rtmp_port": "",
            "timezone": "UTC",
            "timestamp_now": int(time.time()),
            "time_now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    })


def xc_get_live_categories(user):
    """Get live stream categories - only return categories with enabled channels."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    settings = getSettings()
    use_portal_names = settings.get("use portal names as groups", "false") == "true"
    
    categories = []
    categories_with_channels = set()  # Track which categories have enabled channels
    
    if use_portal_names:
        # Use portal names as categories
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT portal
            FROM channels 
            WHERE enabled = 1
            ORDER BY portal
        ''')
        db_portals = cursor.fetchall()
        conn.close()
        
        for portal_data in db_portals:
            portal_id = portal_data['portal']
            portal = portals.get(portal_id)
            
            if not portal or portal.get("enabled") != "true":
                continue
            if allowed_portals and portal_id not in allowed_portals:
                continue
            
            portal_name = portal.get("name", portal_id)
            category_key = f"portal_{portal_id}"
            
            if category_key not in categories_with_channels:
                categories_with_channels.add(category_key)
                categories.append({
                    "category_id": category_key,
                    "category_name": portal_name,
                    "parent_id": 0
                })
    else:
        # Use genres as categories (original behavior)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT portal, 
                   COALESCE(NULLIF(custom_genre, ''), NULLIF(genre, ''), 'Unknown') as genre_name
            FROM channels 
            WHERE enabled = 1
            ORDER BY portal, genre_name
        ''')
        db_genres = cursor.fetchall()
        conn.close()
        
        # Create a copy to avoid RuntimeError if dictionary changes during iteration
        for portal_id, portal in list(portals.items()):
            if portal.get("enabled") != "true":
                continue
            if allowed_portals and portal_id not in allowed_portals:
                continue
            
            # Get genres for this portal from database
            portal_genres = [g for g in db_genres if g['portal'] == portal_id]
            
            for genre_data in portal_genres:
                genre_name = genre_data['genre_name']
                category_key = f"{portal_id}_{genre_name}"
                
                if category_key not in categories_with_channels:
                    categories_with_channels.add(category_key)
                    categories.append({
                        "category_id": category_key,
                        "category_name": genre_name,
                        "parent_id": 0
                    })
    
    return flask.jsonify(categories)


def xc_get_live_streams(user):
    """Get live streams - OPTIMIZED: Fixed N+1 Query Pattern."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    settings = getSettings()
    use_portal_names = settings.get("use portal names as groups", "false") == "true"
    
    streams = []
    
    # OPTIMIZATION: Query per portal instead of loading all channels
    # This fixes the N+1 query pattern by filtering in SQL instead of Python
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create a copy to avoid RuntimeError if dictionary changes during iteration
    for portal_id, portal in list(portals.items()):
        if portal.get("enabled") != "true":
            continue
        if allowed_portals and portal_id not in allowed_portals:
            continue
        
        # OPTIMIZED: SQL-based filtering (uses idx_channels_portal index)
        cursor.execute('''
            SELECT portal, channel_id, name, custom_name, genre, custom_genre, 
                   number, custom_number, custom_epg_id, logo
            FROM channels 
            WHERE enabled = 1 AND portal = ?
            ORDER BY channel_id
        ''', (portal_id,))
        portal_channels = cursor.fetchall()
        
        if not portal_channels:
            continue
        
        for db_channel in portal_channels:
            channel_id = str(db_channel['channel_id'])
            
            # Use custom values if available, otherwise use original values
            channel_name = db_channel['custom_name'] if db_channel['custom_name'] else (db_channel['name'] or "Unknown Channel")
            genre = db_channel['custom_genre'] if db_channel['custom_genre'] else (db_channel['genre'] or "Unknown")
            channel_number = db_channel['custom_number'] if db_channel['custom_number'] else (db_channel['number'] or "")
            epg_id = db_channel['custom_epg_id'] if db_channel['custom_epg_id'] else channel_name
            logo = db_channel['logo'] or ""
            
            # Create internal stream ID
            internal_id = f"{portal_id}_{channel_id}"
            
            # XC API expects numeric stream_id - use deterministic hash
            # Python's hash() is not deterministic across sessions, so use hashlib
            import hashlib
            numeric_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
            
            # Create category_id that matches the one in xc_get_live_categories
            if use_portal_names:
                # Use portal-based category (matches get_live_categories)
                category_id = f"portal_{portal_id}"
            else:
                # Use genre-based category (original behavior)
                category_id = f"{portal_id}_{genre}"
            
            streams.append({
                "num": int(channel_number) if channel_number.isdigit() else 0,
                "name": channel_name,
                "stream_type": "live",
                "stream_id": numeric_id,
                "stream_icon": logo,
                "epg_channel_id": epg_id,
                "added": "",
                "category_id": category_id,
                "custom_sid": internal_id,  # Store real ID for reverse lookup
                "tv_archive": 0,
                "direct_source": "",
                "tv_archive_duration": 0,
                "container_extension": "ts"
            })
    
    conn.close()
    return flask.jsonify(streams)


def xc_get_vod_categories(user):
    """Get VOD categories from selected categories in vods.db."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    categories = []
    
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Get selected VOD categories
        cursor.execute('''
            SELECT vc.portal_id, vc.category_id, vc.title, vc.content_type, vc.item_count
            FROM vod_categories vc
            INNER JOIN vod_selections vs ON vc.portal_id = vs.portal_id 
                AND (vs.category_key = 'vod_' || vc.category_id OR vs.category_key = vc.content_type || '_' || vc.category_id)
            WHERE vc.content_type = 'vod' AND vs.enabled = 1
            ORDER BY vc.portal_id, vc.title
        ''')
        
        db_categories = cursor.fetchall()
        conn.close()
        
        for cat in db_categories:
            portal_id = cat['portal_id']
            
            # Check if portal is enabled and allowed
            portal = portals.get(portal_id)
            if not portal or portal.get("enabled") != "true":
                continue
            if allowed_portals and portal_id not in allowed_portals:
                continue
            
            category_key = f"{portal_id}_vod_{cat['category_id']}"
            
            categories.append({
                "category_id": category_key,
                "category_name": cat['title'],
                "parent_id": 0
            })
    except Exception as e:
        logger.error(f"Error getting VOD categories for XC API: {e}")
    
    return flask.jsonify(categories)


def xc_get_series_categories(user):
    """Get Series categories from selected categories in vods.db."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    categories = []
    
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Get selected Series categories
        cursor.execute('''
            SELECT vc.portal_id, vc.category_id, vc.title, vc.content_type, vc.item_count
            FROM vod_categories vc
            INNER JOIN vod_selections vs ON vc.portal_id = vs.portal_id 
                AND (vs.category_key = 'series_' || vc.category_id OR vs.category_key = vc.content_type || '_' || vc.category_id)
            WHERE vc.content_type = 'series' AND vs.enabled = 1
            ORDER BY vc.portal_id, vc.title
        ''')
        
        db_categories = cursor.fetchall()
        conn.close()
        
        for cat in db_categories:
            portal_id = cat['portal_id']
            
            # Check if portal is enabled and allowed
            portal = portals.get(portal_id)
            if not portal or portal.get("enabled") != "true":
                continue
            if allowed_portals and portal_id not in allowed_portals:
                continue
            
            category_key = f"{portal_id}_series_{cat['category_id']}"
            
            categories.append({
                "category_id": category_key,
                "category_name": cat['title'],
                "parent_id": 0
            })
    except Exception as e:
        logger.error(f"Error getting Series categories for XC API: {e}")
    
    return flask.jsonify(categories)


def xc_get_vod_streams(user):
    """Get VOD streams from selected categories in vods.db."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    streams = []
    
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Get VOD items from selected categories
        cursor.execute('''
            SELECT vi.portal_id, vi.category_id, vi.item_id, vi.name, vi.year, 
                   vi.description, vi.genre, vi.duration, vi.rating, vi.poster_url, vi.cmd
            FROM vod_items vi
            INNER JOIN vod_selections vs ON vi.portal_id = vs.portal_id 
                AND (vs.category_key = 'vod_' || vi.category_id OR vs.category_key = vi.content_type || '_' || vi.category_id)
            WHERE vi.content_type = 'vod' AND vs.enabled = 1
            ORDER BY vi.portal_id, vi.name
        ''')
        
        db_items = cursor.fetchall()
        conn.close()
        
        import hashlib
        
        for item in db_items:
            portal_id = item['portal_id']
            
            # Check if portal is enabled and allowed
            portal = portals.get(portal_id)
            if not portal or portal.get("enabled") != "true":
                continue
            if allowed_portals and portal_id not in allowed_portals:
                continue
            
            internal_id = f"{portal_id}_vod_{item['item_id']}"
            numeric_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
            category_key = f"{portal_id}_vod_{item['category_id']}"
            
            streams.append({
                "num": numeric_id,
                "name": item['name'],
                "stream_type": "movie",
                "stream_id": numeric_id,
                "stream_icon": item['poster_url'] or "",
                "rating": item['rating'] or "",
                "added": "",
                "category_id": category_key,
                "container_extension": "mp4",
                "custom_sid": internal_id,
                "direct_source": ""
            })
    except Exception as e:
        logger.error(f"Error getting VOD streams for XC API: {e}")
    
    return flask.jsonify(streams)


def xc_get_vod_info(user, vod_id):
    """Get VOD/Movie info for XC API.
    
    The vod_id can be either:
    - A numeric hash (from get_vod_streams response)
    - A custom_sid string (portalId_vod_itemId)
    """
    import hashlib
    
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    # Find the VOD by ID
    portal_id = None
    item_id = None
    vod_data = None
    
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Try to find by custom_sid first (string format)
        if '_vod_' in str(vod_id):
            logger.debug(f"XC API: Parsing custom VOD ID format: {vod_id}")
            parts = str(vod_id).split('_vod_')
            if len(parts) == 2:
                portal_id = parts[0]
                item_id = parts[1]
                logger.debug(f"XC API: Parsed - Portal: {portal_id}, Item: {item_id}")
        else:
            # Numeric format - search through all VODs to find matching hash
            logger.debug(f"XC API: Searching for numeric VOD ID: {vod_id}")
            numeric_id = int(vod_id)
            
            cursor.execute('''
                SELECT vi.portal_id, vi.item_id, vi.name, vi.year, 
                       vi.description, vi.genre, vi.duration, vi.rating, vi.poster_url, vi.cmd
                FROM vod_items vi
                INNER JOIN vod_selections vs ON vi.portal_id = vs.portal_id 
                    AND (vs.category_key = 'vod_' || vi.category_id OR vs.category_key = vi.content_type || '_' || vi.category_id)
                WHERE vi.content_type = 'vod' AND vs.enabled = 1
            ''')
            
            for item in cursor.fetchall():
                internal_id = f"{item['portal_id']}_vod_{item['item_id']}"
                check_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
                if check_id == numeric_id:
                    portal_id = item['portal_id']
                    item_id = item['item_id']
                    vod_data = dict(item)
                    break
        
        if not portal_id or not item_id:
            conn.close()
            logger.warning(f"XC API: VOD not found - ID: {vod_id}")
            return flask.jsonify({
                "info": {},
                "movie_data": {},
                "error": "VOD not found"
            })
        
        # Get VOD data if not already fetched
        if not vod_data:
            cursor.execute('''
                SELECT portal_id, item_id, name, year, description, genre, duration, rating, poster_url, cmd
                FROM vod_items
                WHERE portal_id = ? AND item_id = ? AND content_type = 'vod'
            ''', (portal_id, item_id))
            row = cursor.fetchone()
            if row:
                vod_data = dict(row)
        
        conn.close()
        
        if not vod_data:
            return flask.jsonify({"info": {}, "movie_data": {}, "error": "VOD not found"})
        
        portal = portals.get(portal_id)
        if not portal or portal.get("enabled") != "true":
            return flask.jsonify({"info": {}, "movie_data": {}, "error": "Portal unavailable"})
        if allowed_portals and portal_id not in allowed_portals:
            return flask.jsonify({"info": {}, "movie_data": {}, "error": "Access denied"})
        
        # Generate consistent stream ID
        internal_id = f"{portal_id}_vod_{item_id}"
        stream_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
        
        # Determine container extension from cmd
        container_ext = "mp4"  # Default
        if vod_data.get("cmd"):
            cmd_lower = vod_data["cmd"].lower()
            if ".mkv" in cmd_lower:
                container_ext = "mkv"
            elif ".avi" in cmd_lower:
                container_ext = "avi"
            elif ".ts" in cmd_lower:
                container_ext = "ts"
        
        # Build XC API compliant response
        response = {
            "info": {
                "movie_image": vod_data.get('poster_url') or "",
                "tmdb_id": "",
                "backdrop_path": [],
                "youtube_trailer": "",
                "genre": vod_data.get('genre') or "",
                "plot": vod_data.get('description') or "",
                "cast": "",
                "rating": vod_data.get('rating') or "",
                "director": "",
                "releasedate": vod_data.get('year') or "",
                "duration_secs": 0,
                "duration": vod_data.get('duration') or "",
                "video": {},
                "audio": {},
                "bitrate": 0,
                "name": vod_data.get('name') or ""
            },
            "movie_data": {
                "stream_id": stream_id,
                "name": vod_data.get('name') or "",
                "added": "",
                "category_id": "",
                "container_extension": container_ext,
                "custom_sid": internal_id,
                "direct_source": ""
            }
        }
        
        return flask.jsonify(response)
        
    except Exception as e:
        logger.error(f"VOD info error: {e}")
        return flask.jsonify({"info": {}, "movie_data": {}})


def xc_get_series(user):
    """Get Series from selected categories in vods.db."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    series_list = []
    
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Get Series items from selected categories
        cursor.execute('''
            SELECT vi.portal_id, vi.category_id, vi.item_id, vi.name, vi.year, 
                   vi.description, vi.genre, vi.rating, vi.poster_url, vi.cmd
            FROM vod_items vi
            INNER JOIN vod_selections vs ON vi.portal_id = vs.portal_id 
                AND (vs.category_key = 'series_' || vi.category_id OR vs.category_key = vi.content_type || '_' || vi.category_id)
            WHERE vi.content_type = 'series' AND vs.enabled = 1
            ORDER BY vi.portal_id, vi.name
        ''')
        
        db_items = cursor.fetchall()
        conn.close()
        
        import hashlib
        
        for item in db_items:
            portal_id = item['portal_id']
            
            # Check if portal is enabled and allowed
            portal = portals.get(portal_id)
            if not portal or portal.get("enabled") != "true":
                continue
            if allowed_portals and portal_id not in allowed_portals:
                continue
            
            internal_id = f"{portal_id}_series_{item['item_id']}"
            numeric_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
            category_key = f"{portal_id}_series_{item['category_id']}"
            
            series_list.append({
                "num": numeric_id,
                "name": item['name'],
                "series_id": numeric_id,
                "cover": item['poster_url'] or "",
                "plot": item['description'] or "",
                "cast": "",
                "director": "",
                "genre": item['genre'] or "",
                "release_date": item['year'] or "",
                "rating": item['rating'] or "",
                "category_id": category_key,
                "custom_sid": internal_id
            })
    except Exception as e:
        logger.error(f"Error getting Series for XC API: {e}")
    
    return flask.jsonify(series_list)


def generate_episode_id(portal_id, series_id, season_num, episode_num):
    """Generate consistent episode ID for XC API.
    
    Format: MD5 hash of "portalId_series_seriesId_sSeasonNum_eEpisodeNum"
    Returns: Numeric ID as string
    """
    import hashlib
    internal_id = f"{portal_id}_series_{series_id}_s{season_num}_e{episode_num}"
    return str(int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16))


def parse_episode_id(episode_id):
    """Parse episode ID back to components.
    
    Args:
        episode_id: Either custom_sid string or numeric hash
        
    Returns:
        tuple: (portal_id, series_id, season_num, episode_num) or (None, None, None, None)
    """
    if not episode_id:
        return None, None, None, None
    
    episode_str = str(episode_id).strip()
    
    # Handle custom format: portalId_series_itemId_sX_eY
    if '_series_' in episode_str and '_s' in episode_str and '_e' in episode_str:
        try:
            # Split by _series_ first
            parts = episode_str.split('_series_')
            if len(parts) != 2:
                return None, None, None, None
            
            portal_id = parts[0].strip()
            rest = parts[1].strip()
            
            # Split by _s to separate series_id from season/episode
            if '_s' not in rest:
                return None, None, None, None
            
            item_parts = rest.split('_s')
            if len(item_parts) != 2:
                return None, None, None, None
            
            series_id = item_parts[0].strip()
            season_ep = item_parts[1].strip()  # X_eY format
            
            # Split season and episode
            if '_e' not in season_ep:
                return None, None, None, None
            
            season_ep_parts = season_ep.split('_e')
            if len(season_ep_parts) != 2:
                return None, None, None, None
            
            season_num = season_ep_parts[0].strip()
            ep_part = season_ep_parts[1].strip()
            
            # Validate season and episode numbers
            if not season_num.isdigit() or not ep_part.isdigit():
                return None, None, None, None
            
            episode_num = int(ep_part)
            
            # Validate all components are non-empty
            if not portal_id or not series_id or not season_num:
                return None, None, None, None
            
            return portal_id, series_id, season_num, episode_num
            
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning(f"Error parsing episode ID '{episode_id}': {e}")
            return None, None, None, None
    
    # Handle alternative formats if needed (future extensibility)
    # Could add support for other ID formats here
    
    return None, None, None, None


def xc_get_series_info(user, series_id):
    """Get Series info with seasons and episodes for XC API.
    
    The series_id can be either:
    - A numeric hash (from get_series response)
    - A custom_sid string (portalId_series_itemId)
    """
    import hashlib
    
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    # Find the series by ID
    portal_id = None
    item_id = None
    series_data = None
    
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        
        # Try to find by custom_sid first (string format)
        if '_series_' in str(series_id):
            logger.debug(f"XC API: Parsing custom series ID format: {series_id}")
            parts = str(series_id).split('_series_')
            if len(parts) == 2:
                portal_id = parts[0]
                item_id = parts[1]
                logger.debug(f"XC API: Parsed - Portal: {portal_id}, Item: {item_id}")
        else:
            # Numeric format - search through all series to find matching hash
            logger.debug(f"XC API: Searching for numeric series ID: {series_id}")
            numeric_id = int(series_id)
            
            cursor.execute('''
                SELECT vi.portal_id, vi.item_id, vi.name, vi.year, 
                       vi.description, vi.genre, vi.rating, vi.poster_url, vi.cmd
                FROM vod_items vi
                INNER JOIN vod_selections vs ON vi.portal_id = vs.portal_id 
                    AND (vs.category_key = 'series_' || vi.category_id OR vs.category_key = vi.content_type || '_' || vi.category_id)
                WHERE vi.content_type = 'series' AND vs.enabled = 1
            ''')
            
            for item in cursor.fetchall():
                internal_id = f"{item['portal_id']}_series_{item['item_id']}"
                check_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
                if check_id == numeric_id:
                    portal_id = item['portal_id']
                    item_id = item['item_id']
                    series_data = dict(item)
                    break
        
        if not portal_id or not item_id:
            conn.close()
            return flask.jsonify({"info": {}, "episodes": {}, "error": "Series not found"})
        
        if not series_data:
            cursor.execute('''
                SELECT portal_id, item_id, name, year, description, genre, rating, poster_url, cmd
                FROM vod_items WHERE portal_id = ? AND item_id = ? AND content_type = 'series'
            ''', (portal_id, item_id))
            row = cursor.fetchone()
            if row:
                series_data = dict(row)
        
        conn.close()
        
        if not series_data:
            return flask.jsonify({"info": {}, "episodes": {}, "error": "Series data not found"})
        
        # Check portal access
        portal = portals.get(portal_id)
        if not portal or portal.get("enabled") != "true":
            return flask.jsonify({"info": {}, "episodes": {}, "error": "Portal unavailable"})
        if allowed_portals and portal_id not in allowed_portals:
            return flask.jsonify({"info": {}, "episodes": {}, "error": "Access denied"})
        
        # Get series info with episodes from portal
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy")
        
        episodes_by_season = {}
        
        # Try to get episodes from portal
        series_info = None
        working_mac = None
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if not token:
                    continue
                
                series_info = stb.getSeriesInfo(url, mac, token, item_id, proxy)
                
                if series_info and series_info.get("data"):
                    working_mac = mac
                    
                    for season_data in series_info.get("data", []):
                        season_id = season_data.get("id", "")
                        season_num = str(season_id).split(":")[1] if ":" in str(season_id) else "1"
                        episode_nums = season_data.get("series", [])
                        
                        if episode_nums:
                            episodes_by_season[season_num] = []
                            
                            for ep_num in episode_nums:
                                # Create episode entry with consistent ID generation
                                internal_ep_id = f"{portal_id}_series_{item_id}_s{season_num}_e{ep_num}"
                                ep_numeric_id = generate_episode_id(portal_id, item_id, season_num, ep_num)
                                
                                # Determine container extension from series data
                                container_ext = "mkv"  # Default to mkv for series
                                if series_data.get("cmd"):
                                    # Try to extract extension from cmd or use common video extensions
                                    cmd_lower = series_data["cmd"].lower()
                                    if ".ts" in cmd_lower:
                                        container_ext = "ts"
                                    elif ".mp4" in cmd_lower:
                                        container_ext = "mp4"
                                    elif ".avi" in cmd_lower:
                                        container_ext = "avi"
                                
                                # Build episode title - use episode number format
                                episode_title = f"Episode {ep_num}"
                                
                                # Try to get more detailed episode info if available
                                season_name = season_data.get("name", f"Season {season_num}")
                                
                                episodes_by_season[season_num].append({
                                    "id": str(ep_numeric_id),  # String format for compatibility
                                    "episode_num": int(ep_num),
                                    "title": episode_title,
                                    "container_extension": container_ext,
                                    "info": {
                                        "name": episode_title,
                                        "season": int(season_num),
                                        "episode": int(ep_num),
                                        "duration": season_data.get("time", ""),
                                        "plot": season_data.get("description", ""),
                                        "rating": series_data.get("rating", ""),
                                        "genre": series_data.get("genre", ""),
                                        "movie_image": series_data.get("poster_url", ""),
                                        "duration_secs": 0,
                                        "bitrate": 0,
                                        "releasedate": series_data.get("year", ""),
                                        "air_date": ""
                                    },
                                    "custom_sid": internal_ep_id,
                                    "added": "",
                                    "season": int(season_num),
                                    "direct_source": ""
                                })
                    
                    break  # Got episodes, stop trying MACs
                    
            except Exception as e:
                logger.debug(f"Series info MAC error: {e}")
                continue
        
        internal_id = f"{portal_id}_series_{item_id}"
        numeric_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
        
        if not episodes_by_season:
            # Still return series info even if no episodes found
            response = {
                "info": {
                    "name": series_data.get("name", ""),
                    "cover": series_data.get("poster_url", ""),
                    "plot": series_data.get("description", ""),
                    "cast": "",
                    "director": "",
                    "genre": series_data.get("genre", ""),
                    "release_date": series_data.get("year", ""),
                    "rating": series_data.get("rating", ""),
                    "series_id": numeric_id,
                    "category_id": series_data.get("category_id", ""),
                    "backdrop_path": series_data.get("poster_url", ""),
                    "tmdb_id": "",
                    "last_modified": "",
                    "episode_run_time": "",
                    "youtube_trailer": "",
                    "seasons_count": 0,
                    "episodes_count": 0
                },
                "episodes": {},
                "seasons": [],
                "error": "No episodes available from portal"
            }
            return flask.jsonify(response)
        
        # Extract additional metadata from series info if available
        cast = ""
        director = ""
        if episodes_by_season:
            # Try to get cast/director from first season data
            for season_data in series_info.get("data", []):
                if season_data.get("actors"):
                    cast = season_data["actors"]
                if season_data.get("director"):
                    director = season_data["director"]
                break
        
        # Calculate total episodes count
        total_episodes = sum(len(eps) for eps in episodes_by_season.values())
        
        # Sort episodes by season number (ascending) for proper display in IPTV apps
        sorted_seasons = sorted(episodes_by_season.keys(), key=lambda x: int(x))
        sorted_episodes = {str(s): episodes_by_season[s] for s in sorted_seasons}
        
        # Build seasons array with proper structure for XC API
        seasons_array = []
        for season_key in sorted_seasons:
            season_eps = episodes_by_season[season_key]
            seasons_array.append({
                "season_number": int(season_key),
                "name": f"Season {season_key}",
                "episode_count": len(season_eps),
                "air_date": series_data.get("year", ""),
                "cover": series_data.get("poster_url", ""),
                "cover_big": series_data.get("poster_url", "")
            })
        
        response = {
            "info": {
                "name": series_data.get("name", ""),
                "cover": series_data.get("poster_url", ""),
                "plot": series_data.get("description", ""),
                "cast": cast,
                "director": director,
                "genre": series_data.get("genre", ""),
                "release_date": series_data.get("year", ""),
                "rating": series_data.get("rating", ""),
                "series_id": numeric_id,
                "category_id": series_data.get("category_id", ""),
                "backdrop_path": series_data.get("poster_url", ""),
                "tmdb_id": "",
                "last_modified": "",
                "episode_run_time": "",
                "youtube_trailer": "",
                "seasons_count": len(episodes_by_season),
                "episodes_count": total_episodes
            },
            "episodes": sorted_episodes,
            "seasons": seasons_array
        }
        
        logger.debug(f"Series: {series_data.get('name')} - {len(sorted_seasons)} seasons, {total_episodes} eps")
        
        return flask.jsonify(response)
        
    except Exception as e:
        logger.error(f"Series info error: {e}")
        return flask.jsonify({"info": {}, "episodes": {}})


@app.route("/xc/<username>/<password>/", methods=["GET"])
@app.route("/<username>/<password>/", methods=["GET"])
@xc_auth_only
def xc_base(username, password):
    """XC API base endpoint - redirect to player_api.php."""
    # Block access to data directory
    if username == "data" or password == "data":
        return "Access denied", 403
    return redirect(f"/player_api.php?username={username}&password={password}", code=302)


@app.route("/live/<username>/<password>/<stream_id>", methods=["GET"])
@app.route("/live/<username>/<password>/<stream_id>.<extension>", methods=["GET"])
@app.route("/xc/<username>/<password>/<stream_id>", methods=["GET"])
@app.route("/xc/<username>/<password>/<stream_id>.<extension>", methods=["GET"])
@app.route("/<username>/<password>/<stream_id>", methods=["GET"])
@app.route("/<username>/<password>/<stream_id>.<extension>", methods=["GET"])
@xc_auth_only
def xc_stream(username, password, stream_id, extension=None):
    """XC API stream endpoint."""
    # Block access to data directory and other system paths
    if username == "data" or "MacReplayXC.json" in str(stream_id) or str(stream_id).startswith("data/"):
        return "Access denied", 403
    settings = getSettings()
    if settings.get("xc api enabled") != "true":
        return flask.jsonify({
            "user_info": {
                "auth": 0,
                "message": "XC API is disabled"
            }
        }), 403
    
    user_id, user = validateXCUser(username, password)
    if not user_id:
        return flask.jsonify({
            "user_info": {
                "auth": 0,
                "message": user  # user contains error message
            }
        }), 401
    
    # Parse stream_id - can be either "portalId_channelId" or numeric hash
    if '_' in str(stream_id):
        # String format: portalId_channelId
        try:
            portal_id, channel_id = str(stream_id).rsplit('_', 1)
        except:
            return "Invalid stream ID", 400
    else:
        if not str(stream_id).isdigit():
            return "Invalid stream ID", 400
            
        # Numeric format: need to find the matching channel
        # This is inefficient but necessary for XC API compatibility
        numeric_id = int(stream_id)
        portals = getPortals()
        found = False
        
        import hashlib
        # Create a copy to avoid RuntimeError if dictionary changes during iteration
        for pid, portal in list(portals.items()):
            if portal.get("enabled") != "true":
                continue
            enabled_channels = portal.get("enabled channels", [])
            for cid in enabled_channels:
                internal_id = f"{pid}_{cid}"
                check_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
                if check_id == numeric_id:
                    portal_id = pid
                    channel_id = cid
                    found = True
                    break
            if found:
                break
        
        if not found:
            return "Stream not found", 404
    
    # Check if user has access to this portal
    allowed_portals = user.get("allowed_portals", [])
    if allowed_portals and portal_id not in allowed_portals:
        return "Access denied to this portal", 403
    
    # Generate device ID from user agent + IP
    device_id = f"{get_client_ip(request)}_{request.headers.get('User-Agent', 'unknown')}"
    device_id = str(hash(device_id))
    
    can_connect, message = checkXCConnectionLimit(user_id, device_id)
    if not can_connect:
        return message, 429
    
    registerXCConnection(user_id, device_id, portal_id, channel_id, get_client_ip(request))
    
    try:
        response = stream_channel(portal_id, channel_id, xc_user=username)
        
        if hasattr(response, 'response') and hasattr(response.response, '__iter__'):
            original_iter = response.response
            
            def cleanup_wrapper():
                try:
                    for chunk in original_iter:
                        yield chunk
                finally:
                    unregisterXCConnection(user_id, device_id)
            
            response.response = cleanup_wrapper()
        
        return response
    except Exception as e:
        unregisterXCConnection(user_id, device_id)
        logger.error(f"Stream error: {username} - {e}")
        raise


def test_vod_stream_quick(stream_url, proxy=None):
    """Quick test if VOD stream is accessible (without consuming the full token).
    
    Returns True if stream is accessible, False otherwise.
    Uses Range header to only fetch first few bytes.
    """
    import requests
    
    try:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        headers = {
            "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
            "Range": "bytes=0-1023"  # Only request first 1KB
        }
        
        response = requests.get(
            stream_url, 
            headers=headers, 
            proxies=proxies, 
            timeout=10,
            stream=True
        )
        
        # 200 or 206 (Partial Content) means success
        if response.status_code in [200, 206]:
            chunk = next(response.iter_content(chunk_size=1024), None)
            response.close()
            return chunk and len(chunk) > 0
        
        return False
        
    except Exception as e:
        logger.debug(f"Stream test error: {e}")
        return False


def get_vod_stream_settings():
    """Get VOD streaming settings from database."""
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM vod_settings')
        settings = {row['key']: row['value'] for row in cursor.fetchall()}
        conn.close()
        return settings
    except:
        return {'stream_type': 'ffmpeg', 'mac_rotation': 'true'}


def ffmpeg_vod_stream(stream_url, proxy=None):
    """Stream VOD through FFmpeg for better compatibility."""
    
    # Build FFmpeg command
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
    ]
    
    if proxy:
        ffmpeg_cmd.extend(["-http_proxy", proxy])
    
    ffmpeg_cmd.extend([
        "-i", stream_url,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-f", "mpegts",
        "-mpegts_flags", "resend_headers",
        "pipe:1"
    ])
    
    def generate():
        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=65536
            )
            
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
                
        except GeneratorExit:
            logger.info("VOD FFmpeg: Client disconnected")
        except Exception as e:
            logger.error(f"VOD FFmpeg stream error: {e}")
        finally:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    process.kill()
                logger.debug("VOD FFmpeg: Process terminated")
    
    return Response(
        generate(),
        mimetype="video/mp2t",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        }
    )


def proxy_vod_stream(stream_url, proxy=None):
    """Proxy a VOD stream through our server.
    
    This is needed for IPTV apps that don't follow HTTP redirects properly.
    """
    import requests
    
    # Check if this is a HEAD request (iOS apps often do HEAD first)
    is_head_request = request.method == 'HEAD'
    
    proxies = {"http": proxy, "https": proxy} if proxy else None
    req_headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
    }
    
    # Determine content type from URL
    content_type = "video/mp4"
    if ".mkv" in stream_url.lower():
        content_type = "video/x-matroska"
    elif ".ts" in stream_url.lower():
        content_type = "video/mp2t"
    elif ".avi" in stream_url.lower():
        content_type = "video/x-msvideo"
    
    # Build response headers - don't set Content-Length for streaming
    resp_headers = {
        "Content-Disposition": "inline",
        "Cache-Control": "no-cache",
        "Access-Control-Allow-Origin": "*",
    }
    
    # For HEAD requests, try to get content info
    if is_head_request:
        try:
            head_resp = requests.head(stream_url, headers=req_headers, proxies=proxies, 
                                      timeout=10, allow_redirects=True)
            if head_resp.headers.get('Content-Length'):
                resp_headers["Content-Length"] = head_resp.headers.get('Content-Length')
            if head_resp.headers.get('Content-Type'):
                content_type = head_resp.headers.get('Content-Type')
        except:
            pass
        
        logger.debug(f"VOD proxy: Responding to HEAD request")
        return Response('', status=200, mimetype=content_type, headers=resp_headers)
    
    # For GET requests, stream the content
    def generate():
        try:
            with requests.get(stream_url, headers=req_headers, proxies=proxies, 
                            stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
        except GeneratorExit:
            logger.debug("VOD proxy: Client disconnected")
        except Exception as e:
            logger.error(f"VOD proxy stream error: {e}")
    
    return Response(
        generate(),
        mimetype=content_type,
        headers=resp_headers
    )


@app.route("/movie/<username>/<password>/<stream_id>", methods=["GET", "HEAD"])
@app.route("/movie/<username>/<password>/<stream_id>.<extension>", methods=["GET", "HEAD"])
@xc_auth_only
def xc_movie_stream(username, password, stream_id, extension=None):
    """XC API movie/VOD stream endpoint."""
    import hashlib
    
    settings = getSettings()
    if settings.get("xc api enabled") != "true":
        return flask.jsonify({"user_info": {"auth": 0, "message": "XC API disabled"}}), 403
    
    user_id, user = validateXCUser(username, password)
    if not user_id:
        return flask.jsonify({"user_info": {"auth": 0, "message": user}}), 401
    
    # Parse stream_id to find the VOD
    portal_id = None
    item_id = None
    
    if '_vod_' in str(stream_id):
        parts = str(stream_id).split('_vod_')
        if len(parts) == 2:
            portal_id = parts[0]
            item_id = parts[1]
    elif str(stream_id).isdigit():
        # Numeric format - search through all VODs
        numeric_id = int(stream_id)
        portals = getPortals()
        allowed_portals = user.get("allowed_portals", [])
        
        try:
            conn = get_vod_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT vi.portal_id, vi.item_id FROM vod_items vi
                INNER JOIN vod_selections vs ON vi.portal_id = vs.portal_id 
                    AND (vs.category_key = 'vod_' || vi.category_id OR vs.category_key = vi.content_type || '_' || vi.category_id)
                WHERE vi.content_type = 'vod' AND vs.enabled = 1
            ''')
            
            for item in cursor.fetchall():
                p_id = item['portal_id']
                i_id = item['item_id']
                
                portal = portals.get(p_id)
                if not portal or portal.get("enabled") != "true":
                    continue
                if allowed_portals and p_id not in allowed_portals:
                    continue
                
                internal_id = f"{p_id}_vod_{i_id}"
                check_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
                if check_id == numeric_id:
                    portal_id = p_id
                    item_id = i_id
                    break
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error finding VOD: {e}")
            return flask.jsonify({
                "error": "VOD not found",
                "details": str(e)
            }), 404
    else:
        logger.error(f"XC API: Invalid VOD ID format: {stream_id}")
        return flask.jsonify({
            "error": "Invalid VOD ID format",
            "details": f"Could not parse VOD ID: {stream_id}"
        }), 400
    
    if not portal_id or not item_id:
        logger.error(f"XC API: VOD not found - stream_id: {stream_id}")
        return flask.jsonify({
            "error": "VOD not found",
            "details": f"Could not find VOD with ID: {stream_id}"
        }), 404
    
    # Get the stream URL for this VOD
    portals = getPortals()
    portal = portals.get(portal_id)
    if not portal:
        logger.error(f"XC API: Portal {portal_id} not found")
        return flask.jsonify({
            "error": "Portal not found",
            "details": f"Portal {portal_id} is not configured"
        }), 404
    
    url = portal.get("url")
    macs = list(portal.get("macs", {}).keys())
    proxy = portal.get("proxy")
    
    if not macs:
        logger.error(f"XC API: No MACs configured for portal {portal_id}")
        return flask.jsonify({
            "error": "No MACs configured",
            "details": f"Portal {portal_id} has no MAC addresses"
        }), 500
    
    # Get the VOD cmd and cached working_macs from database
    cached_mac = None
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT cmd, working_macs FROM vod_items 
            WHERE portal_id = ? AND item_id = ? AND content_type = 'vod'
        ''', (portal_id, item_id))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            logger.warning(f"VOD: {item_id} not in DB")
            return flask.jsonify({"error": "VOD data not found"}), 404
        
        vod_cmd = row['cmd']
        if row['working_macs']:
            cached_mac = row['working_macs'].split(',')[0]
    except Exception as e:
        logger.error(f"VOD DB error: {e}")
        return flask.jsonify({"error": "Database error"}), 500
    
    # Sort MACs to try cached MAC first
    if cached_mac and cached_mac in macs:
        macs = [cached_mac] + [m for m in macs if m != cached_mac]
    
    failed_macs = []
    
    for mac_index, mac in enumerate(macs, 1):
        try:
            token = stb.getToken(url, mac, proxy)
            if not token:
                failed_macs.append({"mac": mac[:15] + "...", "reason": "No token"})
                continue
            
            link = stb.getVodLink(url, mac, token, vod_cmd, proxy)
            if not link or not link.startswith(('http://', 'https://')):
                failed_macs.append({"mac": mac[:15] + "...", "reason": "No link"})
                continue
            
            # Test stream accessibility
            if not test_vod_stream_quick(link, proxy):
                failed_macs.append({"mac": mac[:15] + "...", "reason": "458/403"})
                continue
            
            logger.info(f"VOD: {item_id} → MAC {mac_index}/{len(macs)} OK")
            
            # Cache working MAC
            try:
                cache_conn = get_vod_db_connection()
                cache_cursor = cache_conn.cursor()
                cache_cursor.execute('UPDATE vod_items SET working_macs = ? WHERE portal_id = ? AND item_id = ? AND content_type = ?', 
                    (mac, portal_id, item_id, 'vod'))
                cache_conn.commit()
                cache_conn.close()
            except:
                pass
            
            # Get fresh link for playback
            fresh_link = stb.getVodLink(url, mac, token, vod_cmd, proxy) or link
            
            # Check VOD settings for stream type
            vod_settings = get_vod_stream_settings()
            stream_type = vod_settings.get('stream_type', 'ffmpeg')
            settings = getSettings()
            
            if stream_type == 'ffmpeg':
                return ffmpeg_vod_stream(fresh_link, proxy)
            elif settings.get("xc vod proxy", "false") == "true":
                return proxy_vod_stream(fresh_link, proxy)
            else:
                return redirect(fresh_link, code=302)
                    
        except Exception as e:
            failed_macs.append({"mac": mac[:15] + "...", "reason": str(e)[:30]})
            continue
    
    # All MACs failed
    logger.warning(f"VOD: {item_id} FAILED - {len(failed_macs)} MACs tried")
    return flask.jsonify({"error": "Stream not available", "failed_macs": failed_macs}), 500


@app.route("/series/<username>/<password>/<stream_id>", methods=["GET", "HEAD"])
@app.route("/series/<username>/<password>/<stream_id>.<extension>", methods=["GET", "HEAD"])
@xc_auth_only
def xc_series_stream(username, password, stream_id, extension=None):
    """XC API series stream endpoint for episodes."""
    import hashlib
    
    settings = getSettings()
    if settings.get("xc api enabled") != "true":
        return flask.jsonify({"user_info": {"auth": 0, "message": "XC API disabled"}}), 403
    
    user_id, user = validateXCUser(username, password)
    if not user_id:
        return flask.jsonify({"user_info": {"auth": 0, "message": user}}), 401
    
    # Parse stream_id to find the episode
    portal_id = None
    series_id = None
    season_num = None
    episode_num = None
    
    portal_id, series_id, season_num, episode_num = parse_episode_id(stream_id)
    
    if not (portal_id and series_id and season_num and episode_num) and str(stream_id).isdigit():
        # Numeric format - search through all episodes
        numeric_id = int(stream_id)
        portals = getPortals()
        allowed_portals = user.get("allowed_portals", [])
        
        try:
            conn = get_vod_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT vi.portal_id, vi.item_id FROM vod_items vi
                INNER JOIN vod_selections vs ON vi.portal_id = vs.portal_id 
                    AND (vs.category_key = 'series_' || vi.category_id OR vs.category_key = vi.content_type || '_' || vi.category_id)
                WHERE vi.content_type = 'series' AND vs.enabled = 1
            ''')
            
            found = False
            for item in cursor.fetchall():
                p_id = item['portal_id']
                i_id = item['item_id']
                
                portal = portals.get(p_id)
                if not portal or portal.get("enabled") != "true":
                    continue
                if allowed_portals and p_id not in allowed_portals:
                    continue
                
                url = portal.get("url")
                macs = list(portal.get("macs", {}).keys())
                proxy = portal.get("proxy")
                
                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        if not token:
                            continue
                        
                        series_info = stb.getSeriesInfo(url, mac, token, i_id, proxy)
                        if series_info and series_info.get("data"):
                            for season_data in series_info.get("data", []):
                                s_id = season_data.get("id", "")
                                s_num = str(s_id).split(":")[1] if ":" in str(s_id) else "1"
                                
                                for ep_num in season_data.get("series", []):
                                    check_id = int(generate_episode_id(p_id, i_id, s_num, ep_num))
                                    if check_id == numeric_id:
                                        portal_id, series_id, season_num, episode_num = p_id, i_id, s_num, ep_num
                                        found = True
                                        break
                                if found:
                                    break
                        if found:
                            break
                    except:
                        continue
                    if found:
                        break
                if found:
                    break
            conn.close()
        except Exception as e:
            logger.error(f"Series search error: {e}")
            return "Episode not found", 404
    elif not (portal_id and series_id and season_num and episode_num):
        return "Invalid episode ID", 400
    
    if not portal_id or not series_id or episode_num is None:
        return flask.jsonify({"error": "Episode not found"}), 404
    
    portals = getPortals()
    portal = portals.get(portal_id)
    if not portal:
        return flask.jsonify({"error": "Portal not found"}), 404
    
    url = portal.get("url")
    macs = list(portal.get("macs", {}).keys())
    proxy = portal.get("proxy")
    
    if not macs:
        return flask.jsonify({"error": "No MACs configured"}), 500
    
    # Get cached working MAC from database
    cached_mac = None
    try:
        conn = get_vod_db_connection()
        cursor = conn.cursor()
        base_id = str(series_id).split(':')[0] if ':' in str(series_id) else str(series_id)
        
        cursor.execute('SELECT working_macs FROM vod_items WHERE portal_id = ? AND item_id LIKE ? AND content_type = ?', 
            (portal_id, f"%{base_id}%", 'series'))
        row = cursor.fetchone()
        conn.close()
        
        if row and row['working_macs']:
            cached_mac = row['working_macs'].split(',')[0]
    except:
        pass
    
    # Sort MACs to try cached MAC first
    if cached_mac and cached_mac in macs:
        macs = [cached_mac] + [m for m in macs if m != cached_mac]
    
    failed_macs = []
    
    for mac_index, mac in enumerate(macs, 1):
        try:
            token = stb.getToken(url, mac, proxy)
            if not token:
                failed_macs.append({"mac": mac[:15] + "...", "reason": "No token"})
                continue
            
            # Build series cmd (Base64-encoded JSON)
            import base64
            import json as json_module
            
            base_series_id = str(series_id).split(':')[0] if ':' in str(series_id) else str(series_id)
            cmd_data = {"series_id": base_series_id, "season_num": int(season_num), "type": "series"}
            current_cmd = base64.b64encode(json_module.dumps(cmd_data).encode()).decode()
            
            link = stb.getSeriesLink(url, mac, token, current_cmd, episode_num, season_num, episode_num, proxy)
            if not link or not link.startswith(('http://', 'https://')):
                failed_macs.append({"mac": mac[:15] + "...", "reason": "No link"})
                continue
            
            # Test stream accessibility
            if not test_vod_stream_quick(link, proxy):
                failed_macs.append({"mac": mac[:15] + "...", "reason": "458/403"})
                continue
            
            logger.info(f"Series: S{season_num}E{episode_num} → MAC {mac_index}/{len(macs)} OK")
            
            # Cache working MAC
            try:
                cache_conn = get_vod_db_connection()
                cache_cursor = cache_conn.cursor()
                cache_cursor.execute('UPDATE vod_items SET working_macs = ? WHERE portal_id = ? AND item_id LIKE ? AND content_type = ?', 
                    (mac, portal_id, f"%{base_series_id}%", 'series'))
                cache_conn.commit()
                cache_conn.close()
            except:
                pass
            
            # Get fresh link for playback
            fresh_link = stb.getSeriesLink(url, mac, token, current_cmd, episode_num, season_num, episode_num, proxy) or link
            
            # Check VOD settings for stream type
            vod_settings = get_vod_stream_settings()
            stream_type = vod_settings.get('stream_type', 'ffmpeg')
            
            if stream_type == 'ffmpeg':
                return ffmpeg_vod_stream(fresh_link, proxy)
            elif settings.get("xc vod proxy", "false") == "true":
                return proxy_vod_stream(fresh_link, proxy)
            else:
                return redirect(fresh_link, code=302)
                    
        except Exception as e:
            failed_macs.append({"mac": mac[:15] + "...", "reason": str(e)[:30]})
            continue
    
    # All MACs failed
    logger.warning(f"Series: S{season_num}E{episode_num} FAILED - {len(failed_macs)} MACs tried")
    return flask.jsonify({"error": "Stream not available", "failed_macs": failed_macs}), 500


@app.route("/xmltv.php", methods=["GET"])
@xc_auth_only
def xc_xmltv():
    """XC API XMLTV endpoint - serves from file, respects auto-refresh settings."""
    global last_updated
    
    cache_file = os.path.join(log_dir, "epg.xml")
    settings = getSettings()
    
    # Check if file exists
    if os.path.exists(cache_file):
        # Check auto-refresh setting
        auto_refresh = settings.get("epg auto refresh", "manual")
        
        if auto_refresh == "manual":
            # Manual mode: Always serve existing file
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return Response(f.read(), mimetype="text/xml")
            except Exception as e:
                logger.error(f"Error reading XMLTV cache file: {e}")
                return Response("Error reading XMLTV file", status=500, mimetype="text/plain")
        else:
            # Auto-refresh enabled: Check interval
            try:
                refresh_days = int(settings.get("epg refresh interval days", "1"))
                max_age = refresh_days * 86400
                file_age = time.time() - os.path.getmtime(cache_file)
                
                if file_age < max_age:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return Response(f.read(), mimetype="text/xml")
                else:
                    refresh_xmltv()
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return Response(f.read(), mimetype="text/xml")
            except Exception as e:
                logger.error(f"Error checking EPG file age: {e}")
                return Response("Error processing XMLTV", status=500, mimetype="text/plain")
    else:
        # File doesn't exist
        auto_refresh = settings.get("epg auto refresh", "manual")
        
        if auto_refresh == "manual":
            # Manual mode: Don't create file - return empty EPG
            logger.warning("XMLTV file not found and auto-refresh is disabled")
            return Response(
                '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n<!-- EPG not available -->\n</tv>',
                mimetype="text/xml"
            )
        else:
            # Auto mode: Create file
            refresh_xmltv()
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return Response(f.read(), mimetype="text/xml")
            except Exception as e:
                logger.error(f"Error reading XMLTV after refresh: {e}")
                return Response("Error generating XMLTV", status=500, mimetype="text/plain")


def stream_channel(portalId, channelId, xc_user=None):
    """Internal function to stream a channel without authentication."""
    def streamData():
        def occupy():
            with occupied_lock:
                occupied.setdefault(portalId, [])
                stream_info = {
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
                if xc_user:
                    stream_info["xc_user"] = xc_user
                occupied.get(portalId, []).append(stream_info)
            logger.info("Occupied Portal({}):MAC({}):User({})".format(portalId, mac, xc_user or "Direct"))

        def unoccupy(ffmpeg_returncode=None):
            stream_info = {
                "mac": mac,
                "channel id": channelId,
                "channel name": channelName,
                "client": ip,
                "portal name": portalName,
                "start time": startTime,
            }
            if xc_user:
                stream_info["xc_user"] = xc_user
            try:
                with occupied_lock:
                    occupied.get(portalId, []).remove(stream_info)
            except ValueError:
                pass  # Already removed
            logger.info("Unoccupied Portal({}):MAC({}):User({})".format(portalId, mac, xc_user or "Direct"))
            
            # Update MAC score based on stream duration AND FFmpeg exit code (thread-safe)
            try:
                import time
                stream_duration = time.time() - startTime
                
                # Determine success/failure based on FFmpeg exit code or duration
                if ffmpeg_returncode is not None:
                    # Use FFmpeg exit code for accurate detection
                    is_success = (ffmpeg_returncode == 0)
                else:
                    # Fallback: Use duration-based detection (for non-FFmpeg modes)
                    is_success = (stream_duration >= 5)
                
                # Update score using thread-safe function
                update_mac_score_in_db(portalId, channelId, mac, is_success, stream_duration)
                
            except Exception as e:
                logger.error(f"[SCORE UPDATE] Error updating score: {e}")

        try:
            startTime = datetime.now(timezone.utc).timestamp()
            occupy()
            with subprocess.Popen(
                ffmpegcmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as ffmpeg_sp:
                bytes_read = 0
                ffmpeg_returncode = None
                while True:
                    chunk = ffmpeg_sp.stdout.read(1024)
                    if len(chunk) == 0:
                        ffmpeg_returncode = ffmpeg_sp.poll()
                        # Log stderr output to see why ffmpeg closed (filter out build/config info)
                        stderr_output = ffmpeg_sp.stderr.read().decode('utf-8', errors='ignore')
                        if stderr_output:
                            # Filter out FFmpeg build/config spam (but keep version)
                            lines = stderr_output.split('\n')
                            filtered_lines = [l for l in lines if not any(skip in l.lower() for skip in 
                                ["configuration:", "built with", "lib"])]
                            filtered_output = '\n'.join(filtered_lines).strip()
                            if filtered_output:
                                logger.warning(f"[FFMPEG STDERR] {filtered_output[:500]}")
                        
                        if ffmpeg_returncode != 0:
                            logger.info("Ffmpeg closed with error({}). Bytes read: {}. Moving MAC({}) for Portal({})".format(ffmpeg_returncode, bytes_read, mac, portalName))
                            moveMac(portalId, mac)
                        else:
                            logger.info("Ffmpeg closed normally (exit 0). Bytes read: {}. MAC({}) for Portal({})".format(bytes_read, mac, portalName))
                        break
                    bytes_read += len(chunk)
                    yield chunk
        except Exception as e:
            logger.error(f"Exception in streamData: {e}")
        finally:
            unoccupy(ffmpeg_returncode)
            ffmpeg_sp.kill()

    def test_stream_with_ffprobe(test_link, proxy, mac=None, log_prefix="[FFPROBE]"):
        """
        Test stream with ffprobe and return (success, duration).
        Centralized function to avoid code duplication.
        """
        timeout = int(getSettings()["ffmpeg timeout"]) * int(1000000)
        user_agent = getSettings().get("user agent", "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3")
        ffprobe_params_str = getSettings().get("ffprobe params", "-analyzeduration 500000 -probesize 100000")
        ffprobe_params = ffprobe_params_str.split() if ffprobe_params_str.strip() else []
        
        ffprobecmd = [ffprobe_path] + ffprobe_params + ["-user_agent", user_agent, "-timeout", str(timeout), "-i", test_link]
        if proxy:
            ffprobecmd.insert(1, "-http_proxy")
            ffprobecmd.insert(2, proxy)
        
        import time
        ffprobe_start = time.time()
        try:
            with subprocess.Popen(
                ffprobecmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            ) as ffprobe_sb:
                ffprobe_sb.communicate(timeout=int(getSettings()["ffmpeg timeout"]))
                ffprobe_duration = time.time() - ffprobe_start
                
                if ffprobe_sb.returncode == 0:
                    mac_info = f"MAC {mac}" if mac else "Stream"
                    logger.info(f"{log_prefix} ✓ {mac_info} works! (ffprobe: {ffprobe_duration:.2f}s)")
                    return (True, ffprobe_duration)
                else:
                    mac_info = f"MAC {mac}" if mac else "Stream"
                    logger.warning(f"{log_prefix} ✗ {mac_info} failed (ffprobe: {ffprobe_duration:.2f}s, returncode: {ffprobe_sb.returncode})")
                    return (False, ffprobe_duration)
        except subprocess.TimeoutExpired:
            ffprobe_duration = time.time() - ffprobe_start
            mac_info = f"MAC {mac}" if mac else "Stream"
            logger.warning(f"{log_prefix} ✗ {mac_info} timeout (ffprobe: {ffprobe_duration:.2f}s)")
            return (False, ffprobe_duration)
        except Exception as e:
            ffprobe_duration = time.time() - ffprobe_start
            mac_info = f"MAC {mac}" if mac else "Stream"
            logger.warning(f"{log_prefix} ✗ {mac_info} error: {e}")
            return (False, ffprobe_duration)

    def testStream():
        """Test stream with ffprobe (legacy function for compatibility)"""
        success, duration = test_stream_with_ffprobe(link, proxy, None, "[STREAM TEST]")
        return success

    def update_mac_stats_on_redirect(portal_id, channel_id, mac, is_success):
        """Update MAC statistics in DB based on redirect feedback (thread-safe)."""
        update_mac_score_in_db(portal_id, channel_id, mac, is_success)


    portal = getPortals().get(portalId)
    
    # Check if portal exists
    if not portal:
        logger.error(f"Portal {portalId} not found")
        return make_response("Portal not found", 404)
    
    portalName = portal.get("name")
    url = portal.get("url")
    macs = list(portal["macs"].keys())
    streamsPerMac = int(portal.get("streams per mac"))
    proxy = portal.get("proxy")
    web = request.args.get("web")
    ip = get_client_ip(request)

    logger.info(
        "IP({}) requested Portal({}):Channel({})".format(ip, portalId, channelId)
    )

    # OPTIMIZATION: Check redirect mode settings
    output_format = getSettings().get("output format", "mpegts")
    stream_method = getSettings().get("stream method", "ffmpeg")
    is_redirect_mode = stream_method == "redirect"
    
    # Direct redirect is ONLY active when stream method is "redirect"
    # (output format determines HLS vs MPEG-TS redirect target)
    direct_redirect = is_redirect_mode
    
    freeMac = False
    
    # OPTIMIERT: DB-basiertes Streaming mit intelligentem MAC-Fallback
    channel = None
    mac = None
    token = None
    cmd = None
    link = None
    channelName = None
    try_all_macs_setting = True  # Always enabled - probiert immer alle MACs durch
    try_all_on_db_miss = getSettings().get("try all macs on db miss", "true") == "true"
    # Test streams: Skip in redirect mode AND proxy mode (both don't need ffprobe testing)
    test_streams_enabled = getSettings().get("test streams", "true") == "true" and stream_method not in ["redirect", "proxy"]
    skip_busy_macs = getSettings().get("skip busy macs", "false") == "true"
    already_tested_with_ffprobe = False  # Track if we already tested with ffprobe in MAC RETRY
    
    # 1. Versuche Channel aus DB zu laden
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT stream_cmd, available_macs, name, custom_name 
            FROM channels 
            WHERE portal = ? AND channel_id = ? AND enabled = 1
        ''', (portalId, channelId))
        
        row = cursor.fetchone()
        conn.close()
        
        if row and row['stream_cmd'] and row['available_macs']:
            # Channel in DB gefunden mit Cache-Daten!
            cmd = row['stream_cmd']
            channelName = row['custom_name'] or row['name']
            available_macs_raw = row['available_macs'].split(',')
            
            # Parse MACs with scoring data and sort by score
            import time
            available_macs, mac_limits, mac_stats = parse_and_sort_macs(','.join(available_macs_raw))
            
            logger.info(f"Channel {channelId} found in DB with {len(available_macs)} MAC(s) (sorted by score):")
            for m in available_macs:
                stats = mac_stats.get(m, {})
                logger.info(f"  {m}: score={stats.get('score', 25):.1f}, limit={mac_limits.get(m, 1)}, success={stats.get('success', 0)}, fail={stats.get('fail', 0)}")
            
            # PROXY MODE: Early exit with MAC retry logic
            if stream_method == "proxy":
                logger.info(f"[PROXY MODE] Starting proxy streaming with {len(available_macs)} MAC(s)")
                
                # Import at function level
                import requests
                from flask import stream_with_context
                
                def proxyStreamDataWithRetry():
                    """Stream data directly from portal to client with automatic MAC retry"""
                    
                    # Get settings
                    buffer_size_kb = int(getSettings().get("proxy buffer size", "1024"))
                    buffer_size = buffer_size_kb * 1024
                    connect_timeout = int(getSettings().get("proxy connect timeout", "5"))
                    read_timeout = int(getSettings().get("proxy read timeout", "30"))
                    skip_busy = getSettings().get("skip busy macs", "false") == "true"
                    
                    # Setup request headers
                    headers = {
                        'User-Agent': str(getSettings().get("user agent", "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3"))
                    }
                    
                    # Setup proxy if configured
                    proxies = None
                    if proxy:
                        proxies = {'http': proxy, 'https': proxy}
                    
                    timeout = (connect_timeout, read_timeout)
                    
                    # Try all MACs until one works
                    for try_mac in available_macs:
                        # Check if MAC is free (local tracking) - thread-safe
                        with occupied_lock:
                            count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                        if streamsPerMac > 0 and count >= streamsPerMac:
                            logger.debug(f"[PROXY RETRY] MAC {try_mac} is full ({count}/{streamsPerMac}), trying next")
                            continue
                        
                        # Get token for this MAC (use cache if enabled)
                        try_token = get_token_cached(url, try_mac, proxy)
                        if not try_token:
                            logger.warning(f"[PROXY RETRY] Failed to get token for MAC {try_mac}, trying next")
                            continue
                        
                        # Check if MAC is busy (if setting enabled)
                        if skip_busy:
                            profile = stb.getProfile(url, try_mac, try_token, proxy)
                            # Validate watchdog_timeout field exists
                            if 'watchdog_timeout' not in profile:
                                logger.warning(f"[PROXY RETRY] MAC {try_mac} - watchdog_timeout missing in profile, assuming busy")
                                continue
                            watchdog_timeout = profile['watchdog_timeout']
                            
                            if watchdog_timeout < 60:
                                logger.warning(f"[PROXY RETRY] MAC {try_mac} is busy (watchdog: {watchdog_timeout}s), trying next")
                                continue
                            logger.info(f"[PROXY RETRY] MAC {try_mac} looks available (watchdog: {watchdog_timeout}s)")
                        else:
                            stb.getProfile(url, try_mac, try_token, proxy)
                        
                        # Generate link for this MAC
                        try_link = None
                        if cmd:
                            if "http://localhost/" in cmd:
                                try_link = stb.getLink(url, try_mac, try_token, cmd, proxy)
                            elif "play_token=" in cmd:
                                try_link = cmd.split(" ")[1]
                                import re
                                stream_match = re.search(r'stream=(\d+)', try_link)
                                if stream_match:
                                    channel_id_from_url = stream_match.group(1)
                                    dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                                    fresh_link = stb.getLink(url, try_mac, try_token, dummy_cmd, proxy)
                                    if fresh_link:
                                        fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                                        if fresh_token_match:
                                            new_token = fresh_token_match.group(1)
                                            try_link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', try_link)
                                if "mac=" in try_link:
                                    old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', try_link)
                                    if old_mac_match:
                                        old_mac = old_mac_match.group(1)
                                        try_link = try_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                            else:
                                try_link = cmd.split(" ")[1]
                                if "mac=" in try_link:
                                    import re
                                    old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', try_link)
                                    if old_mac_match:
                                        old_mac = old_mac_match.group(1)
                                        try_link = try_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                        
                        if not try_link:
                            logger.warning(f"[PROXY RETRY] Failed to generate link for MAC {try_mac}, trying next")
                            continue
                        
                        # Try to connect with this MAC
                        startTime = datetime.now().timestamp()
                        logger.info(f"[PROXY RETRY] Trying MAC {try_mac} (buffer: {buffer_size_kb}KB, timeout: {connect_timeout}s/{read_timeout}s)")
                        logger.info(f"[PROXY RETRY] Connecting to {try_link}")
                        
                        try:
                            # Open stream connection
                            response = requests.get(try_link, stream=True, headers=headers, proxies=proxies, timeout=timeout)
                            
                            if response.status_code == 200:
                                # Success! Mark as occupied and stream to client - thread-safe
                                with occupied_lock:
                                    occupied.setdefault(portalId, [])
                                    stream_info = {
                                        "mac": try_mac,
                                        "channel id": channelId,
                                        "channel name": channelName,
                                        "client": ip,
                                        "portal name": portalName,
                                        "start time": startTime,
                                    }
                                    if xc_user:
                                        stream_info["xc_user"] = xc_user
                                    occupied[portalId].append(stream_info)
                                
                                logger.info(f"[PROXY] ✓ MAC {try_mac} connected successfully, streaming to client")
                                
                                try:
                                    # Stream data to client with validation
                                    bytes_sent = 0
                                    first_chunk_checked = False
                                    
                                    for chunk in response.iter_content(chunk_size=buffer_size):
                                        if chunk:
                                            # Option B: Check first chunk for HTML/invalid data
                                            if not first_chunk_checked and len(chunk) > 100:
                                                first_chunk_checked = True
                                                # Check if portal sent HTML instead of video
                                                if chunk.startswith(b'<!DOCTYPE') or chunk.startswith(b'<html') or chunk.startswith(b'<HTML'):
                                                    logger.error(f"[PROXY] ✗ MAC {try_mac} sent HTML instead of video")
                                                    # Update DB: fail
                                                    update_mac_score_in_db(portalId, channelId, try_mac, is_success=False)
                                                    break  # Stop streaming
                                            
                                            bytes_sent += len(chunk)
                                            
                                            # Option C: Bitrate monitoring (after 10 seconds)
                                            elapsed = datetime.now().timestamp() - startTime
                                            if elapsed >= 10 and bytes_sent > 0:
                                                bitrate_kbps = (bytes_sent * 8) / elapsed / 1000
                                                if bitrate_kbps < 50:  # Very low bitrate = dying stream
                                                    logger.error(f"[PROXY] ✗ MAC {try_mac} bitrate too low ({bitrate_kbps:.1f} kbps)")
                                                    # Update DB: fail
                                                    update_mac_score_in_db(portalId, channelId, try_mac, is_success=False)
                                                    break  # Stop streaming
                                            
                                            yield chunk
                                    
                                    logger.info(f"[PROXY] Stream ended normally (sent {bytes_sent / 1024 / 1024:.2f} MB)")
                                    
                                    # Update DB: success (only if stream ran ≥5 seconds)
                                    stream_duration = datetime.now().timestamp() - startTime
                                    if stream_duration >= 5:
                                        update_mac_score_in_db(portalId, channelId, try_mac, is_success=True)
                                        logger.info(f"[PROXY] Updated DB: MAC {try_mac} success++ (duration: {stream_duration:.1f}s)")
                                    else:
                                        # Stream too short = fail
                                        update_mac_score_in_db(portalId, channelId, try_mac, is_success=False)
                                        logger.info(f"[PROXY] Updated DB: MAC {try_mac} fail++ (stream too short: {stream_duration:.1f}s)")
                                    
                                except GeneratorExit:
                                    logger.info(f"[PROXY] Stream closed by client")
                                finally:
                                    try:
                                        with occupied_lock:
                                            occupied.get(portalId, []).remove(stream_info)
                                    except ValueError:
                                        pass
                                    stream_duration = datetime.now().timestamp() - startTime
                                    logger.info(f"[PROXY] Unoccupied Portal({portalId}):MAC({try_mac}), duration: {stream_duration:.1f}s")
                                
                                return  # Success - exit retry loop
                                
                            else:
                                # Failed - try next MAC
                                logger.error(f"[PROXY RETRY] ✗ MAC {try_mac} failed with status {response.status_code}")
                                response.close()
                                
                                # Update DB: fail
                                update_mac_score_in_db(portalId, channelId, try_mac, is_success=False)
                                
                                continue
                                
                        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.Timeout) as e:
                            logger.error(f"[PROXY RETRY] ✗ MAC {try_mac} timeout: {e}")
                            
                            # Update DB: fail (timeout is always a portal problem)
                            update_mac_score_in_db(portalId, channelId, try_mac, is_success=False)
                            
                            continue
                        except requests.exceptions.RequestException as e:
                            logger.error(f"[PROXY RETRY] ✗ MAC {try_mac} error: {e}")
                            
                            # Update DB: fail (connection error is always a portal problem)
                            update_mac_score_in_db(portalId, channelId, try_mac, is_success=False)
                            
                            continue
                        except Exception as e:
                            logger.error(f"[PROXY RETRY] ✗ MAC {try_mac} unexpected: {e}")
                            continue
                    
                    # All MACs failed
                    logger.error(f"[PROXY RETRY] All {len(available_macs)} MAC(s) failed for channel {channelId}")
                    yield b""
                
                return Response(stream_with_context(proxyStreamDataWithRetry()), mimetype="video/mp2t")
            
            # DIRECT REDIRECT MODE: Early exit with MAC retry logic
            if direct_redirect:
                logger.info(f"[DIRECT REDIRECT] Starting redirect mode with {len(available_macs)} MAC(s)")
                
                # Check for recent redirect (learning logic)
                redirect_key = (ip, portalId, channelId)
                now = time.time()
                excluded_mac = None
                
                with redirect_lock:
                    if redirect_key in recent_redirects:
                        last_mac, last_time = recent_redirects[redirect_key]
                        time_diff = now - last_time
                        
                        if time_diff < 5:  # Within 5s = definitely failed
                            logger.info(f"[REDIRECT LEARN] User re-requested within {time_diff:.1f}s - MAC {last_mac} definitely failed")
                            update_mac_stats_on_redirect(portalId, channelId, last_mac, False)
                            # Harder penalty for very quick return
                            update_mac_stats_on_redirect(portalId, channelId, last_mac, False)
                            excluded_mac = last_mac
                        elif time_diff < 10:  # Within 10s = likely failed
                            logger.info(f"[REDIRECT LEARN] User re-requested within {time_diff:.1f}s - MAC {last_mac} likely failed")
                            update_mac_stats_on_redirect(portalId, channelId, last_mac, False)
                            excluded_mac = last_mac
                        elif time_diff > 30:  # After 30s = success
                            logger.info(f"[REDIRECT LEARN] User still watching after {time_diff:.1f}s - MAC {last_mac} success")
                            update_mac_stats_on_redirect(portalId, channelId, last_mac, True)
                
                # Try all MACs until one works
                for try_mac in available_macs:
                    # Skip excluded MAC (recently failed)
                    if try_mac == excluded_mac:
                        logger.debug(f"[DIRECT REDIRECT] Skipping recently failed MAC {try_mac}")
                        continue
                    
                    # Check busy status if setting enabled
                    if skip_busy_macs:
                        token_temp = stb.getToken(url, try_mac, proxy)
                        if token_temp:
                            profile = stb.getProfile(url, try_mac, token_temp, proxy)
                            # Validate watchdog_timeout field exists
                            if 'watchdog_timeout' not in profile:
                                logger.debug(f"[DIRECT REDIRECT] MAC {try_mac} - watchdog_timeout missing, skipping")
                                continue
                            watchdog_timeout = profile['watchdog_timeout']
                            if watchdog_timeout < 60:
                                logger.debug(f"[DIRECT REDIRECT] Skipping busy MAC {try_mac} (watchdog: {watchdog_timeout}s)")
                                continue
                            logger.debug(f"[DIRECT REDIRECT] MAC {try_mac} available (watchdog: {watchdog_timeout}s)")
                    
                    # Get token and link for this MAC (use cache if enabled)
                    token = get_token_cached(url, try_mac, proxy)
                    if not token:
                        logger.warning(f"[DIRECT REDIRECT] Failed to get token for MAC {try_mac}, trying next")
                        continue
                    
                    stb.getProfile(url, try_mac, token, proxy)
                    
                    # Generate link
                    redirect_link = None
                    if cmd:
                        if "http://localhost/" in cmd:
                            redirect_link = stb.getLink(url, try_mac, token, cmd, proxy)
                        elif "play_token=" in cmd:
                            redirect_link = cmd.split(" ")[1]
                            import re
                            stream_match = re.search(r'stream=(\d+)', redirect_link)
                            if stream_match:
                                channel_id_from_url = stream_match.group(1)
                                dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                                fresh_link = stb.getLink(url, try_mac, token, dummy_cmd, proxy)
                                if fresh_link:
                                    fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                                    if fresh_token_match:
                                        new_token = fresh_token_match.group(1)
                                        redirect_link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', redirect_link)
                            if "mac=" in redirect_link:
                                old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', redirect_link)
                                if old_mac_match:
                                    old_mac = old_mac_match.group(1)
                                    redirect_link = redirect_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                        else:
                            redirect_link = cmd.split(" ")[1]
                            if "mac=" in redirect_link:
                                import re
                                old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', redirect_link)
                                if old_mac_match:
                                    old_mac = old_mac_match.group(1)
                                    redirect_link = redirect_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                    
                    if not redirect_link:
                        logger.warning(f"[DIRECT REDIRECT] Failed to generate link for MAC {try_mac}, trying next")
                        continue
                    
                    # Success! Track this redirect and return
                    with redirect_lock:
                        recent_redirects[redirect_key] = (try_mac, now)
                    
                    # Check output format setting
                    output_format = getSettings().get("output format", "mpegts")
                    
                    if output_format == "hls" and ".m3u8" in redirect_link:
                        # HLS format preferred and available
                        logger.info(f"[DIRECT REDIRECT] ✓ MAC {try_mac} (score: {mac_stats.get(try_mac, {}).get('score', 25):.1f})")
                        logger.info(f"[DIRECT REDIRECT] Redirecting to Portal HLS: {redirect_link}")
                        return redirect(redirect_link)
                    elif output_format == "hls" and ".m3u8" not in redirect_link:
                        # HLS preferred but not available - fallback to MPEG-TS
                        logger.info(f"[DIRECT REDIRECT] ✓ MAC {try_mac} (score: {mac_stats.get(try_mac, {}).get('score', 25):.1f})")
                        logger.info(f"[DIRECT REDIRECT] HLS not available, using Portal MPEG-TS: {redirect_link}")
                        return redirect(redirect_link)
                    else:
                        # MPEG-TS format (default)
                        logger.info(f"[DIRECT REDIRECT] ✓ MAC {try_mac} (score: {mac_stats.get(try_mac, {}).get('score', 25):.1f})")
                        logger.info(f"[DIRECT REDIRECT] Redirecting to Portal MPEG-TS: {redirect_link}")
                        return redirect(redirect_link)
                
                # All MACs failed
                logger.error(f"[DIRECT REDIRECT] All {len(available_macs)} MAC(s) failed for channel {channelId}")
                return make_response("No working MAC available for redirect", 503)
            
            # Probiere MACs die den Channel haben - IMMER alle durchprobieren bis eine funktioniert
            mac_found = None
            busy_macs = []  # Sammle busy MACs als Fallback (max 10)
            MAX_BUSY_MACS = 10  # Limit to prevent unbounded growth
            
            # Test Streams enabled: Teste mit ffprobe
            if test_streams_enabled:
                logger.info(f"'test streams' enabled - will test all MACs with ffprobe until one works")
                
                for try_mac in available_macs:
                    # Check if MAC is free - thread-safe
                    with occupied_lock:
                        count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                    if streamsPerMac == 0 or count < streamsPerMac:
                        logger.info(f"Testing Portal({portalId}):MAC({try_mac}):Channel({channelId})")
                        mac = try_mac
                        token = get_token_cached(url, mac, proxy)
                        if token:
                            # Optional: Check portal-side MAC load
                            is_busy = False
                            if skip_busy_macs:
                                profile = stb.getProfile(url, mac, token, proxy)
                                # Validate watchdog_timeout field exists
                                if 'watchdog_timeout' not in profile:
                                    logger.warning(f"[SKIP BUSY] MAC {mac} - watchdog_timeout missing, treating as busy")
                                    if len(busy_macs) < MAX_BUSY_MACS:
                                        busy_macs.append(try_mac)
                                    is_busy = True
                                else:
                                    watchdog_timeout = profile['watchdog_timeout']
                                    
                                    if watchdog_timeout < 60:
                                        logger.warning(f"[SKIP BUSY] MAC {mac} is very active (watchdog: {watchdog_timeout}s), saving as fallback")
                                        if len(busy_macs) < MAX_BUSY_MACS:
                                            busy_macs.append(try_mac)
                                        is_busy = True
                                    else:
                                        logger.info(f"[SKIP BUSY] MAC {mac} looks available (watchdog: {watchdog_timeout}s)")
                            else:
                                stb.getProfile(url, mac, token, proxy)
                            
                            if is_busy:
                                continue  # Skip busy MAC for now
                            
                            # Generate link for this MAC
                            test_link = None
                            if cmd:
                                if "http://localhost/" in cmd:
                                    test_link = stb.getLink(url, mac, token, cmd, proxy)
                                elif "play_token=" in cmd:
                                    test_link = cmd.split(" ")[1]
                                    import re
                                    stream_match = re.search(r'stream=(\d+)', test_link)
                                    if stream_match:
                                        channel_id_from_url = stream_match.group(1)
                                        dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                                        fresh_link = stb.getLink(url, mac, token, dummy_cmd, proxy)
                                        if fresh_link:
                                            fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                                            if fresh_token_match:
                                                new_token = fresh_token_match.group(1)
                                                test_link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', test_link)
                                    if "mac=" in test_link:
                                        old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                        if old_mac_match:
                                            old_mac = old_mac_match.group(1)
                                            test_link = test_link.replace(f"mac={old_mac}", f"mac={mac}")
                                else:
                                    # Direct link (not localhost) - extract URL
                                    test_link = cmd.split(" ")[1]
                                    # Check if link has mac parameter
                                    if "mac=" in test_link:
                                        import re
                                        old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                        if old_mac_match:
                                            old_mac = old_mac_match.group(1)
                                            test_link = test_link.replace(f"mac={old_mac}", f"mac={mac}")
                                    else:
                                        # No mac parameter - need to generate fresh link via getLink()
                                        logger.info(f"[MAC RETRY] Link has no mac parameter, generating fresh link for MAC {mac}")
                                        # Try to extract channel ID from URL
                                        import re
                                        channel_match = re.search(r'/(\d+)$', test_link)
                                        if channel_match:
                                            ch_id = channel_match.group(1)
                                            dummy_cmd = f"ffmpeg http://localhost/ch/{ch_id}_"
                                            test_link = stb.getLink(url, mac, token, dummy_cmd, proxy)
                                            if not test_link:
                                                logger.warning(f"[MAC RETRY] Failed to generate link for MAC {mac}")
                                        else:
                                            logger.warning(f"[MAC RETRY] Could not extract channel ID from link: {test_link}")
                                            test_link = None
                            
                            # Test link with ffprobe
                            if test_link:
                                logger.info(f"[MAC RETRY] Testing link for MAC {mac}")
                                success, ffprobe_duration = test_stream_with_ffprobe(test_link, proxy, mac, "[MAC RETRY]")
                                
                                if success:
                                    mac_found = mac
                                    freeMac = True
                                    already_tested_with_ffprobe = True  # Mark as already tested
                                    
                                    # Update DB: Increment success count and update timestamp
                                    try:
                                        current_time = int(time.time())
                                        stats = mac_stats.get(mac, {'success': 0, 'fail': 0, 'last_ts': 0, 'score': 25})
                                        stats['success'] += 1
                                        stats['last_ts'] = current_time
                                        mac_stats[mac] = stats
                                        
                                        # Rebuild available_macs string with updated stats
                                        macs_with_data = []
                                        for m in available_macs:
                                            limit = mac_limits.get(m, 1)
                                            st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                            macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                        new_available_macs = ",".join(macs_with_data)
                                        
                                        conn_update = get_db_connection()
                                        cursor_update = conn_update.cursor()
                                        cursor_update.execute('''
                                            UPDATE channels 
                                            SET available_macs = ?
                                            WHERE portal = ? AND channel_id = ?
                                        ''', (new_available_macs, portalId, channelId))
                                        conn_update.commit()
                                        conn_update.close()
                                        logger.info(f"[MAC RETRY] Updated DB: MAC {mac} success count: {stats['success']}")
                                    except Exception as e:
                                        logger.error(f"[MAC RETRY] Error updating DB: {e}")
                                    
                                    break
                                else:
                                    logger.warning(f"[MAC RETRY] ✗ MAC {mac} failed test, trying next MAC")
                                    
                                    # Update DB: Increment fail count
                                    try:
                                        stats = mac_stats.get(mac, {'success': 0, 'fail': 0, 'last_ts': 0, 'score': 25})
                                        stats['fail'] += 1
                                        mac_stats[mac] = stats
                                        
                                        # Rebuild available_macs string
                                        macs_with_data = []
                                        for m in available_macs:
                                            limit = mac_limits.get(m, 1)
                                            st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                            macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                        new_available_macs = ",".join(macs_with_data)
                                        
                                        conn_update = get_db_connection()
                                        cursor_update = conn_update.cursor()
                                        cursor_update.execute('''
                                            UPDATE channels 
                                            SET available_macs = ?
                                            WHERE portal = ? AND channel_id = ?
                                        ''', (new_available_macs, portalId, channelId))
                                        conn_update.commit()
                                        conn_update.close()
                                        logger.info(f"[MAC RETRY] Updated DB: MAC {mac} fail count: {stats['fail']}")
                                    except Exception as e:
                                        logger.error(f"[MAC RETRY] Error updating DB: {e}")
                                    
                                    continue
                            else:
                                # No link generated - harder penalty
                                logger.warning(f"[MAC RETRY] No link generated for MAC {mac}, skipping")
                                try:
                                    stats = mac_stats.get(mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                    stats['fail'] += 2  # Harder penalty
                                    mac_stats[mac] = stats
                                    
                                    macs_with_data = []
                                    for m in available_macs:
                                        limit = mac_limits.get(m, 1)
                                        st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                        macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                    new_available_macs = ",".join(macs_with_data)
                                    
                                    conn_update = get_db_connection()
                                    cursor_update = conn_update.cursor()
                                    cursor_update.execute('''
                                        UPDATE channels 
                                        SET available_macs = ?
                                        WHERE portal = ? AND channel_id = ?
                                    ''', (new_available_macs, portalId, channelId))
                                    conn_update.commit()
                                    conn_update.close()
                                    logger.info(f"[MAC RETRY] Updated DB: MAC {mac} no link penalty (fail +2)")
                                except Exception as e:
                                    logger.error(f"[MAC RETRY] Error updating DB: {e}")
                                continue
                    else:
                        logger.debug(f"MAC {try_mac} is full ({count}/{streamsPerMac}), trying next")
                
                # Fallback: Wenn keine MAC funktioniert hat, probiere busy MACs
                if not mac_found and busy_macs:
                    logger.warning(f"[MAC RETRY] No available MACs worked, trying {len(busy_macs)} busy MAC(s) as fallback")
                    
                    for try_mac in busy_macs:
                        with occupied_lock:
                            count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                        if streamsPerMac == 0 or count < streamsPerMac:
                            logger.info(f"[MAC RETRY FALLBACK] Testing busy MAC {try_mac}")
                            mac = try_mac
                            token = get_token_cached(url, mac, proxy)
                            if token:
                                stb.getProfile(url, mac, token, proxy)
                                
                                # Generate link
                                test_link = None
                                if cmd:
                                    if "http://localhost/" in cmd:
                                        test_link = stb.getLink(url, mac, token, cmd, proxy)
                                    elif "play_token=" in cmd:
                                        test_link = cmd.split(" ")[1]
                                        import re
                                        stream_match = re.search(r'stream=(\d+)', test_link)
                                        if stream_match:
                                            channel_id_from_url = stream_match.group(1)
                                            dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                                            fresh_link = stb.getLink(url, mac, token, dummy_cmd, proxy)
                                            if fresh_link:
                                                fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                                                if fresh_token_match:
                                                    new_token = fresh_token_match.group(1)
                                                    test_link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', test_link)
                                        if "mac=" in test_link:
                                            old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                            if old_mac_match:
                                                old_mac = old_mac_match.group(1)
                                                test_link = test_link.replace(f"mac={old_mac}", f"mac={mac}")
                                    else:
                                        test_link = cmd.split(" ")[1]
                                        if "mac=" in test_link:
                                            import re
                                            old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                            if old_mac_match:
                                                old_mac = old_mac_match.group(1)
                                                test_link = test_link.replace(f"mac={old_mac}", f"mac={mac}")
                                
                                if test_link:
                                    timeout = int(getSettings()["ffmpeg timeout"]) * int(1000000)
                                    user_agent = getSettings().get("user agent", "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3")
                                    # Get custom ffprobe parameters from settings
                                    ffprobe_params_str = getSettings().get("ffprobe params", "-analyzeduration 500000 -probesize 100000")
                                    ffprobe_params = ffprobe_params_str.split() if ffprobe_params_str.strip() else []
                                    
                                    ffprobecmd = [ffprobe_path] + ffprobe_params + ["-user_agent", user_agent, "-timeout", str(timeout), "-i", test_link]
                                    if proxy:
                                        ffprobecmd.insert(1, "-http_proxy")
                                        ffprobecmd.insert(2, proxy)
                                    
                                    try:
                                        import time
                                        ffprobe_start = time.time()
                                        with subprocess.Popen(
                                            ffprobecmd,
                                            stdin=subprocess.DEVNULL,
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.PIPE,
                                        ) as ffprobe_sb:
                                            ffprobe_sb.communicate(timeout=int(getSettings()["ffmpeg timeout"]))
                                            ffprobe_duration = time.time() - ffprobe_start
                                            if ffprobe_sb.returncode == 0:
                                                logger.info(f"[MAC RETRY FALLBACK] ✓ Busy MAC {mac} works! (ffprobe: {ffprobe_duration:.2f}s)")
                                                mac_found = mac
                                                freeMac = True
                                                already_tested_with_ffprobe = True  # Mark as already tested
                                                
                                                # Update DB: Increment success count
                                                try:
                                                    import time
                                                    current_time = int(time.time())
                                                    stats = mac_stats.get(mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                                    stats['success'] += 1
                                                    stats['last_ts'] = current_time
                                                    mac_stats[mac] = stats
                                                    
                                                    macs_with_data = []
                                                    for m in available_macs:
                                                        limit = mac_limits.get(m, 1)
                                                        st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                                        macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                                    new_available_macs = ",".join(macs_with_data)
                                                    
                                                    conn_update = get_db_connection()
                                                    cursor_update = conn_update.cursor()
                                                    cursor_update.execute('''
                                                        UPDATE channels 
                                                        SET available_macs = ?
                                                        WHERE portal = ? AND channel_id = ?
                                                    ''', (new_available_macs, portalId, channelId))
                                                    conn_update.commit()
                                                    conn_update.close()
                                                    logger.info(f"[MAC RETRY FALLBACK] Updated DB: MAC {mac} success count: {stats['success']}")
                                                except Exception as e:
                                                    logger.error(f"[MAC RETRY FALLBACK] Error updating DB: {e}")
                                                
                                                break
                                    except:
                                        continue
            else:
                # Test Streams disabled: Probiere alle MACs ohne ffprobe Test
                logger.info(f"'test streams' disabled - will try all MACs without ffprobe test")
                
                for try_mac in available_macs:
                    # Check if MAC is free - thread-safe
                    with occupied_lock:
                        count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                    if streamsPerMac == 0 or count < streamsPerMac:
                        logger.info(f"Trying Portal({portalId}):MAC({try_mac}):Channel({channelId})")
                        freeMac = True
                        mac = try_mac
                        token = stb.getToken(url, mac, proxy)
                        if token:
                            # Optional: Check portal-side MAC load
                            if skip_busy_macs:
                                profile = stb.getProfile(url, mac, token, proxy)
                                # Validate watchdog_timeout field exists
                                if 'watchdog_timeout' not in profile:
                                    logger.warning(f"[SKIP BUSY] MAC {mac} - watchdog_timeout missing, treating as busy")
                                    if len(busy_macs) < MAX_BUSY_MACS:
                                        busy_macs.append(try_mac)
                                    continue
                                watchdog_timeout = profile['watchdog_timeout']
                                
                                if watchdog_timeout < 60:
                                    logger.warning(f"[SKIP BUSY] MAC {mac} is very active (watchdog: {watchdog_timeout}s), saving as fallback")
                                    if len(busy_macs) < MAX_BUSY_MACS:
                                        busy_macs.append(try_mac)
                                    continue
                                else:
                                    logger.info(f"[SKIP BUSY] MAC {mac} looks available (watchdog: {watchdog_timeout}s)")
                                    mac_found = mac
                                    break
                            else:
                                stb.getProfile(url, mac, token, proxy)
                                mac_found = mac
                                break
                    else:
                        logger.debug(f"MAC {try_mac} is full ({count}/{streamsPerMac}), trying next")
                
                # Fallback: Wenn keine MAC gefunden, probiere busy MACs
                if not mac_found and busy_macs:
                    logger.warning(f"[SKIP BUSY] No available MACs found, trying {len(busy_macs)} busy MAC(s) as fallback")
                    
                    for try_mac in busy_macs:
                        with occupied_lock:
                            count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                        if streamsPerMac == 0 or count < streamsPerMac:
                            logger.info(f"[SKIP BUSY FALLBACK] Using busy MAC {try_mac}")
                            mac = try_mac
                            token = get_token_cached(url, mac, proxy)
                            if token:
                                stb.getProfile(url, mac, token, proxy)
                                mac_found = mac
                                freeMac = True
                                break
            
            if not mac_found:
                logger.warning(f"Channel {channelId} not found on known MACs, trying other MACs")
                # Probiere andere MACs
                other_macs = [m for m in macs if m not in available_macs]
                
                for try_mac in other_macs:
                    with occupied_lock:
                        count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                    if streamsPerMac == 0 or count < streamsPerMac:
                        logger.info(f"Trying other MAC: Portal({portalId}):MAC({try_mac}):Channel({channelId})")
                        freeMac = True
                        mac = try_mac
                        token = get_token_cached(url, mac, proxy)
                        if token:
                            profile = stb.getProfile(url, mac, token, proxy)
                            playback_limit = profile.get('playback_limit', 1) if profile else 1
                            
                            # Lade alle Channels von dieser MAC
                            channels = stb.getAllChannels(url, mac, token, proxy)
                            if channels:
                                # Suche Channel
                                for ch in channels:
                                    if str(ch["id"]) == str(channelId):
                                        channel = ch
                                        cmd = channel["cmd"]
                                        channelName = channel["name"]
                                        mac_found = mac
                                        
                                        # Update DB: Füge diese MAC zu available_macs hinzu
                                        try:
                                            # Add MAC with proper format: MAC|limit|success|fail|last_ts
                                            new_mac_entry = f"{mac}|{playback_limit}|0|0|0"
                                            
                                            # Rebuild available_macs with all MACs
                                            macs_with_data = []
                                            for m in available_macs:
                                                st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                                l = mac_limits.get(m, 1)
                                                macs_with_data.append(f"{m}|{l}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                            macs_with_data.append(new_mac_entry)
                                            new_available_macs = ','.join(macs_with_data)
                                            
                                            conn = get_db_connection()
                                            cursor = conn.cursor()
                                            cursor.execute('''
                                                UPDATE channels 
                                                SET available_macs = ?
                                                WHERE portal = ? AND channel_id = ?
                                            ''', (new_available_macs, portalId, channelId))
                                            conn.commit()
                                            conn.close()
                                            logger.info(f"Updated DB: Added MAC {mac} to available_macs for channel {channelId}")
                                        except Exception as e:
                                            logger.error(f"Error updating DB: {e}")
                                        
                                        break
                                
                                if mac_found:
                                    break
                    
                    # Respect "try all macs" setting
                    if not try_all_macs_setting:
                        logger.info("'try all macs' is disabled, stopping after first MAC")
                        break
            
            if not mac_found:
                logger.warning(f"All MACs busy or channel not found on other MACs for channel {channelId}")
                return make_response("All MACs busy", 503)
            
            mac = mac_found
        elif row:
            # Channel in DB aber OHNE Cache-Daten (stream_cmd oder available_macs ist NULL)
            logger.warning(f"Channel {channelId} in DB but missing cache data (stream_cmd or available_macs), falling back to getAllChannels()")
            channelName = row['custom_name'] or row['name']
            
            # FALLBACK: Lade Channel-Daten vom Portal
            mac_found = None
            for try_mac in macs:
                # Check if MAC is free - thread-safe
                with occupied_lock:
                    count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                if streamsPerMac == 0 or count < streamsPerMac:
                    logger.info(f"Fallback (missing cache): Trying Portal({portalId}):MAC({try_mac}):Channel({channelId})")
                    freeMac = True
                    mac = try_mac
                    token = get_token_cached(url, mac, proxy)
                    if token:
                        profile = stb.getProfile(url, mac, token, proxy)
                        playback_limit = profile.get('playback_limit', 1) if profile else 1
                        
                        # Lade alle Channels von dieser MAC
                        channels = stb.getAllChannels(url, mac, token, proxy)
                        if channels:
                            # Suche Channel
                            for ch in channels:
                                if str(ch["id"]) == str(channelId):
                                    channel = ch
                                    cmd = channel["cmd"]
                                    channelName = channel["name"]
                                    mac_found = mac
                                    
                                    # Speichere Cache-Daten in DB mit proper format
                                    try:
                                        # Format: MAC|limit|success|fail|last_ts
                                        available_macs_entry = f"{mac}|{playback_limit}|0|0|0"
                                        
                                        conn = get_db_connection()
                                        cursor = conn.cursor()
                                        cursor.execute('''
                                            UPDATE channels 
                                            SET stream_cmd = ?, available_macs = ?
                                            WHERE portal = ? AND channel_id = ?
                                        ''', (cmd, available_macs_entry, portalId, channelId))
                                        conn.commit()
                                        conn.close()
                                        logger.info(f"Updated DB: Saved cache data for channel {channelId} (MAC: {mac}, limit: {playback_limit})")
                                    except Exception as e:
                                        logger.error(f"Error updating DB: {e}")
                                    
                                    break
                            
                            if mac_found:
                                break
                
                # Respect "try all macs" setting
                if not try_all_macs_setting:
                    logger.info("'try all macs' is disabled, stopping after first MAC")
                    break
            
            if not mac_found:
                logger.error(f"Channel {channelId} not found on any MAC (missing cache data)")
                return make_response("Channel not found", 404)
            
            mac = mac_found
        else:
            # 4. FALLBACK: Channel nicht in DB - probiere getAllChannels()
            logger.warning(f"Channel {channelId} not in DB, falling back to getAllChannels()")
            
            mac_found = None
            for try_mac in macs:
                # Check if MAC is free - thread-safe
                with occupied_lock:
                    count = sum(1 for i in occupied.get(portalId, []) if i["mac"] == try_mac)
                if streamsPerMac == 0 or count < streamsPerMac:
                    logger.info(f"Fallback: Trying Portal({portalId}):MAC({try_mac}):Channel({channelId})")
                    freeMac = True
                    mac = try_mac
                    token = get_token_cached(url, mac, proxy)
                    if token:
                        stb.getProfile(url, mac, token, proxy)
                        
                        # Lade alle Channels von dieser MAC
                        channels = stb.getAllChannels(url, mac, token, proxy)
                        if channels:
                            # Suche Channel
                            for ch in channels:
                                if str(ch["id"]) == str(channelId):
                                    channel = ch
                                    cmd = channel["cmd"]
                                    channelName = channel["name"]
                                    mac_found = mac
                                    
                                    # Speichere in DB für nächstes Mal
                                    try:
                                        conn = get_db_connection()
                                        cursor = conn.cursor()
                                        cursor.execute('''
                                            UPDATE channels 
                                            SET stream_cmd = ?, available_macs = ?, enabled = 1
                                            WHERE portal = ? AND channel_id = ?
                                        ''', (cmd, mac, portalId, channelId))
                                        conn.commit()
                                        conn.close()
                                        logger.info(f"Auto-learned: Saved channel {channelId} to DB")
                                    except Exception as e:
                                        logger.error(f"Error saving channel to DB: {e}")
                                    
                                    break
                            
                            if mac_found:
                                break
                
                # Respect "try all macs" setting
                if not try_all_macs_setting:
                    logger.info("'try all macs' is disabled, stopping after first MAC")
                    break
            
            if not mac_found:
                logger.error(f"Channel {channelId} not found on any MAC")
                return make_response("Channel not found", 404)
            
            mac = mac_found
    
    except Exception as e:
        logger.error(f"Error loading channel from DB: {e}")
        return make_response("Database error", 500)
    
    # 5. Generate stream link
    if cmd:
        logger.info(f"[STREAM DEBUG] cmd from DB: {cmd}")
        
        if "http://localhost/" in cmd:
            # Localhost URLs brauchen getLink()
            link = stb.getLink(url, mac, token, cmd, proxy)
            logger.info(f"[STREAM DEBUG] Used getLink() for localhost URL")
            logger.info(f"[STREAM DEBUG] Final link: {link}")
        elif "play_token=" in cmd:
            # URLs mit play_token: Ersetze nur den Token (nicht getLink aufrufen!)
            link = cmd.split(" ")[1]
            logger.info(f"[STREAM DEBUG] URL with play_token (before token refresh): {link}")
            
            # Hole frischen Token durch getLink() mit einem Dummy-cmd
            # Extrahiere channel_id aus der URL
            import re
            stream_match = re.search(r'stream=(\d+)', link)
            if stream_match:
                channel_id_from_url = stream_match.group(1)
                # Erstelle localhost-style cmd für getLink()
                dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                fresh_link = stb.getLink(url, mac, token, dummy_cmd, proxy)
                
                if fresh_link:
                    # Extrahiere neuen play_token aus fresh_link
                    fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                    if fresh_token_match:
                        new_token = fresh_token_match.group(1)
                        # Ersetze alten Token mit neuem
                        link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', link)
                        logger.info(f"[STREAM DEBUG] Refreshed play_token: {new_token}")
            
            # Ersetze MAC in URL falls nötig
            if "mac=" in link:
                old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', link)
                if old_mac_match:
                    old_mac = old_mac_match.group(1)
                    link = link.replace(f"mac={old_mac}", f"mac={mac}")
                    logger.info(f"[STREAM DEBUG] Replaced MAC in URL: {old_mac} → {mac}")
            
            logger.info(f"[STREAM DEBUG] Final link (after token refresh): {link}")
        else:
            # Direct URL - ersetze MAC in URL falls vorhanden
            link = cmd.split(" ")[1]
            logger.info(f"[STREAM DEBUG] Direct URL (before MAC replacement): {link}")
            
            if "mac=" in link:
                import re
                old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', link)
                if old_mac_match:
                    old_mac = old_mac_match.group(1)
                    link = link.replace(f"mac={old_mac}", f"mac={mac}")
                    logger.info(f"[STREAM DEBUG] Replaced MAC in URL: {old_mac} → {mac}")
            
            logger.info(f"[STREAM DEBUG] Final link (after MAC replacement): {link}")
    
    if not link:
        logger.warning(f"No stream link generated for MAC {mac}, channel {channelId}")
        # Markiere MAC als defekt
        logger.info("Moving MAC({}) for Portal({})".format(mac, portalName))
        moveMac(portalId, mac)
        return make_response("No stream link available", 404)

    if link:
        # Check output format setting
        output_format = getSettings().get("output format", "mpegts")
        
        if output_format == "hls":
            # HLS mode: Return playlist URL instead of direct stream
            # The HLS route will handle MAC retry with FFmpeg stderr monitoring
            logger.info(f"[HLS MODE] Redirecting to HLS playlist for Portal({portalId}):Channel({channelId})")
            hls_url = f"/hls/{portalId}/{channelId}/stream.m3u8"
            
            # Return M3U8 playlist that points to our HLS endpoint
            playlist_content = f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=5000000
{hls_url}
"""
            return Response(playlist_content, mimetype="application/vnd.apple.mpegurl")
        
        # MPEG-TS mode: Continue with FFmpeg Direct streaming
        # Skip testStream() if we already tested with ffprobe in MAC RETRY or in redirect/proxy mode
        stream_method = getSettings().get("stream method", "ffmpeg")
        skip_test = (getSettings().get("test streams", "true") == "false" or 
                     already_tested_with_ffprobe or 
                     stream_method in ["redirect", "proxy"])
        
        if skip_test or testStream():
            if web:
                ffmpegcmd = [
                    ffmpeg_path,
                    "-loglevel",
                    "panic",
                    "-hide_banner",
                    "-i",
                    link,
                    "-vcodec",
                    "copy",
                    "-f",
                    "mp4",
                    "-movflags",
                    "frag_keyframe+empty_moov",
                    "pipe:",
                ]
                if proxy:
                    ffmpegcmd.insert(1, "-http_proxy")
                    ffmpegcmd.insert(2, proxy)
                # Use correct mimetype for MPEG-TS streams
                response = Response(streamData(), mimetype="video/mp2t")
                response.headers['Content-Type'] = 'video/mp2t'
                response.headers['Accept-Ranges'] = 'none'
                return response
            else:
                stream_method = getSettings().get("stream method", "ffmpeg")
                
                if stream_method == "ffmpeg":
                    user_agent = getSettings().get("user agent", "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3")
                    ffmpegcmd = f"{ffmpeg_path} {getSettings()['ffmpeg command']}"
                    ffmpegcmd = ffmpegcmd.replace("<url>", link)
                    ffmpegcmd = ffmpegcmd.replace("<user_agent>", user_agent)
                    ffmpegcmd = ffmpegcmd.replace(
                        "<timeout>",
                        str(int(getSettings()["ffmpeg timeout"]) * int(1000000)),
                    )
                    if proxy:
                        ffmpegcmd = ffmpegcmd.replace("<proxy>", proxy)
                    else:
                        ffmpegcmd = ffmpegcmd.replace("-http_proxy <proxy>", "")
                    
                    # Bereinige doppelte Leerzeichen und splitte in Array
                    ffmpegcmd = " ".join(ffmpegcmd.split())
                    ffmpegcmd = ffmpegcmd.split()
                    return Response(
                        streamData(), mimetype="application/octet-stream"
                    )
                else:
                    # Redirect mode - add learning logic
                    redirect_key = (ip, portalId, channelId)
                    now = time.time()
                    
                    with redirect_lock:
                        if redirect_key in recent_redirects:
                            last_mac, last_time = recent_redirects[redirect_key]
                            time_diff = now - last_time
                            
                            if time_diff < 5:  # Within 5s = definitely failed
                                logger.info(f"[REDIRECT LEARN] User re-requested within {time_diff:.1f}s - MAC {last_mac} definitely failed")
                                update_mac_stats_on_redirect(portalId, channelId, last_mac, False)
                                # Harder penalty for very quick return
                                update_mac_stats_on_redirect(portalId, channelId, last_mac, False)
                            elif time_diff < 10:  # Within 10s = likely failed
                                logger.info(f"[REDIRECT LEARN] User re-requested within {time_diff:.1f}s - MAC {last_mac} likely failed")
                                update_mac_stats_on_redirect(portalId, channelId, last_mac, False)
                                # Note: MAC already selected, can't change now
                            elif time_diff > 30:  # After 30s = success
                                logger.info(f"[REDIRECT LEARN] User still watching after {time_diff:.1f}s - MAC {last_mac} success")
                                update_mac_stats_on_redirect(portalId, channelId, last_mac, True)
                        
                        # Track this redirect
                        recent_redirects[redirect_key] = (mac, now)
                    
                    logger.info("Redirect sent")
                    return redirect(link)
        else:
            logger.info(
                "Unable to connect to Portal({}) using MAC({})".format(portalId, mac)
            )
            logger.info("Moving MAC({}) for Portal({})".format(mac, portalName))
            moveMac(portalId, mac)
            return make_response("Unable to connect to portal", 503)
    
    # If we reach here, no stream was found
    if freeMac:
        logger.info(
            "No working streams found for Portal({}):Channel({})".format(
                portalId, channelId
            )
        )
    else:
        logger.info(
            "No free MAC for Portal({}):Channel({})".format(portalId, channelId)
        )

    return make_response("No streams available", 503)


@app.route("/play/<portalId>/<channelId>", methods=["GET"])
def channel(portalId, channelId):
    """Stream endpoint with configurable access control."""
    settings = getSettings()
    public_access = settings.get("public playlist access", "true") == "true"
    
    if public_access:
        # Public access enabled - no authentication required
        return stream_channel(portalId, channelId)
    else:
        # Public access disabled - require Basic Auth
        auth = request.authorization
        if not auth or not auth.username or not auth.password:
            # No Basic Auth provided - return 401 with WWW-Authenticate header
            response = Response(
                'Authentication required for stream access\n'
                'Please provide Basic Auth credentials.',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Stream Access"'}
            )
            return response
        
        # Validate Basic Auth credentials
        system_username = settings.get("username", "admin")
        system_password = settings.get("password", "12345")
        
        if auth.username != system_username or auth.password != system_password:
            logger.warning(f"Invalid Basic Auth credentials for stream: {auth.username}")
            response = Response(
                'Invalid credentials for stream access\n'
                'Please check your username and password.',
                401,
                {'WWW-Authenticate': 'Basic realm="MacReplayXC Stream Access"'}
            )
            return response
        
        # Authentication successful
        logger.info(f"Basic Auth successful for stream: {auth.username}")
        return stream_channel(portalId, channelId)


@app.route("/hls/<portalId>/<channelId>/<path:filename>", methods=["GET"])
def hls_stream(portalId, channelId, filename):
    """Serve HLS streams (playlists and segments)."""
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
    file_path = None  # Initialize file_path
    
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
    
    # If file doesn't exist and this is a playlist/segment request, start the stream
    if not file_path and (filename.endswith('.m3u8') or filename.endswith('.ts') or filename.endswith('.m4s')):
        # If stream already exists but file not found, it's probably an old segment that was deleted
        # Don't restart the stream, just return 404
        if stream_exists and not filename.endswith('.m3u8'):
            logger.debug(f"[HLS] Segment {filename} not found for active stream {stream_key} (probably deleted)")
            return make_response("Segment not found (already deleted)", 404)
        
        # OPTIMIERT: DB-basiertes Streaming mit intelligentem MAC-Fallback
        cmd = None
        mac_used = None
        
        # Get HLS retry settings
        hls_auto_retry = True  # Always enabled - probiert immer alle MACs durch
        hls_retry_timeout_str = getSettings().get("hls retry timeout", "3")
        hls_retry_timeout = int(hls_retry_timeout_str) if hls_retry_timeout_str and hls_retry_timeout_str != "false" else 3
        hls_skip_busy = getSettings().get("skip busy macs", "false") == "true"
        
        # 1. Versuche Channel aus DB zu laden
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT stream_cmd, available_macs 
                FROM channels 
                WHERE portal = ? AND channel_id = ? AND enabled = 1
            ''', (portalId, channelId))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row['stream_cmd'] and row['available_macs']:
                cmd = row['stream_cmd']
                available_macs_raw = row['available_macs'].split(',')
                
                # Parse MACs with scoring data and sort by score
                import time
                available_macs, mac_limits, mac_stats = parse_and_sort_macs(','.join(available_macs_raw))
                
                logger.info(f"[HLS] Channel {channelId} found in DB with {len(available_macs)} MAC(s) (sorted by score):")
                for m in available_macs:
                    stats = mac_stats.get(m, {})
                    logger.info(f"  {m}: score={stats.get('score', 25):.1f}, limit={mac_limits.get(m, 1)}, success={stats.get('success', 0)}, fail={stats.get('fail', 0)}")
                
                if hls_auto_retry:
                    logger.info(f"[HLS RETRY] Auto retry enabled, will test all {len(available_macs)} MACs")
                    
                    busy_macs = []  # Sammle busy MACs als Fallback (max 10)
                    MAX_BUSY_MACS = 10  # Limit to prevent unbounded growth
                    
                    # Probiere alle MACs durch
                    for try_mac in available_macs:
                        try:
                            logger.info(f"[HLS RETRY] Testing MAC {try_mac}")
                            
                            # Get token (use cache if enabled)
                            token = get_token_cached(url, try_mac, proxy)
                            if not token:
                                logger.warning(f"[HLS RETRY] Failed to get token for MAC {try_mac}")
                                continue
                            
                            # Optional: Skip busy MACs
                            is_busy = False
                            if hls_skip_busy:
                                profile = stb.getProfile(url, try_mac, token, proxy)
                                # Validate watchdog_timeout field exists
                                if 'watchdog_timeout' not in profile:
                                    logger.warning(f"[HLS RETRY] MAC {try_mac} - watchdog_timeout missing, treating as busy")
                                    if len(busy_macs) < MAX_BUSY_MACS:
                                        busy_macs.append(try_mac)
                                    is_busy = True
                                else:
                                    watchdog = profile['watchdog_timeout']
                                    if watchdog < 60:
                                        logger.warning(f"[HLS RETRY] MAC {try_mac} is busy (watchdog: {watchdog}s), saving as fallback")
                                        if len(busy_macs) < MAX_BUSY_MACS:
                                            busy_macs.append(try_mac)
                                        is_busy = True
                                    else:
                                        logger.info(f"[HLS RETRY] MAC {try_mac} looks available (watchdog: {watchdog}s)")
                            else:
                                stb.getProfile(url, try_mac, token, proxy)
                            
                            if is_busy:
                                continue  # Skip busy MAC for now
                            
                            # Generate link
                            test_link = None
                            if "http://localhost/" in cmd:
                                test_link = stb.getLink(url, try_mac, token, cmd, proxy)
                            elif "play_token=" in cmd:
                                test_link = cmd.split(" ")[1]
                                import re
                                stream_match = re.search(r'stream=(\d+)', test_link)
                                if stream_match:
                                    channel_id_from_url = stream_match.group(1)
                                    dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                                    fresh_link = stb.getLink(url, try_mac, token, dummy_cmd, proxy)
                                    if fresh_link:
                                        fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                                        if fresh_token_match:
                                            new_token = fresh_token_match.group(1)
                                            test_link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', test_link)
                                if "mac=" in test_link:
                                    old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                    if old_mac_match:
                                        old_mac = old_mac_match.group(1)
                                        test_link = test_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                            else:
                                test_link = cmd.split(" ")[1]
                                if "mac=" in test_link:
                                    import re
                                    old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                    if old_mac_match:
                                        old_mac = old_mac_match.group(1)
                                        test_link = test_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                            
                            if not test_link:
                                logger.warning(f"[HLS RETRY] Failed to generate link for MAC {try_mac}")
                                
                                # Update DB: Harder penalty for no link (fail += 2)
                                try:
                                    stats = mac_stats.get(try_mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                    stats['fail'] += 2  # Harder penalty: no link at all
                                    mac_stats[try_mac] = stats
                                    
                                    macs_with_data = []
                                    for m in available_macs:
                                        limit = mac_limits.get(m, 1)
                                        st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                        macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                    new_available_macs = ",".join(macs_with_data)
                                    
                                    conn_update = get_db_connection()
                                    cursor_update = conn_update.cursor()
                                    cursor_update.execute('''
                                        UPDATE channels 
                                        SET available_macs = ?
                                        WHERE portal = ? AND channel_id = ?
                                    ''', (new_available_macs, portalId, channelId))
                                    conn_update.commit()
                                    conn_update.close()
                                    logger.info(f"[HLS RETRY] Updated DB: MAC {try_mac} no link penalty (fail +2)")
                                except Exception as e:
                                    logger.error(f"[HLS RETRY] Error updating DB: {e}")
                                
                                continue
                            
                            # Start HLS stream and test
                            logger.info(f"[HLS RETRY] Starting stream with MAC {try_mac}")
                            stream_info = hls_manager.start_stream(portalId, channelId, test_link, proxy)
                            
                            # Monitor FFmpeg output instead of polling filesystem
                            process = stream_info.get('process')
                            if process:
                                # Use FFmpeg stderr monitoring (fast!)
                                stream_ready = monitor_ffmpeg_hls_output(process, timeout_seconds=hls_retry_timeout)
                            else:
                                # Passthrough stream (no FFmpeg process)
                                # Fall back to filesystem check
                                playlist_path = stream_info.get('playlist_path') or stream_info.get('master_playlist_path')
                                stream_ready = False
                                if playlist_path:
                                    max_wait_iterations = hls_retry_timeout * 10
                                    for wait_i in range(max_wait_iterations):
                                        if os.path.exists(playlist_path):
                                            stream_ready = True
                                            break
                                        time.sleep(0.1)
                            
                            if stream_ready:
                                logger.info(f"[HLS RETRY] ✓ MAC {try_mac} works! Playlist created.")
                                mac_used = try_mac
                                link = test_link
                                
                                # Update DB: Increment success count
                                try:
                                    import time
                                    current_time = int(time.time())
                                    stats = mac_stats.get(try_mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                    stats['success'] += 1
                                    stats['last_ts'] = current_time
                                    mac_stats[try_mac] = stats
                                    
                                    macs_with_data = []
                                    for m in available_macs:
                                        limit = mac_limits.get(m, 1)
                                        st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                        macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                    new_available_macs = ",".join(macs_with_data)
                                    
                                    conn_update = get_db_connection()
                                    cursor_update = conn_update.cursor()
                                    cursor_update.execute('''
                                        UPDATE channels 
                                        SET available_macs = ?
                                        WHERE portal = ? AND channel_id = ?
                                    ''', (new_available_macs, portalId, channelId))
                                    conn_update.commit()
                                    conn_update.close()
                                    logger.info(f"[HLS RETRY] Updated DB: MAC {try_mac} success count: {stats['success']}")
                                except Exception as e:
                                    logger.error(f"[HLS RETRY] Error updating DB: {e}")
                                
                                break
                            else:
                                logger.warning(f"[HLS RETRY] ✗ MAC {try_mac} failed (no playlist after {hls_retry_timeout}s)")
                                hls_manager.stop_stream(portalId, channelId)
                                
                                # Update DB: Increment fail count
                                try:
                                    stats = mac_stats.get(try_mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                    stats['fail'] += 1
                                    mac_stats[try_mac] = stats
                                    
                                    macs_with_data = []
                                    for m in available_macs:
                                        limit = mac_limits.get(m, 1)
                                        st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                        macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                    new_available_macs = ",".join(macs_with_data)
                                    
                                    conn_update = get_db_connection()
                                    cursor_update = conn_update.cursor()
                                    cursor_update.execute('''
                                        UPDATE channels 
                                        SET available_macs = ?
                                        WHERE portal = ? AND channel_id = ?
                                    ''', (new_available_macs, portalId, channelId))
                                    conn_update.commit()
                                    conn_update.close()
                                    logger.info(f"[HLS RETRY] Updated DB: MAC {try_mac} fail count: {stats['fail']}")
                                except Exception as e:
                                    logger.error(f"[HLS RETRY] Error updating DB: {e}")
                                
                                continue
                                
                        except Exception as e:
                            logger.error(f"[HLS RETRY] Error testing MAC {try_mac}: {e}")
                            try:
                                hls_manager.stop_stream(portalId, channelId)
                            except:
                                pass
                            continue
                    
                    # Fallback: Wenn keine MAC funktioniert hat, probiere busy MACs
                    if not mac_used and busy_macs:
                        logger.warning(f"[HLS RETRY] No available MACs worked, trying {len(busy_macs)} busy MAC(s) as fallback")
                        
                        for try_mac in busy_macs:
                            try:
                                logger.info(f"[HLS RETRY FALLBACK] Testing busy MAC {try_mac}")
                                
                                token = get_token_cached(url, try_mac, proxy)
                                if not token:
                                    continue
                                
                                stb.getProfile(url, try_mac, token, proxy)
                                
                                # Generate link (same logic as above)
                                test_link = None
                                if "http://localhost/" in cmd:
                                    test_link = stb.getLink(url, try_mac, token, cmd, proxy)
                                elif "play_token=" in cmd:
                                    test_link = cmd.split(" ")[1]
                                    import re
                                    stream_match = re.search(r'stream=(\d+)', test_link)
                                    if stream_match:
                                        channel_id_from_url = stream_match.group(1)
                                        dummy_cmd = f"ffmpeg http://localhost/ch/{channel_id_from_url}_"
                                        fresh_link = stb.getLink(url, try_mac, token, dummy_cmd, proxy)
                                        if fresh_link:
                                            fresh_token_match = re.search(r'play_token=([^&]+)', fresh_link)
                                            if fresh_token_match:
                                                new_token = fresh_token_match.group(1)
                                                test_link = re.sub(r'play_token=[^&]+', f'play_token={new_token}', test_link)
                                    if "mac=" in test_link:
                                        old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                        if old_mac_match:
                                            old_mac = old_mac_match.group(1)
                                            test_link = test_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                                else:
                                    test_link = cmd.split(" ")[1]
                                    if "mac=" in test_link:
                                        import re
                                        old_mac_match = re.search(r'mac=([0-9A-Fa-f:]+)', test_link)
                                        if old_mac_match:
                                            old_mac = old_mac_match.group(1)
                                            test_link = test_link.replace(f"mac={old_mac}", f"mac={try_mac}")
                                
                                if not test_link:
                                    # Harder penalty for no link
                                    try:
                                        stats = mac_stats.get(try_mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                        stats['fail'] += 2
                                        mac_stats[try_mac] = stats
                                        
                                        macs_with_data = []
                                        for m in available_macs:
                                            limit = mac_limits.get(m, 1)
                                            st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                            macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                        new_available_macs = ",".join(macs_with_data)
                                        
                                        conn_update = get_db_connection()
                                        cursor_update = conn_update.cursor()
                                        cursor_update.execute('''
                                            UPDATE channels 
                                            SET available_macs = ?
                                            WHERE portal = ? AND channel_id = ?
                                        ''', (new_available_macs, portalId, channelId))
                                        conn_update.commit()
                                        conn_update.close()
                                        logger.info(f"[HLS RETRY FALLBACK] Updated DB: MAC {try_mac} no link penalty (fail +2)")
                                    except Exception as e:
                                        logger.error(f"[HLS RETRY FALLBACK] Error updating DB: {e}")
                                    
                                    continue
                                
                                # Start HLS stream and test
                                stream_info = hls_manager.start_stream(portalId, channelId, test_link, proxy)
                                
                                # Monitor FFmpeg output
                                process = stream_info.get('process')
                                if process:
                                    stream_ready = monitor_ffmpeg_hls_output(process, timeout_seconds=hls_retry_timeout)
                                else:
                                    # Passthrough stream
                                    playlist_path = stream_info.get('playlist_path') or stream_info.get('master_playlist_path')
                                    stream_ready = False
                                    if playlist_path:
                                        max_wait_iterations = hls_retry_timeout * 10
                                        for wait_i in range(max_wait_iterations):
                                            if os.path.exists(playlist_path):
                                                stream_ready = True
                                                break
                                            time.sleep(0.1)
                                
                                if stream_ready:
                                    logger.info(f"[HLS RETRY FALLBACK] ✓ Busy MAC {try_mac} works!")
                                    mac_used = try_mac
                                    link = test_link
                                    
                                    # Update DB: Increment success count
                                    try:
                                        import time
                                        current_time = int(time.time())
                                        stats = mac_stats.get(try_mac, {'success': 0, 'fail': 0, 'last_ts': 0})
                                        stats['success'] += 1
                                        stats['last_ts'] = current_time
                                        mac_stats[try_mac] = stats
                                        
                                        macs_with_data = []
                                        for m in available_macs:
                                            limit = mac_limits.get(m, 1)
                                            st = mac_stats.get(m, {'success': 0, 'fail': 0, 'last_ts': 0})
                                            macs_with_data.append(f"{m}|{limit}|{st['success']}|{st['fail']}|{st['last_ts']}")
                                        new_available_macs = ",".join(macs_with_data)
                                        
                                        conn_update = get_db_connection()
                                        cursor_update = conn_update.cursor()
                                        cursor_update.execute('''
                                            UPDATE channels 
                                            SET available_macs = ?
                                            WHERE portal = ? AND channel_id = ?
                                        ''', (new_available_macs, portalId, channelId))
                                        conn_update.commit()
                                        conn_update.close()
                                        logger.info(f"[HLS RETRY FALLBACK] Updated DB: MAC {try_mac} success count: {stats['success']}")
                                    except Exception as e:
                                        logger.error(f"[HLS RETRY FALLBACK] Error updating DB: {e}")
                                    
                                    break
                                else:
                                    hls_manager.stop_stream(portalId, channelId)
                                    
                            except Exception as e:
                                logger.error(f"[HLS RETRY FALLBACK] Error with MAC {try_mac}: {e}")
                                try:
                                    hls_manager.stop_stream(portalId, channelId)
                                except:
                                    pass
                                continue
                    
                    if not mac_used:
                        logger.error(f"[HLS RETRY] All MACs failed for channel {channelId}")
                        return make_response("All MACs failed", 503)
                else:
                    # Auto Retry disabled: use first MAC, but skip busy ones if setting is enabled
                    mac_used = None
                    
                    if hls_skip_busy:
                        logger.info(f"HLS: Skip busy MACs enabled, checking {len(available_macs)} MAC(s)")
                        # Try to find first non-busy MAC
                        for try_mac in available_macs:
                            try:
                                token = get_token_cached(url, try_mac, proxy)
                                if token:
                                    profile = stb.getProfile(url, try_mac, token, proxy)
                                    # Validate watchdog_timeout field exists
                                    if 'watchdog_timeout' not in profile:
                                        logger.debug(f"HLS: MAC {try_mac} - watchdog_timeout missing, skipping")
                                        continue
                                    watchdog = profile['watchdog_timeout']
                                    if watchdog >= 60:
                                        mac_used = try_mac
                                        logger.info(f"HLS: Using non-busy MAC {mac_used} (watchdog: {watchdog}s)")
                                        break
                                    else:
                                        logger.debug(f"HLS: Skipping busy MAC {try_mac} (watchdog: {watchdog}s)")
                            except Exception as e:
                                logger.warning(f"HLS: Error checking MAC {try_mac}: {e}")
                                continue
                        
                        # Fallback: use first MAC even if busy
                        if not mac_used:
                            mac_used = available_macs[0]
                            logger.warning(f"HLS: All MACs busy, using first MAC {mac_used} as fallback")
                    else:
                        # Old behavior: use first MAC without checking
                        mac_used = available_macs[0]
                        logger.info(f"HLS: Using first MAC {mac_used} (skip busy disabled)")
            else:
                # Fallback: getAllChannels()
                logger.warning(f"HLS: Channel {channelId} not in DB, falling back")
                for try_mac in macs:
                    token = get_token_cached(url, try_mac, proxy)
                    if token:
                        stb.getProfile(url, try_mac, token, proxy)
                        channels = stb.getAllChannels(url, try_mac, token, proxy)
                        if channels:
                            for ch in channels:
                                if str(ch["id"]) == str(channelId):
                                    cmd = ch["cmd"]
                                    mac_used = try_mac
                                    break
                            if cmd:
                                break
        except Exception as e:
            logger.error(f"HLS: Error loading channel from DB: {e}")
        
        # If auto retry was used, link is already set
        if not (hls_auto_retry and link):
            # Generate link for non-retry mode
            if cmd and mac_used:
                try:
                    # Get token for the MAC that has the channel
                    token = stb.getToken(url, mac_used, proxy)
                    if token:
                        stb.getProfile(url, mac_used, token, proxy)
                        
                        if "http://localhost/" in cmd:
                            link = stb.getLink(url, mac_used, token, cmd, proxy)
                        else:
                            link = cmd.split(" ")[1]
                        
                        logger.info(f"Stream URL obtained from MAC {mac_used} for Channel {channelId}")
                except Exception as e:
                    logger.error(f"Error getting stream URL with MAC {mac_used}: {e}")
                logger.error(f"Error getting stream URL with MAC {mac_used}: {e}")
        
        if not link:
            logger.error(f"Could not get stream URL for Portal({portalId}):Channel({channelId})")
            return make_response("Stream not available", 503)
        
        # Start the HLS stream (skip if already started by auto retry)
        if not (hls_auto_retry and stream_key in hls_manager.streams):
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
        else:
            # Stream was already started by auto retry, just get the file
            logger.info(f"[HLS] Stream already started by auto retry, getting file {filename}")
            if filename.endswith('.m3u8'):
                # Wait for playlist
                for wait_count in range(100):
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
    
    # Serve the file
    if file_path and os.path.exists(file_path):
        logger.info(f"[HLS] Serving file: {file_path}")
        
        # Debug: Log playlist content
        if filename.endswith('.m3u8'):
            try:
                with open(file_path, 'r') as f:
                    playlist_content = f.read()
                    logger.debug(f"[HLS] Playlist content ({len(playlist_content)} bytes):\n{playlist_content[:500]}")
            except Exception as e:
                logger.error(f"[HLS] Error reading playlist: {e}")
        
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
        logger.warning(f"[HLS] File not found: {filename} for stream {stream_key} (file_path: {file_path})")
        return make_response("File not found", 404)


@app.route("/dashboard")
@authorise
def dashboard():
    return render_template("dashboard.html")

@app.route("/streaming")
@authorise
def streaming():
    return flask.jsonify(occupied)

# Store server start time
server_start_time = time.time()

@app.route("/dashboard/stats")
@authorise
def dashboard_stats():
    """Get dashboard statistics."""
    # Count total enabled channels from database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM channels WHERE enabled = 1')
    total_channels = cursor.fetchone()[0]
    conn.close()
    
    # Get last playlist update time
    global last_updated
    last_update_time = datetime.fromtimestamp(last_updated).isoformat() if last_updated > 0 else None
    
    # Calculate uptime
    uptime_seconds = int(time.time() - server_start_time)
    
    # Memory diagnostics
    import sys
    import os
    
    # Check XMLTV file size instead of RAM cache
    xmltv_file = os.path.join(log_dir, "epg.xml")
    xmltv_file_mb = 0
    if os.path.exists(xmltv_file):
        xmltv_file_mb = round(os.path.getsize(xmltv_file) / (1024*1024), 2)
    
    # CloudScraper status
    import stb
    cloudscraper_status = {
        "available": stb.CLOUDSCRAPER_AVAILABLE,
        "version": stb.CLOUDSCRAPER_VERSION if stb.CLOUDSCRAPER_AVAILABLE else None,
        "status": "✅ Active" if stb.CLOUDSCRAPER_AVAILABLE else "❌ Not Available"
    }
    
    # Get occupied stats thread-safe
    with occupied_lock:
        # Count total streams across all portals
        occupied_streams_count = sum(len(streams) for streams in occupied.values()) if occupied else 0
        occupied_portals_count = len(occupied.keys())
    
    memory_info = {
        "xmltv_file_mb": xmltv_file_mb,  # File size, not RAM
        "xmltv_in_ram": False,  # XMLTV no longer cached in RAM
        "occupied_streams": occupied_streams_count,
        "occupied_portals": occupied_portals_count,
        "hls_active_streams": len(hls_manager.streams) if hls_manager else 0,
    }
    
    return flask.jsonify({
        "total_channels": total_channels,
        "last_updated": last_update_time,
        "uptime_seconds": uptime_seconds,
        "memory_info": memory_info,
        "cloudscraper": cloudscraper_status
    })

@app.route("/log")
@authorise
def log():
    logFilePath = "/app/logs/MacReplayXC.log"
    
    try:
        # Check if file exists
        if not os.path.exists(logFilePath):
            # Create empty log file if it doesn't exist
            logger.info("Log file requested but not found - creating new log file")
            with open(logFilePath, 'w') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Log file created\n")
        
        with open(logFilePath, 'r') as f:
            log_content = f.read()
        
        if not log_content:
            return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Log file is empty - no logs yet"
        
        return log_content
    except FileNotFoundError:
        return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Log file not found at {logFilePath}"
    except PermissionError:
        return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Permission denied reading log file"
    except Exception as e:
        return f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] Error reading log file: {str(e)}"

def hdhr(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        settings = getSettings()
        security = settings["enable security"]
        username = settings["username"]
        password = settings["password"]
        hdhrenabled = settings["enable hdhr"]
        if (
            security == "false"
            or auth
            and auth.username == username
            and auth.password == password
        ):
            if hdhrenabled:
                return f(*args, **kwargs)
        return make_response("Error", 404)

    return decorated

@app.route("/discover.json", methods=["GET"])
@hdhr
def discover():
    logger.info("HDHR Status Requested.")
    settings = getSettings()
    name = settings["hdhr name"]
    id = settings["hdhr id"]
    tuners = settings["hdhr tuners"]
    data = {
        "BaseURL": host,
        "DeviceAuth": name,
        "DeviceID": id,
        "FirmwareName": "MacReplayXC",
        "FirmwareVersion": "666",
        "FriendlyName": name,
        "LineupURL": host + "/lineup.json",
        "Manufacturer": "Evilvirus",
        "ModelNumber": "666",
        "TunerCount": int(tuners),
    }
    return flask.jsonify(data)

@app.route("/lineup_status.json", methods=["GET"])
@hdhr
def status():
    data = {
        "ScanInProgress": 0,
        "ScanPossible": 0,
        "Source": "Cable",
        "SourceList": ["Cable"],
    }
    return flask.jsonify(data)

def refresh_lineup():
    global cached_lineup
    logger.info("Refreshing Lineup from database...")
    lineup = []
    
    # Get enabled channels from database (single source of truth)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT portal, channel_id, name, custom_name, number, custom_number
            FROM channels 
            WHERE enabled = 1
            ORDER BY portal, CAST(COALESCE(custom_number, number, '0') AS INTEGER)
        ''')
        db_channels = cursor.fetchall()
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass
    
    # Get portal info
    portals = getPortals()
    
    # Get external host configuration
    external_host, external_scheme = get_external_host_config()
    host = external_host or request.host or "0.0.0.0:8001"
    
    for channel in db_channels:
        portal_id = channel['portal']
        channel_id = str(channel['channel_id'])
        
        # Check if portal is enabled
        if portal_id not in portals or portals[portal_id].get("enabled") != "true":
            continue
        
        # Use custom values if available, otherwise use original values
        channel_name = channel['custom_name'] if channel['custom_name'] else (channel['name'] or "Unknown Channel")
        channel_number = channel['custom_number'] if channel['custom_number'] else (channel['number'] or "0")
        
        lineup.append({
            "GuideNumber": str(channel_number),
            "GuideName": channel_name,
            "URL": f"{external_scheme or 'http'}://{host}/play/{portal_id}/{channel_id}"
        })
    
    # Sort by channel number
    try:
        lineup.sort(key=lambda x: int(x["GuideNumber"]))
    except:
        lineup.sort(key=lambda x: x["GuideNumber"])
    
    cached_lineup = lineup
    logger.info(f"Lineup refreshed from database - {len(lineup)} channels")
    
@app.route("/lineup.json", methods=["GET"])
@app.route("/lineup.post", methods=["POST"])
@hdhr
def lineup():
    logger.info("Lineup Requested")
    if not cached_lineup:
        refresh_lineup()
    logger.info("Lineup Delivered")
    return jsonify(cached_lineup)

@app.route("/refresh_lineup", methods=["POST"])
@authorise
def refresh_lineup_endpoint():
    try:
        refresh_lineup()
        logger.info("Lineup refreshed via dashboard")
        return jsonify({"status": "Lineup refreshed successfully"})
    except Exception as e:
        logger.error(f"Error refreshing lineup: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cache/clear", methods=["POST"])
@authorise
def cache_clear():
    """Clear all caches (lineup, playlist, EPG, channels.db)."""
    try:
        global cached_lineup, cached_playlist, last_playlist_host
        
        # Clear channels.db (stream_cmd and available_macs)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE channels SET stream_cmd = NULL, available_macs = NULL')
            db_cleared = cursor.rowcount
            conn.commit()
            conn.close()
            logger.info(f"Cleared stream_cmd and available_macs from {db_cleared} channels in DB")
        except Exception as e:
            logger.error(f"Error clearing channels.db: {e}")
            db_cleared = 0
        
        # Clear lineup cache
        cached_lineup = []
        
        # Clear playlist cache
        cached_playlist = None
        last_playlist_host = None
        
        logger.info(f"All caches cleared via dashboard ({db_cleared} DB entries)")
        return jsonify({
            "success": True, 
            "message": f"Cache cleared successfully ({db_cleared} DB entries)",
            "cleared_entries": db_cleared
        })
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/cache/stats", methods=["GET"])
@authorise
def cache_stats():
    """Get cache statistics."""
    try:
        # Return DB-based stats instead of channel_cache
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Count channels with stream data
        cursor.execute('SELECT COUNT(*) FROM channels WHERE stream_cmd IS NOT NULL')
        cached_channels = cursor.fetchone()[0]
        
        # Count total channels in DB
        cursor.execute('SELECT COUNT(*) FROM channels')
        total_channels = cursor.fetchone()[0]
        
        # Count enabled channels
        cursor.execute('SELECT COUNT(*) FROM channels WHERE enabled = 1')
        enabled_channels = cursor.fetchone()[0]
        
        conn.close()
        
        stats = {
            "mode": "db-direct",
            "cached_channels": cached_channels,
            "total_channels": total_channels,
            "enabled_channels": enabled_channels,
            "cache_duration": "persistent"
        }
        
        return jsonify({
            "success": True,
            "stats": stats
        })
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/cache/vacuum", methods=["POST"])
@authorise
def cache_vacuum():
    """Run VACUUM on channels.db and vods.db to reclaim disk space."""
    try:
        results = {}
        
        # VACUUM channels.db
        try:
            conn = get_db_connection()
            
            # Get size before VACUUM
            cursor = conn.cursor()
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size_before = cursor.fetchone()[0]
            
            # Run VACUUM
            cursor.execute("VACUUM")
            conn.commit()
            
            # Get size after VACUUM
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size_after = cursor.fetchone()[0]
            
            conn.close()
            
            saved_bytes = size_before - size_after
            saved_mb = saved_bytes / (1024 * 1024)
            
            results['channels_db'] = {
                'success': True,
                'size_before_mb': round(size_before / (1024 * 1024), 2),
                'size_after_mb': round(size_after / (1024 * 1024), 2),
                'saved_mb': round(saved_mb, 2)
            }
            
            logger.info(f"VACUUM channels.db: {results['channels_db']['size_before_mb']} MB → {results['channels_db']['size_after_mb']} MB (saved {results['channels_db']['saved_mb']} MB)")
        except Exception as e:
            logger.error(f"Error running VACUUM on channels.db: {e}")
            results['channels_db'] = {'success': False, 'error': str(e)}
        
        # VACUUM vods.db
        try:
            conn = get_vod_db_connection()
            
            # Get size before VACUUM
            cursor = conn.cursor()
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size_before = cursor.fetchone()[0]
            
            # Run VACUUM
            cursor.execute("VACUUM")
            conn.commit()
            
            # Get size after VACUUM
            cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size_after = cursor.fetchone()[0]
            
            conn.close()
            
            saved_bytes = size_before - size_after
            saved_mb = saved_bytes / (1024 * 1024)
            
            results['vods_db'] = {
                'success': True,
                'size_before_mb': round(size_before / (1024 * 1024), 2),
                'size_after_mb': round(size_after / (1024 * 1024), 2),
                'saved_mb': round(saved_mb, 2)
            }
            
            logger.info(f"VACUUM vods.db: {results['vods_db']['size_before_mb']} MB → {results['vods_db']['size_after_mb']} MB (saved {results['vods_db']['saved_mb']} MB)")
        except Exception as e:
            logger.error(f"Error running VACUUM on vods.db: {e}")
            results['vods_db'] = {'success': False, 'error': str(e)}
        
        # Calculate total savings
        total_saved = 0
        if results['channels_db'].get('success'):
            total_saved += results['channels_db']['saved_mb']
        if results['vods_db'].get('success'):
            total_saved += results['vods_db']['saved_mb']
        
        return jsonify({
            "success": True,
            "message": f"VACUUM completed - reclaimed {round(total_saved, 2)} MB total",
            "results": results,
            "total_saved_mb": round(total_saved, 2)
        })
    except Exception as e:
        logger.error(f"Error in cache_vacuum: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/logs/recent", methods=["GET"])
@authorise
def get_recent_logs():
    """Get recent log entries for live log display."""
    try:
        # Use existing log() function to get log content
        log_content = log()
        
        # Split into lines and get last 200 (increased from 50)
        lines = log_content.split('\n')
        recent_lines = lines[-200:] if len(lines) > 200 else lines
        
        logs = []
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
                
            # Parse log format: "2024-01-01 12:00:00,123 [LEVEL] message"
            try:
                if ' [' in line and '] ' in line:
                    # Split at first occurrence of ' ['
                    parts = line.split(' [', 1)
                    timestamp_part = parts[0]
                    
                    # Split at first occurrence of '] '
                    rest = parts[1]
                    level_and_message = rest.split('] ', 1)
                    
                    if len(level_and_message) >= 2:
                        level_part = level_and_message[0]
                        message_part = level_and_message[1]
                    else:
                        # No message after level
                        level_part = level_and_message[0]
                        message_part = ""
                    
                    logs.append({
                        'timestamp': timestamp_part,
                        'level': level_part,
                        'message': message_part
                    })
                else:
                    # Fallback for lines that don't match format
                    logs.append({
                        'timestamp': datetime.now().isoformat(),
                        'level': 'INFO',
                        'message': line
                    })
            except Exception as e:
                # Skip malformed lines
                logger.debug(f"Failed to parse log line: {line[:50]}... Error: {e}")
                continue
        
        return jsonify(logs)
        
    except Exception as e:
        logger.error(f"Error reading recent logs: {e}")
        return jsonify([])


@app.route("/api/logs/clear", methods=["POST"])
@authorise
def clear_logs():
    """Clear the log file."""
    try:
        logFilePath = "/app/logs/MacReplayXC.log"
        
        # Truncate log file (keep file but clear content)
        with open(logFilePath, 'w') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFO] Log file cleared by user\n")
        
        logger.info("Log file cleared by user via web UI")
        return jsonify({"success": True, "message": "Log file cleared"})
        
    except Exception as e:
        logger.error(f"Error clearing log file: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


def start_refresh():
    threading.Thread(target=refresh_lineup, daemon=True).start()
    threading.Thread(target=refresh_xmltv, daemon=True).start()


@app.route("/proxy/test", methods=["POST"])
@authorise
def proxy_test():
    """Test proxy connectivity and functionality."""
    try:
        data = request.json
        proxy_url = data.get('proxy_url', '').strip()
        test_url = data.get('test_url', 'http://httpbin.org/ip')
        
        if not proxy_url:
            return flask.jsonify({"error": "No proxy URL provided"}), 400
        
        # Test 1: Validation
        is_valid = validate_proxy_url(proxy_url)
        proxy_type = get_proxy_type(proxy_url)
        
        result = {
            "proxy_url": proxy_url,
            "proxy_type": proxy_type,
            "valid": is_valid,
            "tests": {}
        }
        
        if not is_valid:
            result["error"] = f"Invalid proxy format. Detected type: {proxy_type}"
            return flask.jsonify(result), 400
        
        # Test 2: Parse proxy
        try:
            parsed_proxy = parse_proxy_url(proxy_url)
            result["parsed"] = parsed_proxy
            result["tests"]["parsing"] = {"success": True, "message": "Proxy URL parsed successfully"}
        except Exception as e:
            result["tests"]["parsing"] = {"success": False, "error": str(e)}
            return flask.jsonify(result), 500
        
        # Test 3: HTTP connectivity test
        try:
            import requests
            
            # For SOCKS proxies, ensure we have the right dependencies and use HTTP
            if proxy_type in ['socks5', 'socks4']:
                try:
                    import socks
                except ImportError:
                    result["tests"]["connectivity"] = {
                        "success": False, 
                        "error": "PySocks library not available. Install with: pip install requests[socks]"
                    }
                    return flask.jsonify(result), 500
                
                # Use HTTP instead of HTTPS for SOCKS to avoid SSL issues
                if test_url.startswith('https://'):
                    test_url = test_url.replace('https://', 'http://')
            
            response = requests.get(test_url, proxies=parsed_proxy, timeout=10)
            
            if response.status_code == 200:
                try:
                    # Try JSON first (httpbin.org/ip format)
                    data = response.json()
                    external_ip = data.get('origin', 'Unknown')
                    result["tests"]["connectivity"] = {
                        "success": True, 
                        "message": f"Connection successful via proxy",
                        "external_ip": external_ip,
                        "status_code": response.status_code
                    }
                except:
                    # Fallback to plain text (ipinfo.io/ip format)
                    external_ip = response.text.strip()
                    if external_ip and len(external_ip) < 50:  # Reasonable IP length
                        result["tests"]["connectivity"] = {
                            "success": True, 
                            "message": f"Connection successful via proxy",
                            "external_ip": external_ip,
                            "status_code": response.status_code
                        }
                    else:
                        result["tests"]["connectivity"] = {
                            "success": True, 
                            "message": f"Connection successful via proxy",
                            "status_code": response.status_code,
                            "response_preview": response.text[:100]
                        }
            else:
                result["tests"]["connectivity"] = {
                    "success": False, 
                    "error": f"HTTP {response.status_code}",
                    "status_code": response.status_code
                }
        except requests.exceptions.ProxyError as e:
            result["tests"]["connectivity"] = {"success": False, "error": f"Proxy error: {str(e)}"}
        except requests.exceptions.ConnectTimeout:
            result["tests"]["connectivity"] = {"success": False, "error": "Connection timeout"}
        except requests.exceptions.ConnectionError as e:
            result["tests"]["connectivity"] = {"success": False, "error": f"Connection error: {str(e)}"}
        except Exception as e:
            result["tests"]["connectivity"] = {"success": False, "error": f"Unexpected error: {str(e)}"}
        
        # Test 4: Shadowsocks specific test (if applicable)
        if proxy_type == 'shadowsocks':
            try:
                # Try to import shadowsocks library
                import shadowsocks
                result["tests"]["shadowsocks_library"] = {"success": True, "message": "Shadowsocks library available"}
                
                # Additional Shadowsocks connectivity test could go here
                result["tests"]["shadowsocks_connectivity"] = {
                    "success": True, 
                    "message": "Shadowsocks library detected, basic validation passed"
                }
            except ImportError:
                result["tests"]["shadowsocks_library"] = {
                    "success": False, 
                    "error": "Shadowsocks library not available. Install with: pip install shadowsocks==2.8.2"
                }
            except Exception as e:
                result["tests"]["shadowsocks_connectivity"] = {"success": False, "error": str(e)}
        
        # Overall success
        all_tests_passed = all(
            test.get("success", False) 
            for test in result["tests"].values()
        )
        result["overall_success"] = all_tests_passed
        
        return flask.jsonify(result)
        
    except Exception as e:
        logger.error(f"Error in proxy_test: {e}")
        return flask.jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    config = loadConfig()
    
    # Initialize the database
    init_db()
    
    # Initialize the VOD database
    init_vod_db()
    
    # Check if database has any channels
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM channels")
    count = cursor.fetchone()[0]
    conn.close()
    
    # If no channels in database, refresh from portals
    if count == 0:
        logger.info("No channels in database, fetching from portals...")
        refresh_channels_cache()
    
    # Auto Line Refresh deaktiviert - wird über Settings konfiguriert
    # start_refresh()  # Deaktiviert für v2.4.1
    
    # Initialize HLS stream manager with settings
    settings = getSettings()
    
    # Parse HLS settings with error handling
    try:
        max_streams = int(settings.get("hls max streams", "10"))
    except (ValueError, TypeError):
        max_streams = 10
        logger.warning("Invalid 'hls max streams' value, using default: 10")
    
    try:
        inactive_timeout = int(settings.get("hls inactive timeout", "30"))
    except (ValueError, TypeError):
        inactive_timeout = 30
        logger.warning("Invalid 'hls inactive timeout' value, using default: 30")
    
    hls_manager = HLSStreamManager(max_streams=max_streams, inactive_timeout=inactive_timeout)
    hls_manager.start_monitoring()
    logger.info(f"HLS Stream Manager initialized (max_streams={max_streams}, timeout={inactive_timeout}s)")
    
    # Start periodic cleanup of recent_redirects dictionary
    logger.info("Starting periodic memory cleanup for recent_redirects (every 30 minutes)")
    cleanup_recent_redirects()
    
    # Channel-Cache läuft unbegrenzt - nur manueller Refresh über Dashboard
    # Kein automatischer Cleanup - maximale Performance
    logger.info("Channel cache runs indefinitely - manual refresh only via Dashboard")
    
    # Start automatic log cleanup (every 6 hours, deletes logs older than 24 hours)
    logger.info("Starting automatic log cleanup (every 6 hours, deletes logs older than 24 hours)")
    schedule_log_cleanup()
    
    # Start automatic cleanup of occupied streams dictionary (memory leak prevention)
    logger.info("Starting automatic cleanup of occupied streams (every 3 minutes)")
    cleanup_occupied_streams()
    
    # Start automatic cleanup of recent_redirects dictionary (memory leak prevention)
    logger.info("Starting automatic cleanup of recent_redirects (every 30 minutes)")
    cleanup_recent_redirects()
    
    # Start automatic token refresh for active streams (prevents token expiration)
    logger.info("Starting automatic token refresh for active streams (every 50 minutes)")
    refresh_tokens_for_active_streams()
    
    # Start automatic EPG refresh scheduler (if enabled)
    start_epg_auto_refresh_scheduler()
    
    # Waitress Performance Configuration
    # Optimized for high-performance streaming and concurrent requests
    logger.info("Starting Waitress server on 0.0.0.0:8001")
    logger.info("Performance: 48 threads, 8192 channel timeout, 1MB buffers")
    
    waitress.serve(
        app,
        host="0.0.0.0",
        port=8001,
        threads=48,                    # Increased from 24 to 48 for better concurrency
        channel_timeout=8192,          # Increased timeout for long-running streams (2+ hours)
        recv_bytes=1048576,            # 1MB receive buffer (better for large requests)
        send_bytes=1048576,            # 1MB send buffer (better for streaming)
        outbuf_overflow=2097152,       # 2MB overflow buffer (prevents blocking)
        inbuf_overflow=1048576,        # 1MB input overflow buffer
        connection_limit=1000,         # Max 1000 concurrent connections
        cleanup_interval=30,           # Cleanup idle connections every 30s
        asyncore_use_poll=True,        # Use poll() instead of select() (better performance)
        _quiet=True
    )
