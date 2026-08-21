# Sandbox Security Architecture

## Executive Summary

This document describes the comprehensive security architecture for the Sterna sandbox environment, designed to safely execute untrusted code from AI assistants while protecting the host system, network, and user data.

**Security Philosophy**: Defense in depth with monitoring over blocking. Allow AI agents flexibility while detecting and alerting on abuse patterns.

## Threat Model

### Threats We Protect Against

1. **Container Escape**: Attacker breaks out of sandbox to access host
2. **Crypto-Mining**: Resource abuse for cryptocurrency mining
3. **Data Exfiltration**: Stealing user data or secrets via network
4. **Network Attacks**: Port scanning, DDoS participation, reverse shells
5. **Resource Exhaustion**: CPU/memory/disk/PID abuse (DoS)
6. **Privilege Escalation**: Gaining root or elevated privileges
7. **Lateral Movement**: Accessing other containers or services
8. **Persistence**: Installing backdoors or malware

### Out of Scope

- Physical access attacks
- Supply chain attacks (assumed trusted base images)
- Social engineering
- Quantum cryptography attacks

## Security Layers

### Layer 1: Container Isolation

**Technology**: Docker containers with gVisor runtime (Linux production, Docker/VPS
deployment path only — see `README.md#-security--isolation` for why this does not
currently hold on the Kubernetes deployment)

**Configuration** (`sandbox_manager.py:88-116`):
```python
container_config = {
    "user": "1000:1000",              # Non-root user
    "read_only": True,                 # Read-only root filesystem
    "security_opt": ["no-new-privileges:true"],  # Prevent privilege escalation
    "cap_drop": ["ALL"],              # Drop all Linux capabilities
    "mem_limit": "2G",                # Memory limit
    "nano_cpus": 2e9,                 # CPU limit (2 cores)
    "pids_limit": 200,                # Process limit (anti fork-bomb)
    "runtime": "runsc",               # gVisor (user-space kernel)
    "network": "sandbox-network",     # Isolated network
}
```

**Protection Against**:
- Container escape (gVisor intercepts syscalls)
- Privilege escalation (no capabilities, no setuid)
- Fork bombs (PID limit)
- Resource exhaustion (CPU, memory limits)

### Layer 2: Filesystem Restrictions

**Configuration** (`sandbox_manager.py:102-109`):
```python
"volumes": {
    volume_name: {"bind": "/workspace", "mode": "rw"}
},
"tmpfs": {
    "/tmp": "size=200M,mode=1777",
    "/run/secrets": "size=10M,mode=0700,uid=1000,gid=1000",
}
```

**Features**:
- Root filesystem is read-only
- Only /workspace is writable (per-user volume)
- Temporary files in memory-backed tmpfs (200MB limit)
- Secrets directory isolated (if needed)
- No access to /proc, /sys (gVisor virtualizes)

**Protection Against**:
- Filesystem persistence of malware
- Disk exhaustion
- Access to sensitive host files

### Layer 3: Network Filtering

**Architecture**:
```
Container -> Egress Proxy (Tinyproxy) -> Traefik -> Internet
```

**Egress Proxy Configuration** (`tinyproxy.conf`):
```conf
# Whitelist approach: only allow specific domains
FilterDefaultDeny Yes

# Allowed domains (example)
Allow .python.org
Allow .npmjs.org
Allow .github.com
Allow .githubusercontent.com

# Block all other outbound connections
MaxClients 20
```

**Features**:
- All HTTP/HTTPS traffic routed through proxy
- Whitelist-based filtering
- Rate limiting at proxy level
- Request logging for audit

**Protection Against**:
- Data exfiltration to arbitrary servers
- Reverse shells
- Command & control communication
- Network scanning

### Layer 4: Resource Monitoring

**Implementation**: `security_monitor.py`

**Real-time Monitoring**:
```python
# CPU usage (crypto-mining detection)
MAX_CPU_PERCENT = 95  # Alert if sustained

# Memory usage
MAX_MEMORY_PERCENT = 95

# Network upload (data exfiltration detection)
MAX_NETWORK_TX_MB = 100  # per 5 minutes

# Process count (fork bomb detection)
MAX_PIDS = 180  # (limit is 200)
```

**Background Task** (`main.py:65-104`):
- Monitors all active containers every 30 seconds
- Checks CPU, memory, network, PID usage
- Logs alerts to security event log
- Automatic cleanup of old data

**Protection Against**:
- Crypto-mining (sustained high CPU)
- Data exfiltration (high network upload)
- Fork bombs (approaching PID limit)
- Memory leaks

### Layer 5: Command Auditing & Detection

**Implementation**: `security_monitor.py:78-137`

**Suspicious Pattern Detection**:
```python
SUSPICIOUS_PATTERNS = {
    'crypto_mining': [
        r'(xmrig|cpuminer|cgminer|ethminer)',
        r'stratum\+tcp://',
    ],
    'network_scanning': [
        r'(nmap|masscan|zmap)\s',
        r'nc\s+-[lv]',
    ],
    'reverse_shell': [
        r'bash\s+-i\s*>',
        r'/dev/tcp/',
        r'nc\s+.+\s+-e',
    ],
    'privilege_escalation': [
        r'(sudo|su\s)',
        r'chmod\s+[4567]\d{3}',
    ],
    'data_exfiltration': [
        r'curl\s+.*-T',
        r'wget\s+.*--post-file',
        r'base64.*\|.*curl',
    ],
    'container_escape': [
        r'/proc/self/(cgroup|mounts)',
        r'docker\.sock',
        r'runc',
    ],
}
```

**Detection, Not Blocking**:
- Commands are logged but ALLOWED
- Suspicious patterns trigger ALERTS
- AI agents need flexibility to work
- Focus on detection and visibility

**Audit Trail**:
- Every command logged with timestamp
- User/project context preserved
- Source tracked (terminal, API, skill)
- Searchable for forensics

**Protection Against**:
- Undetected attacks
- Post-incident forensics gaps
- Compliance violations

### Layer 6: Rate Limiting

**Implementation**: `security_monitor.py:239-260`

**Limits** (generous for AI agents):
```python
MAX_COMMANDS_PER_MINUTE = 60   # 1 command/second sustained
MAX_COMMANDS_PER_HOUR = 1000   # Burst protection
```

**Strategy**:
- Sliding window rate limiting
- Per user×project isolation
- Violations logged but not hard-blocked
- Repeated violations -> escalate alerts

**Protection Against**:
- Automated abuse
- Brute force attacks
- Resource exhaustion via API spam

## Security Monitoring Dashboard

### Metrics Exposed

**API Endpoint**: `GET /security/metrics/{user_id}/{project_id}`

**Response**:
```json
{
  "container_id": "user123-project456",
  "total_commands": 2547,
  "rate_violations": 0,
  "events_24h": 15,
  "warnings_24h": 2,
  "critical_24h": 0,
  "latest_metrics": {
    "cpu_percent": 12.5,
    "memory_mb": 341.2,
    "pids": 8
  },
  "recent_events": [
    {
      "timestamp": "2025-01-10T15:32:10Z",
      "type": "suspicious_pattern",
      "severity": "warning",
      "details": {
        "command": "curl http://example.com",
        "threats": ["data_exfiltration"],
        "action": "allowed_with_alert"
      }
    }
  ]
}
```

### Alert Levels

1. **INFO**: Normal operations, command logging
2. **WARNING**: Suspicious pattern detected, rate limit warning, elevated resource usage
3. **CRITICAL**: Sustained resource abuse, repeated suspicious patterns, container crash

### Response Actions

**Automated**:
- Log all events
- Alert on threshold breaches
- Cleanup old data (7 day retention)

**Manual** (requires admin):
- Kill container
- Ban user temporarily
- Adjust resource limits
- Update pattern detection rules

## Deployment Security

### Production Checklist

- [ ] gVisor runtime installed and verified (`runsc --version`)
- [ ] Egress proxy configured with domain whitelist
- [ ] Resource limits tested under load
- [ ] Monitoring dashboard accessible
- [ ] Alert notifications configured (email, Slack, PagerDuty)
- [ ] Backup/recovery procedures documented
- [ ] Incident response plan defined
- [ ] Security audit completed

### Environment Variables

```bash
# Required
USE_GVISOR=true                      # Enable gVisor (Linux only)
SKILLS_REGISTRY_URL=http://skills-registry:8002

# Optional
SECURITY_ALERT_WEBHOOK=https://...   # Webhook for critical alerts
SECURITY_LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
SECURITY_RETENTION_DAYS=7            # Event retention
```

### Recommended Production Settings

```python
# sandbox_manager.py overrides
PROD_LIMITS = {
    "cpu_limit": "1.0",          # Tighter limits
    "memory_limit": "1G",
    "pids_limit": 100,
    "network_enabled": True,     # But filtered via proxy
}

# security_monitor.py overrides
PROD_MONITORING = {
    "MAX_COMMANDS_PER_MINUTE": 30,
    "MAX_CPU_PERCENT": 80,       # More aggressive
    "MAX_MEMORY_PERCENT": 85,
    "MAX_NETWORK_TX_MB": 50,     # Lower threshold
}
```

## Incident Response

### Scenario: Crypto-Mining Detected

**Symptoms**:
- Sustained CPU usage > 95%
- Container running for hours
- Minimal network activity

**Response**:
1. Alert triggered automatically
2. Admin reviews security metrics
3. Check command audit trail for miner installation
4. Kill container: `docker stop sandbox-ide-{user}-{project}`
5. Review user activity patterns
6. Consider temporary suspension

### Scenario: Data Exfiltration Attempt

**Symptoms**:
- High network upload (> 100MB in 5 min)
- Suspicious curl/wget patterns in audit log
- Multiple attempts to external domains

**Response**:
1. Alert triggered automatically
2. Review command history for exfiltration commands
3. Check egress proxy logs for blocked requests
4. Kill container if active exfiltration
5. Analyze workspace volume for sensitive data
6. Report to security team

### Scenario: Container Escape Attempt

**Symptoms**:
- Attempts to access /proc/self/cgroup, docker.sock
- Kernel vulnerability exploit attempts
- Unusual syscall patterns (if gVisor logs available)

**Response**:
1. Critical alert triggered
2. IMMEDIATELY kill container
3. Review full audit trail
4. Check host system integrity
5. Update gVisor if vulnerability found
6. Ban user pending investigation

## Compliance & Audit

### Data Retention

- **Command logs**: 7 days in memory, 90 days in persistent storage (if configured)
- **Security events**: 7 days in memory, 90 days in persistent storage
- **Resource metrics**: 1 hour in memory, 24 hours in persistent storage
- **Container volumes**: Deleted 24 hours after last activity

### GDPR Considerations

- User data in /workspace is isolated per user
- Commands may contain PII (names, emails, etc.)
- Right to erasure: Delete volume on request
- Data portability: Export workspace volume

### SOC 2 Compliance

- Access controls: JWT authentication required
- Audit trail: All commands logged
- Encryption: TLS in transit, at-rest optional
- Monitoring: Real-time security monitoring
- Incident response: Documented procedures

## Limitations & Residual Risks

### Known Limitations

1. **gVisor Not Perfect**: Kernel vulnerabilities still possible (but rare)
2. **Zero-Day Exploits**: Unknown container escape vulnerabilities
3. **Social Engineering**: User convinced to run malicious code
4. **Supply Chain**: Malicious packages from PyPI, npm (not blocked)
5. **Resource Limits Bypass**: Creative resource abuse (e.g., I/O exhaustion)

### Residual Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Container escape via gVisor bug | Low | High | Update gVisor regularly, monitor security advisories |
| Crypto-mining undetected | Low | Medium | Sustained CPU monitoring, alert tuning |
| Data exfiltration via steganography | Very Low | Medium | Network traffic analysis, egress filtering |
| Resource exhaustion (disk I/O) | Medium | Low | I/O limits (not yet implemented) |
| Supply chain attack (malicious package) | Medium | High | User responsibility, sandboxing contains damage |

### Recommended Future Enhancements

1. **Seccomp Profiles**: Custom syscall filtering beyond gVisor
2. **AppArmor/SELinux**: Additional MAC layer
3. **I/O Limits**: Prevent disk exhaustion attacks
4. **SIEM Integration**: Export events to Splunk, ELK, etc.
5. **ML-Based Detection**: Behavioral anomaly detection
6. **Network Intrusion Detection**: Snort/Suricata integration
7. **Honeypots**: Decoy files to detect malicious behavior

## Security Testing

### Penetration Testing Checklist

- [ ] Attempt container escape (known CVEs)
- [ ] Fork bomb attack
- [ ] Crypto-mining simulation
- [ ] Network scanning
- [ ] Reverse shell attempts
- [ ] Data exfiltration (large file upload)
- [ ] Privilege escalation (sudo, setuid)
- [ ] Resource exhaustion (CPU, memory, disk, PIDs)
- [ ] Rate limit bypass
- [ ] Command injection in file paths

### Regular Security Audits

- **Monthly**: Review security event logs, tune detection rules
- **Quarterly**: Penetration testing, dependency updates
- **Annually**: Full security audit by third party

## Conclusion

The Sterna sandbox environment implements defense-in-depth security with seven distinct layers:

1. Container isolation (Docker + gVisor)
2. Filesystem restrictions (read-only + tmpfs)
3. Network filtering (egress proxy)
4. Resource monitoring (CPU, memory, network, PIDs)
5. Command auditing (full audit trail)
6. Suspicious pattern detection (ML-ready)
7. Rate limiting (per-user)

This architecture prioritizes **detection and visibility** over **restriction**, enabling AI agents to work flexibly while maintaining strong security posture. All suspicious activity is logged and alerted, allowing rapid incident response without hindering legitimate use cases.

**Security is a continuous process**: Regular updates, monitoring, and testing are essential to maintain protection against evolving threats.
