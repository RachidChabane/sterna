#!/usr/bin/env node
/**
 * MCP Gateway - Manages multiple MCP server processes inside the sandbox
 *
 * This runs as a single process inside the user's sandbox container and manages
 * MCP servers as child processes. This avoids creating one container per MCP server.
 *
 * Architecture:
 *   HTTP API (port 3100) → MCP Gateway → Child processes (npx @package/mcp-server)
 *
 * Network: Child processes inherit the sandbox's network configuration including
 * egress proxy settings, so all outbound requests go through the controlled proxy.
 */

const http = require('http');
const { spawn } = require('child_process');
const readline = require('readline');

const PORT = process.env.MCP_GATEWAY_PORT || 3100;

// Active MCP server processes: serverId → { process, stdin, buffer, requestQueue, tools }
const servers = new Map();

// Pending JSON-RPC responses: requestId → { resolve, reject, timeout }
const pendingRequests = new Map();

/**
 * Start an MCP server process
 */
function startServer(serverId, npmPackage, envVars = {}) {
  if (servers.has(serverId)) {
    const existing = servers.get(serverId);
    if (existing.process && !existing.process.killed) {
      console.log(`[MCP Gateway] Server ${serverId} already running`);
      return { success: true, message: 'Server already running' };
    }
  }

  console.log(`[MCP Gateway] Starting server ${serverId}: ${npmPackage}`);

  // Build environment - inherit sandbox env (including proxy settings)
  // Note: We disable SSL verification because the egress proxy does TLS inspection
  const processEnv = {
    ...process.env,
    ...envVars,
    NODE_ENV: 'production',
    NO_COLOR: '1',
    // Disable SSL verification for npm (egress proxy does TLS inspection)
    NODE_TLS_REJECT_UNAUTHORIZED: '0',
    npm_config_strict_ssl: 'false',
    // Preload proxy bootstrap to configure undici's global dispatcher
    // This makes Node.js native fetch() use the egress proxy
    NODE_OPTIONS: '--require /opt/mcp-gateway/proxy-bootstrap.js',
  };

  // Start the MCP server via npx
  const child = spawn('npx', ['-y', npmPackage], {
    env: processEnv,
    stdio: ['pipe', 'pipe', 'pipe'],
    cwd: '/workspace',
  });

  const serverState = {
    process: child,
    stdin: child.stdin,
    buffer: '',
    tools: [],
    startedAt: Date.now(),
    npmPackage,
  };

  // Handle stdout (JSON-RPC responses)
  const rl = readline.createInterface({ input: child.stdout });
  rl.on('line', (line) => {
    try {
      const response = JSON.parse(line);
      if (response.id && pendingRequests.has(response.id)) {
        const { resolve, timeout } = pendingRequests.get(response.id);
        clearTimeout(timeout);
        pendingRequests.delete(response.id);
        resolve(response);
      } else {
        // Notification or unexpected message
        console.log(`[MCP ${serverId}] Notification:`, line.substring(0, 200));
      }
    } catch (e) {
      console.log(`[MCP ${serverId}] stdout:`, line.substring(0, 500));
    }
  });

  // Handle stderr
  child.stderr.on('data', (data) => {
    console.error(`[MCP ${serverId}] stderr:`, data.toString().substring(0, 500));
  });

  // Handle process exit
  child.on('exit', (code, signal) => {
    console.log(`[MCP ${serverId}] Process exited: code=${code}, signal=${signal}`);
    servers.delete(serverId);

    // Reject any pending requests
    for (const [reqId, { reject, timeout }] of pendingRequests.entries()) {
      clearTimeout(timeout);
      reject(new Error('MCP server process exited'));
      pendingRequests.delete(reqId);
    }
  });

  child.on('error', (err) => {
    console.error(`[MCP ${serverId}] Process error:`, err.message);
    servers.delete(serverId);
  });

  servers.set(serverId, serverState);

  // Initialize the MCP connection
  setTimeout(() => initializeMCP(serverId), 1000);

  return { success: true, message: 'Server started', pid: child.pid };
}

/**
 * Initialize MCP protocol with the server
 */
async function initializeMCP(serverId) {
  try {
    // Send initialize request
    const initResult = await sendRPC(serverId, 'initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'sterna-sandbox',
        version: '1.0.0',
      },
    }, 10000);

    if (initResult.error) {
      console.error(`[MCP ${serverId}] Initialize failed:`, initResult.error);
      return;
    }

    console.log(`[MCP ${serverId}] Initialized:`, JSON.stringify(initResult.result).substring(0, 200));

    // Send initialized notification
    sendNotification(serverId, 'notifications/initialized', {});

    // Discover tools
    const toolsResult = await sendRPC(serverId, 'tools/list', {}, 10000);
    if (toolsResult.result && toolsResult.result.tools) {
      const serverState = servers.get(serverId);
      if (serverState) {
        serverState.tools = toolsResult.result.tools;
        console.log(`[MCP ${serverId}] Discovered ${serverState.tools.length} tools`);
      }
    }
  } catch (e) {
    console.error(`[MCP ${serverId}] Initialization error:`, e.message);
  }
}

/**
 * Send a JSON-RPC notification (no response expected)
 */
function sendNotification(serverId, method, params) {
  const server = servers.get(serverId);
  if (!server || !server.stdin) {
    return;
  }

  const notification = {
    jsonrpc: '2.0',
    method,
    params: params || {},
  };

  server.stdin.write(JSON.stringify(notification) + '\n');
}

/**
 * Send a JSON-RPC request and wait for response
 */
function sendRPC(serverId, method, params, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const server = servers.get(serverId);
    if (!server || !server.stdin) {
      reject(new Error(`Server ${serverId} not running`));
      return;
    }

    const requestId = `${serverId}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const request = {
      jsonrpc: '2.0',
      id: requestId,
      method,
      params: params || {},
    };

    // Set up timeout
    const timeout = setTimeout(() => {
      pendingRequests.delete(requestId);
      reject(new Error(`Request timeout: ${method}`));
    }, timeoutMs);

    pendingRequests.set(requestId, { resolve, reject, timeout });

    // Send request
    server.stdin.write(JSON.stringify(request) + '\n');
  });
}

/**
 * Stop an MCP server process
 */
function stopServer(serverId) {
  const server = servers.get(serverId);
  if (!server) {
    return { success: false, message: 'Server not found' };
  }

  console.log(`[MCP Gateway] Stopping server ${serverId}`);

  if (server.process && !server.process.killed) {
    server.process.kill('SIGTERM');

    // Force kill after 5 seconds
    setTimeout(() => {
      if (server.process && !server.process.killed) {
        server.process.kill('SIGKILL');
      }
    }, 5000);
  }

  servers.delete(serverId);
  return { success: true, message: 'Server stopped' };
}

/**
 * Get server status
 */
function getServerStatus(serverId) {
  const server = servers.get(serverId);
  if (!server) {
    return { running: false };
  }

  return {
    running: !server.process.killed,
    pid: server.process.pid,
    npmPackage: server.npmPackage,
    uptime: Date.now() - server.startedAt,
    toolsCount: server.tools.length,
  };
}

/**
 * List all running servers
 */
function listServers() {
  const result = [];
  for (const [serverId, server] of servers.entries()) {
    result.push({
      serverId,
      running: !server.process.killed,
      pid: server.process.pid,
      npmPackage: server.npmPackage,
      uptime: Date.now() - server.startedAt,
      toolsCount: server.tools.length,
    });
  }
  return result;
}

/**
 * HTTP API Server
 */
const httpServer = http.createServer(async (req, res) => {
  // CORS headers
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(200);
    res.end();
    return;
  }

  // Parse URL
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;

  // Collect body
  let body = '';
  for await (const chunk of req) {
    body += chunk;
  }
  let data = {};
  if (body) {
    try {
      data = JSON.parse(body);
    } catch (e) {
      res.writeHead(400);
      res.end(JSON.stringify({ error: 'Invalid JSON' }));
      return;
    }
  }

  try {
    // Routes
    if (path === '/health' && req.method === 'GET') {
      res.writeHead(200);
      res.end(JSON.stringify({ status: 'healthy', servers: servers.size }));
      return;
    }

    if (path === '/servers' && req.method === 'GET') {
      res.writeHead(200);
      res.end(JSON.stringify({ servers: listServers() }));
      return;
    }

    if (path === '/servers/start' && req.method === 'POST') {
      const { serverId, npmPackage, envVars } = data;
      if (!serverId || !npmPackage) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'serverId and npmPackage required' }));
        return;
      }
      const result = startServer(serverId, npmPackage, envVars || {});
      res.writeHead(200);
      res.end(JSON.stringify(result));
      return;
    }

    if (path === '/servers/stop' && req.method === 'POST') {
      const { serverId } = data;
      if (!serverId) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'serverId required' }));
        return;
      }
      const result = stopServer(serverId);
      res.writeHead(200);
      res.end(JSON.stringify(result));
      return;
    }

    if (path === '/servers/status' && req.method === 'POST') {
      const { serverId } = data;
      if (!serverId) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'serverId required' }));
        return;
      }
      const result = getServerStatus(serverId);
      res.writeHead(200);
      res.end(JSON.stringify(result));
      return;
    }

    if (path === '/rpc' && req.method === 'POST') {
      const { serverId, method, params, timeout } = data;
      if (!serverId || !method) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'serverId and method required' }));
        return;
      }

      try {
        const result = await sendRPC(serverId, method, params || {}, timeout || 30000);
        res.writeHead(200);
        res.end(JSON.stringify(result));
      } catch (e) {
        res.writeHead(200);
        res.end(JSON.stringify({
          jsonrpc: '2.0',
          id: null,
          error: { code: -32000, message: e.message },
        }));
      }
      return;
    }

    if (path === '/tools/list' && req.method === 'POST') {
      const { serverId } = data;
      if (!serverId) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'serverId required' }));
        return;
      }

      const server = servers.get(serverId);
      if (!server) {
        res.writeHead(404);
        res.end(JSON.stringify({ error: 'Server not found' }));
        return;
      }

      res.writeHead(200);
      res.end(JSON.stringify({ tools: server.tools }));
      return;
    }

    if (path === '/tools/call' && req.method === 'POST') {
      const { serverId, toolName, arguments: args, timeout } = data;
      if (!serverId || !toolName) {
        res.writeHead(400);
        res.end(JSON.stringify({ error: 'serverId and toolName required' }));
        return;
      }

      try {
        const result = await sendRPC(serverId, 'tools/call', {
          name: toolName,
          arguments: args || {},
        }, timeout || 60000);
        res.writeHead(200);
        res.end(JSON.stringify(result));
      } catch (e) {
        res.writeHead(200);
        res.end(JSON.stringify({
          jsonrpc: '2.0',
          id: null,
          error: { code: -32000, message: e.message },
        }));
      }
      return;
    }

    // 404
    res.writeHead(404);
    res.end(JSON.stringify({ error: 'Not found' }));

  } catch (e) {
    console.error('[MCP Gateway] Request error:', e);
    res.writeHead(500);
    res.end(JSON.stringify({ error: e.message }));
  }
});

httpServer.listen(PORT, '0.0.0.0', () => {
  console.log(`[MCP Gateway] Listening on port ${PORT}`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('[MCP Gateway] Shutting down...');
  for (const [serverId] of servers.entries()) {
    stopServer(serverId);
  }
  httpServer.close(() => {
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('[MCP Gateway] Interrupted, shutting down...');
  for (const [serverId] of servers.entries()) {
    stopServer(serverId);
  }
  httpServer.close(() => {
    process.exit(0);
  });
});
