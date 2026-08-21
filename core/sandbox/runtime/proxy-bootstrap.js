/**
 * Proxy Bootstrap for Node.js native fetch()
 *
 * This script is loaded via NODE_OPTIONS --require before MCP servers start.
 * It configures undici's global dispatcher to route all fetch() requests
 * through the egress proxy.
 *
 * Environment variables:
 *   - HTTPS_PROXY or HTTP_PROXY: The proxy URL (e.g., http://egress-proxy:8888)
 */

const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;

if (proxyUrl) {
  try {
    const { setGlobalDispatcher, ProxyAgent } = require('/opt/mcp-gateway/node_modules/undici');

    // Create a proxy agent
    const proxyAgent = new ProxyAgent({
      uri: proxyUrl,
      // Don't verify TLS since the egress proxy does TLS inspection
      requestTls: {
        rejectUnauthorized: false,
      },
    });

    // Set as the global dispatcher for all fetch() calls
    setGlobalDispatcher(proxyAgent);

    console.log(`[Proxy Bootstrap] Configured fetch() proxy: ${proxyUrl}`);
  } catch (err) {
    console.error(`[Proxy Bootstrap] Failed to configure proxy: ${err.message}`);
  }
} else {
  console.log('[Proxy Bootstrap] No proxy configured (HTTPS_PROXY/HTTP_PROXY not set)');
}
