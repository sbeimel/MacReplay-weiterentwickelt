# Proxy Support in MacReplayXC

MacReplayXC supports multiple proxy types including HTTP/HTTPS, SOCKS, and Shadowsocks proxies for connecting to IPTV portals.

## Supported Proxy Types

### HTTP/HTTPS Proxies
- `http://proxy.example.com:8080`
- `https://proxy.example.com:8080`
- `http://username:password@proxy.example.com:8080`

### SOCKS Proxies
- `socks5://proxy.example.com:1080`
- `socks4://proxy.example.com:1080`
- `socks5://username:password@proxy.example.com:1080`

### Shadowsocks Proxies
- `ss://aes-256-gcm:password@proxy.example.com:8388`
- `ss://chacha20-ietf-poly1305:mypassword@server.com:443`

### Simplified Format
- `proxy.example.com:8080` (defaults to HTTP)

## Configuration

### Portal Configuration
When adding or editing a portal, you can specify a proxy in the "Proxy" field:

1. **HTTP Proxy**: `http://192.168.1.100:8080`
2. **SOCKS5 Proxy**: `socks5://192.168.1.100:1080`
3. **SOCKS5 with Authentication**: `socks5://user:pass@192.168.1.100:1080`
4. **Shadowsocks**: `ss://aes-256-gcm:mypassword@192.168.1.100:8388`

### Validation
The system automatically validates proxy URLs and will show an error if the format is incorrect.

## Use Cases

### When to Use SOCKS5
- **Better Performance**: SOCKS5 can be faster than HTTP proxies for some connections
- **Protocol Support**: SOCKS5 works at a lower level and supports any protocol
- **Authentication**: Built-in username/password authentication
- **Firewall Bypass**: Some networks allow SOCKS5 but block HTTP proxies

### When to Use Shadowsocks
- **Encryption**: All traffic is encrypted using modern ciphers
- **Censorship Resistance**: Designed to bypass internet censorship
- **Stealth**: Traffic appears as regular HTTPS connections
- **Performance**: Optimized for speed with minimal overhead

### When to Use HTTP Proxies
- **Web-Specific**: Optimized for HTTP/HTTPS traffic
- **Caching**: HTTP proxies can cache content
- **Content Filtering**: Can modify or filter HTTP content

## Technical Implementation

### Dependencies
- `requests[socks]` - Adds SOCKS proxy support to the requests library
- `PySocks` - SOCKS client implementation
- `shadowsocks` - Shadowsocks client implementation

### Code Changes
1. **utils.py**: Added proxy parsing and validation functions
2. **stb.py**: Updated all network functions to use parsed proxy configuration
3. **app-docker.py**: Added proxy validation in portal add/update functions
4. **templates/portals.html**: Updated UI with Shadowsocks examples and validation

### Functions Added
- `parse_proxy_url(proxy_url)` - Parses proxy URL into requests-compatible format
- `validate_proxy_url(proxy_url)` - Validates proxy URL format
- `get_proxy_type(proxy_url)` - Determines proxy type (http, socks5, shadowsocks, etc.)
- `create_shadowsocks_session(ss_config)` - Creates a session with Shadowsocks proxy

## Testing

Run the test scripts to verify proxy functionality:

```bash
python test_socks5_support.py
python test_shadowsocks_support.py
python test_shadowsocks_integration.py
```

This will test:
- Proxy URL parsing
- Type detection
- Validation logic
- SOCKS5 and Shadowsocks configuration

## Troubleshooting

### Quick Debugging Tools

1. **Shadowsocks Connectivity Test**
   ```bash
   python test_shadowsocks_connectivity.py ss://aes-256-gcm:password@server:port
   ```
   This script tests server connectivity, library availability, and proxy functionality.

2. **Gluetun + Shadowsocks Issues**
   See `GLUETUN_SHADOWSOCKS_TROUBLESHOOTING.md` for detailed Gluetun-specific troubleshooting.

### Common Issues

1. **"Invalid proxy format" error**
   - Check that the URL includes the protocol (socks5://, http://, ss://, etc.)
   - Ensure the port number is included
   - Verify username/password format if using authentication

2. **Connection timeouts with SOCKS5**
   - Verify the SOCKS5 server is running and accessible
   - Check firewall settings
   - Try without authentication first

3. **Authentication failures**
   - Verify username and password are correct
   - Some SOCKS5 servers don't support authentication
   - Try connecting without credentials first

4. **Shadowsocks connection issues**
   - Run the connectivity test script first: `python test_shadowsocks_connectivity.py ss://method:pass@server:port`
   - Verify the encryption method is supported
   - Check that the password is correct
   - Ensure the Shadowsocks server is running
   - Try a different encryption method

5. **"Unexpected EOF" with Shadowsocks**
   - Usually indicates server connectivity issues
   - Check if server is behind a firewall or NAT
   - Verify server credentials are correct
   - Test with the connectivity script

6. **Gluetun Configuration Confusion**
   - Don't confuse Gluetun's SOCKS5 proxy with Shadowsocks
   - Use `socks5://gluetun:1080` for Gluetun's SOCKS5 proxy
   - Use `ss://method:pass@gluetun:8388` for Gluetun's Shadowsocks server

### Debug Information
The system now provides detailed logging for Shadowsocks connections:
```
[INFO] Creating Shadowsocks session for server.com:8388 using aes-256-gcm
[DEBUG] Testing connectivity to Shadowsocks server server.com:8388
[DEBUG] Successfully connected to Shadowsocks server server.com:8388
[DEBUG] Shadowsocks local proxy responding on port 12345 (attempt 1)
[INFO] Shadowsocks session working correctly - external IP: 203.0.113.1
[INFO] Shadowsocks session created successfully with local SOCKS5 proxy on port 12345
```

### Error Analysis

**"Cannot connect to Shadowsocks server"**
- Server is down or unreachable
- Port is blocked by firewall
- Incorrect server address or port
- Network connectivity issues

**"Shadowsocks local proxy failed to start"**
- Incorrect server credentials
- Unsupported encryption method
- Server-side authentication failure
- Network issues preventing local proxy startup

**"Shadowsocks library not available"**
- Missing Python package: `pip install shadowsocks==2.8.2`
- MacReplayXC includes automatic Python 3.10+ compatibility fix
- Alternative: Use SOCKS5 proxy instead

**"collections.MutableMapping" Error (Python 3.10+)**
- Compatibility issue with older shadowsocks library
- Solution 1: Use MacReplayXC's built-in compatibility fix (automatic)
- Solution 2: Use Python 3.9 or earlier
- Solution 3: Use SOCKS5 proxy: `socks5://server:port`

## Examples

### Tor Network
```
socks5://127.0.0.1:9050
```

### SSH Tunnel
```
socks5://127.0.0.1:1080
```

### Commercial SOCKS5 Service
```
socks5://username:password@proxy.service.com:1080
```

### Shadowsocks Server
```
ss://aes-256-gcm:mypassword@shadowsocks.server.com:8388
```

## Shadowsocks Encryption Methods

Supported encryption methods:
- `aes-128-gcm` (recommended)
- `aes-256-gcm` (recommended)
- `chacha20-ietf-poly1305` (recommended)
- `xchacha20-ietf-poly1305`
- `aes-128-cfb`
- `aes-192-cfb`
- `aes-256-cfb`
- `rc4-md5` (deprecated, not recommended)

## Security Considerations

1. **Credentials in URLs**: Proxy credentials are stored in the configuration. Ensure your MacReplayXC instance is secure.
2. **Traffic Routing**: All portal traffic will go through the configured proxy.
3. **Logging**: Proxy URLs (including credentials) may appear in debug logs.
4. **Encryption**: Shadowsocks provides end-to-end encryption, while SOCKS5 and HTTP proxies may not encrypt traffic.

## Performance Notes

- Shadowsocks typically provides the best balance of security and performance
- SOCKS5 proxies typically have lower overhead than HTTP proxies
- Authentication adds a small overhead to connection establishment
- Connection pooling is maintained through the proxy
- Some IPTV portals may work better with specific proxy types