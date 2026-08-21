"""
Security Monitoring and Threat Detection for Sandbox Containers

This module provides:
- Command logging and audit trail
- Suspicious pattern detection (crypto-mining, data exfiltration, etc.)
- Resource usage monitoring (CPU, memory, network)
- Rate limiting per user/project
- Real-time alerting for security events
"""

import re
import logging
import hashlib
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

# Docker is optional - may not be available in Kubernetes environments
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    docker = None
    DOCKER_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class SecurityEvent:
    """Represents a security event/alert."""
    timestamp: datetime
    user_id: str
    project_id: str
    event_type: str  # command, resource_spike, suspicious_pattern, rate_limit
    severity: str    # info, warning, critical
    details: Dict
    action_taken: Optional[str] = None


@dataclass
class ResourceMetrics:
    """Container resource usage metrics."""
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    network_rx_mb: float
    network_tx_mb: float
    pids_count: int
    timestamp: datetime


@dataclass
class RateLimitState:
    """Tracks rate limiting state per user/project."""
    commands_count: int = 0
    window_start: datetime = field(default_factory=datetime.now)
    total_commands: int = 0
    violations: int = 0


class SecurityMonitor:
    """
    Monitors sandbox security and detects threats.

    Design philosophy:
    - MONITOR first, BLOCK second (don't break legitimate AI agent workflows)
    - Alert on suspicious patterns but allow execution (with logging)
    - Rate limit only on extreme abuse
    - Focus on detection and visibility rather than lockdown
    """

    # Rate limiting (generous for AI agents)
    MAX_COMMANDS_PER_MINUTE = 60  # 1 command/second sustained
    MAX_COMMANDS_PER_HOUR = 1000
    MAX_CPU_PERCENT = 95  # Alert if sustained
    MAX_MEMORY_PERCENT = 95
    MAX_NETWORK_TX_MB = 100  # Alert if > 100MB uploaded in 5 minutes

    # Suspicious patterns (for DETECTION only, not blocking)
    SUSPICIOUS_PATTERNS = {
        'crypto_mining': [
            r'(xmrig|cpuminer|cgminer|bfgminer|ethminer)',
            r'stratum\+tcp://',
            r'--algo\s+(randomx|ethash|kawpow)',
        ],
        'network_scanning': [
            r'(nmap|masscan|zmap)\s',
            r'nc\s+-[lv]',  # Netcat listening/verbose
            r'\d+\.\d+\.\d+\.\d+/\d+',  # CIDR notation scan
        ],
        'reverse_shell': [
            r'bash\s+-i\s*>',
            r'/dev/tcp/',
            r'nc\s+.+\s+-e',
            r'python.*socket.*connect',
        ],
        'privilege_escalation': [
            r'(sudo|su\s)',
            r'chmod\s+[4567]\d{3}',  # SUID/SGID
            r'(chown|chgrp)\s+root',
        ],
        'data_exfiltration': [
            r'curl\s+.*-T',  # Upload
            r'wget\s+.*--post-file',
            r'scp\s+.*:',
            r'base64.*\|.*curl',
        ],
        'container_escape': [
            r'/proc/self/(cgroup|mounts|mountinfo)',
            r'/sys/class/net',
            r'docker\.sock',
            r'runc',
        ],
    }

    def __init__(self):
        # Docker client is optional - may not be available in Kubernetes
        self.client = None
        if DOCKER_AVAILABLE:
            try:
                self.client = docker.from_env()
                logger.info("Docker client initialized for security monitoring")
            except Exception as e:
                logger.warning(f"Docker not available for security monitoring: {e}")
                self.client = None
        else:
            logger.info("Running without Docker - security monitoring will use Kubernetes APIs")

        self.events: List[SecurityEvent] = []
        self.rate_limits: Dict[str, RateLimitState] = defaultdict(RateLimitState)
        self.resource_history: Dict[str, List[ResourceMetrics]] = defaultdict(list)
        self.command_hashes: Dict[str, int] = defaultdict(int)  # Detect command repetition

    def log_command(self, user_id: str, project_id: str, command: str,
                   source: str = "terminal") -> Tuple[bool, Optional[str]]:
        """
        Log a command execution and check for security issues.

        Returns:
            (allowed, reason) - Whether command should be allowed and reason if blocked
        """
        container_id = f"{user_id}-{project_id}"

        # 1. Rate limiting check
        rate_ok, rate_reason = self._check_rate_limit(user_id, project_id)
        if not rate_ok:
            self._log_event(
                user_id, project_id, "rate_limit", "warning",
                {"command": command, "reason": rate_reason, "source": source}
            )
            # ALLOW but log for severe rate limit violations
            logger.warning(f"Rate limit warning for {container_id}: {rate_reason}")

        # 2. Check for suspicious patterns
        threats = self._detect_threats(command)
        if threats:
            self._log_event(
                user_id, project_id, "suspicious_pattern", "warning",
                {
                    "command": command,
                    "threats": threats,
                    "source": source,
                    "action": "allowed_with_alert"
                }
            )
            logger.warning(
                f"Suspicious command detected for {container_id}: "
                f"threats={threats}, command={command[:100]}"
            )

        # 3. Detect command repetition (potential automated abuse)
        cmd_hash = hashlib.md5(command.encode()).hexdigest()
        self.command_hashes[f"{container_id}:{cmd_hash}"] += 1
        if self.command_hashes[f"{container_id}:{cmd_hash}"] > 50:
            self._log_event(
                user_id, project_id, "command_repetition", "info",
                {"command": command, "count": self.command_hashes[f"{container_id}:{cmd_hash}"]}
            )

        # 4. Log to audit trail
        logger.info(
            f"COMMAND: user={user_id} project={project_id} "
            f"source={source} cmd={command[:200]}"
        )

        # ALLOW all commands (we monitor but don't block for AI flexibility)
        return True, None

    def check_resource_usage(self, user_id: str, project_id: str,
                            container_name: str) -> Optional[SecurityEvent]:
        """
        Check container resource usage for anomalies.

        Returns:
            SecurityEvent if threshold exceeded, None otherwise
        """
        try:
            container = self.client.containers.get(container_name)
            stats = container.stats(stream=False)

            # Parse stats
            cpu_percent = self._calculate_cpu_percent(stats)
            memory_stats = stats['memory_stats']
            memory_usage = memory_stats.get('usage', 0)
            memory_limit = memory_stats.get('limit', 1)
            memory_percent = (memory_usage / memory_limit) * 100
            memory_mb = memory_usage / (1024 * 1024)

            # Network stats
            networks = stats.get('networks', {})
            network_rx = sum(net.get('rx_bytes', 0) for net in networks.values())
            network_tx = sum(net.get('tx_bytes', 0) for net in networks.values())
            network_rx_mb = network_rx / (1024 * 1024)
            network_tx_mb = network_tx / (1024 * 1024)

            # PIDs
            pids_count = stats.get('pids_stats', {}).get('current', 0)

            # Store metrics
            metrics = ResourceMetrics(
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                network_rx_mb=network_rx_mb,
                network_tx_mb=network_tx_mb,
                pids_count=pids_count,
                timestamp=datetime.now()
            )

            container_id = f"{user_id}-{project_id}"
            self.resource_history[container_id].append(metrics)

            # Keep only last 1 hour of metrics
            cutoff = datetime.now() - timedelta(hours=1)
            self.resource_history[container_id] = [
                m for m in self.resource_history[container_id]
                if m.timestamp > cutoff
            ]

            # Check thresholds
            alerts = []

            # CPU sustained high usage (crypto-mining indicator)
            if cpu_percent > self.MAX_CPU_PERCENT:
                recent_metrics = self.resource_history[container_id][-10:]
                if len(recent_metrics) >= 5:
                    avg_cpu = sum(m.cpu_percent for m in recent_metrics) / len(recent_metrics)
                    if avg_cpu > self.MAX_CPU_PERCENT:
                        alerts.append(f"Sustained high CPU: {avg_cpu:.1f}%")

            # Memory excessive usage
            if memory_percent > self.MAX_MEMORY_PERCENT:
                alerts.append(f"High memory: {memory_percent:.1f}%")

            # High network upload (data exfiltration indicator)
            recent_5min = [
                m for m in self.resource_history[container_id]
                if m.timestamp > datetime.now() - timedelta(minutes=5)
            ]
            if len(recent_5min) >= 2:
                tx_delta = network_tx_mb - recent_5min[0].network_tx_mb
                if tx_delta > self.MAX_NETWORK_TX_MB:
                    alerts.append(f"High network upload: {tx_delta:.1f}MB in 5min")

            # PIDs approaching limit
            if pids_count > 180:  # Limit is 200
                alerts.append(f"High PIDs count: {pids_count}/200")

            if alerts:
                event = self._log_event(
                    user_id, project_id, "resource_spike", "warning",
                    {
                        "alerts": alerts,
                        "metrics": {
                            "cpu_percent": cpu_percent,
                            "memory_percent": memory_percent,
                            "memory_mb": memory_mb,
                            "network_tx_mb": network_tx_mb,
                            "pids": pids_count,
                        }
                    }
                )
                logger.warning(f"Resource alert for {container_id}: {', '.join(alerts)}")
                return event

            return None

        except docker.errors.NotFound:
            logger.debug(f"Container {container_name} not found for monitoring")
            return None
        except Exception as e:
            logger.error(f"Error checking resources for {container_name}: {e}")
            return None

    def get_security_summary(self, user_id: str, project_id: str) -> Dict:
        """Get security summary for a user/project."""
        container_id = f"{user_id}-{project_id}"
        rate_state = self.rate_limits.get(container_id)

        # Get recent events
        recent_events = [
            e for e in self.events
            if e.user_id == user_id and e.project_id == project_id
            and e.timestamp > datetime.now() - timedelta(hours=24)
        ]

        # Get latest metrics
        latest_metrics = None
        if container_id in self.resource_history and self.resource_history[container_id]:
            latest_metrics = self.resource_history[container_id][-1]

        return {
            "container_id": container_id,
            "total_commands": rate_state.total_commands if rate_state else 0,
            "rate_violations": rate_state.violations if rate_state else 0,
            "events_24h": len(recent_events),
            "warnings_24h": len([e for e in recent_events if e.severity == "warning"]),
            "critical_24h": len([e for e in recent_events if e.severity == "critical"]),
            "latest_metrics": {
                "cpu_percent": latest_metrics.cpu_percent if latest_metrics else 0,
                "memory_mb": latest_metrics.memory_mb if latest_metrics else 0,
                "pids": latest_metrics.pids_count if latest_metrics else 0,
            } if latest_metrics else None,
            "recent_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "type": e.event_type,
                    "severity": e.severity,
                    "details": e.details
                }
                for e in recent_events[-10:]  # Last 10 events
            ]
        }

    def _check_rate_limit(self, user_id: str, project_id: str) -> Tuple[bool, Optional[str]]:
        """Check if user/project is within rate limits."""
        container_id = f"{user_id}-{project_id}"
        state = self.rate_limits[container_id]
        now = datetime.now()

        # Reset window if needed (1 minute windows)
        if now - state.window_start > timedelta(minutes=1):
            state.commands_count = 0
            state.window_start = now

        # Increment counters
        state.commands_count += 1
        state.total_commands += 1

        # Check limits
        if state.commands_count > self.MAX_COMMANDS_PER_MINUTE:
            state.violations += 1
            return False, f"Rate limit: {state.commands_count} commands/minute (max {self.MAX_COMMANDS_PER_MINUTE})"

        return True, None

    def _detect_threats(self, command: str) -> List[str]:
        """Detect suspicious patterns in command."""
        detected = []

        for threat_type, patterns in self.SUSPICIOUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    detected.append(threat_type)
                    break

        return detected

    def _calculate_cpu_percent(self, stats: Dict) -> float:
        """Calculate CPU percentage from Docker stats."""
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            cpu_count = stats['cpu_stats']['online_cpus']

            if system_delta > 0:
                return (cpu_delta / system_delta) * cpu_count * 100
        except (KeyError, ZeroDivisionError):
            pass

        return 0.0

    def _log_event(self, user_id: str, project_id: str, event_type: str,
                   severity: str, details: Dict) -> SecurityEvent:
        """Log a security event."""
        event = SecurityEvent(
            timestamp=datetime.now(),
            user_id=user_id,
            project_id=project_id,
            event_type=event_type,
            severity=severity,
            details=details
        )

        self.events.append(event)

        # Keep only last 10000 events in memory
        if len(self.events) > 10000:
            self.events = self.events[-5000:]

        return event

    def cleanup_old_data(self):
        """Cleanup old monitoring data (call periodically)."""
        cutoff = datetime.now() - timedelta(days=7)

        # Clean events
        self.events = [e for e in self.events if e.timestamp > cutoff]

        # Clean resource history
        for container_id in list(self.resource_history.keys()):
            self.resource_history[container_id] = [
                m for m in self.resource_history[container_id]
                if m.timestamp > cutoff
            ]
            if not self.resource_history[container_id]:
                del self.resource_history[container_id]

        # Clean command hashes (keep only last 1000 per container)
        for key in list(self.command_hashes.keys()):
            if self.command_hashes[key] > 1000:
                del self.command_hashes[key]

        logger.info("Security monitor cleanup completed")


# Global instance
security_monitor = SecurityMonitor()
