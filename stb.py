import requests
from requests.adapters import HTTPAdapter, Retry
from urllib.parse import urlparse
import re
import logging
import time

logger = logging.getLogger("MacReplay.stb")
logger.setLevel(logging.DEBUG)

# Session management with periodic refresh to prevent memory leaks
_session = None
_session_created = 0
_SESSION_MAX_AGE = 300  # Refresh session every 5 minutes


def _get_session():
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
        
        _session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
        _session.mount("http://", HTTPAdapter(max_retries=retries))
        _session.mount("https://", HTTPAdapter(max_retries=retries))
        _session_created = current_time
        logger.debug("Created new requests session")
    
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
    def parseResponse(url, data):
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

    url = urlparse(url).scheme + "://" + urlparse(url).netloc
    urls = [
        "/c/xpcom.common.js",
        "/client/xpcom.common.js",
        "/c_/xpcom.common.js",
        "/stalker_portal/c/xpcom.common.js",
        "/stalker_portal/c_/xpcom.common.js",
    ]

    proxies = {"http": proxy, "https": proxy}
    headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}

    try:
        session = _get_session()
        for i in urls:
            try:
                response = session.get(url + i, headers=headers, proxies=proxies, timeout=10)
            except:
                response = None
            if response:
                return parseResponse(url + i, response)
    except:
        pass

    # sometimes these pages dont like proxies!
    try:
        session = _get_session()
        for i in urls:
            try:
                response = session.get(url + i, headers=headers, timeout=10)
            except:
                response = None
            if response:
                return parseResponse(url + i, response)
    except:
        pass


def getToken(url, mac, proxy=None):
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}
    try:
        logger.debug(f"Getting token for MAC {mac} from {url}")
        response = _get_session().get(
            url + "?type=stb&action=handshake&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=20,
        )
        logger.debug(f"Token request status: {response.status_code}")
        token = response.json()["js"]["token"]
        if token:
            logger.info(f"Successfully got token for MAC {mac}")
            return token
    except requests.Timeout:
        logger.error(f"Timeout getting token for MAC {mac} from {url}")
    except requests.RequestException as e:
        logger.error(f"Request error getting token for MAC {mac}: {e}")
    except Exception as e:
        logger.error(f"Error getting token for MAC {mac}: {e}")


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
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    try:
        logger.debug(f"Getting all channels for MAC {mac}")
        response = _get_session().get(
            url
            + "?type=itv&action=get_all_channels&force_ch_link_check=&JsHttpRequest=1-xml",
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
    except requests.Timeout:
        logger.error(f"Timeout getting channels for MAC {mac}")
    except requests.RequestException as e:
        logger.error(f"Request error getting channels for MAC {mac}: {e}")
    except Exception as e:
        logger.error(f"Error getting channels for MAC {mac}: {e}")


def getGenres(url, mac, token, proxy=None):
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    try:
        response = _get_session().get(
            url + "?action=get_genres&type=itv&JsHttpRequest=1-xml",
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
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    try:
        response = _get_session().get(
            url
            + "?type=itv&action=create_link&cmd="
            + cmd
            + "&series=0&forced_storage=false&disable_ad=false&download=false&force_ch_link_check=false&JsHttpRequest=1-xml",
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


def getEpg(url, mac, token, period, proxy=None):
    proxies = {"http": proxy, "https": proxy}
    cookies = {"mac": mac, "stb_lang": "en", "timezone": "Europe/London"}
    headers = {
        "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
        "Authorization": "Bearer " + token,
    }
    try:
        response = _get_session().get(
            url
            + "?type=itv&action=get_epg_info&period="
            + str(period)
            + "&JsHttpRequest=1-xml",
            cookies=cookies,
            headers=headers,
            proxies=proxies,
            timeout=30,
        )
        data = response.json()["js"]["data"]
        if data:
            return data
    except:
        pass
