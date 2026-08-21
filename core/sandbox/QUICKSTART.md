# 🚀 Quick Start - Sandbox System

## Getting Started (2 minutes)

### 1️⃣ **Start all services**

```bash
# Terminal 1: Sandbox services
cd /path/to/sterna/core/sandbox
docker-compose -f docker-compose.sandbox.yml up -d

# Terminal 2: Backend + Frontend
cd /path/to/sterna/core
docker-compose up -d
```

### 2️⃣ **Verify everything is running**

```bash
# Sandbox services (should be "healthy")
docker ps --filter "name=sterna-" --format "table {{.Names}}\t{{.Status}}" | head -5

# Backend + Frontend
docker ps --filter "name=core-" --format "table {{.Names}}\t{{.Status}}" | grep -E "web|frontend"
```

**Expected result**:
```
✅ sterna-orchestrator      Up X minutes (healthy)
✅ core-web-1               Up X minutes
✅ core-frontend-1          Up X minutes
```

### 3️⃣ **Test the interface**

1. **Open**: http://localhost:5173
2. **Sign in** (via GitHub OAuth, see the project's CLAUDE.md for local login notes)

---

## 🔧 Useful Commands

### Stop all services

```bash
# Stop sandbox
cd /path/to/sterna/core/sandbox
docker-compose -f docker-compose.sandbox.yml down

# Stop backend + frontend
cd /path/to/sterna/core
docker-compose down
```

### Restart after a code change

```bash
# Restart only the Django backend
docker-compose restart web

# Rebuild after a dependency change
docker-compose up -d --build web
```

### View logs

```bash
# Django backend logs
docker logs -f core-web-1

# Orchestrator logs
docker logs -f sterna-orchestrator

# All sandbox logs
cd /path/to/sterna/core/sandbox
docker-compose -f docker-compose.sandbox.yml logs -f
```

---

## 🐛 Troubleshooting

### Problem: "Service Unavailable 503"

**Cause**: The Django backend is not connected to the sandbox network.

**Solution**:
```bash
# Check the configuration
grep -A5 "networks:" /path/to/sterna/core/docker-compose.yml

# Should contain:
# networks:
#   - default
#   - sandbox-network

# If not, restart:
docker-compose down
docker-compose up -d
```

### Problem: Frontend won't load

**Solutions**:
```bash
# Check status
docker logs core-frontend-1

# Restart
docker-compose restart frontend

# Rebuild if needed
docker-compose up -d --build frontend
```

---

## 📊 Ports Used

| Service | Port | URL |
|---------|------|-----|
| Frontend | 5173 | http://localhost:5173 |
| Backend Django | 8000 | http://localhost:8000 |
| Orchestrator | 8003 | http://localhost:8003 |

---

## ✅ Startup Checklist

- [ ] Sandbox services started: `docker-compose -f docker-compose.sandbox.yml up -d`
- [ ] Backend + frontend started: `docker-compose up -d`
- [ ] Orchestrator healthy: `curl http://localhost:8003/health`
- [ ] Backend accessible: `curl http://localhost:8000/api/health/`
- [ ] Frontend accessible: http://localhost:5173

---

## 🎯 Development Workflow

### Modifying the Django backend

```bash
# 1. Edit code under core/api/ or core/sterna/
# 2. Code reloads automatically (hot reload via mounted volume)
# 3. Watch the logs: docker logs -f core-web-1
```

### Modifying the React frontend

```bash
# 1. Edit code under core/frontend/src/
# 2. Vite HMR reloads automatically
# 3. Refresh the browser if needed
```

### Modifying the orchestrator

```bash
# 1. Edit code under core/sandbox/orchestrator/
# 2. Rebuild the image
cd core/sandbox
docker-compose -f docker-compose.sandbox.yml build orchestrator

# 3. Restart
docker-compose -f docker-compose.sandbox.yml up -d --force-recreate orchestrator
```

---

## 📚 Full Documentation

- **`SECURITY_ARCHITECTURE.md`** — defense-in-depth security layers
- **`DEPLOYMENT.md`** — production deployment guide
- **`GVISOR_SETUP.md`** — gVisor installation for Linux production
- **`QUICKSTART.md`** — this file

---

## 🆘 Support

If you run into trouble:

1. **Check the services**: `docker ps --filter "name=sterna-"`
2. **Check the logs**: `docker logs <service-name>`
3. **Check the networks**:
   ```bash
   docker network ls | grep sandbox
   docker inspect core-web-1 --format '{{range $net, $_ := .NetworkSettings.Networks}}{{$net}}{{"\n"}}{{end}}'
   ```
4. **Restart everything**:
   ```bash
   docker-compose down
   cd sandbox && docker-compose -f docker-compose.sandbox.yml down
   # Then start back up in order
   ```

---

**🎉 You're ready! Head to http://localhost:5173**
