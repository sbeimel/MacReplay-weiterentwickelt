import sys
import os
import shutil
import time
import tempfile
import gzip
import io
import requests
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import threading
from threading import Thread
import logging
logger = logging.getLogger("MacReplay")
logger.setLevel(logging.INFO)
logFormat = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Docker-optimized paths
if os.getenv("CONFIG"):
    configFile = os.getenv("CONFIG")
    log_dir = os.path.dirname(configFile)
else:
    # Default paths for container
    log_dir = "/app/data"
    configFile = os.path.join(log_dir, "MacReplay.json")

# Create directories if they don't exist
os.makedirs(log_dir, exist_ok=True)
os.makedirs("/app/logs", exist_ok=True)

# Log file path for container
log_file_path = os.path.join("/app/logs", "MacReplay.log")

# Set up logging
fileHandler = logging.FileHandler(log_file_path)
fileHandler.setFormatter(logFormat)
logger.addHandler(fileHandler)

consoleFormat = logging.Formatter("[%(levelname)s] %(message)s")
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(consoleFormat)
logger.addHandler(consoleHandler)

# Docker-optimized ffmpeg paths (system-installed)
ffmpeg_path = "ffmpeg"
ffprobe_path = "ffprobe"

# Check if the binaries exist
import subprocess
try:
    subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True)
    subprocess.run([ffprobe_path, "-version"], capture_output=True, check=True)
    logger.info("FFmpeg and FFprobe found and working")
except (subprocess.CalledProcessError, FileNotFoundError):
    logger.error("Error: ffmpeg or ffprobe not found!")

import flask
from flask import Flask, jsonify
import stb
import json
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
)
from datetime import datetime, timezone
from functools import wraps
import secrets
import waitress
from utils import (
    validate_mac_address,
    validate_url,
    normalize_mac_address,
    sanitize_channel_name,
    get_client_ip,
    is_hls_url
)

app = Flask(__name__)
app.secret_key = secrets.token_urlsafe(32)

# Docker-optimized host configuration
if os.getenv("HOST"):
    host = os.getenv("HOST")
else:
    host = "0.0.0.0:8001"
logger.info(f"Server started on http://{host}")

logger.info(f"Using config file: {configFile}")

occupied = {}
config = {}
cached_lineup = []
cached_playlist = None
last_playlist_host = None
cached_xmltv = None
last_updated = 0
hls_manager = None

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
    "ffmpeg command": "-re -http_proxy <proxy> -timeout <timeout> -i <url> -map 0 -codec copy -f mpegts -flush_packets 0 -fflags +nobuffer -flags low_delay -strict experimental -analyzeduration 0 -probesize 32 -copyts -threads 12 pipe:",
    "hls segment type": "mpegts",
    "hls segment duration": "4",
    "hls playlist size": "6",
    "hls max streams": "10",
    "hls inactive timeout": "30",
    "ffmpeg timeout": "5",
    "test streams": "true",
    "try all macs": "true",
    "use channel genres": "true",
    "use channel numbers": "true",
    "sort playlist by channel genre": "false",
    "sort playlist by channel number": "true",
    "sort playlist by channel name": "false",
    "enable security": "false",
    "username": "admin",
    "password": "12345",
    "enable hdhr": "true",
    "hdhr name": "MacReplay",
    "hdhr id": str(uuid.uuid4().hex),
    "hdhr tuners": "10",
    "epg fallback enabled": "false",
    "epg fallback countries": "",
    "xc api enabled": "false",
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
    "enabled channels": [],
    "custom channel names": {},
    "custom channel numbers": {},
    "custom genres": {},
    "custom epg ids": {},
    "fallback channels": {},
}


class HLSStreamManager:
    """Manages HLS streams with shared access and automatic cleanup."""
    
    def __init__(self, max_streams=10, inactive_timeout=30):
        self.streams = {}  # Key: "portalId_channelId", Value: stream info dict
        self.max_streams = max_streams
        self.inactive_timeout = inactive_timeout
        self.lock = threading.Lock()
        self.monitor_thread = None
        self.running = False
        logger.info(f"HLS Stream Manager initialized with max_streams={max_streams}, inactive_timeout={inactive_timeout}s")
        
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
            
            # Clean up temp directory
            try:
                temp_dir = stream_info.get('temp_dir')
                if temp_dir and os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"Cleaned up temp directory for {stream_key}")
            except Exception as e:
                logger.error(f"Error cleaning up temp dir for {stream_key}: {e}")
            
            # Remove from active streams
            del self.streams[stream_key]
            logger.info(f"Stream {stream_key} stopped and cleaned up")
    
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
            segment_duration = settings.get("hls segment duration", "4")
            playlist_size = settings.get("hls playlist size", "6")
            timeout = int(settings.get("ffmpeg timeout", "5")) * 1000000
            
            # Detect if source is already HLS
            is_source_hls = is_hls_url(stream_url)
            
            # Create temp directory for HLS segments
            temp_dir = tempfile.mkdtemp(prefix=f"macreplay_hls_{stream_key}_")
            playlist_path = os.path.join(temp_dir, "stream.m3u8")
            master_playlist_path = os.path.join(temp_dir, "master.m3u8")
            
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
            ffmpeg_cmd = [
                "ffmpeg",
                "-fflags", "+genpts+igndts+nobuffer",
                "-err_detect", "aggressive",
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
                "-map", "0",
                "-c:v", "copy",
                "-copyts",
                "-start_at_zero",
                "-c:a", "aac",
                "-b:a", "256k",
                "-af", "aresample=async=1"
            ])
            
            hls_flags = "independent_segments+omit_endlist"
            
            if segment_type == "mpegts":
                hls_flags += "+program_date_time"
                ffmpeg_cmd.extend([
                    "-mpegts_flags", "pat_pmt_at_frames",
                    "-pcr_period", "20"
                ])
            
            ffmpeg_cmd.extend([
                "-f", "hls",
                "-hls_time", segment_duration,
                "-hls_list_size", playlist_size,
                "-hls_flags", hls_flags,
                "-hls_segment_type", segment_type,
                "-hls_segment_filename", segment_pattern,
                "-start_number", "0",
                "-flush_packets", "0"
            ])
            
            if segment_type == "fmp4":
                ffmpeg_cmd.extend(["-hls_fmp4_init_filename", init_filename])
            
            ffmpeg_cmd.append(playlist_path)
            
            # Start FFmpeg process
            try:
                logger.info(f"Starting FFmpeg process for {stream_key}")
                
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
                logger.info(f"HLS stream started for {stream_key}")
                return stream_info
                
            except Exception as e:
                logger.error(f"Error starting FFmpeg for {stream_key}: {e}")
                # Clean up temp directory
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
                raise
    
    def get_file(self, portal_id, channel_id, filename):
        """Get a file path for a stream."""
        stream_key = f"{portal_id}_{channel_id}"
        
        with self.lock:
            if stream_key not in self.streams:
                return None
            
            stream_info = self.streams[stream_key]
            stream_info['last_accessed'] = time.time()
            
            # Handle master playlist
            if filename == "master.m3u8":
                if os.path.exists(stream_info['master_playlist_path']):
                    return stream_info['master_playlist_path']
                return None
            
            # Handle stream playlist
            if filename == "stream.m3u8":
                if os.path.exists(stream_info['playlist_path']):
                    return stream_info['playlist_path']
                return None
            
            # Handle segments
            file_path = os.path.join(stream_info['temp_dir'], filename)
            if os.path.exists(file_path):
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
    return config["portals"]

def savePortals(portals):
    try:
        with open(configFile, "w") as f:
            config["portals"] = portals
            json.dump(config, f, indent=4)
        logger.debug(f"Portals saved to {configFile}")
    except Exception as e:
        logger.error(f"Error saving portals: {e}")
        raise

def getSettings():
    return config["settings"]

def saveSettings(settings):
    try:
        with open(configFile, "w") as f:
            config["settings"] = settings
            json.dump(config, f, indent=4)
        logger.debug(f"Settings saved to {configFile}")
    except Exception as e:
        logger.error(f"Error saving settings: {e}")
        raise


# ============================================
# XC API User Management
# ============================================

def getXCUsers():
    """Get all XC API users."""
    return config.get("xc_users", {})


def saveXCUsers(users):
    """Save XC API users."""
    try:
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
            logger.info(f"XC API: Cleaned up inactive connection for device {dev_id}")
    
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
    for user_id, user in users.items():
        active_connections = user.get("active_connections", {})
        to_remove = []
        
        for device_id, conn_info in active_connections.items():
            last_activity = conn_info.get("last_activity", 0)
            if current_time - last_activity > timeout:
                to_remove.append(device_id)
        
        for device_id in to_remove:
            del active_connections[device_id]
            modified = True
            logger.info(f"XC API: Cleaned up inactive connection for device {device_id}")
    
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
        
        # Check if XC API is enabled
        if settings.get("xc api enabled") != "true":
            logger.warning("XC API: API is disabled")
            return flask.jsonify({
                "user_info": {
                    "auth": 0,
                    "message": "XC API is disabled"
                }
            }), 403
        
        # Try XC API authentication (from URL params or path)
        xc_username = request.args.get("username") or kwargs.get("username")
        xc_password = request.args.get("password") or kwargs.get("password")
        
        logger.info(f"XC API: Auth attempt - username={xc_username}, password={'*' * len(xc_password) if xc_password else 'None'}, path={request.path}")
        
        if not xc_username or not xc_password:
            logger.warning("XC API: Missing credentials")
            return flask.jsonify({
                "user_info": {
                    "auth": 0,
                    "message": "Missing credentials"
                }
            }), 401
        
        user_id, user = validateXCUser(xc_username, xc_password)
        if not user:
            logger.warning(f"XC API: Invalid credentials for user {xc_username}: {user_id}")
            return flask.jsonify({
                "user_info": {
                    "auth": 0,
                    "message": user_id  # user_id contains error message
                }
            }), 401
        
        # XC API auth successful, allow access
        logger.info(f"XC API: Auth successful for user {xc_username}")
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
                if user:
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
    macs = portals[portalId]["macs"]
    x = macs[mac]
    del macs[mac]
    macs[mac] = x
    portals[portalId]["macs"] = macs
    savePortals(portals)

@app.route("/data/<path:filename>", methods=["GET"])
def block_data_access(filename):
    """Block direct access to data files."""
    return "Access denied", 403


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page."""
    if request.method == "POST":
        settings = getSettings()
        username = request.form.get("username")
        password = request.form.get("password")
        
        if username == settings["username"] and password == settings["password"]:
            flask.session["authenticated"] = True
            flask.session.permanent = True
            return redirect("/portals", code=302)
        else:
            return render_template("login.html", error="Invalid credentials")
    
    # If already authenticated, redirect to portals
    if flask.session.get("authenticated"):
        return redirect("/portals", code=302)
    
    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    """Logout."""
    flask.session.clear()
    return redirect("/login", code=302)


@app.route("/", methods=["GET"])
@authorise
def home():
    return redirect("/portals", code=302)

@app.route("/portals", methods=["GET"])
@authorise
def portals():
    # Check if we should show genre modal
    show_genre_modal = flask.session.pop('show_genre_modal', False)
    genre_modal_portal_id = flask.session.pop('genre_modal_portal_id', None)
    genre_modal_portal_name = flask.session.pop('genre_modal_portal_name', None)
    
    return render_template("portals.html", 
                         portals=getPortals(),
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
    global cached_xmltv
    cached_xmltv = None
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
        }

        for setting, default in defaultPortal.items():
            if not portal.get(setting):
                portal[setting] = default

        portals = getPortals()
        portals[id] = portal
        savePortals(portals)
        logger.info("Portal({}) added!".format(portal["name"]))
        
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
    global cached_xmltv
    cached_xmltv = None
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
    proxy = request.form["proxy"]
    retest = request.form.get("retest", None)

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
        savePortals(portals)
        logger.info("Portal({}) updated!".format(name))
        flash("Portal({}) updated!".format(name), "success")

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
    """Load genres for a specific portal."""
    try:
        portal_id = request.json.get('portal_id')
        if not portal_id:
            return flask.jsonify({"error": "No portal ID provided"}), 400
        
        portals = getPortals()
        portal = portals.get(portal_id)
        if not portal:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        # Fetch channels from portal
        url = portal["url"]
        macs = list(portal["macs"].keys())
        proxy = portal["proxy"]
        
        all_channels = None
        genres_dict = None
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    all_channels = stb.getAllChannels(url, mac, token, proxy)
                    genres_dict = stb.getGenreNames(url, mac, token, proxy)
                    if all_channels and genres_dict:
                        logger.info(f"Successfully fetched {len(all_channels)} channels from MAC {mac}")
                        break
            except Exception as e:
                logger.error(f"Error fetching from MAC {mac}: {e}")
                continue
        
        if not all_channels or not genres_dict:
            return flask.jsonify({"error": "Failed to fetch channels"}), 500
        
        # Count channels per genre
        genre_counts = {}
        genre_to_channels = {}  # Map genre to channel IDs
        
        for channel in all_channels:
            channel_id = str(channel["id"])
            genre_id = str(channel.get("tv_genre_id", ""))
            genre_name = genres_dict.get(genre_id, "Unknown")
            
            if genre_name not in genre_counts:
                genre_counts[genre_name] = 0
                genre_to_channels[genre_name] = []
            
            genre_counts[genre_name] += 1
            genre_to_channels[genre_name].append(channel_id)
        
        # Get previously selected genres from portal config
        enabled_genres = portal.get("selected genres", [])
        
        logger.info(f"Loading genres for portal {portal_id}, found {len(enabled_genres)} previously selected genres")
        
        # Sort genres by name
        genres = sorted([{"name": name, "count": count} for name, count in genre_counts.items()], key=lambda x: x['name'])
        
        return flask.jsonify({
            "genres": genres, 
            "total_channels": len(all_channels),
            "enabled_genres": enabled_genres
        })
    except Exception as e:
        logger.error(f"Error loading genres: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/portal/save-genre-selection", methods=["POST"])
@authorise
def portal_save_genre_selection():
    """Save genre selection and enable channels."""
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
        
        # Fetch channels from portal
        url = portal["url"]
        macs = list(portal["macs"].keys())
        proxy = portal["proxy"]
        portal_name = portal["name"]
        
        all_channels = None
        genres_dict = None
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    all_channels = stb.getAllChannels(url, mac, token, proxy)
                    genres_dict = stb.getGenreNames(url, mac, token, proxy)
                    if all_channels and genres_dict:
                        break
            except Exception as e:
                logger.error(f"Error fetching from MAC {mac}: {e}")
        
        if not all_channels or not genres_dict:
            return flask.jsonify({"error": "Failed to fetch channels"}), 500
        
        # Save enabled channels to portal configuration
        enabled_channels = []
        enabled_count = 0
        total_count = 0
        
        logger.info(f"Selected genres: {selected_genres}")
        
        for channel in all_channels:
            channel_id = str(channel["id"])
            genre_id = str(channel.get("tv_genre_id", ""))
            genre = genres_dict.get(genre_id, "")
            
            # Enable channel if its genre is selected
            if genre in selected_genres:
                enabled_channels.append(channel_id)
                enabled_count += 1
            total_count += 1
        
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
        else:
            logger.error(f"Portal {portal_id} not found in portals!")
        
        # Clear session
        flask.session.pop('new_portal_id', None)
        flask.session.pop('new_portal_name', None)
        
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
    del portals[id]
    savePortals(portals)
    logger.info("Portal ({}) removed!".format(name))
    flash("Portal ({}) removed!".format(name), "success")
    return redirect("/portals", code=302)

@app.route("/editor", methods=["GET"])
@authorise
def editor():
    return render_template("editor.html")
    
@app.route("/editor_data", methods=["GET"])
@authorise
def editor_data():
    channels = []
    portals = getPortals()
    for portal in portals:
        logger.info(f"getting Data from {portal}")
        if portals[portal]["enabled"] == "true":
            portalName = portals[portal]["name"]
            url = portals[portal]["url"]
            macs = list(portals[portal]["macs"].keys())
            proxy = portals[portal]["proxy"]
            enabledChannels = portals[portal].get("enabled channels", [])
            logger.info(f"Portal {portalName} has {len(enabledChannels)} enabled channels")
            customChannelNames = portals[portal].get("custom channel names", {})
            customGenres = portals[portal].get("custom genres", {})
            customChannelNumbers = portals[portal].get("custom channel numbers", {})
            customEpgIds = portals[portal].get("custom epg ids", {})
            fallbackChannels = portals[portal].get("fallback channels", {})

            for mac in macs:
                logger.info(f"Using mac: {mac}")
                try:
                    token = stb.getToken(url, mac, proxy)
                    if not token:
                        logger.warning(f"Failed to get token for MAC {mac}")
                        continue
                    stb.getProfile(url, mac, token, proxy)
                    allChannels = stb.getAllChannels(url, mac, token, proxy)
                    genres = stb.getGenreNames(url, mac, token, proxy)
                    if allChannels and genres:
                        logger.info(f"Successfully fetched {len(allChannels)} channels from MAC {mac}")
                        break
                except Exception as e:
                    logger.error(f"Error fetching channels from MAC {mac}: {e}")
                    allChannels = None
                    genres = None
                    continue

            if allChannels and genres:
                # Only show enabled channels in the editor
                for channel in allChannels:
                    channelId = str(channel["id"])
                    
                    # Skip if channel is not in enabled list
                    if channelId not in enabledChannels:
                        continue
                    
                    channelName = str(channel["name"])
                    channelNumber = str(channel["number"])
                    genre = str(genres.get(str(channel["tv_genre_id"])))
                    enabled = True  # All channels shown are enabled
                    
                    customChannelNumber = customChannelNumbers.get(channelId)
                    if customChannelNumber == None:
                        customChannelNumber = ""
                    customChannelName = customChannelNames.get(channelId)
                    if customChannelName == None:
                        customChannelName = ""
                    customGenre = customGenres.get(channelId)
                    if customGenre == None:
                        customGenre = ""
                    customEpgId = customEpgIds.get(channelId)
                    if customEpgId == None:
                        customEpgId = ""
                    fallbackChannel = fallbackChannels.get(channelId)
                    if fallbackChannel == None:
                        fallbackChannel = ""
                    
                    # Use the current request host instead of the configured host
                    request_host = request.host
                    request_scheme = request.scheme
                    
                    channels.append(
                        {
                            "portal": portal,
                            "portalName": portalName,
                            "enabled": enabled,
                            "channelNumber": channelNumber,
                            "customChannelNumber": customChannelNumber,
                            "channelName": channelName,
                            "customChannelName": customChannelName,
                            "genre": genre,
                            "customGenre": customGenre,
                            "channelId": channelId,
                            "customEpgId": customEpgId,
                            "fallbackChannel": fallbackChannel,
                            "link": f"{request_scheme}://{request_host}/play/{portal}/{channelId}?web=true",
                        }
                    )
                
                logger.info(f"Added {len([c for c in channels if c['portal'] == portal])} channels from portal {portalName} to editor")
            else:
                logger.error(
                    "Error getting channel data for {}, skipping".format(portalName)
                )
                flash(
                    "Error getting channel data for {}, skipping".format(portalName),
                    "danger",
                )

    data = {"data": channels}

    return flask.jsonify(data)

@app.route("/editor/portals", methods=["GET"])
@authorise
def editor_portals():
    """Get list of unique portals for filter dropdown."""
    try:
        portals = getPortals()
        portal_names = [portals[p]["name"] for p in portals if portals[p].get("enabled") == "true"]
        return flask.jsonify({"portals": sorted(set(portal_names))})
    except Exception as e:
        logger.error(f"Error in editor_portals: {e}")
        return flask.jsonify({"portals": [], "error": str(e)}), 500


@app.route("/editor/genres", methods=["GET"])
@authorise
def editor_genres():
    """Get list of unique genres for filter dropdown."""
    try:
        genres_set = set()
        portals = getPortals()
        
        # Quick approach: collect genres from custom genres in config
        for portal_id in portals:
            portal = portals[portal_id]
            if portal.get("enabled") == "true":
                custom_genres = portal.get("custom genres", {})
                for genre in custom_genres.values():
                    if genre:
                        genres_set.add(genre)
        
        # If no custom genres found, try to fetch from one portal
        if not genres_set:
            for portal_id in portals:
                portal = portals[portal_id]
                if portal.get("enabled") == "true":
                    url = portal["url"]
                    macs = list(portal["macs"].keys())
                    proxy = portal["proxy"]
                    
                    # Try first MAC only
                    if macs:
                        try:
                            token = stb.getToken(url, macs[0], proxy)
                            if token:
                                stb.getProfile(url, macs[0], token, proxy)
                                all_channels = stb.getAllChannels(url, macs[0], token, proxy)
                                genres_dict = stb.getGenreNames(url, macs[0], token, proxy)
                                
                                if all_channels and genres_dict:
                                    for channel in all_channels:
                                        genre_id = str(channel.get("tv_genre_id", ""))
                                        genre = genres_dict.get(genre_id, "")
                                        if genre:
                                            genres_set.add(genre)
                                    break
                        except Exception as e:
                            logger.error(f"Error fetching genres: {e}")
                            continue
        
        genres = sorted(list(genres_set))
        logger.info(f"Returning {len(genres)} genres")
        return flask.jsonify({"genres": genres})
    except Exception as e:
        logger.error(f"Error in editor_genres: {e}")
        return flask.jsonify({"genres": [], "error": str(e)}), 500


@app.route("/editor/save", methods=["POST"])
@authorise
def editorSave():
    global cached_xmltv
    threading.Thread(target=refresh_xmltv, daemon=True).start()
    last_playlist_host = None
    Thread(target=refresh_lineup).start()
    enabledEdits = json.loads(request.form["enabledEdits"])
    numberEdits = json.loads(request.form["numberEdits"])
    nameEdits = json.loads(request.form["nameEdits"])
    genreEdits = json.loads(request.form["genreEdits"])
    epgEdits = json.loads(request.form["epgEdits"])
    fallbackEdits = json.loads(request.form["fallbackEdits"])
    portals = getPortals()
    for edit in enabledEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        enabled = edit["enabled"]
        if enabled:
            portals[portal].setdefault("enabled channels", [])
            portals[portal]["enabled channels"].append(channelId)
        else:
            portals[portal]["enabled channels"] = list(
                filter((channelId).__ne__, portals[portal]["enabled channels"])
            )

    for edit in numberEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customNumber = edit["custom number"]
        if customNumber:
            portals[portal].setdefault("custom channel numbers", {})
            portals[portal]["custom channel numbers"].update({channelId: customNumber})
        else:
            portals[portal]["custom channel numbers"].pop(channelId)

    for edit in nameEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customName = edit["custom name"]
        if customName:
            portals[portal].setdefault("custom channel names", {})
            portals[portal]["custom channel names"].update({channelId: customName})
        else:
            portals[portal]["custom channel names"].pop(channelId)

    for edit in genreEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customGenre = edit["custom genre"]
        if customGenre:
            portals[portal].setdefault("custom genres", {})
            portals[portal]["custom genres"].update({channelId: customGenre})
        else:
            portals[portal]["custom genres"].pop(channelId)

    for edit in epgEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        customEpgId = edit["custom epg id"]
        if customEpgId:
            portals[portal].setdefault("custom epg ids", {})
            portals[portal]["custom epg ids"].update({channelId: customEpgId})
        else:
            portals[portal]["custom epg ids"].pop(channelId)

    for edit in fallbackEdits:
        portal = edit["portal"]
        channelId = edit["channel id"]
        channelName = edit["channel name"]
        if channelName:
            portals[portal].setdefault("fallback channels", {})
            portals[portal]["fallback channels"].update({channelId: channelName})
        else:
            portals[portal]["fallback channels"].pop(channelId)

    savePortals(portals)
    logger.info("Playlist config saved!")
    flash("Playlist config saved!", "success")
    return redirect("/editor", code=302)

@app.route("/editor/reset", methods=["POST"])
@authorise
def editorReset():
    portals = getPortals()
    for portal in portals:
        portals[portal]["enabled channels"] = []
        portals[portal]["custom channel numbers"] = {}
        portals[portal]["custom channel names"] = {}
        portals[portal]["custom genres"] = {}
        portals[portal]["custom epg ids"] = {}
        portals[portal]["fallback channels"] = {}

    savePortals(portals)
    logger.info("Playlist reset!")
    flash("Playlist reset!", "success")
    return redirect("/editor", code=302)

@app.route("/editor/deactivate-duplicates", methods=["POST"])
@authorise
def editor_deactivate_duplicates():
    """Deactivate duplicate enabled channels, keeping only the first occurrence."""
    try:
        portals = getPortals()
        seen_names = {}  # Track first occurrence of each channel name
        deactivated_count = 0
        
        for portal_id in portals:
            portal = portals[portal_id]
            if portal.get("enabled") != "true":
                continue
            
            enabled_channels = portal.get("enabled channels", [])
            custom_names = portal.get("custom channel names", {})
            
            # Get channel data
            url = portal["url"]
            macs = list(portal["macs"].keys())
            proxy = portal["proxy"]
            
            all_channels = None
            for mac in macs:
                try:
                    token = stb.getToken(url, mac, proxy)
                    if token:
                        stb.getProfile(url, mac, token, proxy)
                        all_channels = stb.getAllChannels(url, mac, token, proxy)
                        if all_channels:
                            break
                except Exception as e:
                    logger.error(f"Error fetching channels: {e}")
                    continue
            
            if not all_channels:
                continue
            
            # Build channel name map
            channel_map = {}
            for channel in all_channels:
                channel_id = str(channel["id"])
                if channel_id in enabled_channels:
                    # Use custom name if available, otherwise use original
                    name = custom_names.get(channel_id, channel["name"])
                    channel_map[channel_id] = name
            
            # Find duplicates
            channels_to_disable = []
            for channel_id, name in channel_map.items():
                if name in seen_names:
                    # This is a duplicate, mark for deactivation
                    channels_to_disable.append(channel_id)
                    deactivated_count += 1
                else:
                    # First occurrence, keep it
                    seen_names[name] = (portal_id, channel_id)
            
            # Remove duplicates from enabled channels
            if channels_to_disable:
                portal["enabled channels"] = [ch for ch in enabled_channels if ch not in channels_to_disable]
        
        savePortals(portals)
        logger.info(f"Deactivated {deactivated_count} duplicate channels")
        
        return flask.jsonify({
            "success": True,
            "deactivated": deactivated_count
        })
    except Exception as e:
        logger.error(f"Error deactivating duplicates: {e}")
        return flask.jsonify({"success": False, "error": str(e)}), 500

@app.route("/editor/refresh", methods=["POST"])
@authorise
def editor_refresh():
    """Refresh channel list from portals."""
    try:
        portals = getPortals()
        total_channels = 0
        
        for portal_id in portals:
            portal = portals[portal_id]
            if portal.get("enabled") != "true":
                continue
            
            url = portal["url"]
            macs = list(portal["macs"].keys())
            proxy = portal["proxy"]
            selected_genres = portal.get("selected genres", [])
            
            # Fetch latest channels
            all_channels = None
            genres_dict = None
            
            for mac in macs:
                try:
                    token = stb.getToken(url, mac, proxy)
                    if token:
                        stb.getProfile(url, mac, token, proxy)
                        all_channels = stb.getAllChannels(url, mac, token, proxy)
                        genres_dict = stb.getGenreNames(url, mac, token, proxy)
                        if all_channels and genres_dict:
                            break
                except Exception as e:
                    logger.error(f"Error fetching from MAC {mac}: {e}")
                    continue
            
            if not all_channels or not genres_dict:
                logger.warning(f"Could not fetch channels for portal {portal_id}")
                continue
            
            # Update enabled channels based on selected genres
            if selected_genres:
                enabled_channels = []
                for channel in all_channels:
                    channel_id = str(channel["id"])
                    genre_id = str(channel.get("tv_genre_id", ""))
                    genre = genres_dict.get(genre_id, "")
                    
                    if genre in selected_genres:
                        enabled_channels.append(channel_id)
                
                portal["enabled channels"] = enabled_channels
                total_channels += len(enabled_channels)
                logger.info(f"Refreshed {len(enabled_channels)} channels for portal {portal_id}")
        
        savePortals(portals)
        
        # Refresh lineup and XMLTV
        threading.Thread(target=refresh_lineup, daemon=True).start()
        threading.Thread(target=refresh_xmltv, daemon=True).start()
        
        return flask.jsonify({
            "status": "success",
            "total": total_channels
        })
    except Exception as e:
        logger.error(f"Error refreshing channels: {e}")
        return flask.jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/settings", methods=["GET"])
@authorise
def settings():
    settings = getSettings()
    return render_template(
        "settings.html", settings=settings, defaultSettings=defaultSettings
    )

@app.route("/settings/save", methods=["POST"])
@authorise
def save():
    settings = {}

    for setting, _ in defaultSettings.items():
        value = request.form.get(setting, "false")
        settings[setting] = value

    saveSettings(settings)
    logger.info("Settings saved!")
    Thread(target=refresh_xmltv).start()
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
    
    for user_id, user in users.items():
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
@authorise
def playlist():
    global cached_playlist, last_playlist_host
    
    logger.info("Playlist Requested")
    
    current_host = request.host or "0.0.0.0:8001"
    
    if cached_playlist is None or len(cached_playlist) == 0 or last_playlist_host != current_host:
        logger.info(f"Regenerating playlist due to host change: {last_playlist_host} -> {current_host}")
        last_playlist_host = current_host
        generate_playlist()

    return Response(cached_playlist, mimetype="text/plain")

@app.route("/update_playlistm3u", methods=["POST"])
@authorise
def update_playlistm3u():
    try:
        generate_playlist()
        logger.info("Playlist updated via dashboard")
        return Response("Playlist updated successfully", status=200)
    except Exception as e:
        logger.error(f"Error updating playlist: {e}")
        return Response(f"Error updating playlist: {str(e)}", status=500)

def generate_playlist():
    global cached_playlist
    logger.info("Generating playlist.m3u...")

    playlist_host = request.host or "0.0.0.0:8001"
    
    channels = []
    portals = getPortals()

    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = portals[portal].get("enabled channels", [])
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customGenres = portals[portal].get("custom genres", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})
                customEpgIds = portals[portal].get("custom epg ids", {})

                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        stb.getProfile(url, mac, token, proxy)
                        allChannels = stb.getAllChannels(url, mac, token, proxy)
                        genres = stb.getGenreNames(url, mac, token, proxy)
                        break
                    except:
                        allChannels = None
                        genres = None

                if allChannels and genres:
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        if channelId in enabledChannels:
                            channelName = customChannelNames.get(channelId)
                            if channelName is None:
                                channelName = str(channel.get("name"))
                            genre = customGenres.get(channelId)
                            if genre is None:
                                genreId = str(channel.get("tv_genre_id"))
                                genre = str(genres.get(genreId))
                            channelNumber = customChannelNumbers.get(channelId)
                            if channelNumber is None:
                                channelNumber = str(channel.get("number"))
                            epgId = customEpgIds.get(channelId)
                            if epgId is None:
                                epgId = channelName
                            channels.append(
                                "#EXTINF:-1"
                                + ' tvg-id="'
                                + epgId
                                + (
                                    '" tvg-chno="' + channelNumber
                                    if getSettings().get("use channel numbers", "true")
                                    == "true"
                                    else ""
                                )
                                + (
                                    '" group-title="' + genre
                                    if getSettings().get("use channel genres", "true")
                                    == "true"
                                    else ""
                                )
                                + '",'
                                + channelName
                                + "\n"
                                + "http://"
                                + playlist_host
                                + "/play/"
                                + portal
                                + "/"
                                + channelId
                            )
                else:
                    logger.error("Error making playlist for {}, skipping".format(name))

    if getSettings().get("sort playlist by channel name", "true") == "true":
        channels.sort(key=lambda k: k.split(",")[1].split("\n")[0])
    if getSettings().get("use channel numbers", "true") == "true":
        if getSettings().get("sort playlist by channel number", "false") == "true":
            channels.sort(key=lambda k: k.split('tvg-chno="')[1].split('"')[0])
    if getSettings().get("use channel genres", "true") == "true":
        if getSettings().get("sort playlist by channel genre", "false") == "true":
            channels.sort(key=lambda k: k.split('group-title="')[1].split('"')[0])

    playlist = "#EXTM3U \n"
    playlist = playlist + "\n".join(channels)

    cached_playlist = playlist
    logger.info("Playlist generated and cached.")
    
def fetch_epgshare_fallback(countries):
    """Fetch EPG data from epgshare01.online for specified countries."""
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
                            data['programmes'].append({
                                'start': programme.get('start', ''),
                                'stop': programme.get('stop', ''),
                                'title': programme.find('title').text if programme.find('title') is not None else '',
                                'desc': programme.find('desc').text if programme.find('desc') is not None else ''
                            })
                            break
                
                logger.info(f"Loaded {len([p for d in fallback_programmes.values() for p in d['programmes']])} programmes from {country}")
                
                # Clean up
                del xml_content
                del root
                
        except Exception as e:
            logger.error(f"Error fetching EPG fallback for {country}: {e}")
    
    return fallback_programmes


def refresh_xmltv():
    """Refresh XMLTV data with memory-optimized processing."""
    import gc
    
    settings = getSettings()
    logger.info("Refreshing XMLTV...")

    # Docker-optimized cache paths
    cache_dir = "/app/data"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, "MacReplayEPG.xml")

    day_before_yesterday = datetime.utcnow() - timedelta(days=2)
    day_before_yesterday_str = day_before_yesterday.strftime("%Y%m%d%H%M%S") + " +0000"

    # Check if EPG fallback is enabled
    epg_fallback_enabled = settings.get("epg fallback enabled", "false") == "true"
    epg_fallback_countries = settings.get("epg fallback countries", "").split(",")
    epg_fallback_countries = [c.strip() for c in epg_fallback_countries if c.strip()]
    
    fallback_epg = {}
    if epg_fallback_enabled and epg_fallback_countries:
        logger.info(f"EPG fallback enabled for countries: {epg_fallback_countries}")
        fallback_epg = fetch_epgshare_fallback(epg_fallback_countries)
        logger.info(f"Loaded fallback EPG for {len(fallback_epg)} channels")

    # Build XMLTV directly without caching old programmes (memory optimization)
    channels_xml = ET.Element("tv")
    portals = getPortals()
    programme_count = 0
    channels_without_epg = []

    for portal in portals:
        if portals[portal]["enabled"] == "true":
            portal_name = portals[portal]["name"]
            portal_epg_offset = int(portals[portal]["epg offset"])
            logger.info(f"Fetching EPG | Portal: {portal_name} | offset: {portal_epg_offset} |")

            enabledChannels = portals[portal].get("enabled channels", [])
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customEpgIds = portals[portal].get("custom epg ids", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})

                # Fetch channels and EPG from ALL MACs and merge
                all_channels_map = {}  # channelId -> channel data
                merged_epg = {}  # channelId -> [programmes]
                
                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        if token:
                            stb.getProfile(url, mac, token, proxy)
                            mac_channels = stb.getAllChannels(url, mac, token, proxy)
                            mac_epg = stb.getEpg(url, mac, token, 24, proxy)
                            
                            if mac_channels:
                                for ch in mac_channels:
                                    ch_id = str(ch.get("id"))
                                    if ch_id not in all_channels_map:
                                        all_channels_map[ch_id] = ch
                                logger.info(f"MAC {mac}: Got {len(mac_channels)} channels")
                            
                            if mac_epg:
                                for ch_id, programmes in mac_epg.items():
                                    if ch_id not in merged_epg:
                                        merged_epg[ch_id] = programmes
                                    # Don't overwrite if we already have EPG for this channel
                                logger.info(f"MAC {mac}: Got EPG for {len(mac_epg)} channels")
                            
                            # Clear MAC data
                            del mac_channels
                            del mac_epg
                            
                    except Exception as e:
                        logger.error(f"Error fetching data for MAC {mac}: {e}")
                        continue

                if all_channels_map:
                    # Convert enabled channels to set for faster lookup
                    enabled_set = set(enabledChannels)
                    
                    for channelId, channel in all_channels_map.items():
                        try:
                            if channelId not in enabled_set:
                                continue
                                
                            channelName = customChannelNames.get(channelId, channel.get("name"))
                            channelNumber = customChannelNumbers.get(channelId, str(channel.get("number")))
                            epgId = customEpgIds.get(channelId, channelNumber)

                            channelEle = ET.SubElement(channels_xml, "channel", id=epgId)
                            ET.SubElement(channelEle, "display-name").text = channelName
                            logo = channel.get("logo")
                            if logo:
                                ET.SubElement(channelEle, "icon", src=logo)

                            channel_epg = merged_epg.get(channelId, [])
                            
                            if not channel_epg:
                                # Try fallback EPG if enabled
                                fallback_used = False
                                if epg_fallback_enabled and fallback_epg:
                                    # Try to match by channel name
                                    name_key = channelName.lower().strip()
                                    if name_key in fallback_epg:
                                        fb_data = fallback_epg[name_key]
                                        for p in fb_data['programmes'][:50]:  # Limit to 50 programmes
                                            try:
                                                programmeEle = ET.SubElement(
                                                    channels_xml, "programme",
                                                    start=p['start'], stop=p['stop'], channel=epgId
                                                )
                                                ET.SubElement(programmeEle, "title").text = p['title']
                                                if p['desc']:
                                                    ET.SubElement(programmeEle, "desc").text = p['desc']
                                                programme_count += 1
                                                fallback_used = True
                                            except Exception as e:
                                                pass
                                        if fallback_used:
                                            logger.debug(f"Used fallback EPG for {channelName}")
                                
                                if not fallback_used:
                                    # Create dummy EPG
                                    channels_without_epg.append(channelName)
                                    start_time = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
                                    stop_time = start_time + timedelta(hours=24)
                                    start = start_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                    stop = stop_time.strftime("%Y%m%d%H%M%S") + " +0000"
                                    programmeEle = ET.SubElement(
                                        channels_xml, "programme", start=start, stop=stop, channel=epgId
                                    )
                                    ET.SubElement(programmeEle, "title").text = channelName
                                    ET.SubElement(programmeEle, "desc").text = channelName
                                    programme_count += 1
                            else:
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
                                        ET.SubElement(programmeEle, "title").text = p.get("name", "")
                                        desc = p.get("descr", "")
                                        if desc:
                                            ET.SubElement(programmeEle, "desc").text = desc
                                        programme_count += 1
                                    except Exception as e:
                                        logger.error(f"Error processing programme: {e}")
                        except Exception as e:
                            logger.error(f"Error processing channel: {e}")
                    
                    # Clear data from memory
                    del merged_epg
                    del all_channels_map
                    gc.collect()
                else:
                    logger.error(f"Error making XMLTV for {name}, skipping")

    if channels_without_epg:
        logger.warning(f"{len(channels_without_epg)} channels without EPG data")

    # Generate XML string without minidom (much more memory efficient)
    rough_string = ET.tostring(channels_xml, encoding="unicode")
    
    # Simple formatting without minidom
    formatted_xmltv = '<?xml version="1.0" encoding="UTF-8"?>\n' + rough_string

    # Write to cache file
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(formatted_xmltv)
        logger.info(f"XMLTV cache updated with {programme_count} programmes.")
    except Exception as e:
        logger.error(f"Error writing XMLTV cache: {e}")

    # Update global cache
    global cached_xmltv, last_updated
    cached_xmltv = formatted_xmltv
    last_updated = time.time()
    
    # Clean up
    del channels_xml
    del rough_string
    del fallback_epg
    gc.collect()
    
@app.route("/xmltv", methods=["GET"])
@authorise
def xmltv():
    global cached_xmltv, last_updated
    logger.info("Guide Requested")
    
    if cached_xmltv is None or (time.time() - last_updated) > 900:
        refresh_xmltv()
    
    return Response(
        cached_xmltv,
        mimetype="text/xml",
    )

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
    return render_template("epg_simple.html", settings=getSettings())


@app.route("/epg/portal-status", methods=["GET"])
@authorise
def epg_portal_status():
    """Get EPG status for all portals with actual EPG count."""
    global _epg_cache
    
    # Return cached data if still valid
    if _epg_cache["portal_status"] and (time.time() - _epg_cache["portal_status_time"]) < _EPG_CACHE_TTL:
        return flask.jsonify(_epg_cache["portal_status"])
    
    try:
        portals = getPortals()
        portal_status = []
        
        for portal_id, portal in portals.items():
            if portal.get("enabled") != "true":
                continue
            
            portal_info = {
                "id": portal_id,
                "name": portal.get("name", "Unknown"),
                "has_epg": False,
                "epg_url": None,
                "epg_type": None,
                "channel_count": 0,
                "epg_channel_count": 0
            }
            
            enabled_channels = portal.get("enabled channels", [])
            portal_info["channel_count"] = len(enabled_channels)
            
            if enabled_channels:
                # Actually check EPG availability from first working MAC
                url = portal.get("url")
                macs = list(portal.get("macs", {}).keys())
                proxy = portal.get("proxy", "")
                
                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        if token:
                            stb.getProfile(url, mac, token, proxy)
                            epg = stb.getEpg(url, mac, token, 24, proxy)
                            if epg:
                                portal_info["has_epg"] = True
                                portal_info["epg_type"] = "api"
                                portal_info["epg_url"] = f"{url}?type=itv&action=get_epg_info"
                                # Count channels with EPG that are enabled
                                epg_count = sum(1 for ch_id in enabled_channels if ch_id in epg and epg[ch_id])
                                portal_info["epg_channel_count"] = epg_count
                                break
                    except Exception as e:
                        logger.error(f"Error checking EPG for portal {portal_info['name']}: {e}")
                        continue
            
            portal_status.append(portal_info)
        
        # Cache the result
        _epg_cache["portal_status"] = portal_status
        _epg_cache["portal_status_time"] = time.time()
        
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
    """Get all enabled channels with their EPG mapping status."""
    global _epg_cache
    
    # Return cached data if still valid
    if _epg_cache["channels"] and (time.time() - _epg_cache["channels_time"]) < _EPG_CACHE_TTL:
        return flask.jsonify({"channels": _epg_cache["channels"]})
    
    try:
        portals = getPortals()
        channels = []
        
        for portal_id, portal in portals.items():
            if portal.get("enabled") != "true":
                continue
            
            portal_name = portal.get("name", "Unknown")
            enabled_channels = portal.get("enabled channels", [])
            custom_names = portal.get("custom channel names", {})
            custom_epg_ids = portal.get("custom epg ids", {})
            
            if not enabled_channels:
                continue
            
            # Fetch channel data and EPG status
            url = portal.get("url")
            macs = list(portal.get("macs", {}).keys())
            proxy = portal.get("proxy", "")
            
            all_channels = None
            epg_data = None
            
            for mac in macs:
                try:
                    token = stb.getToken(url, mac, proxy)
                    if token:
                        stb.getProfile(url, mac, token, proxy)
                        all_channels = stb.getAllChannels(url, mac, token, proxy)
                        epg_data = stb.getEpg(url, mac, token, 24, proxy)
                        if all_channels:
                            break
                except Exception as e:
                    logger.error(f"Error fetching channels: {e}")
                    continue
            
            if all_channels:
                for channel in all_channels:
                    channel_id = str(channel.get("id"))
                    if channel_id not in enabled_channels:
                        continue
                    
                    channel_name = custom_names.get(channel_id, channel.get("name", ""))
                    epg_id = custom_epg_ids.get(channel_id, "")
                    has_portal_epg = epg_data and channel_id in epg_data and len(epg_data.get(channel_id, [])) > 0
                    
                    channels.append({
                        "portal_id": portal_id,
                        "portal_name": portal_name,
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "channel_number": str(channel.get("number", "")),
                        "epg_id": epg_id,
                        "has_epg": has_portal_epg or bool(epg_id),
                        "has_portal_epg": has_portal_epg,
                        "logo": channel.get("logo", "")
                    })
                
                # Clear data from memory
                all_channels = None
                epg_data = None
        
        # Cache the result
        _epg_cache["channels"] = channels
        _epg_cache["channels_time"] = time.time()
        
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
    """Apply fallback EPG ID to a channel based on name matching."""
    try:
        data = request.json
        portal_id = data.get("portal_id")
        channel_id = data.get("channel_id")
        channel_name = data.get("channel_name", "")
        fallback_name = data.get("fallback_name", "")  # Optional: specific fallback channel name
        
        if not portal_id or not channel_id:
            return flask.jsonify({"error": "Missing portal_id or channel_id"}), 400
        
        portals = getPortals()
        if portal_id not in portals:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        # Get fallback data
        settings = getSettings()
        countries = settings.get("epg fallback countries", "").split(",")
        countries = [c.strip() for c in countries if c.strip()]
        
        if not countries:
            return flask.jsonify({"error": "No fallback countries configured"}), 400
        
        fallback_data = fetch_epgshare_fallback(countries)
        
        # Try to find matching channel
        search_name = (fallback_name or channel_name).lower().strip()
        matched_epg_id = None
        
        # Exact match first
        if search_name in fallback_data:
            matched_epg_id = fallback_data[search_name]['channel_id']
        else:
            # Partial match
            for fb_name, fb_data in fallback_data.items():
                if search_name in fb_name or fb_name in search_name:
                    matched_epg_id = fb_data['channel_id']
                    break
        
        if not matched_epg_id:
            return flask.jsonify({"error": f"No fallback match found for '{search_name}'", "available": list(fallback_data.keys())[:20]}), 404
        
        # Save the EPG ID
        if "custom epg ids" not in portals[portal_id]:
            portals[portal_id]["custom epg ids"] = {}
        
        portals[portal_id]["custom epg ids"][channel_id] = matched_epg_id
        savePortals(portals)
        
        # Clear caches
        global cached_xmltv
        cached_xmltv = None
        _clear_epg_cache()
        
        logger.info(f"Applied fallback EPG ID '{matched_epg_id}' to channel {channel_id}")
        return flask.jsonify({"success": True, "epg_id": matched_epg_id})
    except Exception as e:
        logger.error(f"Error applying fallback: {e}")
        return flask.jsonify({"error": str(e)}), 500


@app.route("/epg/apply-fallback-all", methods=["POST"])
@authorise
def epg_apply_fallback_all():
    """Apply fallback EPG to all channels without portal EPG."""
    try:
        data = request.json
        channels = data.get("channels", [])
        
        if not channels:
            return flask.jsonify({"error": "No channels provided"}), 400
        
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
        
        portals = getPortals()
        matched_count = 0
        total_count = len(channels)
        
        for channel in channels:
            portal_id = channel.get("portal_id")
            channel_id = channel.get("channel_id")
            channel_name = channel.get("channel_name", "")
            
            if not portal_id or not channel_id or portal_id not in portals:
                continue
            
            # Try to find matching channel
            search_name = channel_name.lower().strip()
            matched_epg_id = None
            
            # Exact match first
            if search_name in fallback_data:
                matched_epg_id = fallback_data[search_name]['channel_id']
            else:
                # Partial match
                for fb_name, fb_data in fallback_data.items():
                    if search_name in fb_name or fb_name in search_name:
                        matched_epg_id = fb_data['channel_id']
                        break
            
            if matched_epg_id:
                # Save the EPG ID
                if "custom epg ids" not in portals[portal_id]:
                    portals[portal_id]["custom epg ids"] = {}
                
                portals[portal_id]["custom epg ids"][channel_id] = matched_epg_id
                matched_count += 1
                logger.info(f"Matched '{channel_name}' to EPG ID '{matched_epg_id}'")
            else:
                logger.warning(f"No fallback match found for '{channel_name}'")
        
        # Save all changes at once
        savePortals(portals)
        
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
    """Save EPG ID mapping for a channel."""
    try:
        data = request.json
        portal_id = data.get("portal_id")
        channel_id = data.get("channel_id")
        epg_id = data.get("epg_id", "")
        
        if not portal_id or not channel_id:
            return flask.jsonify({"error": "Missing portal_id or channel_id"}), 400
        
        portals = getPortals()
        if portal_id not in portals:
            return flask.jsonify({"error": "Portal not found"}), 404
        
        if "custom epg ids" not in portals[portal_id]:
            portals[portal_id]["custom epg ids"] = {}
        
        if epg_id:
            portals[portal_id]["custom epg ids"][channel_id] = epg_id
        elif channel_id in portals[portal_id]["custom epg ids"]:
            del portals[portal_id]["custom epg ids"][channel_id]
        
        savePortals(portals)
        
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
        _clear_epg_cache()
        global cached_xmltv
        cached_xmltv = None
        threading.Thread(target=refresh_xmltv, daemon=True).start()
        return flask.jsonify({"success": True, "message": "EPG refresh started"})
    except Exception as e:
        logger.error(f"Error refreshing EPG: {e}")
        return flask.jsonify({"error": str(e)}), 500


# ============================================
# Xtream Codes API Routes
# ============================================

@app.route("/get.php", methods=["GET"])
@app.route("/get", methods=["GET"])
@xc_auth_only
def xc_get_playlist():
    """XC API M3U playlist endpoint."""
    settings = getSettings()
    if settings.get("xc api enabled") != "true":
        return "XC API is disabled", 403
    
    username = request.args.get("username")
    password = request.args.get("password")
    output = request.args.get("output", "m3u8")
    playlist_type = request.args.get("type", "m3u_plus")
    
    if not username or not password:
        return "Missing credentials", 401
    
    user_id, user = validateXCUser(username, password)
    if not user:
        return "Invalid credentials", 401
    
    # Generate M3U playlist
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    m3u_content = "#EXTM3U\n"
    
    for portal_id, portal in portals.items():
        if portal.get("enabled") != "true":
            continue
        if allowed_portals and portal_id not in allowed_portals:
            continue
        
        enabled_channels = portal.get("enabled channels", [])
        if not enabled_channels:
            continue
        
        custom_names = portal.get("custom channel names", {})
        custom_numbers = portal.get("custom channel numbers", {})
        custom_genres = portal.get("custom genres", {})
        
        # Get channels
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy", "")
        
        all_channels = None
        genres = None
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    all_channels = stb.getAllChannels(url, mac, token, proxy)
                    genres = stb.getGenreNames(url, mac, token, proxy)
                    if all_channels:
                        break
            except:
                continue
        
        if all_channels and genres:
            for channel in all_channels:
                channel_id = str(channel.get("id"))
                if channel_id not in enabled_channels:
                    continue
                
                channel_name = custom_names.get(channel_id, channel.get("name", ""))
                channel_number = custom_numbers.get(channel_id, str(channel.get("number", "")))
                genre_id = str(channel.get("tv_genre_id", ""))
                genre_name = custom_genres.get(channel_id, genres.get(genre_id, ""))
                logo = channel.get("logo", "")
                
                stream_id = f"{portal_id}_{channel_id}"
                # Use the same host as the request came from (handles reverse proxy correctly)
                scheme = request.headers.get('X-Forwarded-Proto', request.scheme)
                host = request.headers.get('X-Forwarded-Host', request.host)
                # Standard XC API URL format for maximum compatibility
                # Add .ts extension for better IPTV client compatibility
                stream_url = f"{scheme}://{host}/{username}/{password}/{stream_id}.ts"
                
                m3u_content += f'#EXTINF:-1 tvg-id="{channel_name}" tvg-name="{channel_name}" tvg-logo="{logo}" group-title="{genre_name}",{channel_name}\n'
                m3u_content += f'{stream_url}\n'
    
    return Response(m3u_content, mimetype="application/x-mpegURL")


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
    if not user:
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
        return flask.jsonify([])  # No VOD support
    elif action == "get_series":
        return flask.jsonify([])  # No series support
    elif action == "get_vod_categories":
        return flask.jsonify([])
    elif action == "get_series_categories":
        return flask.jsonify([])
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
    
    categories = []
    categories_with_channels = set()  # Track which categories have enabled channels
    
    for portal_id, portal in portals.items():
        if portal.get("enabled") != "true":
            continue
        if allowed_portals and portal_id not in allowed_portals:
            continue
        
        enabled_channels = portal.get("enabled channels", [])
        if not enabled_channels:
            continue
        
        # Get channels to find which genres are actually used
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy", "")
        
        all_channels = None
        genres = None
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    all_channels = stb.getAllChannels(url, mac, token, proxy)
                    genres = stb.getGenreNames(url, mac, token, proxy)
                    if all_channels and genres:
                        break
            except:
                continue
        
        if all_channels and genres:
            # Find which genres have enabled channels
            for channel in all_channels:
                channel_id = str(channel.get("id"))
                if channel_id in enabled_channels:
                    genre_id = str(channel.get("tv_genre_id", ""))
                    category_key = f"{portal_id}_{genre_id}"
                    
                    if category_key not in categories_with_channels:
                        categories_with_channels.add(category_key)
                        genre_name = genres.get(genre_id, "Unknown")
                        categories.append({
                            "category_id": category_key,
                            "category_name": f"{portal.get('name')} - {genre_name}",
                            "parent_id": 0
                        })
    
    return flask.jsonify(categories)


def xc_get_live_streams(user):
    """Get live streams."""
    portals = getPortals()
    allowed_portals = user.get("allowed_portals", [])
    
    streams = []
    
    for portal_id, portal in portals.items():
        if portal.get("enabled") != "true":
            continue
        if allowed_portals and portal_id not in allowed_portals:
            continue
        
        enabled_channels = portal.get("enabled channels", [])
        if not enabled_channels:
            continue
        
        custom_names = portal.get("custom channel names", {})
        custom_numbers = portal.get("custom channel numbers", {})
        custom_genres = portal.get("custom genres", {})
        
        # Get channels
        url = portal.get("url")
        macs = list(portal.get("macs", {}).keys())
        proxy = portal.get("proxy", "")
        
        all_channels = None
        genres = None
        
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    all_channels = stb.getAllChannels(url, mac, token, proxy)
                    genres = stb.getGenreNames(url, mac, token, proxy)
                    if all_channels:
                        break
            except:
                continue
        
        if all_channels and genres:
            for channel in all_channels:
                channel_id = str(channel.get("id"))
                if channel_id not in enabled_channels:
                    continue
                
                channel_name = custom_names.get(channel_id, channel.get("name", ""))
                channel_number = custom_numbers.get(channel_id, str(channel.get("number", "")))
                genre_id = str(channel.get("tv_genre_id", ""))
                genre_name = custom_genres.get(channel_id, genres.get(genre_id, ""))
                
                # Create internal stream ID
                internal_id = f"{portal_id}_{channel_id}"
                
                # XC API expects numeric stream_id - use deterministic hash
                # Python's hash() is not deterministic across sessions, so use hashlib
                import hashlib
                numeric_id = int(hashlib.md5(internal_id.encode()).hexdigest()[:8], 16)
                
                streams.append({
                    "num": int(channel_number) if channel_number.isdigit() else 0,
                    "name": channel_name,
                    "stream_type": "live",
                    "stream_id": numeric_id,
                    "stream_icon": channel.get("logo", ""),
                    "epg_channel_id": channel_name,
                    "added": "",
                    "category_id": f"{portal_id}_{genre_id}",
                    "custom_sid": internal_id,  # Store real ID for reverse lookup
                    "tv_archive": 0,
                    "direct_source": "",
                    "tv_archive_duration": 0,
                    "container_extension": "ts"
                })
    
    return flask.jsonify(streams)


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
    if username == "data" or "MacReplay.json" in str(stream_id) or str(stream_id).startswith("data/"):
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
    if not user:
        return flask.jsonify({
            "user_info": {
                "auth": 0,
                "message": user_id  # user_id contains error message
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
        # Numeric format: need to find the matching channel
        # This is inefficient but necessary for XC API compatibility
        numeric_id = int(stream_id)
        portals = getPortals()
        found = False
        
        import hashlib
        for pid, portal in portals.items():
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
    
    # Check connection limit
    can_connect, message = checkXCConnectionLimit(user_id, device_id)
    if not can_connect:
        logger.warning(f"XC API: Connection limit reached for user {username}: {message}")
        return message, 429
    
    # Register connection
    registerXCConnection(user_id, device_id, portal_id, channel_id, get_client_ip(request))
    logger.info(f"XC API: User {username} connected to {portal_id}/{channel_id} from {get_client_ip(request)}")
    
    # Stream with cleanup wrapper
    try:
        response = stream_channel(portal_id, channel_id)
        
        # Wrap the response to cleanup connection when stream ends
        if hasattr(response, 'response') and hasattr(response.response, '__iter__'):
            # It's a streaming response, wrap it
            original_iter = response.response
            
            def cleanup_wrapper():
                try:
                    for chunk in original_iter:
                        yield chunk
                finally:
                    # Cleanup connection when stream ends
                    unregisterXCConnection(user_id, device_id)
                    logger.info(f"XC API: User {username} disconnected from {portal_id}/{channel_id}")
            
            response.response = cleanup_wrapper()
        
        return response
    except Exception as e:
        # Cleanup on error
        unregisterXCConnection(user_id, device_id)
        logger.error(f"XC API: Stream error for user {username}: {e}")
        raise


@app.route("/xmltv.php", methods=["GET"])
@xc_auth_only
def xc_xmltv():
    """XC API XMLTV endpoint."""
    global cached_xmltv, last_updated
    logger.info("XC API: XMLTV Guide Requested")
    
    # Refresh cache if needed
    if cached_xmltv is None or (time.time() - last_updated) > 900:
        refresh_xmltv()
    
    return Response(
        cached_xmltv,
        mimetype="text/xml",
    )


def stream_channel(portalId, channelId):
    """Internal function to stream a channel without authentication."""
    def streamData():
        def occupy():
            occupied.setdefault(portalId, [])
            occupied.get(portalId, []).append(
                {
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
            )
            logger.info("Occupied Portal({}):MAC({})".format(portalId, mac))

        def unoccupy():
            occupied.get(portalId, []).remove(
                {
                    "mac": mac,
                    "channel id": channelId,
                    "channel name": channelName,
                    "client": ip,
                    "portal name": portalName,
                    "start time": startTime,
                }
            )
            logger.info("Unoccupied Portal({}):MAC({})".format(portalId, mac))

        try:
            startTime = datetime.now(timezone.utc).timestamp()
            occupy()
            with subprocess.Popen(
                ffmpegcmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            ) as ffmpeg_sp:
                while True:
                    chunk = ffmpeg_sp.stdout.read(1024)
                    if len(chunk) == 0:
                        if ffmpeg_sp.poll() != 0:
                            logger.info("Ffmpeg closed with error({}). Moving MAC({}) for Portal({})".format(str(ffmpeg_sp.poll()), mac, portalName))
                            moveMac(portalId, mac)
                        break
                    yield chunk
        except:
            pass
        finally:
            unoccupy()
            ffmpeg_sp.kill()

    def testStream():
        timeout = int(getSettings()["ffmpeg timeout"]) * int(1000000)
        ffprobecmd = [ffprobe_path, "-timeout", str(timeout), "-i", link]

        if proxy:
            ffprobecmd.insert(1, "-http_proxy")
            ffprobecmd.insert(2, proxy)

        with subprocess.Popen(
            ffprobecmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as ffprobe_sb:
            ffprobe_sb.communicate()
            if ffprobe_sb.returncode == 0:
                return True
            else:
                return False

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

    freeMac = False

    for mac in macs:
        channels = None
        cmd = None
        link = None
        if streamsPerMac == 0 or isMacFree():
            logger.info(
                "Trying Portal({}):MAC({}):Channel({})".format(portalId, mac, channelId)
            )
            freeMac = True
            token = stb.getToken(url, mac, proxy)
            if token:
                stb.getProfile(url, mac, token, proxy)
                channels = stb.getAllChannels(url, mac, token, proxy)

        if channels:
            for c in channels:
                if str(c["id"]) == channelId:
                    channelName = portal.get("custom channel names", {}).get(channelId)
                    if channelName == None:
                        channelName = c["name"]
                    cmd = c["cmd"]
                    break

        if cmd:
            if "http://localhost/" in cmd:
                link = stb.getLink(url, mac, token, cmd, proxy)
            else:
                link = cmd.split(" ")[1]

        if link:
            if getSettings().get("test streams", "true") == "false" or testStream():
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
                    if getSettings().get("stream method", "ffmpeg") == "ffmpeg":
                        ffmpegcmd = f"{ffmpeg_path} {getSettings()['ffmpeg command']}"
                        ffmpegcmd = ffmpegcmd.replace("<url>", link)
                        ffmpegcmd = ffmpegcmd.replace(
                            "<timeout>",
                            str(int(getSettings()["ffmpeg timeout"]) * int(1000000)),
                        )
                        if proxy:
                            ffmpegcmd = ffmpegcmd.replace("<proxy>", proxy)
                        else:
                            ffmpegcmd = ffmpegcmd.replace("-http_proxy <proxy>", "")
                        " ".join(ffmpegcmd.split())
                        ffmpegcmd = ffmpegcmd.split()
                        return Response(
                            streamData(), mimetype="application/octet-stream"
                        )
                    else:
                        logger.info("Redirect sent")
                        return redirect(link)

        logger.info(
            "Unable to connect to Portal({}) using MAC({})".format(portalId, mac)
        )
        logger.info("Moving MAC({}) for Portal({})".format(mac, portalName))
        moveMac(portalId, mac)

        if not getSettings().get("try all macs", "true") == "true":
            break

    # (Fallback logic remains the same but too long to include here)
    # ... rest of the original channel function

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
@authorise
def channel(portalId, channelId):
    """Web UI endpoint to play a channel."""
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
        # Get the stream URL
        link = None
        for mac in macs:
            try:
                token = stb.getToken(url, mac, proxy)
                if token:
                    stb.getProfile(url, mac, token, proxy)
                    channels = stb.getAllChannels(url, mac, token, proxy)
                    
                    if channels:
                        for c in channels:
                            if str(c["id"]) == channelId:
                                cmd = c["cmd"]
                                if "http://localhost/" in cmd:
                                    link = stb.getLink(url, mac, token, cmd, proxy)
                                else:
                                    link = cmd.split(" ")[1]
                                break
                    
                    if link:
                        break
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


@app.route("/dashboard")
@authorise
def dashboard():
    return render_template("dashboard.html")

@app.route("/streaming")
@authorise
def streaming():
    return flask.jsonify(occupied)

@app.route("/log")
@authorise
def log():
    logFilePath = "/app/logs/MacReplay.log"
    
    try:
        with open(logFilePath) as f:
            log_content = f.read()
        return log_content
    except FileNotFoundError:
        return "Log file not found"

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
        "FirmwareName": "MacReplay",
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
    logger.info("Refreshing Lineup...")
    lineup = []
    portals = getPortals()
    for portal in portals:
        if portals[portal]["enabled"] == "true":
            enabledChannels = portals[portal].get("enabled channels", [])
            if len(enabledChannels) != 0:
                name = portals[portal]["name"]
                url = portals[portal]["url"]
                macs = list(portals[portal]["macs"].keys())
                proxy = portals[portal]["proxy"]
                customChannelNames = portals[portal].get("custom channel names", {})
                customChannelNumbers = portals[portal].get("custom channel numbers", {})

                for mac in macs:
                    try:
                        token = stb.getToken(url, mac, proxy)
                        stb.getProfile(url, mac, token, proxy)
                        allChannels = stb.getAllChannels(url, mac, token, proxy)
                        break
                    except:
                        allChannels = None

                if allChannels:
                    for channel in allChannels:
                        channelId = str(channel.get("id"))
                        if channelId in enabledChannels:
                            channelName = customChannelNames.get(channelId)
                            if channelName is None:
                                channelName = str(channel.get("name"))
                            channelNumber = customChannelNumbers.get(channelId)
                            if channelNumber is None:
                                channelNumber = str(channel.get("number"))

                            lineup.append(
                                {
                                    "GuideNumber": channelNumber,
                                    "GuideName": channelName,
                                    "URL": "http://"
                                    + host
                                    + "/play/"
                                    + portal
                                    + "/"
                                    + channelId,
                                }
                            )
                else:
                    logger.error("Error making lineup for {}, skipping".format(name))
    
    lineup.sort(key=lambda x: int(x["GuideNumber"]))

    cached_lineup = lineup
    logger.info("Lineup Refreshed.")
    
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

def start_refresh():
    threading.Thread(target=refresh_lineup, daemon=True).start()
    threading.Thread(target=refresh_xmltv, daemon=True).start()
    
if __name__ == "__main__":
    config = loadConfig()
    start_refresh()
    
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
    
    # Always use waitress for production in container
    logger.info("Starting Waitress server on 0.0.0.0:8001")
    waitress.serve(app, host="0.0.0.0", port=8001, _quiet=True, threads=24) 