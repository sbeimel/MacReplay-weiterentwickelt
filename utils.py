"""
Utility functions for MacReplayXC
"""
import re
import logging

logger = logging.getLogger("MacReplayXC")


def validate_mac_address(mac):
    """
    Validate MAC address format.
    
    Accepts formats:
    - 00:1A:79:XX:XX:XX
    - 00-1A-79-XX-XX-XX
    - 001A79XXXXXX
    
    Args:
        mac (str): MAC address to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not mac or not isinstance(mac, str):
        return False
    
    pattern = r'^([0-9A-Fa-f]{2}[:-]?){5}([0-9A-Fa-f]{2})$'
    return bool(re.match(pattern, mac.strip()))


def validate_url(url):
    """
    Validate URL format.
    
    Args:
        url (str): URL to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    
    pattern = r'^https?://.+'
    return bool(re.match(pattern, url.strip()))


def normalize_mac_address(mac):
    """
    Normalize MAC address to standard format (XX:XX:XX:XX:XX:XX).
    
    Args:
        mac (str): MAC address in any format
        
    Returns:
        str: Normalized MAC address or original if invalid
    """
    if not validate_mac_address(mac):
        return mac
    
    # Remove all separators
    clean_mac = re.sub(r'[:-]', '', mac.strip())
    
    # Add colons every 2 characters
    normalized = ':'.join(clean_mac[i:i+2] for i in range(0, 12, 2))
    
    return normalized.upper()


def sanitize_channel_name(name):
    """
    Sanitize channel name for safe use in filenames and URLs.
    
    Args:
        name (str): Channel name
        
    Returns:
        str: Sanitized name
    """
    if not name:
        return ""
    
    # Remove or replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', str(name))
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    return sanitized


def format_duration(seconds):
    """
    Format duration in seconds to human-readable string.
    
    Args:
        seconds (int/float): Duration in seconds
        
    Returns:
        str: Formatted duration (e.g., "2h 30m", "45s")
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"


def safe_get_nested(dictionary, *keys, default=None):
    """
    Safely get nested dictionary values.
    
    Args:
        dictionary (dict): Dictionary to search
        *keys: Keys to traverse
        default: Default value if key not found
        
    Returns:
        Value at nested key or default
        
    Example:
        safe_get_nested(config, "portals", "portal1", "name", default="Unknown")
    """
    result = dictionary
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
            if result is None:
                return default
        else:
            return default
    return result


def chunk_list(lst, chunk_size):
    """
    Split a list into chunks of specified size.
    
    Args:
        lst (list): List to chunk
        chunk_size (int): Size of each chunk
        
    Yields:
        list: Chunks of the original list
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def retry_on_exception(func, max_retries=3, delay=1, exceptions=(Exception,)):
    """
    Retry a function on exception.
    
    Args:
        func (callable): Function to retry
        max_retries (int): Maximum number of retries
        delay (int): Delay between retries in seconds
        exceptions (tuple): Exceptions to catch
        
    Returns:
        Result of function or raises last exception
    """
    import time
    
    last_exception = None
    for attempt in range(max_retries):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
    
    raise last_exception


def get_client_ip(request):
    """
    Get client IP address from request, considering proxies.
    
    Args:
        request: Flask request object
        
    Returns:
        str: Client IP address
    """
    # Check for X-Forwarded-For header (proxy)
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    
    # Check for X-Real-IP header (nginx)
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    
    # Fall back to remote_addr
    return request.remote_addr or 'unknown'


def is_hls_url(url):
    """
    Check if URL is an HLS stream.
    
    Args:
        url (str): URL to check
        
    Returns:
        bool: True if HLS, False otherwise
    """
    if not url:
        return False
    
    url_lower = url.lower()
    return ('.m3u8' in url_lower or 
            'hls' in url_lower or 
            'stitcher' in url_lower or
            '/manifest/' in url_lower)


def parse_m3u_line(line):
    """
    Parse M3U playlist line to extract attributes.
    
    Args:
        line (str): M3U line (e.g., #EXTINF:-1 tvg-id="..." ...)
        
    Returns:
        dict: Parsed attributes
    """
    attributes = {}
    
    if not line.startswith('#EXTINF'):
        return attributes
    
    # Extract tvg-id
    tvg_id_match = re.search(r'tvg-id="([^"]*)"', line)
    if tvg_id_match:
        attributes['tvg_id'] = tvg_id_match.group(1)
    
    # Extract tvg-name
    tvg_name_match = re.search(r'tvg-name="([^"]*)"', line)
    if tvg_name_match:
        attributes['tvg_name'] = tvg_name_match.group(1)
    
    # Extract tvg-logo
    tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', line)
    if tvg_logo_match:
        attributes['tvg_logo'] = tvg_logo_match.group(1)
    
    # Extract group-title
    group_match = re.search(r'group-title="([^"]*)"', line)
    if group_match:
        attributes['group_title'] = group_match.group(1)
    
    # Extract channel name (after last comma)
    name_match = re.search(r',(.+)$', line)
    if name_match:
        attributes['name'] = name_match.group(1).strip()
    
    return attributes


def parse_proxy_url(proxy_url):
    """
    Parse proxy URL and determine proxy type and configuration.
    
    Supports:
    - HTTP: http://proxy:port or http://user:pass@proxy:port
    - HTTPS: https://proxy:port or https://user:pass@proxy:port  
    - SOCKS5: socks5://proxy:port or socks5://user:pass@proxy:port
    - SOCKS4: socks4://proxy:port or socks4://user:pass@proxy:port
    - Shadowsocks: ss://method:password@server:port
    
    Args:
        proxy_url (str): Proxy URL to parse
        
    Returns:
        dict: Proxy configuration for requests library or None if invalid
    """
    if not proxy_url or not isinstance(proxy_url, str):
        return None
    
    proxy_url = proxy_url.strip()
    if not proxy_url:
        return None
    
    # Check for Shadowsocks proxies
    if proxy_url.startswith('ss://'):
        # Parse Shadowsocks URL: ss://method:password@server:port
        try:
            import base64
            from urllib.parse import urlparse
            
            parsed = urlparse(proxy_url)
            if parsed.hostname and parsed.port:
                # Extract method and password from userinfo
                if parsed.username and parsed.password:
                    method = parsed.username
                    password = parsed.password
                else:
                    # Try base64 decoding for method:password
                    if '@' in proxy_url:
                        auth_part = proxy_url.split('://')[1].split('@')[0]
                        try:
                            decoded = base64.b64decode(auth_part).decode('utf-8')
                            if ':' in decoded:
                                method, password = decoded.split(':', 1)
                            else:
                                return None
                        except:
                            return None
                    else:
                        return None
                
                return {
                    'type': 'shadowsocks',
                    'server': parsed.hostname,
                    'port': parsed.port,
                    'method': method,
                    'password': password
                }
        except Exception as e:
            logger.debug(f"Failed to parse Shadowsocks URL: {e}")
            return None
    
    # Check for SOCKS proxies
    if proxy_url.startswith(('socks5://', 'socks4://')):
        # SOCKS proxy - return as-is for requests[socks]
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    # Check for HTTP/HTTPS proxies
    if proxy_url.startswith(('http://', 'https://')):
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    # If no protocol specified, assume HTTP
    if '://' not in proxy_url:
        http_url = f"http://{proxy_url}"
        return {
            'http': http_url,
            'https': http_url
        }
    
    return None


def validate_proxy_url(proxy_url):
    """
    Validate proxy URL format.
    
    Args:
        proxy_url (str): Proxy URL to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not proxy_url or not isinstance(proxy_url, str):
        return True  # Empty proxy is valid (no proxy)
    
    proxy_url = proxy_url.strip()
    if not proxy_url:
        return True  # Empty proxy is valid
    
    # Pattern for proxy URLs
    patterns = [
        r'^https?://[^:]+:\d+$',  # http://host:port
        r'^https?://[^:]+:[^@]+@[^:]+:\d+$',  # http://user:pass@host:port
        r'^socks[45]://[^:]+:\d+$',  # socks5://host:port
        r'^socks[45]://[^:]+:[^@]+@[^:]+:\d+$',  # socks5://user:pass@host:port
        r'^ss://[^@]+@[^:]+:\d+$',  # ss://method:password@host:port
        r'^[^:]+:\d+$',  # host:port (will be treated as HTTP)
    ]
    
    return any(re.match(pattern, proxy_url) for pattern in patterns)


def get_proxy_type(proxy_url):
    """
    Get the type of proxy from URL.
    
    Args:
        proxy_url (str): Proxy URL
        
    Returns:
        str: 'http', 'https', 'socks5', 'socks4', 'shadowsocks', or 'unknown'
    """
    if not proxy_url:
        return 'none'
    
    proxy_url = proxy_url.strip().lower()
    
    if proxy_url.startswith('ss://'):
        return 'shadowsocks'
    elif proxy_url.startswith('socks5://'):
        return 'socks5'
    elif proxy_url.startswith('socks4://'):
        return 'socks4'
    elif proxy_url.startswith('https://'):
        return 'https'
    elif proxy_url.startswith('http://'):
        return 'http'
    elif '://' not in proxy_url:
        return 'http'  # Default to HTTP
    else:
        return 'unknown'


def get_supported_shadowsocks_method(requested_method):
    """
    Get a supported Shadowsocks encryption method, with fallback if requested method is not supported.
    
    Args:
        requested_method (str): The requested encryption method
        
    Returns:
        str: A supported encryption method
    """
    # Mapping of unsupported methods to supported alternatives
    method_fallbacks = {
        'aes-256-gcm': 'aes-256-cfb',
        'aes-192-gcm': 'aes-192-cfb', 
        'aes-128-gcm': 'aes-128-cfb',
        'chacha20-ietf-poly1305': 'chacha20',
        'xchacha20-ietf-poly1305': 'chacha20',
    }
    
    # List of known supported methods (shadowsocks==2.8.2)
    supported_methods = [
        'aes-256-cfb', 'aes-192-cfb', 'aes-128-cfb',
        'chacha20', 'salsa20',
        'rc4-md5', 'bf-cfb', 'des-cfb'  # Less secure but supported
    ]
    
    # Check if requested method is supported
    if requested_method in supported_methods:
        return requested_method
    
    # Check if we have a fallback mapping
    if requested_method in method_fallbacks:
        fallback_method = method_fallbacks[requested_method]
        logger.info(f"Shadowsocks method fallback: {requested_method} → {fallback_method}")
        return fallback_method
    
    # Default fallback to most secure supported method
    logger.warning(f"Unknown Shadowsocks method '{requested_method}', using 'aes-256-cfb' as fallback")
    return 'aes-256-cfb'


def create_shadowsocks_session(ss_config):
    """
    Create a requests session configured to use Shadowsocks proxy.
    
    Args:
        ss_config (dict): Shadowsocks configuration with server, port, method, password
        
    Returns:
        requests.Session: Configured session or None if failed
    """
    try:
        # Apply Shadowsocks compatibility fix for Python 3.10+
        try:
            from shadowsocks_fix import apply_shadowsocks_fix
            apply_shadowsocks_fix()
        except ImportError:
            # Fallback: apply fix inline
            import sys
            if sys.version_info >= (3, 10):
                import collections.abc
                import collections
                if not hasattr(collections, 'MutableMapping'):
                    collections.MutableMapping = collections.abc.MutableMapping
                if not hasattr(collections, 'Mapping'):
                    collections.Mapping = collections.abc.Mapping
                if not hasattr(collections, 'Iterable'):
                    collections.Iterable = collections.abc.Iterable
        
        import shadowsocks.local
        import threading
        import time
        import socket
        import requests
        
        # Check and adjust encryption method if needed
        original_method = ss_config['method']
        adjusted_method = get_supported_shadowsocks_method(original_method)
        
        if adjusted_method != original_method:
            logger.warning(f"Shadowsocks method '{original_method}' not supported, using '{adjusted_method}' instead")
        
        logger.info(f"Creating Shadowsocks session for {ss_config['server']}:{ss_config['port']} using {adjusted_method}")
        
        # Find available local port for SOCKS proxy
        sock = socket.socket()
        sock.bind(('', 0))
        local_port = sock.getsockname()[1]
        sock.close()
        
        # Configure Shadowsocks local client with improved settings
        config = {
            'server': ss_config['server'],
            'server_port': ss_config['port'],
            'local_address': '127.0.0.1',
            'local_port': local_port,
            'password': ss_config['password'],
            'method': adjusted_method,  # Use the adjusted/supported method
            'timeout': 30,  # Shorter timeout for faster failure detection
            'fast_open': False,
            'workers': 1,
            'verbose': True  # Enable verbose logging for debugging
        }
        
        logger.debug(f"Shadowsocks config: server={config['server']}:{config['server_port']}, method={config['method']}, local_port={local_port}")
        
        # Test server connectivity first
        logger.debug(f"Testing connectivity to Shadowsocks server {ss_config['server']}:{ss_config['port']}")
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(10)
        try:
            result = test_sock.connect_ex((ss_config['server'], ss_config['port']))
            if result != 0:
                logger.error(f"Cannot connect to Shadowsocks server {ss_config['server']}:{ss_config['port']} - connection refused (error {result})")
                logger.error("This could indicate:")
                logger.error("1. Server is down or unreachable")
                logger.error("2. Port is blocked by firewall")
                logger.error("3. Incorrect server address or port")
                logger.error("4. Network connectivity issues")
                return None
            else:
                logger.debug(f"Successfully connected to Shadowsocks server {ss_config['server']}:{ss_config['port']}")
        except Exception as e:
            logger.error(f"Failed to test Shadowsocks server connectivity: {e}")
            return None
        finally:
            test_sock.close()
        
        # Start Shadowsocks local client in background thread
        ss_error = []  # Capture errors from thread
        
        def run_ss_local():
            try:
                logger.debug("Starting Shadowsocks local client thread")
                
                # Alternative approach: Use shadowsocks programmatically
                import sys
                import os
                import tempfile
                import json
                
                # Create temporary config file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(config, f)
                    config_file = f.name
                
                try:
                    # Set sys.argv for shadowsocks (it reads from sys.argv)
                    original_argv = sys.argv.copy()
                    sys.argv = ['shadowsocks', '-c', config_file]
                    
                    # Call main without arguments (it reads from sys.argv)
                    shadowsocks.local.main()
                    
                finally:
                    # Restore original argv and cleanup
                    sys.argv = original_argv
                    try:
                        os.unlink(config_file)
                    except:
                        pass
                        
            except Exception as e:
                error_msg = f"Shadowsocks local client error: {e}"
                logger.error(error_msg)
                ss_error.append(error_msg)
        
        ss_thread = threading.Thread(target=run_ss_local, daemon=True)
        ss_thread.start()
        
        # Wait for local client to start and test multiple times
        max_attempts = 6
        for attempt in range(max_attempts):
            time.sleep(1)  # Wait 1 second between attempts
            
            # Check if thread had errors
            if ss_error:
                logger.error(f"Shadowsocks thread failed: {ss_error[0]}")
                return None
            
            # Test if local SOCKS5 proxy is working
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(2)
            try:
                result = test_sock.connect_ex(('127.0.0.1', local_port))
                if result == 0:
                    logger.debug(f"Shadowsocks local proxy responding on port {local_port} (attempt {attempt + 1})")
                    break
                else:
                    logger.debug(f"Shadowsocks local proxy not ready on port {local_port} (attempt {attempt + 1}/{max_attempts})")
            except Exception as e:
                logger.debug(f"Test connection failed (attempt {attempt + 1}): {e}")
            finally:
                test_sock.close()
            
            if attempt == max_attempts - 1:
                logger.error(f"Shadowsocks local proxy failed to start on port {local_port} after {max_attempts} attempts")
                logger.error("This could indicate:")
                logger.error("1. Incorrect Shadowsocks server credentials")
                logger.error("2. Unsupported encryption method")
                logger.error("3. Server-side authentication failure")
                logger.error("4. Network issues preventing local proxy startup")
                return None
        
        # Create session with SOCKS5 proxy pointing to local Shadowsocks client
        session = requests.Session()
        session.proxies = {
            'http': f'socks5://127.0.0.1:{local_port}',
            'https': f'socks5://127.0.0.1:{local_port}'
        }
        
        # Set reasonable timeouts and retries
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Test the session with a simple request
        try:
            logger.debug("Testing Shadowsocks session with connectivity check")
            test_response = session.get('http://httpbin.org/ip', timeout=10)
            if test_response.status_code == 200:
                logger.info(f"Shadowsocks session working correctly - external IP: {test_response.json().get('origin', 'unknown')}")
            else:
                logger.warning(f"Shadowsocks session test returned status {test_response.status_code}")
        except Exception as e:
            logger.warning(f"Shadowsocks session test failed (session may still work for IPTV): {e}")
        
        logger.info(f"Shadowsocks session created successfully with local SOCKS5 proxy on port {local_port}")
        return session
        
    except ImportError as e:
        logger.error(f"Shadowsocks library not available: {e}")
        logger.error("Install with: pip install shadowsocks==2.8.2")
        logger.error("Note: Some systems may require: pip install shadowsocks-libev")
        return None
    except Exception as e:
        error_msg = str(e)
        if "MutableMapping" in error_msg:
            logger.error("Shadowsocks compatibility issue detected (Python 3.10+ collections.MutableMapping)")
            logger.error("Solutions:")
            logger.error("1. Install compatible version: pip install shadowsocks-libev")
            logger.error("2. Use Python 3.9 or earlier")
            logger.error("3. Use SOCKS5 proxy instead of Shadowsocks")
        elif "method" in error_msg and "not supported" in error_msg:
            logger.error("Shadowsocks encryption method not supported")
            logger.error(f"Requested method: {ss_config.get('method', 'unknown')}")
            logger.error("Supported methods: aes-256-cfb, aes-192-cfb, aes-128-cfb, chacha20, salsa20")
            logger.error("Solutions:")
            logger.error("1. Change server to use aes-256-cfb instead of aes-256-gcm")
            logger.error("2. Use SOCKS5 proxy: socks5://server:port")
            logger.error("3. Use Gluetun for method conversion")
        else:
            logger.error(f"Failed to create Shadowsocks session: {e}")
            logger.error("Check your Shadowsocks configuration:")
            logger.error(f"- Server: {ss_config.get('server', 'unknown')}")
            logger.error(f"- Port: {ss_config.get('port', 'unknown')}")
            logger.error(f"- Method: {ss_config.get('method', 'unknown')}")
            logger.error("- Ensure server is running and accessible")
            logger.error("- Verify credentials are correct")
        return None