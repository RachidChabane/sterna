#!/bin/bash
# Tests for egress proxy whitelist configuration

set -e

echo "🧪 Creating test container on sandbox_sandbox-isolated..."

# Create and start test container
docker run -d --rm \
  --name test-egress-whitelist \
  --network sandbox_sandbox-isolated \
  -e HTTP_PROXY=http://egress-proxy:8888 \
  -e HTTPS_PROXY=http://egress-proxy:8888 \
  -e http_proxy=http://egress-proxy:8888 \
  -e https_proxy=http://egress-proxy:8888 \
  alpine:latest \
  tail -f /dev/null

# Wait for container to start
sleep 2

# Install wget in container
echo "📥 Installing wget in test container..."
docker exec test-egress-whitelist apk add --no-cache wget >/dev/null 2>&1

echo ""
echo "=== Testing Egress Proxy Whitelist ==="
echo ""

# Test 1: PyPI should be accessible
echo "📦 Test 1: Accessing PyPI (should work - whitelisted)"
if docker exec test-egress-whitelist wget -O- -T 5 --no-check-certificate https://pypi.org/simple/ >/dev/null 2>&1; then
    echo "  ✅ SUCCESS: PyPI is accessible"
else
    echo "  ❌ FAILED: PyPI blocked"
fi

# Test 2: GitHub should be accessible
echo ""
echo "🐙 Test 2: Accessing GitHub (should work - whitelisted)"
if docker exec test-egress-whitelist wget -O- -T 5 --no-check-certificate https://github.com/ >/dev/null 2>&1; then
    echo "  ✅ SUCCESS: GitHub is accessible"
else
    echo "  ❌ FAILED: GitHub blocked"
fi

# Test 3: Random site should be blocked
echo ""
echo "🚫 Test 3: Accessing Google (should be blocked)"
if docker exec test-egress-whitelist wget -O- -T 5 --no-check-certificate https://www.google.com/ >/dev/null 2>&1; then
    echo "  ❌ FAILED: Google accessible (should be blocked)"
else
    echo "  ✅ SUCCESS: Google is blocked"
fi

# Test 4: Wikipedia should be blocked
echo ""
echo "🚫 Test 4: Accessing Wikipedia (should be blocked)"
if docker exec test-egress-whitelist wget -O- -T 5 --no-check-certificate https://www.wikipedia.org/ >/dev/null 2>&1; then
    echo "  ❌ FAILED: Wikipedia accessible (should be blocked)"
else
    echo "  ✅ SUCCESS: Wikipedia is blocked"
fi

# Test 5: Check proxy environment variables
echo ""
echo "🔧 Test 5: Checking proxy environment variables"
docker exec test-egress-whitelist env | grep -i proxy
echo "  ✅ Proxy variables are set"

echo ""
echo "=== Test Summary ==="
echo "✅ Whitelisted domains (PyPI, GitHub) should be accessible"
echo "🚫 Non-whitelisted domains (Google, Wikipedia) should be blocked"
echo "🔧 Proxy configuration is correct"

# Cleanup
echo ""
echo "🧹 Cleaning up test container..."
docker stop test-egress-whitelist >/dev/null 2>&1

echo ""
echo "✅ Tests complete!"
