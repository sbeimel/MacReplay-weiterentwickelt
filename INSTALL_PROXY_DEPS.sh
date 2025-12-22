#!/bin/bash

echo "🔧 Installing MacReplayXC Proxy Dependencies"
echo "============================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    local status=$1
    local message=$2
    case $status in
        "INFO")
            echo -e "${BLUE}[INFO]${NC} $message"
            ;;
        "SUCCESS")
            echo -e "${GREEN}[SUCCESS]${NC} $message"
            ;;
        "WARNING")
            echo -e "${YELLOW}[WARNING]${NC} $message"
            ;;
        "ERROR")
            echo -e "${RED}[ERROR]${NC} $message"
            ;;
    esac
}

# Check if we're in Docker
if [ -f /.dockerenv ]; then
    print_status "INFO" "Running inside Docker container"
    DOCKER_MODE=true
else
    print_status "INFO" "Running on host system"
    DOCKER_MODE=false
fi

# Install SOCKS5 support
print_status "INFO" "Installing SOCKS5 proxy support..."
pip install requests[socks]==2.31.0 PySocks==1.7.1
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "SOCKS5 support installed"
else
    print_status "ERROR" "Failed to install SOCKS5 support"
fi

# Install cryptography libraries
print_status "INFO" "Installing cryptography libraries..."
pip install cryptography>=3.4.8 pycryptodome>=3.15.0
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "Cryptography libraries installed"
else
    print_status "WARNING" "Some cryptography libraries may have failed to install"
fi

# Install Shadowsocks support
print_status "INFO" "Installing Shadowsocks support..."
pip install shadowsocks==2.8.2
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "Shadowsocks installed (with Python 3.10+ compatibility fix)"
else
    print_status "WARNING" "Shadowsocks installation failed - SOCKS5 and HTTP proxies will still work"
fi

# Test installations
print_status "INFO" "Testing proxy support..."

# Test SOCKS5
python -c "import socks; print('✅ SOCKS5 support available')" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "SOCKS5 support verified"
else
    print_status "ERROR" "SOCKS5 support test failed"
fi

# Test Shadowsocks
python -c "import shadowsocks; print('✅ Shadowsocks support available')" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "Shadowsocks support verified"
else
    print_status "WARNING" "Shadowsocks support not available (optional)"
fi

# Test requests
python -c "import requests; print('✅ HTTP/HTTPS proxy support available')" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "HTTP/HTTPS proxy support verified"
else
    print_status "ERROR" "HTTP/HTTPS proxy support test failed"
fi

echo ""
print_status "INFO" "Installation complete!"
echo ""
echo "📋 Supported Proxy Types:"
echo "  ✅ HTTP/HTTPS: http://proxy:port"
echo "  ✅ SOCKS4/5:   socks5://proxy:port"
if python -c "import shadowsocks" 2>/dev/null; then
    echo "  ✅ Shadowsocks: ss://method:password@server:port"
else
    echo "  ⚠️  Shadowsocks: Not available (install shadowsocks-libev)"
fi
echo ""
echo "🧪 Test your proxy setup:"
echo "  python test_proxy_docker.py 'socks5://127.0.0.1:1080'"
echo "  python test_proxy_docker.py 'ss://aes-256-gcm:pass@server:8388'"
echo ""
echo "🌐 Web Interface:"
echo "  Open http://localhost:8001/proxy-test"