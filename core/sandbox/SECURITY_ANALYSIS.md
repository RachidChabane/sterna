# Security Analysis: Root in Sandbox Containers

## Question: Is it really dangerous to give root inside an isolated container?

**Short answer: YES, very dangerous, even with the current protections.**

## Real Container-Escape Threats

### 1. **Kernel Vulnerabilities (Container Escape)**

#### CVE-2019-5736 (runc vulnerability)
- **Impact**: Lets root inside the container overwrite the runc binary on the host
- **Consequence**: Arbitrary code execution on the host with host privileges
- **Current protection**: Depends on the runc version installed on the host Docker engine
- **Exploit**: Publicly available, relatively simple to exploit

```bash
# Simplified exploit outline (do not run!)
# If you're root inside the container:
#!/bin/bash
# Overwrite /bin/sh in the container
# Use /proc/self/exe to access the runc binary on the host
# Overwrite runc on the host = code execution on the host
```

#### CVE-2022-0492 (cgroups v1 vulnerability)
- **Impact**: Privilege escalation via `release_agent` in cgroups
- **Consequence**: Command execution on the host
- **Current protection**: `cap_drop=ALL` helps, but is not sufficient with root

```python
# Conceptual exploit outline (do not run!)
# With root inside the container:
import os
# Mount the cgroup with release_agent pointing to a malicious script
# Trigger the release_agent, which runs on the host
os.system("mkdir /tmp/cgrp && mount -t cgroup -o memory cgroup /tmp/cgrp")
os.system("echo '/cmd' > /tmp/cgrp/release_agent")
```

### 2. **Linux Capabilities - Always Present with Root**

Even with `cap_drop=ALL`, root inside the container still retains certain powers:

```bash
# Test inside a container with cap_drop=ALL but user=root
docker run --rm --cap-drop=ALL -u root alpine sh -c "
  # Can still:
  - Change file permissions
  - Read any file inside the container
  - Install rootkits inside the container
  - Manipulate any namespaces it has access to
"
```

### 3. **Attacks via Mounted Volumes**

If volumes are mounted read-write:

```python
# With root + a mounted volume:
# /workspace mounted from the host or another container
import os
os.system("chmod 777 /workspace")  # Change permissions
os.system("echo 'malicious code' > /workspace/.bashrc")  # Backdoor
```

### 4. **PID Namespace - Process Access**

Without full PID namespace isolation:

```bash
# With root, can send signals to processes
kill -9 1  # Try to kill the container's init process
# Can cause DoS or unpredictable behavior
```

### 5. **Gaps in Filtered Syscalls**

The default seccomp profile blocks certain syscalls, but:
- Docker's seccomp profile is not perfect
- New dangerous syscalls keep being added to the kernel
- Bypasses are regularly discovered

## Comparison: User vs Root

### Current Configuration (user=sandboxuser)

```python
# What an attacker CAN do:
- Read/write in /tmp and /workspace (tmpfs)
- Execute Python/Bash code
- Make network requests (through the proxy)
- pip install --user (ephemeral)

# What an attacker CANNOT do:
- ❌ apt install (no permissions)
- ❌ Modify /etc (read-only or no permissions)
- ❌ Access other users' files
- ❌ Escalate to root (no-new-privileges)
- ❌ Exploit most container escapes (they require root)
```

### If root were granted (user=root)

```python
# What an attacker could do IN ADDITION:
- ✅ apt install (install attack tooling)
- ✅ Modify /etc/passwd, /etc/shadow
- ✅ Install rootkits inside the container
- ✅ Exploit CVEs that require root (runc, cgroups, etc.)
- ✅ Manipulate permissions on any file
- ✅ Load kernel modules (if not blocked)
- ✅ Mount filesystems (if not blocked)
- ✅ Access /proc, /sys with elevated permissions
```

## Why gVisor Matters

gVisor adds an **additional layer of defense**:

```
Without gVisor:
┌──────────────────┐
│  Malicious code   │
│   in sandbox      │
└─────────┬─────────┘
          │ syscall
          ↓
┌──────────────────┐
│  Linux Kernel     │ ← Direct attack surface on the kernel
│  (vulnerable)     │
└──────────────────┘

With gVisor:
┌──────────────────┐
│  Malicious code   │
│   in sandbox      │
└─────────┬─────────┘
          │ syscall
          ↓
┌──────────────────┐
│  gVisor Sentry    │ ← Intercepts syscalls
│  (user-space)     │
└─────────┬─────────┘
          │ filtered/emulated syscalls
          ↓
┌──────────────────┐
│  Linux Kernel     │ ← Much less exposed
└──────────────────┘
```

gVisor only runs on the Docker/VPS deployment path in this codebase (see
`README.md#-security--isolation`); it is not currently wired into the Kubernetes
deployment.

## Recommendations

### Option 1: Stay with a non-root user (RECOMMENDED)
**Advantages**:
- Blocks the majority of known container escapes
- Defense in depth
- Even if a CVE surfaces, it will likely still require root

**Drawbacks**:
- No `apt install`
- Limited system packages

**Solution**: pre-install the packages you need into the image.

### Option 2: Root user with hardened protections (RISKY)
If truly necessary:

```python
# sandbox_executor.py
container = client.containers.run(
    user="root",  # ⚠️ Dangerous

    # MAXIMUM protections:
    security_opt=[
        "no-new-privileges:true",
        "seccomp=/path/to/strict-seccomp.json"  # Very strict seccomp profile
    ],
    cap_drop=["ALL"],  # Drop all capabilities
    # NEVER add cap_add alongside root!

    read_only=True,  # Strict read-only filesystem
    tmpfs={
        '/tmp': 'size=100M,mode=1777,noexec,nosuid,nodev',  # noexec matters here
        '/var/tmp': 'size=50M,mode=1777,noexec,nosuid,nodev'
    },

    # No sensitive volumes mounted
    # No privileged mode
    # No --pid=host, --net=host, etc.
)
```

### Option 3: Hybrid containers
- A base container (non-root) for code execution
- A separate privileged container (init container) for installs
- The two never run at the same time

## Recommended Security Tests

1. **Vulnerability scanning**:
```bash
docker scan sandbox-base:latest
trivy image sandbox-base:latest
```

2. **Escape tests**:
```bash
# Test with public exploits (test environment only!)
# https://github.com/cdk-team/CDK (container penetration toolkit)
```

3. **Syscall auditing**:
```bash
# Log all suspicious syscalls
strace -c -f docker run ...
```

## Conclusion

**Granting root inside the container multiplies the attack surface by 10.**

Even with all our current protections (`cap_drop`, `no-new-privileges`, network
isolation), an attacker with root has FAR more options to:
1. Escape the container to the host
2. Persist in the environment
3. Pivot to other containers
4. Exfiltrate data

**Verdict**: Keep `user=sandboxuser` and pre-install the packages you need into the
Dockerfiles.
