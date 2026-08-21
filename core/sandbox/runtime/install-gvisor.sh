#!/bin/bash
#
# Install gVisor (runsc) runtime for secure sandbox execution
# This script must be run with sudo privileges
#

set -e

echo "🔐 Installing gVisor (runsc) runtime..."

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
  x86_64)
    ARCH="x86_64"
    ;;
  aarch64|arm64)
    ARCH="aarch64"
    ;;
  *)
    echo "❌ Unsupported architecture: $ARCH"
    exit 1
    ;;
esac

# Download runsc and runsc-sha512
RUNSC_URL="https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}"

echo "📥 Downloading runsc for ${ARCH}..."
curl -fsSL "${RUNSC_URL}/runsc" -o /tmp/runsc
curl -fsSL "${RUNSC_URL}/runsc.sha512" -o /tmp/runsc.sha512

# Verify checksum
echo "🔍 Verifying checksum..."
cd /tmp
sha512sum -c runsc.sha512

# Install runsc
echo "📦 Installing runsc to /usr/local/bin..."
chmod +x /tmp/runsc
sudo mv /tmp/runsc /usr/local/bin/runsc
rm -f /tmp/runsc.sha512

# Verify installation
echo "✅ Verifying installation..."
runsc --version

# Update Docker daemon configuration
DAEMON_JSON="/etc/docker/daemon.json"
BACKUP_JSON="/etc/docker/daemon.json.backup"

echo "⚙️  Configuring Docker daemon..."

if [ -f "$DAEMON_JSON" ]; then
  echo "📋 Backing up existing daemon.json to ${BACKUP_JSON}"
  sudo cp "$DAEMON_JSON" "$BACKUP_JSON"
fi

# Merge with existing config or create new
if [ -f "$DAEMON_JSON" ]; then
  # Use jq to merge configurations
  if command -v jq &> /dev/null; then
    sudo jq -s '.[0] * .[1]' "$DAEMON_JSON" "$(dirname "$0")/daemon.json" | sudo tee "$DAEMON_JSON" > /dev/null
  else
    echo "⚠️  jq not found. Please manually merge $(dirname "$0")/daemon.json with $DAEMON_JSON"
    exit 1
  fi
else
  sudo cp "$(dirname "$0")/daemon.json" "$DAEMON_JSON"
fi

# Restart Docker daemon
echo "🔄 Restarting Docker daemon..."
sudo systemctl restart docker

echo "✅ gVisor installation complete!"
echo "
To use gVisor runtime, add the following to your docker run or docker-compose:
  runtime: runsc

Test with:
  docker run --rm --runtime=runsc hello-world
"
