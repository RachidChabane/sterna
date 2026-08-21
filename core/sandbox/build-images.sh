#!/bin/bash
#
# Build all Docker images for the Sterna Sandbox System
#

set -e

echo "🏗️  Building Sterna Sandbox Images..."
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Base directory
SANDBOX_DIR="$(cd "$(dirname "$0")" && pwd)"

# Canonical build path: docker-compose.sandbox.yml's `build:` blocks are the
# single source of truth for orchestrator/egress-proxy/sandbox-base/
# sandbox-datascience (see `make sandbox-build` in core/Makefile, which runs
# the same two commands). This script is kept as a convenience entrypoint for
# people working directly under sandbox/ without cd'ing to core/.
echo -e "${BLUE}Building orchestrator, egress-proxy, sandbox-base, sandbox-datascience via compose...${NC}"
# sandbox-base MUST build before sandbox-datascience: Dockerfile.sandbox-datascience
# does `FROM ${BASE_IMAGE:-sandbox-base:latest}`, and `docker compose build` does not
# reliably serialize builds by `depends_on` across versions, so it's explicit here.
docker compose -f "$SANDBOX_DIR/docker-compose.sandbox.yml" build sandbox-base
docker compose -f "$SANDBOX_DIR/docker-compose.sandbox.yml" --profile build-only build
echo -e "${GREEN}✓ Compose-managed images built${NC}"
echo ""

# Sandbox IDE (not yet wired into docker-compose.sandbox.yml or spawned by
# the orchestrator by image name — kept building here so the image stays
# available for whoever picks that integration back up).
echo -e "${BLUE}Building sandbox IDE image...${NC}"
docker build -f "$SANDBOX_DIR/runtime/Dockerfile.sandbox-ide" \
    -t sterna-sandbox-ide:latest \
    "$SANDBOX_DIR/runtime"

echo -e "${GREEN}✓ Sandbox IDE built${NC}"
echo ""

echo -e "${GREEN}🎉 All images built successfully!${NC}"
echo ""
echo "Built images:"
docker images | grep -E "(sandbox-|sterna-)" | head -20 || true
echo ""
echo "📦 Sandbox images:"
echo "  - sandbox-base:latest         (~500MB  - minimal Python, base for the image below)"
echo "  - sandbox-datascience:latest  (~3GB    - full data science stack; the image sandbox_executor.py spawns per session)"
echo ""
echo "Next steps:"
echo "  1. Install gVisor: cd runtime && sudo ./install-gvisor.sh"
echo "  2. Start services: docker compose -f docker-compose.sandbox.yml up -d"
echo "  3. Verify: curl http://localhost:8003/health"
