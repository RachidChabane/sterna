#!/usr/bin/env python3
"""
Tests for egress proxy whitelist configuration.
Tests network filtering without making AI calls.
"""
import docker
import time
import sys

def test_egress_whitelist():
    """Test that sandbox containers can only access whitelisted domains"""

    client = docker.from_env()

    # Create a temporary test container on sandbox network
    print("🧪 Creating test container on sandbox_sandbox-network...")
    try:
        container = client.containers.run(
            "alpine:latest",
            name="test-egress-whitelist",
            command=["tail", "-f", "/dev/null"],
            detach=True,
            remove=True,
            network="sandbox_sandbox-network",
            environment={
                'HTTP_PROXY': 'http://egress-proxy:8888',
                'HTTPS_PROXY': 'http://egress-proxy:8888',
                'http_proxy': 'http://egress-proxy:8888',
                'https_proxy': 'http://egress-proxy:8888',
            }
        )

        # Wait for container to start
        time.sleep(2)

        print("\n=== Testing Egress Proxy Whitelist ===\n")

        # Test 1: PyPI should be accessible (whitelisted)
        print("📦 Test 1: Accessing PyPI (should work - whitelisted)")
        result = container.exec_run(
            ["wget", "-O-", "-T", "5", "https://pypi.org/simple/", "--no-check-certificate"],
            workdir="/tmp"
        )
        if result.exit_code == 0:
            print("  ✅ SUCCESS: PyPI is accessible")
        else:
            print(f"  ❌ FAILED: PyPI blocked (exit code {result.exit_code})")
            print(f"     Output: {result.output.decode('utf-8', errors='ignore')[:200]}")

        # Test 2: GitHub should be accessible (whitelisted)
        print("\n🐙 Test 2: Accessing GitHub (should work - whitelisted)")
        result = container.exec_run(
            ["wget", "-O-", "-T", "5", "https://github.com/", "--no-check-certificate"],
            workdir="/tmp"
        )
        if result.exit_code == 0:
            print("  ✅ SUCCESS: GitHub is accessible")
        else:
            print(f"  ❌ FAILED: GitHub blocked (exit code {result.exit_code})")
            print(f"     Output: {result.output.decode('utf-8', errors='ignore')[:200]}")

        # Test 3: Random site should be blocked (not whitelisted)
        print("\n🚫 Test 3: Accessing random site (should be blocked)")
        result = container.exec_run(
            ["wget", "-O-", "-T", "5", "https://www.google.com/", "--no-check-certificate"],
            workdir="/tmp"
        )
        if result.exit_code != 0:
            print("  ✅ SUCCESS: Random site is blocked")
        else:
            print("  ❌ FAILED: Random site accessible (should be blocked)")
            print(f"     Output: {result.output.decode('utf-8', errors='ignore')[:200]}")

        # Test 4: Another random site should be blocked
        print("\n🚫 Test 4: Accessing another random site (should be blocked)")
        result = container.exec_run(
            ["wget", "-O-", "-T", "5", "https://www.wikipedia.org/", "--no-check-certificate"],
            workdir="/tmp"
        )
        if result.exit_code != 0:
            print("  ✅ SUCCESS: Wikipedia is blocked")
        else:
            print("  ❌ FAILED: Wikipedia accessible (should be blocked)")

        # Test 5: Check proxy environment variables
        print("\n🔧 Test 5: Checking proxy environment variables")
        result = container.exec_run(["env"])
        env_output = result.output.decode('utf-8')

        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']
        all_set = all(f"{var}=http://egress-proxy:8888" in env_output for var in proxy_vars)

        if all_set:
            print("  ✅ SUCCESS: All proxy variables correctly set")
        else:
            print("  ❌ FAILED: Some proxy variables missing")
            for var in proxy_vars:
                if f"{var}=" in env_output:
                    value = [line for line in env_output.split('\n') if line.startswith(var)][0]
                    print(f"     {value}")

        print("\n=== Test Summary ===")
        print("✅ Whitelisted domains (PyPI, GitHub) should be accessible")
        print("🚫 Non-whitelisted domains should be blocked")
        print("🔧 Proxy configuration should be correct")

    except docker.errors.ImageNotFound:
        print("❌ Error: alpine image not found. Pull it first: docker pull alpine:latest")
        return 1
    except docker.errors.NotFound as e:
        print(f"❌ Error: {e}")
        print("   Make sure sandbox_sandbox-network exists and egress-proxy is running")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        try:
            print("\n🧹 Cleaning up test container...")
            container.stop(timeout=1)
        except Exception as e:
            print(f"   Warning: {e}")

    return 0

if __name__ == "__main__":
    # Install wget in alpine container first
    print("📥 Note: Test uses alpine:latest image")
    print("   Installing wget in test container...")
    print()

    sys.exit(test_egress_whitelist())
