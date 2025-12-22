# Gluetun + Shadowsocks Troubleshooting Guide

## Overview
This guide helps troubleshoot Shadowsocks connection issues when using Gluetun as a VPN container with MacReplayXC.

## Understanding Gluetun vs Shadowsocks

### Gluetun
- **Purpose**: VPN client container that routes traffic through various VPN providers
- **Protocols**: Supports OpenVPN, Wireguard, and some VPN providers
- **SOCKS5**: Gluetun can expose a SOCKS5 proxy for applications to use

### Shadowsocks
- **Purpose**: Proxy protocol designed for censorship circumvention
- **Encryption**: Uses various encryption methods (AES, ChaCha20, etc.)
- **Stealth**: Traffic appears as regular HTTPS connections

## Common Configuration Issues

### Issue 1: Confusing Gluetun SOCKS5 with Shadowsocks

**Problem**: User tries to use Gluetun's SOCKS5 proxy as a Shadowsocks proxy
```
# WRONG - This is Gluetun's SOCKS5 proxy, not Shadowsocks
socks5://gluetun:1080
```

**Solution**: Use the correct proxy type
```
# CORRECT - Use SOCKS5 for Gluetun
socks5://gluetun:1080

# OR use actual Shadowsocks server
ss://aes-256-gcm:password@shadowsocks-server:8388
```

### Issue 2: Shadowsocks Server Behind Gluetun

**Problem**: Shadowsocks server is running inside Gluetun container but not accessible

**Gluetun Docker Compose Example**:
```yaml
version: '3.8'
services:
  gluetun:
    image: qmcgaw/gluetun
    container_name: gluetun
    cap_add:
      - NET_ADMIN
    environment:
      - VPN_SERVICE_PROVIDER=your_provider
      - VPN_TYPE=openvpn
      - OPENVPN_USER=your_user
      - OPENVPN_PASSWORD=your_password
      - SHADOWSOCKS=on
      - SHADOWSOCKS_PASSWORD=your_ss_password
      - SHADOWSOCKS_METHOD=aes-256-gcm
      - SHADOWSOCKS_PORT=8388
    ports:
      - "8388:8388"  # Shadowsocks port
      - "1080:1080"  # SOCKS5 proxy port
    restart: unless-stopped

  macreplayxc:
    image: your_macreplayxc_image
    container_name: macreplayxc
    depends_on:
      - gluetun
    environment:
      # Use Gluetun's Shadowsocks server
      - PROXY_URL=ss://aes-256-gcm:your_ss_password@gluetun:8388
    restart: unless-stopped
```

### Issue 3: Network Connectivity Problems

**Problem**: "Unexpected EOF" or connection refused errors

**Debugging Steps**:

1. **Check Gluetun Status**:
```bash
docker logs gluetun | grep -i shadowsocks
docker logs gluetun | grep -i error
```

2. **Test Shadowsocks Port**:
```bash
# From host machine
telnet localhost 8388

# From another container
telnet gluetun 8388
```

3. **Check Gluetun Network**:
```bash
docker exec gluetun netstat -tlnp | grep 8388
docker exec gluetun ss -tlnp | grep 8388
```

## MacReplayXC Configuration Examples

### Option 1: Use Gluetun's SOCKS5 Proxy
```
Proxy: socks5://gluetun:1080
```
- Simpler setup
- All traffic goes through Gluetun's VPN
- No Shadowsocks encryption (VPN provides encryption)

### Option 2: Use Gluetun's Shadowsocks Server
```
Proxy: ss://aes-256-gcm:your_password@gluetun:8388
```
- Double encryption (VPN + Shadowsocks)
- More complex setup
- Better for censorship circumvention

### Option 3: External Shadowsocks Server
```
Proxy: ss://chacha20-ietf-poly1305:secret@external-server.com:443
```
- Independent of Gluetun
- Direct Shadowsocks connection
- May not benefit from VPN routing

## Troubleshooting Steps

### Step 1: Verify Gluetun Configuration

Check Gluetun environment variables:
```bash
docker exec gluetun env | grep SHADOWSOCKS
```

Expected output:
```
SHADOWSOCKS=on
SHADOWSOCKS_PASSWORD=your_password
SHADOWSOCKS_METHOD=aes-256-gcm
SHADOWSOCKS_PORT=8388
```

### Step 2: Test Shadowsocks Connectivity

From MacReplayXC container:
```bash
# Test if Shadowsocks port is reachable
nc -zv gluetun 8388

# Test SOCKS5 proxy
curl --socks5 gluetun:1080 http://httpbin.org/ip
```

### Step 3: Check MacReplayXC Logs

Look for Shadowsocks-related errors:
```bash
docker logs macreplayxc | grep -i shadowsocks
docker logs macreplayxc | grep -i proxy
docker logs macreplayxc | grep -i "unexpected eof"
```

### Step 4: Validate Proxy Configuration

In MacReplayXC portal settings, ensure:
- Correct proxy format: `ss://method:password@server:port`
- Matching credentials with Gluetun configuration
- Correct server hostname (usually `gluetun` in Docker)
- Correct port (usually `8388` for Shadowsocks)

## Common Error Messages and Solutions

### "Unexpected EOF"
**Cause**: Connection dropped by server or network issues
**Solutions**:
1. Check Gluetun VPN connection status
2. Verify Shadowsocks server is running
3. Test network connectivity between containers
4. Check firewall rules

### "Connection refused"
**Cause**: Shadowsocks server not listening on specified port
**Solutions**:
1. Verify `SHADOWSOCKS=on` in Gluetun
2. Check port mapping in Docker Compose
3. Ensure Shadowsocks port is exposed
4. Restart Gluetun container

### "Authentication failed"
**Cause**: Incorrect Shadowsocks credentials
**Solutions**:
1. Verify password matches Gluetun configuration
2. Check encryption method is supported
3. Ensure no special characters causing parsing issues

### "Shadowsocks library not available"
**Cause**: Missing Python shadowsocks package
**Solutions**:
1. Ensure `shadowsocks==2.8.2` is in requirements.txt
2. Rebuild Docker image with updated requirements
3. Check if alternative shadowsocks packages are needed

## Best Practices

### 1. Use SOCKS5 for Simplicity
If you just need VPN routing, use Gluetun's SOCKS5 proxy:
```
socks5://gluetun:1080
```

### 2. Use Shadowsocks for Censorship Circumvention
If you need stealth and encryption:
```
ss://aes-256-gcm:strong_password@gluetun:8388
```

### 3. Monitor Container Health
```bash
# Check if containers are healthy
docker ps
docker logs gluetun --tail 50
docker logs macreplayxc --tail 50
```

### 4. Test Configuration Changes
After changing proxy settings:
1. Restart MacReplayXC container
2. Test portal connectivity
3. Check logs for errors
4. Verify external IP changed (if using VPN)

## Advanced Debugging

### Enable Verbose Logging

In MacReplayXC, the improved Shadowsocks implementation now includes:
- Server connectivity testing
- Detailed error messages
- Step-by-step connection debugging
- External IP verification

### Network Analysis

Use tcpdump to analyze traffic:
```bash
# Monitor traffic between containers
docker exec gluetun tcpdump -i any port 8388

# Monitor SOCKS5 traffic
docker exec gluetun tcpdump -i any port 1080
```

### Container Network Inspection

```bash
# Check container networks
docker network ls
docker network inspect bridge

# Check container connectivity
docker exec macreplayxc ping gluetun
docker exec macreplayxc nslookup gluetun
```

## Recommended Configuration

For most users, this Docker Compose setup works well:

```yaml
version: '3.8'
services:
  gluetun:
    image: qmcgaw/gluetun
    container_name: gluetun
    cap_add:
      - NET_ADMIN
    environment:
      - VPN_SERVICE_PROVIDER=surfshark  # or your provider
      - VPN_TYPE=wireguard
      - WIREGUARD_PRIVATE_KEY=your_key
      - WIREGUARD_ADDRESSES=10.64.0.1/32
      - SERVER_COUNTRIES=Netherlands
      - HTTPPROXY=on
      - HTTPPROXY_LOG=on
      - SHADOWSOCKS=on
      - SHADOWSOCKS_PASSWORD=secure_password_123
      - SHADOWSOCKS_METHOD=aes-256-gcm
    ports:
      - "8388:8388"  # Shadowsocks
      - "1080:1080"  # SOCKS5
      - "8080:8080"  # HTTP proxy
    restart: unless-stopped

  macreplayxc:
    build: .
    container_name: macreplayxc
    depends_on:
      - gluetun
    ports:
      - "5000:5000"
    restart: unless-stopped
```

Then in MacReplayXC portal settings, use:
```
socks5://gluetun:1080
```

This provides VPN routing with minimal complexity and maximum compatibility.