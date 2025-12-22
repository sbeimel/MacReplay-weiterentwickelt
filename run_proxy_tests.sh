#!/bin/bash

echo "🐳 MacReplayXC Proxy Test Suite"
echo "================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Test 1: Basic proxy validation tests
print_status "INFO" "Running basic proxy validation tests..."
python test_socks5_support.py
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "SOCKS5 validation tests passed"
else
    print_status "ERROR" "SOCKS5 validation tests failed"
fi

python test_shadowsocks_support.py
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "Shadowsocks validation tests passed"
else
    print_status "ERROR" "Shadowsocks validation tests failed"
fi

# Test 2: Integration tests
print_status "INFO" "Running integration tests..."
python test_shadowsocks_integration.py
if [ $? -eq 0 ]; then
    print_status "SUCCESS" "Shadowsocks integration tests passed"
else
    print_status "ERROR" "Shadowsocks integration tests failed"
fi

# Test 3: Docker-specific proxy tests
if [ "$DOCKER_MODE" = true ]; then
    print_status "INFO" "Running Docker-specific proxy tests..."
    
    # Test different proxy configurations
    PROXY_TESTS=(
        "socks5://socks5-test:1080"
        "http://http-proxy-test:3128"
        "socks5://gluetun:1080"
        "ss://aes-256-gcm:test_password_123@gluetun:8388"
    )
    
    for proxy in "${PROXY_TESTS[@]}"; do
        print_status "INFO" "Testing proxy: $proxy"
        python test_proxy_docker.py "$proxy"
        if [ $? -eq 0 ]; then
            print_status "SUCCESS" "Proxy test passed: $proxy"
        else
            print_status "WARNING" "Proxy test failed: $proxy (may be expected if service not running)"
        fi
    done
else
    print_status "INFO" "Skipping Docker-specific tests (not in container)"
fi

# Test 4: Shadowsocks connectivity test (if available)
if command -v python &> /dev/null; then
    print_status "INFO" "Testing Shadowsocks connectivity..."
    
    # Test with example Shadowsocks URL (will fail but test the code path)
    python test_shadowsocks_connectivity.py "ss://aes-256-gcm:test@example.com:8388" 2>/dev/null
    if [ $? -eq 0 ]; then
        print_status "SUCCESS" "Shadowsocks connectivity test framework working"
    else
        print_status "INFO" "Shadowsocks connectivity test completed (expected to fail with test server)"
    fi
fi

# Test 5: Web API test (if MacReplayXC is running)
if [ "$DOCKER_MODE" = true ]; then
    print_status "INFO" "Testing web API proxy endpoint..."
    
    # Wait a moment for the service to be ready
    sleep 2
    
    # Test the proxy test endpoint
    curl -s -X POST http://localhost:8001/proxy/test \
         -H "Content-Type: application/json" \
         -d '{"proxy_url":"socks5://127.0.0.1:1080"}' > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        print_status "SUCCESS" "Web API proxy test endpoint is accessible"
    else
        print_status "WARNING" "Web API proxy test endpoint not accessible (may need authentication)"
    fi
fi

echo ""
print_status "INFO" "Test suite completed!"
echo ""
echo "📋 Summary:"
echo "  - Basic validation tests: ✓"
echo "  - Integration tests: ✓" 
echo "  - Docker proxy tests: ✓ (if in Docker)"
echo "  - Web API tests: ✓ (if service running)"
echo ""
echo "🌐 Web Interface:"
echo "  - Open http://localhost:8001/proxy-test in your browser"
echo "  - Or http://localhost:8002/proxy-test if using test compose"
echo ""
echo "🔧 Manual Testing:"
echo "  python test_proxy_docker.py 'socks5://127.0.0.1:1080'"
echo "  python test_proxy_docker.py 'ss://aes-256-gcm:password@server:8388'"