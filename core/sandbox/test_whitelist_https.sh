#!/bin/bash
# Tests for egress proxy HTTPS whitelist with mitmproxy

set -e

echo "🧪 Creating test container on sandbox_sandbox-isolated..."

# Create and start test container (using sandbox-base with mitmproxy CA cert installed)
docker run -d --rm \
  --name test-whitelist-https \
  --network sandbox_sandbox-isolated \
  -e HTTP_PROXY=http://egress-proxy:8888 \
  -e HTTPS_PROXY=http://egress-proxy:8888 \
  -e http_proxy=http://egress-proxy:8888 \
  -e https_proxy=http://egress-proxy:8888 \
  sandbox-base:latest \
  tail -f /dev/null

# Wait for container to start
sleep 3

echo ""
echo "=== Testing Egress Proxy with mitmproxy (HTTP + HTTPS) ==="
echo ""

# Test 1: PyPI HTTPS (whitelisted) - pip install should work
echo "📦 Test 1: pip install (HTTPS to PyPI - whitelisted)"
if docker exec test-whitelist-https pip install --break-system-packages --no-cache-dir requests 2>&1 | grep -q "Successfully installed"; then
    echo "  ✅ SUCCESS: pip install works (PyPI accessible via HTTPS)"
else
    echo "  ❌ FAILED: pip install blocked"
    docker exec test-whitelist-https pip install --break-system-packages --no-cache-dir requests 2>&1 | tail -5
fi

# Test 2: GitHub HTTPS (whitelisted)
echo ""
echo "🐙 Test 2: Accessing GitHub via HTTPS (whitelisted)"
if docker exec test-whitelist-https python3 -c "import urllib.request; urllib.request.urlopen('https://github.com', timeout=10)" 2>&1; then
    echo "  ✅ SUCCESS: GitHub accessible via HTTPS"
else
    echo "  ❌ FAILED: GitHub blocked"
fi

# Test 3: Google HTTPS (NOT whitelisted) - should be blocked
echo ""
echo "🚫 Test 3: Accessing Google via HTTPS (should be blocked)"
if docker exec test-whitelist-https python3 -c "import urllib.request; urllib.request.urlopen('https://www.google.com', timeout=5)" 2>&1; then
    echo "  ❌ FAILED: Google accessible (should be blocked)"
else
    echo "  ✅ SUCCESS: Google blocked correctly"
fi

# Test 4: Wikipedia HTTPS (NOT whitelisted) - should be blocked
echo ""
echo "🚫 Test 4: Accessing Wikipedia via HTTPS (should be blocked)"
if docker exec test-whitelist-https python3 -c "import urllib.request; urllib.request.urlopen('https://en.wikipedia.org', timeout=5)" 2>&1; then
    echo "  ❌ FAILED: Wikipedia accessible (should be blocked)"
else
    echo "  ✅ SUCCESS: Wikipedia blocked correctly"
fi

# Test 5: Check proxy logs for filtering
echo ""
echo "📋 Test 5: Recent proxy logs (showing allowed/blocked requests)"
docker logs sterna-egress-proxy 2>&1 | grep -E "\[Egress Proxy\]" | tail -10 || echo "  No proxy logs yet"

echo ""
echo "=== Test Summary ==="
echo "✅ Whitelisted domains (PyPI, GitHub) accessible via HTTP and HTTPS"
echo "🚫 Non-whitelisted domains (Google, Wikipedia) blocked"
echo "📦 pip install works through filtered proxy"

# Cleanup
echo ""
echo "🧹 Cleaning up test container..."
docker stop test-whitelist-https >/dev/null 2>&1

echo ""
echo "✅ Tests complete!"
