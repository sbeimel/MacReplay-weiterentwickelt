import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urlparse
import re
import logging
import time

# Try to import cloudscraper for Cloudflare bypass
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    logging.getLogger("MacReplay.stb").info("cloudscraper not available - some portals with Cloudflare protection may not work")

logger = logging.getLogger("MacReplay.stb")
logger.setLevel(logging.DEBUG)

# Session management with periodic refresh to prevent memory leaks
_session = None
_session_created = 0
_SESSION_MAX_AGE = 300  # Refresh session every 5 minutes


def _get_session(use_cloudscraper=False):
    """Get or create a requests session with automatic refresh."""
    global _session, _session_created
    
    current_time = time.time()
    
    # Create new session if none exists or if too old
    if _session is None or (current_time - _session_created) > _SESSION_MAX_AGE:
        if _session is not None:
            try:
                _session.close()
            except:
                pass
        
        # Use cloudscraper if available and requested (for Cloudflare bypass)
        if use_cloudscraper and CLOUDSCRAPER_AVAILABLE:
            _session = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'linux',
                    'desktop': True
                }
            )
            logger.debug("Created cloudscraper session for Cloudflare bypass")
        else:
            _session = requests.Session()
            retries = Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
            _session.mount("http://", HTTPAdapter(max_retries=retries))
            _session.mount("https://", HTTPAdapter(max_retries=retries))
            logger.debug("Created new requests session")
        
        _session_created = current_time
    
    return _session


def clear_session():
    """Clear the session to free memory."""
    global _session, _session_created
    if _session is not None:
        try:
            _session.close()
        except:
            pass
        _session = None
        _session_created = 0
        logger.debug("Cleared requests session")


def getUrl(url, proxy=None):
    """Get portal URL by parsing xpcom.common.js - tries multiple paths and methods."""
    def parseResponse(url, data):
        try:
            java = data.text.replace(" ", "").replace("'", "").replace("+", "")
            pattern = re.search(r"varpattern.*\/(\(http.*)\/;", java).group(1)
            result = re.search(pattern, url)
            protocolIndex = re.search(r"this\.portal_protocol.*(\d).*;", java).group(1)
            ipIndex = re.search(r"this\.portal_ip.*(\d).*;", java).group(1)
            pathIndex = re.search(r"this\.portal_path.*(\d).*;", java).group(1)
            protocol = result.group(int(protocolIndex))
            ip = result.group(int(ipIndex))
            path = result.group(int(pathIndex))
            portalPatern = re.search(r"this\.ajax_loader=(.*\.php);", java).group(1)
            portal = (
                portalPatern.replace("this.portal_protocol", protocol)
                .replace("this.portal_ip", ip)
                .replace("this.portal_path", path)
            )
            return portal
        except Exception as e:
            logger.debug(f"Failed to parse response: {e}")
            return None

    # Parse the base URL
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    # If URL already has a path, try to use it
    url_path = parsed.path.rstrip('/')
    
    # Extended list of paths to try
    urls = [
        "/c/xpcom.common.js",
        "/client/xpcom.common.js",
        "/c_/xpcom.common.js",
        "/stalker_portal/c/xpcom.common.js",
        "/stalker_portal/c_/xpcom.common.js",
        "/portal/c/xpcom.common.js",
        "/server/c/xpcom.common.js",
    ]
    
    # If URL has a path component, try it first
    if url_path and url_path != '/':
        urls.insert(0, f"{url_path}/xpcom.common.js")
        urls.insert(1, f"{url_path}xpcom.common.js")

    proxies = {"http": proxy, "https": proxy}
    
    # Enhanced headers to bypass Cloudflare and other protections
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Referer": base_url + "/",
    }

    # Try with proxy first (use cloudscraper for Cloudflare bypass)
    session = _get_session(use_cloudscraper=True)
    for path in urls:
        try:
            test_url = base_url + path
            logger.debug(f"Trying xpcom.common.js at: {test_url}")
            response = session.get(test_url, headers=headers, proxies=proxies, timeout=10)
            if response.status_code == 200:
                logger.debug(f"Found xpcom.common.js at: {test_url}")
                portal = parseResponse(test_url, response)
                if portal:
                    logger.info(f"Successfully parsed portal URL: {portal}")
                    return portal
        except Exception as e:
            logger.debug(f"Failed to fetch {path}: {e}")
            continue

    # Try without proxy (some portals don't like proxies)
    logger.debug("Retrying without proxy...")
    for path in urls:
        try:
            test_url = base_url + path
            logger.debug(f"Trying xpcom.common.js at: {test_url} (no proxy)")
            response = session.get(test_url, headers=headers, timeout=10)
            if response.status_code == 200:
                logger.debug(f"Found xpcom.common.js at: {test_url}")
                portal = parseResponse(test_url, response)
                if portal:
                    logger.info(f"Successfully parsed portal URL: {portal}")
                    return portal
        except Exception as e:
            logger.debug(f"Failed to fetch {path} without proxy: {e}")
            continue
    
    logger.error(f"Could not find xpcom.common.js for {url}")
    return None


def getToken(url, mac, proxy=None):
    """Get token with support for multiple portal endpoints."""
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    
    # Enhanced headers to bypass protections
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept": "*/*",
        "Referer": base_url + "/",
        "X-User-Agent": "Model: MAG250; Link: WiFi",
    }
    
    # If URL already contains a path (like /c/ or /stalker_portal/), use it
    url_path = parsed.path.rstrip('/')
    
    # Try different endpoint variations
    endpoints = []
    
    # If URL has a specific path, try it first
    if url_path and url_path != '/':
        endpoints.extend([
            f"{url_path}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml",
            f"{url_path}/server/load.php?type=stb&action=handshake&JsHttpRequest=1-xml",
            f"{url_path}?type=stb&action=handshake&JsHttpRequest=1-xml",
        ])
    
    # Standard endpoints
    endpoints.extend([
        "?type=stb&action=handshake&JsHttpRequest=1-xml",  # Root
        "/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml",  # Standard portal.php
        "/server/load.php?type=stb&action=handshake&JsHttpRequest=1-xml",  # Standard load.php
        "/stalker_portal/server/load.php?type=stb&action=handshake&JsHttpRequest=1-xml",  # Stalker path
        "/c/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml",  # /c/ path
    ])
    
    for endpoint in endpoints:
        try:
            # Build full URL
            if endpoint.startswith('/') or endpoint.startswith('?'):
                full_url = base_url + endpoint
            else:
                full_url = url + endpoint
            
            logger.debug(f"Trying token endpoint: {full_url}")
            response = _get_session().get(
                full_url,
                cookies=cookies,
                headers=headers,
                proxies=proxies,
                timeout=20,
            )
            logger.debug(f"Token request status: {response.status_code}")
            
            # Try to parse response
            if response.status_code == 200:
                data = response.json()
                if "js" in data and "token" in data["js"]:
                    token = data["js"]["token"]
                    if token:
                        logger.info(f"Successfully got token for MAC {mac} using endpoint: {full_url}")
                        return token
        except requests.Timeout:
            logger.debug(f"Timeout on endpoint {endpoint}")
            continue
        except requests.RequestException as e:
            logger.debug(f"Request error on endpoint {endpoint}: {e}")
            continue
        except Exception as e:
            logger.debug(f"Error on endpoint {endpoint}: {e}")
            continue
    
    logger.error(f"Failed to get token for MAC {mac} from all endpoints")
    return None


def getProfile(url, mac, token, proxy=None):
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    try:
        response = _get_session().get(
            url + "?type=stb&action=get_profile&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=10,
        )
        profile = response.json()["js"]
        if profile:
            return profile
    except:
        pass


def getExpires(url, mac, token, proxy=None):
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    try:
        logger.debug(f"Getting expiry for MAC {mac}")
        response = _get_session().get(
            url + "?type=account_info&action=get_main_info&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=15,
        )
        logger.debug(f"Expiry request status: {response.status_code}")
        expires = response.json()["js"]["phone"]
        if expires:
            logger.info(f"Got expiry for MAC {mac}: {expires}")
            return expires
    except requests.Timeout:
        logger.error(f"Timeout getting expiry for MAC {mac}")
    except requests.RequestException as e:
        logger.error(f"Request error getting expiry for MAC {mac}: {e}")
    except Exception as e:
        logger.error(f"Error getting expiry for MAC {mac}: {e}")


def getAllChannels(url, mac, token, proxy=None):
    """Get all channels with support for GET and POST methods."""
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    
    # Enhanced headers
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Authorization": "Bearer " + token,
        "Accept": "*/*",
        "Referer": base_url + "/",
        "X-User-Agent": "Model: MAG250; Link: WiFi",
    }
    
    params = {
        "type": "itv",
        "action": "get_all_channels",
        "force_ch_link_check": "",
        "JsHttpRequest": "1-xml"
    }
    
    # Try GET first (standard)
    try:
        logger.debug(f"Getting all channels for MAC {mac} (GET)")
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        logger.debug(f"Channels request status: {response.status_code}")
        channels = response.json()["js"]["data"]
        if channels:
            logger.info(f"Got {len(channels)} channels for MAC {mac}")
            return channels
    except Exception as e:
        logger.debug(f"GET request failed: {e}, trying POST")
    
    # Try POST as fallback (some portals require this)
    try:
        logger.debug(f"Getting all channels for MAC {mac} (POST)")
        response = _get_session().post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        logger.debug(f"Channels request status: {response.status_code}")
        channels = response.json()["js"]["data"]
        if channels:
            logger.info(f"Got {len(channels)} channels for MAC {mac} via POST")
            return channels
    except requests.Timeout:
        logger.error(f"Timeout getting channels for MAC {mac}")
    except requests.RequestException as e:
        logger.error(f"Request error getting channels for MAC {mac}: {e}")
    except Exception as e:
        logger.error(f"Error getting channels for MAC {mac}: {e}")


def getGenres(url, mac, token, proxy=None):
    """Get genres with support for GET and POST methods."""
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    params = {
        "action": "get_genres",
        "type": "itv",
        "JsHttpRequest": "1-xml"
    }
    
    # Try GET first
    try:
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=10,
        )
        genreData = response.json()["js"]
        if genreData:
            return genreData
    except Exception as e:
        logger.debug(f"GET genres failed: {e}, trying POST")
    
    # Try POST as fallback
    try:
        response = _get_session().post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=10,
        )
        genreData = response.json()["js"]
        if genreData:
            return genreData
    except:
        pass
    
    return None


def getGenreNames(url, mac, token, proxy=None):
    try:
        genreData = getGenres(url, mac, token, proxy)
        genres = {}
        for i in genreData:
            gid = i["id"]
            name = i["title"]
            genres[gid] = name
        if genres:
            return genres
    except:
        pass


def getLink(url, mac, token, cmd, proxy=None):
    """Get stream link with support for GET and POST methods."""
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    params = {
        "type": "itv",
        "action": "create_link",
        "cmd": cmd,
        "series": "0",
        "forced_storage": "false",
        "disable_ad": "false",
        "download": "false",
        "force_ch_link_check": "false",
        "JsHttpRequest": "1-xml"
    }
    
    # Try GET first
    try:
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=10,
        )
        data = response.json()
        link = data["js"]["cmd"].split()[-1]
        if link:
            return link
    except Exception as e:
        logger.debug(f"GET link failed: {e}, trying POST")
    
    # Try POST as fallback
    try:
        response = _get_session().post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=10,
        )
        data = response.json()
        link = data["js"]["cmd"].split()[-1]
        if link:
            return link
    except:
        pass
    
    return None


def getEpg(url, mac, token, period, proxy=None):
    """Get EPG with support for GET and POST methods."""
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    params = {
        "type": "itv",
        "action": "get_epg_info",
        "period": str(period),
        "JsHttpRequest": "1-xml"
    }
    
    # Try GET first
    try:
        logger.debug(f"Getting EPG for MAC {mac} (GET)")
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        data = response.json()["js"]["data"]
        if data:
            logger.debug(f"Got EPG data for {len(data)} channels via GET")
            return data
    except Exception as e:
        logger.debug(f"GET EPG failed: {e}, trying POST")
    
    # Try POST as fallback
    try:
        logger.debug(f"Getting EPG for MAC {mac} (POST)")
        response = _get_session().post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        data = response.json()["js"]["data"]
        if data:
            logger.debug(f"Got EPG data for {len(data)} channels via POST")
            return data
    except Exception as e:
        logger.debug(f"POST EPG failed: {e}")
    
    return None


def parseM3U(content):
    """Parse M3U playlist content and extract channels."""
    import re
    channels = []
    lines = content.split('\n')
    
    current_channel = {}
    channel_id = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Parse #EXTINF line
        if line.startswith('#EXTINF:'):
            channel_id += 1
            current_channel = {
                'id': str(channel_id),
                'number': str(channel_id)
            }
            
            # Extract tvg-id
            tvg_id_match = re.search(r'tvg-id="([^"]*)"', line)
            if tvg_id_match:
                current_channel['tvg_id'] = tvg_id_match.group(1)
            
            # Extract tvg-name
            tvg_name_match = re.search(r'tvg-name="([^"]*)"', line)
            if tvg_name_match:
                current_channel['tvg_name'] = tvg_name_match.group(1)
            
            # Extract tvg-logo
            tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', line)
            if tvg_logo_match:
                current_channel['logo'] = tvg_logo_match.group(1)
            
            # Extract group-title (genre)
            group_match = re.search(r'group-title="([^"]*)"', line)
            if group_match:
                current_channel['tv_genre_id'] = group_match.group(1)
            
            # Extract channel name (after last comma)
            name_match = re.search(r',(.+)$', line)
            if name_match:
                current_channel['name'] = name_match.group(1).strip()
        
        # Parse URL line (follows #EXTINF)
        elif line and not line.startswith('#') and current_channel:
            current_channel['cmd'] = line
            channels.append(current_channel)
            current_channel = {}
    
    return channels


def getM3UChannels(url, proxy=None):
    """Fetch and parse M3U playlist."""
    proxies = {"http": proxy, "https": proxy}
    headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}
    
    try:
        logger.debug(f"Fetching M3U playlist from {url}")
        response = _get_session().get(
            url,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        
        if response.status_code == 200:
            channels = parseM3U(response.text)
            logger.info(f"Parsed {len(channels)} channels from M3U")
            return channels
    except Exception as e:
        logger.error(f"Error fetching M3U playlist: {e}")
    
    return None
