# gVisor Setup Guide

## Overview

gVisor provides **kernel-level isolation** for containers, adding an extra security layer by intercepting syscalls through a user-space kernel (runsc). This is critical for production sandbox environments where untrusted code execution occurs.

## macOS Development Environment

**⚠️ IMPORTANT**: gVisor is **not available on Docker Desktop for macOS/Windows**.

Docker Desktop runs containers inside a Linux VM, and custom runtimes like gVisor are not exposed through Docker Desktop's interface. For local development on macOS:

- **Use standard Docker isolation** (already provides VM-level isolation via Docker Desktop)
- **Security layers still active**:
  - Docker network isolation
  - Resource limits (CPU, memory, PIDs)
  - Read-only filesystems
  - Non-root users
  - Egress proxy filtering
  - Capability dropping

### Development vs Production

| Feature | macOS Dev | Linux Prod |
|---------|-----------|------------|
| VM Isolation | ✅ Docker Desktop VM | ❌ Not applicable |
| gVisor (runsc) | ❌ Not available | ✅ Recommended |
| Network filtering | ✅ Egress proxy | ✅ Egress proxy |
| Resource limits | ✅ Docker limits | ✅ Docker limits |
| Seccomp/AppArmor | ⚠️ Limited | ✅ Full support |

## Linux Production Setup

### Prerequisites

- Linux host (Ubuntu 20.04+, Debian 11+, RHEL 8+)
- Docker 20.10+
- Root/sudo access
- `jq` installed (`apt install jq` or `yum install jq`)

### Installation Steps

1. **Run the installation script**:
   ```bash
   cd /path/to/sandbox/runtime
   sudo ./install-gvisor.sh
   ```

2. **Verify installation**:
   ```bash
   runsc --version
   docker run --rm --runtime=runsc alpine echo "gVisor works!"
   ```

3. **Uncomment gVisor containers** in `docker-compose.sandbox.yml`:
   ```bash
   # Remove the comment markers from these sections:
   # - sandbox-example (lines 245-322)
   # - sandbox-ide-user1-project1 (lines 323-404)
   ```

4. **Restart sandbox services**:
   ```bash
   docker-compose -f docker-compose.sandbox.yml up -d
   ```

### What the Script Does

1. **Downloads runsc binary** for your architecture (x86_64 or aarch64)
2. **Verifies checksum** for security
3. **Installs runsc** to `/usr/local/bin/`
4. **Configures Docker daemon** to register runsc runtime
5. **Restarts Docker** to apply changes

### Manual Installation (if script fails)

```bash
# 1. Download runsc
ARCH=$(uname -m)
curl -fsSL "https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}/runsc" -o runsc
curl -fsSL "https://storage.googleapis.com/gvisor/releases/release/latest/${ARCH}/runsc.sha512" -o runsc.sha512

# 2. Verify and install
sha512sum -c runsc.sha512
chmod +x runsc
sudo mv runsc /usr/local/bin/

# 3. Configure Docker daemon
sudo nano /etc/docker/daemon.json
```

Add this configuration:
```json
{
  "runtimes": {
    "runsc": {
      "path": "/usr/local/bin/runsc",
      "runtimeArgs": [
        "--platform=systrap"
      ]
    }
  }
}
```

```bash
# 4. Restart Docker
sudo systemctl restart docker

# 5. Test
docker run --rm --runtime=runsc alpine echo "Success!"
```

## Security Benefits

gVisor provides defense-in-depth by:

1. **Syscall interception**: All syscalls go through gVisor's user-space kernel
2. **Reduced attack surface**: Only ~70 syscalls implemented vs 300+ in Linux
3. **Isolation from host kernel**: Container breakout doesn't compromise host
4. **Resource isolation**: Separate memory address space
5. **Network sandboxing**: gVisor's netstack isolates network operations

## Performance Considerations

gVisor adds **~10-30% overhead** compared to standard runc:
- CPU overhead: ~5-15% for compute tasks
- I/O overhead: ~20-30% for disk/network operations
- Memory overhead: ~50MB per container

**Trade-off**: Slightly slower execution for significantly better security.

## Troubleshooting

### Error: "unknown or invalid runtime name: runsc"

**Solution**: runsc not installed or Docker not restarted
```bash
runsc --version  # Should show version
sudo systemctl restart docker
```

### Error: "operation not permitted" when running containers

**Solution**: Check seccomp configuration
```yaml
security_opt:
  - no-new-privileges:true
  - seccomp:unconfined  # Required for gVisor
```

### Container fails to start with gVisor

**Check logs**:
```bash
docker logs <container-name>
runsc --debug --log=/tmp/runsc.log run <container-id>
```

## References

- [gVisor Documentation](https://gvisor.dev/)
- [gVisor GitHub](https://github.com/google/gvisor)
- [Docker Runtime Configuration](https://docs.docker.com/engine/reference/commandline/dockerd/#daemon-configuration-file)
- [Security Comparison: gVisor vs Kata vs Firecracker](https://gvisor.dev/docs/architecture_guide/security/)

## Next Steps

Once gVisor is installed on your Linux production server:

1. ✅ Uncomment sandbox example containers in docker-compose
2. ✅ Test skill execution with gVisor runtime
3. ✅ Monitor performance impact
4. ✅ Update deployment documentation
5. ✅ Configure monitoring/alerting for runsc processes
