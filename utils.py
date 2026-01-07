"""
Utility functions for MacReplay
"""
import re
import logging

logger = logging.getLogger("MacReplay")


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
