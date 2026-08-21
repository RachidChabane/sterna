"""
Egress proxy with domain whitelist for sandbox containers.
Allows access only to approved domains (PyPI, npm, GitHub, docs, etc.)
Supports both HTTP and HTTPS traffic.

Dynamic whitelist API:
- POST /whitelist/add with JSON body {"domains": ["domain1.com", "domain2.com"]}
- POST /whitelist/remove with JSON body {"domains": ["domain1.com"]}
- GET /whitelist returns all whitelisted domains (static + dynamic)
"""
from mitmproxy import http
import logging
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Set

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Control API port (separate from proxy port 8888)
CONTROL_API_PORT = 8889

# Thread-safe set for dynamic domains
_dynamic_domains: Set[str] = set()
_domains_lock = threading.Lock()


def add_dynamic_domains(domains: list) -> int:
    """Add domains to the dynamic whitelist. Returns count added."""
    with _domains_lock:
        before = len(_dynamic_domains)
        for domain in domains:
            domain = domain.strip().lower()
            if domain:
                _dynamic_domains.add(domain)
                logger.info(f"[Egress Proxy] Added dynamic domain: {domain}")
        return len(_dynamic_domains) - before


def remove_dynamic_domains(domains: list) -> int:
    """Remove domains from the dynamic whitelist. Returns count removed."""
    with _domains_lock:
        before = len(_dynamic_domains)
        for domain in domains:
            domain = domain.strip().lower()
            _dynamic_domains.discard(domain)
            logger.info(f"[Egress Proxy] Removed dynamic domain: {domain}")
        return before - len(_dynamic_domains)


def get_dynamic_domains() -> list:
    """Get all dynamic domains."""
    with _domains_lock:
        return list(_dynamic_domains)


class ControlAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for the control API."""

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.info(f"[Control API] {args[0]}")

    def _send_json_response(self, data: dict, status: int = 200):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/whitelist':
            # Return all whitelisted domains
            static = []
            try:
                with open('/app/whitelist.txt', 'r') as f:
                    static = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.strip().startswith('#')
                    ]
            except Exception as e:
                logger.error(f"[Control API] Failed to read static whitelist: {e}")

            dynamic = get_dynamic_domains()

            self._send_json_response({
                "static": static,
                "dynamic": dynamic,
                "all": list(set(static + dynamic))
            })
        elif self.path == '/health':
            self._send_json_response({"status": "healthy"})
        else:
            self._send_json_response({"error": "Not found"}, 404)

    def do_POST(self):
        """Handle POST requests."""
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode()

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_json_response({"error": "Invalid JSON"}, 400)
            return

        if self.path == '/whitelist/add':
            domains = data.get('domains', [])
            if not isinstance(domains, list):
                self._send_json_response({"error": "domains must be a list"}, 400)
                return

            count = add_dynamic_domains(domains)
            self._send_json_response({
                "success": True,
                "added": count,
                "dynamic_domains": get_dynamic_domains()
            })

        elif self.path == '/whitelist/remove':
            domains = data.get('domains', [])
            if not isinstance(domains, list):
                self._send_json_response({"error": "domains must be a list"}, 400)
                return

            count = remove_dynamic_domains(domains)
            self._send_json_response({
                "success": True,
                "removed": count,
                "dynamic_domains": get_dynamic_domains()
            })

        else:
            self._send_json_response({"error": "Not found"}, 404)


def start_control_api():
    """Start the control API server in a background thread."""
    server = HTTPServer(('0.0.0.0', CONTROL_API_PORT), ControlAPIHandler)
    logger.info(f"[Egress Proxy] Control API listening on port {CONTROL_API_PORT}")
    server.serve_forever()


class DomainWhitelistFilter:
    def __init__(self):
        # Load static whitelist from file
        with open('/app/whitelist.txt', 'r') as f:
            self.static_domains = [
                line.strip()
                for line in f
                if line.strip() and not line.strip().startswith('#')
            ]

        logger.info(f"[Egress Proxy] Loaded {len(self.static_domains)} static domains:")
        for domain in self.static_domains:
            logger.info(f"  - {domain}")

        # Start control API in background thread
        api_thread = threading.Thread(target=start_control_api, daemon=True)
        api_thread.start()

    def is_allowed(self, host: str) -> bool:
        """Check if host is in whitelist (static or dynamic, supports subdomains)"""
        host = host.lower()

        # Build combined whitelist
        with _domains_lock:
            all_domains = self.static_domains + list(_dynamic_domains)

        for allowed in all_domains:
            # Exact match
            if host == allowed:
                return True
            # Subdomain match (e.g., www.pypi.org matches pypi.org)
            if host.endswith('.' + allowed):
                return True

        return False

    def request(self, flow: http.HTTPFlow) -> None:
        """Filter requests based on whitelist"""
        host = flow.request.pretty_host

        if not self.is_allowed(host):
            dynamic = get_dynamic_domains()

            logger.warning(f"[Egress Proxy] ❌ BLOCKED: {host} (not in whitelist)")
            flow.response = http.Response.make(
                403,
                f"Access denied: {host}\n\n"
                f"This domain is not in the whitelist.\n\n"
                f"Static domains ({len(self.static_domains)}):\n" +
                "\n".join(f"  - {d}" for d in self.static_domains) +
                f"\n\nDynamic domains ({len(dynamic)}):\n" +
                ("\n".join(f"  - {d}" for d in dynamic) if dynamic else "  (none)"),
                {"Content-Type": "text/plain"}
            )
        else:
            logger.info(f"[Egress Proxy] ✅ ALLOWED: {flow.request.method} {host}{flow.request.path}")


# Create and export the addon
addons = [DomainWhitelistFilter()]
