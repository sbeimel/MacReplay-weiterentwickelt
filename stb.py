import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urlparse
import re
import logging
import time
from utils import parse_proxy_url, validate_proxy_url, get_proxy_type, create_shadowsocks_session

# Try to import cloudscraper for Cloudflare bypass
try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    logging.getLogger("MacReplayXC.stb").info("cloudscraper not available - some portals with Cloudflare protection may not work")

logger = logging.getLogger("MacReplayXC.stb")
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


def _get_proxy_session(proxy=None, use_cloudscraper=False):
    """Get a session configured for the specified proxy type."""
    if not proxy:
        return _get_session(use_cloudscraper)
    
    proxy_config = parse_proxy_url(proxy)
    proxy_type = get_proxy_type(proxy)
    
    if proxy_type == 'shadowsocks' and proxy_config:
        # Create Shadowsocks session
        ss_session = create_shadowsocks_session(proxy_config)
        if ss_session:
            logger.debug(f"Using Shadowsocks session for proxy: {proxy}")
            return ss_session
        else:
            logger.warning(f"Failed to create Shadowsocks session, falling back to regular session")
            return _get_session(use_cloudscraper)
    else:
        # Use regular session for HTTP/SOCKS proxies
        return _get_session(use_cloudscraper)


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

    # Parse proxy configuration for all proxy types
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    logger.debug(f"Using proxy type: {proxy_type}, config: {proxies}")
    
    # Enhanced headers to bypass Cloudflare and other protections
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Referer": base_url + "/",
    }

    # Get appropriate session based on proxy type
    session = _get_proxy_session(proxy, use_cloudscraper=True)
    for path in urls:
        try:
            test_url = base_url + path
            logger.debug(f"Trying xpcom.common.js at: {test_url}")
            # For Shadowsocks, proxies=None since session is pre-configured
            request_proxies = None if proxy_type == 'shadowsocks' else proxies
            response = session.get(test_url, headers=headers, proxies=request_proxies, timeout=10)
            if response.status_code == 200:
                logger.debug(f"Found xpcom.common.js at: {test_url}")
                portal = parseResponse(test_url, response)
                if portal:
                    logger.info(f"Successfully parsed portal URL: {portal}")
                    return portal
        except Exception as e:
            logger.debug(f"Failed to fetch {path}: {e}")
            continue

    # Try without proxy (some portals don't like proxies) - skip for Shadowsocks
    if proxy_type != 'shadowsocks':
        logger.debug("Retrying without proxy...")
        no_proxy_session = _get_session(use_cloudscraper=True)
        for path in urls:
            try:
                test_url = base_url + path
                logger.debug(f"Trying xpcom.common.js at: {test_url} (no proxy)")
                response = no_proxy_session.get(test_url, headers=headers, timeout=10)
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
    # Parse proxy configuration for all proxy types
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    # Prepare enhanced cookies and headers
    import hashlib
    import random
    import string
    
    # Generate device IDs based on MAC
    device_id = hashlib.sha256(mac.encode()).hexdigest()
    device_id2 = hashlib.sha256((mac + "salt").encode()).hexdigest()
    serial_number = hashlib.md5(mac.encode()).hexdigest().upper()
    random_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
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
    
    # Enhanced headers to bypass protections
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept": "*/*",
        "Referer": base_url + "/",
        "X-User-Agent": f"Model: MAG250; Link: WiFi; MAC: {mac}", # Added MAC to match legacy logic
        "Authorization": "Bearer undefined"
    }
    
    # If URL already contains a path (like /c/ or /stalker_portal/), use it
    url_path = parsed.path.rstrip('/')
    
    # Try different endpoint variations
    endpoints = []
    
    # CRITICAL: If URL already ends with .php, use it directly first
    if url_path.endswith('.php'):
        # URL is already a complete endpoint like /portal.php
        endpoints.append(f"{url_path}?type=stb&action=handshake&JsHttpRequest=1-xml")
    elif url_path and url_path != '/':
        # URL has a path but not ending in .php - try appending portal.php etc.
        endpoints.extend([
            f"{url_path}/portal.php?type=stb&action=handshake&JsHttpRequest=1-xml",
            f"{url_path}/server/load.php?type=stb&action=handshake&JsHttpRequest=1-xml",
            f"{url_path}?type=stb&action=handshake&JsHttpRequest=1-xml",
        ])
    
    # Standard endpoints (only if not already ending in .php)
    if not url_path.endswith('.php'):
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
            session = _get_proxy_session(proxy)
            request_proxies = None if proxy_type == 'shadowsocks' else proxies
            response = session.get(
                full_url,
                cookies=cookies,
                headers=headers,
                proxies=request_proxies,
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
            elif response.status_code == 403:
                logger.debug(f"403 Forbidden on endpoint {endpoint} - trying MAG254/MAG420 headers and cookies")
                
                # Try with MAG254 headers
                headers_mag254 = headers.copy()
                headers_mag254["User-Agent"] = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2712 Safari/533.3"
                headers_mag254["X-User-Agent"] = "Model: MAG254; Link: WiFi"
                
                try:
                    response = session.get(
                        full_url,
                        cookies=cookies,
                        headers=headers_mag254,
                        proxies=request_proxies,
                        timeout=20,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if "js" in data and "token" in data["js"]:
                            token = data["js"]["token"]
                            if token:
                                logger.info(f"Successfully got token for MAC {mac} using endpoint: {full_url} (MAG254 fallback)")
                                return token
                            
                    # Start MAG 420 Fallback
                    if response.status_code == 403:
                         headers_mag420 = headers.copy()
                         headers_mag420["User-Agent"] = "Mozilla/5.0 (Linux; Android 7.0; MAG420) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.84 Mobile Safari/537.36"
                         headers_mag420["X-User-Agent"] = "Model: MAG420; Link: WiFi"
                         
                         response = session.get(
                            full_url,
                            cookies=cookies,
                            headers=headers_mag420,
                            proxies=request_proxies,
                            timeout=20,
                        )
                         if response.status_code == 200:
                            data = response.json()
                            if "js" in data and "token" in data["js"]:
                                token = data["js"]["token"]
                                if token:
                                    logger.info(f"Successfully got token for MAC {mac} using endpoint: {full_url} (MAG420 fallback)")
                                    return token

                except:
                    pass

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


def _get_enhanced_cookies(mac):
    """Generate enhanced cookies for STB emulation."""
    import hashlib
    import random
    import string
    
    device_id = hashlib.sha256(mac.encode()).hexdigest()
    device_id2 = hashlib.sha256((mac + "salt").encode()).hexdigest()
    serial_number = hashlib.md5(mac.encode()).hexdigest().upper()
    random_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    
    return {
        "mac": mac,
        "stb_lang": "en",
        "timezone": "Europe/London",
        "deviceId": device_id,
        "deviceId2": device_id2,
        "serial_number": serial_number,
        "sn": serial_number,
        "rand": random_id
    }

def getProfile(url, mac, token, proxy=None):
    # Parse proxy configuration
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    
    cookies = _get_enhanced_cookies(mac)
    
    # Enhanced headers
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept": "*/*",
        "Referer": base_url + "/",
        "X-User-Agent": f"Model: MAG250; Link: WiFi; MAC: {mac}",
        "Authorization": "Bearer " + token,
    }
    
    try:
        # Check if URL already involves a path
        parsed = urlparse(url)
        url_path = parsed.path.rstrip('/')
        
        # Determine the correct profile endpoint
        if url_path.endswith('.php'):
             profile_url = f"{url}?type=stb&action=get_profile&JsHttpRequest=1-xml"
        else:
             profile_url = f"{url}/portal.php?type=stb&action=get_profile&JsHttpRequest=1-xml"
             
        logger.debug(f"Getting profile for MAC {mac}")
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        
        response = session.get(
            profile_url,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
            timeout=15,
        )
        
        # Fallback if 404/403 - try alternative endpoints
        if response.status_code != 200:
             if url_path.endswith('.php'):
                 # Already using direct PHP file, try just append query
                 pass 
             else:
                 # Try other endpoints
                 alternatives = [
                     f"{url}/server/load.php?type=stb&action=get_profile&JsHttpRequest=1-xml",
                     f"{url}?type=stb&action=get_profile&JsHttpRequest=1-xml"
                 ]
                 for alt_url in alternatives:
                     try:
                         response = session.get(
                            alt_url,
                            cookies=cookies,
                            headers=headers,
                            proxies=request_proxies,
                            timeout=15,
                        )
                         if response.status_code == 200:
                             break
                     except:
                         pass

        logger.debug(f"Profile request status: {response.status_code}")
        
        js = response.json()["js"]
        logger.info(f"Got profile for MAC {mac}")
        return js
    except requests.Timeout:
        logger.error(f"Timeout getting profile for MAC {mac}")
    except requests.RequestException as e:
        logger.error(f"Request error getting profile for MAC {mac}: {e}")
    except Exception as e:
        logger.error(f"Error getting profile for MAC {mac}: {e}")
    return {}


def getExpires(url, mac, token, proxy=None):
    # Parse proxy configuration
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    
    cookies = _get_enhanced_cookies(mac)
    
    # Enhanced headers
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
        "Accept": "*/*",
        "Referer": base_url + "/",
        "X-User-Agent": f"Model: MAG250; Link: WiFi; MAC: {mac}",
        "Authorization": "Bearer " + token,
    }
    
    try:
        # Check if URL already involves a path
        parsed = urlparse(url)
        url_path = parsed.path.rstrip('/')
        
        # Determine endpoint
        if url_path.endswith('.php'):
             expires_url = f"{url}?type=account_info&action=get_main_info&JsHttpRequest=1-xml"
        else:
             expires_url = f"{url}/portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml"

        logger.debug(f"Getting expiry for MAC {mac}")
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        
        response = session.get(
            expires_url,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
            timeout=15,
        )
        
        # Fallback for endpoints
        if response.status_code != 200 and not url_path.endswith('.php'):
             try:
                 response = session.get(
                    f"{url}/server/load.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml",
                    cookies=cookies,
                    headers=headers,
                    proxies=request_proxies,
                    timeout=15,
                )
             except:
                 pass

        logger.debug(f"Expiry request status: {response.status_code}")
        
        # Determine active account status from 'phone' or other fields usually
        data = response.json()
        expires = data["js"].get("phone", "")
        
        if expires:
            logger.info(f"Got expiry for MAC {mac}: {expires}")
            return expires
        else:
            # Sometimes expiry is in different field or empty means unlimited
            return "Unlimited"
            
    except requests.Timeout:
        logger.error(f"Timeout getting expiry for MAC {mac}")
    except requests.RequestException as e:
        logger.error(f"Request error getting expiry for MAC {mac}: {e}")
    except Exception as e:
        logger.error(f"Error getting expiry for MAC {mac}: {e}")


def getAllChannels(url, mac, token, proxy=None):
    """Get all channels with support for GET and POST methods."""
    # Parse proxy configuration for all proxy types
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
    # Parse proxy configuration for all proxy types
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
            timeout=10,
        )
        genreData = response.json()["js"]
        if genreData:
            return genreData
    except Exception as e:
        logger.debug(f"GET genres failed: {e}, trying POST")
    
    # Try POST as fallback
    try:
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.post(
            url,
            data=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
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
    # Parse proxy configuration for all proxy types
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}
    
    try:
        logger.debug(f"Fetching M3U playlist from {url}")
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            headers=headers,
            proxies=request_proxies,
            timeout=30,
        )
        
        if response.status_code == 200:
            channels = parseM3U(response.text)
            logger.info(f"Parsed {len(channels)} channels from M3U")
            return channels
    except Exception as e:
        logger.error(f"Error fetching M3U playlist: {e}")
    
    return None


# ============================================================================
# VOD/Series API Functions
# ============================================================================

def getVodCategories(url, mac, token, proxy=None):
    """Get VOD categories from portal.
    
    API Endpoint: portal.php?type=vod&action=get_categories&JsHttpRequest=1-xml
    """
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    params = {
        "type": "vod",
        "action": "get_categories",
        "JsHttpRequest": "1-xml"
    }
    
    try:
        logger.debug(f"Getting VOD categories for MAC {mac}")
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            if "js" in data:
                categories = data["js"]
                logger.info(f"Got {len(categories)} VOD categories for MAC {mac}")
                return categories
    except Exception as e:
        logger.error(f"Error getting VOD categories: {e}")
    
    return None


def getSeriesCategories(url, mac, token, proxy=None):
    """Get Series categories from portal.
    
    API Endpoint: portal.php?type=series&action=get_categories&JsHttpRequest=1-xml
    """
    proxies = parse_proxy_url(proxy) if proxy else None
    proxy_type = get_proxy_type(proxy) if proxy else 'none'
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    params = {
        "type": "series",
        "action": "get_categories",
        "JsHttpRequest": "1-xml"
    }
    
    try:
        logger.debug(f"Getting Series categories for MAC {mac}")
        session = _get_proxy_session(proxy)
        request_proxies = None if proxy_type == 'shadowsocks' else proxies
        response = session.get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=request_proxies,
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json()
            if "js" in data:
                categories = data["js"]
                logger.info(f"Got {len(categories)} Series categories for MAC {mac}")
                return categories
    except Exception as e:
        logger.error(f"Error getting Series categories: {e}")
    
    return None


def getVodItems(url, mac, token, category_id, page=1, proxy=None):
    """Get VOD items for a category with pagination.
    
    API Endpoint: portal.php?type=vod&action=get_ordered_list&category={cat}&p={page}&JsHttpRequest=1-xml
    Based on macvod.py implementation.
    """
    proxies = {"http": proxy, "https": proxy} if proxy else None
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    # Build URL with all required parameters (matching macvod.py exactly)
    # macvod.py uses: type=vod&action=get_ordered_list&movie_id=0&season_id=0&episode_id=0&row=0&
    #                 JsHttpRequest=1-xml&category={cat}&sortby=added&fav=0&hd=0&not_ended=0&abc=*&genre=*&years=*&search=&p={page}
    params = {
        "type": "vod",
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
        "p": str(page)
    }
    
    try:
        logger.info(f"Getting VOD items for category {category_id}, page {page}, MAC {mac[:15]}...")
        
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        
        # Log full request URL for debugging
        logger.info(f"VOD items request URL: {response.url}")
        logger.info(f"VOD items response status: {response.status_code}")
        
        if response.status_code == 200:
            # Log raw response for debugging
            raw_text = response.text[:1000] if len(response.text) > 1000 else response.text
            logger.info(f"VOD items raw response: {raw_text}")
            
            try:
                data = response.json()
            except Exception as json_err:
                logger.error(f"Failed to parse JSON response: {json_err}")
                logger.error(f"Raw response: {response.text[:500]}")
                return None
            
            logger.debug(f"VOD items response keys: {data.keys() if isinstance(data, dict) else 'not dict'}")
            
            if "js" in data:
                js_data = data["js"]
                logger.debug(f"js_data type: {type(js_data)}")
                
                if isinstance(js_data, dict):
                    logger.debug(f"js_data keys: {js_data.keys()}")
                    
                    # Try multiple possible data keys
                    items = None
                    for data_key in ["data", "items", "list", "movies", "vods"]:
                        if data_key in js_data:
                            items = js_data[data_key]
                            logger.info(f"Found items under key '{data_key}'")
                            break
                    
                    if items is not None:
                        # Get total from various possible keys
                        total = 0
                        for total_key in ["total_items", "total", "count", "max_page_items"]:
                            if total_key in js_data:
                                try:
                                    total = int(js_data[total_key])
                                    break
                                except (ValueError, TypeError):
                                    pass
                        if total == 0:
                            total = len(items) if isinstance(items, list) else 0
                        
                        logger.info(f"Got {len(items) if isinstance(items, list) else 0} VOD items for category {category_id} (total: {total})")
                        return {
                            "items": items if isinstance(items, list) else [],
                            "total": total,
                            "page": page
                        }
                    else:
                        logger.warning(f"No data key found in js_data. Available keys: {list(js_data.keys())}")
                        logger.warning(f"js_data content: {str(js_data)[:500]}")
                        
                elif isinstance(js_data, list):
                    # Some APIs return items directly as list
                    logger.info(f"Got {len(js_data)} VOD items (list format) for category {category_id}")
                    return {
                        "items": js_data,
                        "total": len(js_data),
                        "page": page
                    }
                elif js_data is False or js_data is None:
                    logger.warning(f"API returned js=false/null - category may be empty or access denied")
                else:
                    logger.warning(f"Unexpected js structure: {type(js_data)}, value: {str(js_data)[:200]}")
            else:
                logger.warning(f"No 'js' key in response. Available keys: {data.keys() if isinstance(data, dict) else 'not dict'}")
                logger.warning(f"Full response: {str(data)[:500]}")
        else:
            logger.warning(f"VOD items request failed with status {response.status_code}")
            logger.warning(f"Response text: {response.text[:500]}")
    except Exception as e:
        logger.error(f"Error getting VOD items: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return None


def getSeriesItems(url, mac, token, category_id, page=1, proxy=None):
    """Get Series items for a category with pagination.
    
    API Endpoint: portal.php?type=series&action=get_ordered_list&category={cat}&p={page}&JsHttpRequest=1-xml
    Based on macvod.py implementation pattern.
    """
    proxies = {"http": proxy, "https": proxy} if proxy else None
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    # Build URL with all required parameters (matching macvod.py pattern)
    params = {
        "type": "series",
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
        "p": str(page)
    }
    
    try:
        logger.info(f"Getting Series items for category {category_id}, page {page}, MAC {mac[:15]}...")
        
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        
        # Log full request URL for debugging
        logger.info(f"Series items request URL: {response.url}")
        logger.info(f"Series items response status: {response.status_code}")
        
        if response.status_code == 200:
            # Log raw response for debugging
            raw_text = response.text[:1000] if len(response.text) > 1000 else response.text
            logger.info(f"Series items raw response: {raw_text}")
            
            try:
                data = response.json()
            except Exception as json_err:
                logger.error(f"Failed to parse JSON response: {json_err}")
                logger.error(f"Raw response: {response.text[:500]}")
                return None
            
            logger.debug(f"Series items response keys: {data.keys() if isinstance(data, dict) else 'not dict'}")
            
            if "js" in data:
                js_data = data["js"]
                logger.debug(f"js_data type: {type(js_data)}")
                
                if isinstance(js_data, dict):
                    logger.debug(f"js_data keys: {js_data.keys()}")
                    
                    # Try multiple possible data keys
                    items = None
                    for data_key in ["data", "items", "list", "series", "shows"]:
                        if data_key in js_data:
                            items = js_data[data_key]
                            logger.info(f"Found items under key '{data_key}'")
                            break
                    
                    if items is not None:
                        # Get total from various possible keys
                        total = 0
                        for total_key in ["total_items", "total", "count", "max_page_items"]:
                            if total_key in js_data:
                                try:
                                    total = int(js_data[total_key])
                                    break
                                except (ValueError, TypeError):
                                    pass
                        if total == 0:
                            total = len(items) if isinstance(items, list) else 0
                        
                        logger.info(f"Got {len(items) if isinstance(items, list) else 0} Series items for category {category_id} (total: {total})")
                        return {
                            "items": items if isinstance(items, list) else [],
                            "total": total,
                            "page": page
                        }
                    else:
                        logger.warning(f"No data key found in js_data. Available keys: {list(js_data.keys())}")
                        logger.warning(f"js_data content: {str(js_data)[:500]}")
                        
                elif isinstance(js_data, list):
                    # Some APIs return items directly as list
                    logger.info(f"Got {len(js_data)} Series items (list format) for category {category_id}")
                    return {
                        "items": js_data,
                        "total": len(js_data),
                        "page": page
                    }
                elif js_data is False or js_data is None:
                    logger.warning(f"API returned js=false/null - category may be empty or access denied")
                else:
                    logger.warning(f"Unexpected js structure: {type(js_data)}, value: {str(js_data)[:200]}")
            else:
                logger.warning(f"No 'js' key in response. Available keys: {data.keys() if isinstance(data, dict) else 'not dict'}")
                logger.warning(f"Full response: {str(data)[:500]}")
        else:
            logger.warning(f"Series items request failed with status {response.status_code}")
            logger.warning(f"Response text: {response.text[:500]}")
    except Exception as e:
        logger.error(f"Error getting Series items: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return None


def getSeriesInfo(url, mac, token, series_id, proxy=None, category_id="*"):
    """Get series details including seasons and episodes.
    
    API Endpoint: portal.php?type=series&action=get_ordered_list&movie_id={series_id}&JsHttpRequest=1-xml
    Based on macshow.py implementation - returns seasons with episode lists.
    """
    from urllib.parse import quote
    
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    # Full params matching macshow.py exactly
    params = {
        "type": "series",
        "action": "get_ordered_list",
        "movie_id": str(series_id),
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
    
    try:
        logger.info(f"Getting Series info for series {series_id}, category {category_id}")
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        
        logger.info(f"Series info request URL: {response.url}")
        logger.info(f"Series info response status: {response.status_code}")
        
        if response.status_code == 200:
            raw_text = response.text[:1000] if len(response.text) > 1000 else response.text
            logger.info(f"Series info raw response: {raw_text}")
            
            data = response.json()
            if "js" in data:
                js_data = data["js"]
                logger.info(f"Series info js type: {type(js_data)}")
                
                if isinstance(js_data, dict):
                    # Return the full js object which contains 'data' with seasons
                    logger.info(f"Series info keys: {js_data.keys() if isinstance(js_data, dict) else 'N/A'}")
                    return js_data
                elif isinstance(js_data, list):
                    # Some APIs return list directly
                    return {"data": js_data}
                    
    except Exception as e:
        logger.error(f"Error getting Series info: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return None


def getVodLink(url, mac, token, cmd, proxy=None):
    """Get playback URL for VOD item.
    
    API Endpoint: portal.php?type=vod&action=create_link&cmd={cmd}&JsHttpRequest=1-xml
    """
    from urllib.parse import quote
    
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    params = {
        "type": "vod",
        "action": "create_link",
        "cmd": cmd,
        "series": "0",
        "forced_storage": "false",
        "disable_ad": "false",
        "download": "false",
        "JsHttpRequest": "1-xml"
    }
    
    try:
        logger.debug(f"Getting VOD link for cmd: {cmd[:50]}...")
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            if "js" in data and "cmd" in data["js"]:
                # Extract URL from cmd (format: "ffmpeg http://...")
                link = data["js"]["cmd"].split()[-1]
                logger.debug(f"Got VOD link: {link[:50]}...")
                return link
    except Exception as e:
        logger.error(f"Error getting VOD link: {e}")
    
    return None


def getSeriesLink(url, mac, token, cmd, episode_num, season_id=None, episode_id=None, proxy=None):
    """Get playback URL for Series episode.
    
    API Endpoint: portal.php?type=vod&action=create_link&cmd={cmd}&series={episode_num}&JsHttpRequest=1-xml
    
    Note: The 'series' parameter is the episode NUMBER, not the series ID!
    Based on macshow.py: url = f"{base_url}/portal.php?type=vod&action=create_link&cmd={quote(cmd)}&series={episode_num}"
    """
    from urllib.parse import quote
    
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    
    # The 'series' parameter is the episode number, not series_id!
    params = {
        "type": "vod",
        "action": "create_link",
        "cmd": cmd,
        "series": str(episode_num),  # This is the episode number!
        "forced_storage": "false",
        "disable_ad": "false",
        "download": "false",
        "JsHttpRequest": "1-xml"
    }
    
    try:
        logger.info(f"Getting Series link for episode {episode_num} (S{season_id}E{episode_id}) - series param: {episode_num}")
        response = _get_session().get(
            url,
            params=params,
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=15,
        )
        
        logger.info(f"Series link request URL: {response.url}")
        logger.info(f"Series link response status: {response.status_code}")
        
        if response.status_code == 200:
            raw_text = response.text[:500] if len(response.text) > 500 else response.text
            logger.info(f"Series link raw response: {raw_text}")
            
            data = response.json()
            if "js" in data and "cmd" in data["js"]:
                # Extract URL from cmd (format: "ffmpeg http://..." or just the URL)
                cmd_value = data["js"]["cmd"]
                link = cmd_value.split()[-1] if ' ' in cmd_value else cmd_value
                logger.info(f"Got Series link: {link[:80]}...")
                return link
    except Exception as e:
        logger.error(f"Error getting Series link: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    return None


def testStreamLink(link, proxy=None, timeout=5):
    """Test if a stream link is accessible.
    
    Makes a HEAD request to check if the stream URL is valid and accessible.
    Returns True if the stream is accessible, False otherwise.
    """
    if not link:
        return False
    
    proxies = {"http": proxy, "https": proxy} if proxy else None
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
    }
    
    try:
        logger.debug(f"Testing stream link: {link[:80]}...")
        
        # Try HEAD request first (faster)
        response = _get_session().head(
            link,
            headers=headers,
            proxies=proxies,
            timeout=timeout,
            allow_redirects=True
        )
        
        if response.status_code in [200, 206]:
            logger.info(f"Stream link test passed (HEAD): {link[:50]}...")
            return True
        
        # If HEAD fails, try GET with range header (some servers don't support HEAD)
        headers["Range"] = "bytes=0-1024"
        response = _get_session().get(
            link,
            headers=headers,
            proxies=proxies,
            timeout=timeout,
            stream=True,
            allow_redirects=True
        )
        
        if response.status_code in [200, 206]:
            # Read a small chunk to verify stream is working
            chunk = next(response.iter_content(chunk_size=1024), None)
            if chunk:
                logger.info(f"Stream link test passed (GET): {link[:50]}...")
                return True
        
        logger.warning(f"Stream link test failed with status {response.status_code}: {link[:50]}...")
        return False
        
    except Exception as e:
        logger.warning(f"Stream link test failed: {e}")
        return False


# ============================================================================
# Smart MAC Selection System with Internal Usage Tracking
# ============================================================================

# Global tracking of internally used MACs
_internal_mac_usage = {}

def markMacAsUsed(mac, usage_type="internal", details=None):
    """Mark a MAC as being used internally by our system.
    
    Args:
        mac: MAC address being used
        usage_type: Type of usage (e.g., "streaming", "epg", "channels")
        details: Additional details about the usage
    """
    global _internal_mac_usage
    import time
    
    _internal_mac_usage[mac] = {
        'usage_type': usage_type,
        'details': details or {},
        'started_at': time.time(),
        'last_activity': time.time()
    }
    logger.debug(f"Marked MAC {mac} as used for {usage_type}")

def markMacAsUnused(mac):
    """Mark a MAC as no longer being used internally."""
    global _internal_mac_usage
    
    if mac in _internal_mac_usage:
        del _internal_mac_usage[mac]
        logger.debug(f"Marked MAC {mac} as unused")

def updateMacActivity(mac):
    """Update the last activity time for an internally used MAC."""
    global _internal_mac_usage
    import time
    
    if mac in _internal_mac_usage:
        _internal_mac_usage[mac]['last_activity'] = time.time()

def isInternallyUsed(mac):
    """Check if a MAC is currently being used internally."""
    global _internal_mac_usage
    return mac in _internal_mac_usage

def getInternalUsage(mac):
    """Get internal usage information for a MAC."""
    global _internal_mac_usage
    return _internal_mac_usage.get(mac)

def calculateStreamUsage(watchdog_timeout, playback_limit):
    """Calculate estimated stream usage based on watchdog timeout and limits.
    
    Returns tuple: (estimated_streams_used, max_streams, usage_ratio)
    """
    if not watchdog_timeout or not playback_limit:
        return (0, playback_limit or 1, 0.0)
    
    # Estimate streams based on activity level
    if watchdog_timeout < 60:  # Very active - likely using streams
        estimated_used = min(playback_limit, max(1, playback_limit // 2))  # At least half capacity
    elif watchdog_timeout < 300:  # Active - some streams likely
        estimated_used = min(playback_limit, max(1, playback_limit // 3))  # About 1/3 capacity
    elif watchdog_timeout < 1800:  # Moderate - minimal usage
        estimated_used = 1 if playback_limit > 1 else 0
    else:  # Idle - no streams
        estimated_used = 0
    
    usage_ratio = estimated_used / playback_limit if playback_limit > 0 else 0.0
    
    return (estimated_used, playback_limit, usage_ratio)

def checkMacStatus(url, mac, proxy=None):
    """Check the real-time status of a single MAC address.
    
    Returns a dict with MAC status information including:
    - watchdog_timeout: seconds since last activity
    - playback_limit: max concurrent streams allowed
    - account_active: whether account is active
    - is_blocked: whether MAC is blocked
    - expires: expiry date string
    - internal_usage: whether MAC is used internally by our system
    - stream_usage: estimated stream usage (used/total)
    - success: whether check was successful
    """
    try:
        # Clear session to ensure clean state and avoid cookie pollution from previous MACs
        clear_session()
        
        # Get token first
        token = getToken(url, mac, proxy)
        if not token:
            return {
                'success': False,
                'mac': mac,
                'error': 'Failed to get authentication token'
            }
        
        # Get profile information (contains watchdog_timeout)
        profile = getProfile(url, mac, token, proxy)
        if not profile:
            return {
                'success': False,
                'mac': mac,
                'error': 'Failed to get profile information'
            }
        
        # Get account information (contains expiry)
        expires = getExpires(url, mac, token, proxy)
        
        # Extract key status information
        watchdog_timeout = profile.get('watchdog_timeout')
        playback_limit = profile.get('playback_limit', 1)
        account_status = profile.get('status', 0)
        is_blocked = profile.get('blocked', '0') != '0'
        
        # Check internal usage
        internal_usage = getInternalUsage(mac)
        is_internally_used = isInternallyUsed(mac)
        
        # Calculate stream usage
        streams_used, max_streams, usage_ratio = calculateStreamUsage(watchdog_timeout, playback_limit)
        
        # Adjust status based on internal usage
        if is_internally_used:
            # If we're using it internally, mark as at least partially used
            streams_used = max(streams_used, 1)
        
        return {
            'success': True,
            'mac': mac,
            'watchdog_timeout': watchdog_timeout,
            'playback_limit': playback_limit,
            'account_active': account_status == 1,
            'is_blocked': is_blocked,
            'expires': expires,
            'token': token,
            'internal_usage': internal_usage,
            'is_internally_used': is_internally_used,
            'streams_used': streams_used,
            'max_streams': max_streams,
            'usage_ratio': usage_ratio
        }
        
    except Exception as e:
        logger.error(f"Error checking MAC status for {mac}: {e}")
        return {
            'success': False,
            'mac': mac,
            'error': str(e)
        }


def getMacAvailabilityScore(mac_status):
    """Calculate availability score for a MAC address based on its status.
    
    Returns a score from 0-100 where:
    - 100 = Completely free and available
    - 0 = Completely unavailable
    
    Factors considered:
    - Stream usage (lower usage = higher score)
    - Internal usage (penalize if we're using it)
    - Account status (active = good)
    - Blocked status (blocked = bad)
    - Available stream slots
    """
    if not mac_status.get('success', False):
        return 0
    
    score = 0
    
    # Account must be active and not blocked
    if not mac_status.get('account_active', False):
        return 0
    
    if mac_status.get('is_blocked', False):
        return 0
    
    # Base score for working MAC
    score = 20
    
    # Stream usage scoring (most important factor)
    streams_used = mac_status.get('streams_used', 0)
    max_streams = mac_status.get('max_streams', 1)
    usage_ratio = mac_status.get('usage_ratio', 0.0)
    
    if usage_ratio == 0.0:  # No streams used
        score += 60
    elif usage_ratio <= 0.33:  # Low usage (1/3 or less)
        score += 40
    elif usage_ratio <= 0.66:  # Medium usage (2/3 or less)
        score += 20
    else:  # High usage (more than 2/3)
        score += 0
    
    # Internal usage penalty
    if mac_status.get('is_internally_used', False):
        score -= 15  # Penalty for internal usage
    
    # Available streams bonus
    available_streams = max_streams - streams_used
    if available_streams > 0:
        score += min(available_streams * 5, 20)  # Up to 20 bonus points
    
    return max(0, min(score, 100))


def selectBestMac(url, mac_list, proxy=None, min_score=50):
    """Select the best available MAC address from a list.
    
    Args:
        url: Portal URL
        mac_list: List of MAC addresses to check
        proxy: Proxy configuration (optional)
        min_score: Minimum availability score required (default: 50)
    
    Returns:
        dict: Best MAC info with status, or None if no suitable MAC found
    """
    if not mac_list:
        logger.warning("No MAC addresses provided for selection")
        return None
    
    logger.info(f"Selecting best MAC from {len(mac_list)} candidates...")
    
    mac_scores = []
    
    # Check status of all MACs
    for mac in mac_list:
        logger.debug(f"Checking status of MAC {mac}")
        status = checkMacStatus(url, mac, proxy)
        
        if status['success']:
            score = getMacAvailabilityScore(status)
            mac_scores.append({
                'mac': mac,
                'status': status,
                'score': score
            })
            logger.info(f"MAC {mac}: Score {score}/100 (watchdog: {status.get('watchdog_timeout', 'N/A')}s)")
        else:
            logger.warning(f"MAC {mac}: Status check failed - {status.get('error', 'Unknown error')}")
    
    # Sort by score (highest first)
    mac_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # Find best MAC that meets minimum score
    for mac_info in mac_scores:
        if mac_info['score'] >= min_score:
            logger.info(f"Selected MAC {mac_info['mac']} with score {mac_info['score']}/100")
            return mac_info
    
    # If no MAC meets minimum score, return the best available
    if mac_scores:
        best_mac = mac_scores[0]
        logger.warning(f"No MAC meets minimum score {min_score}, using best available: {best_mac['mac']} (score: {best_mac['score']}/100)")
        return best_mac
    
    logger.error("No working MAC addresses found")
    return None


def getChannelsWithSmartMac(url, mac_list, proxy=None):
    """Get channels using the best available MAC address.
    
    Automatically selects the most suitable MAC and retrieves channels.
    """
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting channels")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    # Mark MAC as used for channel retrieval
    markMacAsUsed(mac, "channels", {"url": url})
    
    try:
        logger.info(f"Getting channels using MAC {mac}")
        result = getAllChannels(url, mac, token, proxy)
        updateMacActivity(mac)
        return result
    finally:
        # Mark as unused after operation
        markMacAsUnused(mac)


def getLinkWithSmartMac(url, mac_list, cmd, proxy=None):
    """Get stream link using the best available MAC address.
    
    Automatically selects the most suitable MAC and retrieves stream link.
    """
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting stream link")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    # Mark MAC as used for streaming (keep marked longer)
    markMacAsUsed(mac, "streaming", {"url": url, "cmd": cmd})
    
    logger.info(f"Getting stream link using MAC {mac}")
    result = getLink(url, mac, token, cmd, proxy)
    updateMacActivity(mac)
    
    # Don't unmark streaming MACs immediately - they stay marked
    return result


def getEpgWithSmartMac(url, mac_list, period, proxy=None):
    """Get EPG using the best available MAC address.
    
    Automatically selects the most suitable MAC and retrieves EPG data.
    """
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting EPG")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting EPG using MAC {mac}")
    return getEpg(url, mac, token, period, proxy)


def getVodCategoriesWithSmartMac(url, mac_list, proxy=None):
    """Get VOD categories using the best available MAC address."""
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting VOD categories")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting VOD categories using MAC {mac}")
    return getVodCategories(url, mac, token, proxy)


def getVodItemsWithSmartMac(url, mac_list, category_id, page=1, proxy=None):
    """Get VOD items using the best available MAC address."""
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting VOD items")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting VOD items using MAC {mac}")
    return getVodItems(url, mac, token, category_id, page, proxy)


def getSeriesCategoriesWithSmartMac(url, mac_list, proxy=None):
    """Get Series categories using the best available MAC address."""
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting Series categories")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting Series categories using MAC {mac}")
    return getSeriesCategories(url, mac, token, proxy)


def getSeriesItemsWithSmartMac(url, mac_list, category_id, page=1, proxy=None):
    """Get Series items using the best available MAC address."""
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting Series items")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting Series items using MAC {mac}")
    return getSeriesItems(url, mac, token, category_id, page, proxy)


def getVodLinkWithSmartMac(url, mac_list, cmd, proxy=None):
    """Get VOD playback link using the best available MAC address."""
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting VOD link")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting VOD link using MAC {mac}")
    return getVodLink(url, mac, token, cmd, proxy)


def getSeriesLinkWithSmartMac(url, mac_list, cmd, episode_num, season_id=None, episode_id=None, proxy=None):
    """Get Series playback link using the best available MAC address."""
    best_mac = selectBestMac(url, mac_list, proxy)
    if not best_mac:
        logger.error("No suitable MAC address available for getting Series link")
        return None
    
    mac = best_mac['mac']
    token = best_mac['status']['token']
    
    logger.info(f"Getting Series link using MAC {mac}")
    return getSeriesLink(url, mac, token, cmd, episode_num, season_id, episode_id, proxy)


def getMacStatusSummary(url, mac_list, proxy=None):
    """Get a summary of all MAC statuses for monitoring/debugging.
    
    Returns a list of MAC status information for all provided MACs.
    """
    logger.info(f"Getting status summary for {len(mac_list)} MAC addresses...")
    
    mac_statuses = []
    for mac in mac_list:
        status = checkMacStatus(url, mac, proxy)
        score = getMacAvailabilityScore(status) if status['success'] else 0
        
        # Determine availability status
        if not status['success']:
            availability = 'Unavailable'
        elif status.get('is_internally_used', False):
            availability = 'Used (Internal)'
        elif status.get('streams_used', 0) >= status.get('max_streams', 1):
            availability = 'Used (Full)'
        elif status.get('streams_used', 0) > 0:
            streams_used = status.get('streams_used', 0)
            max_streams = status.get('max_streams', 1)
            availability = f'Used ({streams_used}/{max_streams})'
        elif score >= 50:
            availability = 'Available'
        else:
            availability = 'Busy'
        
        mac_statuses.append({
            'mac': mac,
            'status': status,
            'score': score,
            'availability': availability,
            'stream_usage': f"{status.get('streams_used', 0)}/{status.get('max_streams', 1)}" if status['success'] else 'N/A',
            'internal_usage': status.get('is_internally_used', False)
        })
    
    # Sort by score for easy viewing
    mac_statuses.sort(key=lambda x: x['score'], reverse=True)
    
    return mac_statuses
