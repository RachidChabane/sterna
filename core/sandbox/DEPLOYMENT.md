# Sterna Sandbox System - Deployment Guide

Complete guide for deploying the Sterna sandbox system in production.

## Prerequisites

- **OS**: Linux (Ubuntu 22.04+ recommended)
- **Docker**: 24.0+
- **Docker Compose**: 2.20+
- **CPU**: 8+ cores recommended
- **RAM**: 16GB+ recommended
- **Disk**: 100GB+ SSD

## Quick Start

### 1. Install gVisor

```bash
cd sandbox/runtime
sudo ./install-gvisor.sh
```

Verify installation:
```bash
docker run --rm --runtime=runsc hello-world
```

### 2. Configure Environment

Create `.env` file:

```bash
# S3/MinIO Configuration
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=CHANGE_ME_ACCESS_KEY
S3_SECRET_KEY=CHANGE_ME_SECRET_KEY
S3_BUCKET=sterna-artifacts

# Redis Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# OpenTelemetry (optional)
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENVIRONMENT=production

# Resource Limits
SANDBOX_CPU_LIMIT=2.0
SANDBOX_MEMORY_LIMIT=2G
MAX_FILE_SIZE=10485760

# Network
SKILLS_REGISTRY_URL=http://skills-registry:8002
FS_SERVICE_URL=http://fs-service:8001
```

### 3. Build Docker Images

```bash
cd sandbox

# Build all images
./build-images.sh
```

Or manually:

```bash
# Skill runtimes
docker build -f skills/images/Dockerfile.skill-python \
    -t sterna-skill-python:latest .

docker build -f skills/images/Dockerfile.skill-node \
    -t sterna-skill-node:latest .

docker build -f skills/images/Dockerfile.skill-shell \
    -t sterna-skill-shell:latest .

# Sandbox IDE
docker build -f runtime/Dockerfile.sandbox-ide \
    -t sterna-sandbox-ide:latest .

# Services
docker build -f fs-service/Dockerfile \
    -t sterna-fs-service:latest fs-service/

docker build -f skills/registry/Dockerfile \
    -t sterna-skills-registry:latest skills/registry/

docker build -f orchestrator/Dockerfile \
    -t sterna-orchestrator:latest orchestrator/
```

### 4. Start Services

```bash
docker-compose -f docker-compose.sandbox.yml up -d
```

### 5. Verify Deployment

```bash
# Check service health
curl http://localhost:8001/health  # FS Service
curl http://localhost:8002/health  # Skills Registry
curl http://localhost:8003/health  # Orchestrator

# List available skills
curl http://localhost:8002/skills

# Check MinIO
curl http://localhost:9000/minio/health/live

# Check Redis
docker exec sterna-redis redis-cli ping
```

## Production Configuration

### Security Hardening

1. **Change default credentials**:
```bash
# In .env or docker-compose.yml
MINIO_ROOT_USER=<strong-username>
MINIO_ROOT_PASSWORD=<strong-password>
```

2. **Enable TLS for Traefik**:
```yaml
# In traefik.yml
entryPoints:
  websecure:
    address: ":443"
    http:
      tls:
        certResolver: letsencrypt
```

3. **Restrict network access**:
```yaml
# Only expose necessary ports
ports:
  - "127.0.0.1:8001:8001"  # FS Service (internal only)
  - "0.0.0.0:443:443"      # HTTPS (public)
```

### Resource Tuning

For production workloads, adjust resource limits in `docker-compose.sandbox.yml`:

```yaml
orchestrator:
  deploy:
    resources:
      limits:
        cpus: '4.0'      # Increase for heavy workloads
        memory: 4G
      reservations:
        cpus: '2.0'
        memory: 2G

celery-worker:
  command: celery -A celery_tasks worker --loglevel=info --concurrency=8
  deploy:
    resources:
      limits:
        cpus: '8.0'
        memory: 8G
```

### Scaling

#### Horizontal Scaling (Multiple Workers)

```bash
# Scale Celery workers
docker-compose -f docker-compose.sandbox.yml up -d --scale celery-worker=4
```

#### Vertical Scaling (More Resources)

Update `docker-compose.sandbox.yml` resource limits and restart:

```bash
docker-compose -f docker-compose.sandbox.yml up -d --force-recreate
```

### High Availability

For HA deployment:

1. **Use external Redis cluster**:
```yaml
environment:
  - CELERY_BROKER_URL=redis-sentinel://sentinel1:26379,sentinel2:26379/0
```

2. **Use external S3** (AWS S3, Cloudflare R2, etc.):
```yaml
environment:
  - S3_ENDPOINT_URL=https://s3.amazonaws.com
  - S3_REGION=us-east-1
```

3. **Run multiple orchestrator instances**:
```bash
docker-compose -f docker-compose.sandbox.yml up -d --scale orchestrator=3
```

Add a load balancer (e.g., nginx) in front.

### Monitoring

#### Metrics (Prometheus)

Add Prometheus to `docker-compose.sandbox.yml`:

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
  ports:
    - "9090:9090"
  networks:
    - sandbox-network
```

`monitoring/prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'orchestrator'
    static_configs:
      - targets: ['orchestrator:8003']

  - job_name: 'fs-service'
    static_configs:
      - targets: ['fs-service:8001']

  - job_name: 'skills-registry'
    static_configs:
      - targets: ['skills-registry:8002']
```

#### Tracing (Jaeger)

Add Jaeger for distributed tracing:

```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  ports:
    - "16686:16686"  # UI
    - "4317:4317"    # OTLP gRPC
  environment:
    - COLLECTOR_OTLP_ENABLED=true
  networks:
    - sandbox-network
```

Set in `.env`:
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
```

#### Logging (Loki)

Centralized logging with Grafana Loki:

```yaml
loki:
  image: grafana/loki:latest
  ports:
    - "3100:3100"
  networks:
    - sandbox-network

promtail:
  image: grafana/promtail:latest
  volumes:
    - /var/lib/docker/containers:/var/lib/docker/containers:ro
    - ./monitoring/promtail-config.yml:/etc/promtail/config.yml
  networks:
    - sandbox-network
```

### Backup & Recovery

#### Backup MinIO Data

```bash
# Using MinIO Client (mc)
mc alias set myminio http://localhost:9000 minioadmin minioadmin
mc mirror myminio/sterna-artifacts /backup/artifacts/$(date +%Y%m%d)
```

#### Backup Redis Data

```bash
# Redis automatically snapshots to /data
docker cp sterna-redis:/data/dump.rdb /backup/redis/$(date +%Y%m%d)/
```

#### Backup Workspace Volumes

```bash
# Backup user workspace
docker run --rm \
  -v sandbox-ide-user1-project1-workspace:/source:ro \
  -v /backup/workspaces:/backup \
  alpine tar czf /backup/user1-project1-$(date +%Y%m%d).tar.gz -C /source .
```

### Disaster Recovery

1. **Restore MinIO**:
```bash
mc mirror /backup/artifacts/20250101 myminio/sterna-artifacts
```

2. **Restore Redis**:
```bash
docker cp /backup/redis/20250101/dump.rdb sterna-redis:/data/
docker restart sterna-redis
```

3. **Restore Workspaces**:
```bash
docker run --rm \
  -v sandbox-ide-user1-project1-workspace:/target \
  -v /backup/workspaces:/backup \
  alpine tar xzf /backup/user1-project1-20250101.tar.gz -C /target
```

## Troubleshooting

### gVisor Issues

**Error**: `unknown runtime: runsc`

```bash
# Check Docker daemon config
cat /etc/docker/daemon.json

# Should contain:
{
  "runtimes": {
    "runsc": {
      "path": "/usr/local/bin/runsc"
    }
  }
}

# Restart Docker
sudo systemctl restart docker
```

### Out of Disk Space

```bash
# Clean up unused images
docker image prune -a

# Clean up unused volumes
docker volume prune

# Clean up stopped containers
docker container prune
```

### Service Not Starting

```bash
# Check logs
docker-compose -f docker-compose.sandbox.yml logs <service-name>

# Check resource usage
docker stats

# Restart specific service
docker-compose -f docker-compose.sandbox.yml restart <service-name>
```

### Network Issues

```bash
# Verify network exists
docker network ls | grep sandbox-network

# Inspect network
docker network inspect sandbox-network

# Recreate network
docker-compose -f docker-compose.sandbox.yml down
docker-compose -f docker-compose.sandbox.yml up -d
```

## Maintenance

### Update Services

```bash
# Pull latest images
docker-compose -f docker-compose.sandbox.yml pull

# Rebuild custom images
./build-images.sh

# Restart with new images
docker-compose -f docker-compose.sandbox.yml up -d --force-recreate
```

### Clean Old Artifacts

Celery beat runs daily cleanup automatically. To manually clean:

```bash
# Via orchestrator API
curl -X POST http://localhost:8003/admin/cleanup-artifacts?days=30
```

### Monitor Resource Usage

```bash
# Container stats
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

# Disk usage
du -sh /var/lib/docker/volumes/sandbox_*
```

## Performance Optimization

1. **Use SSD for Docker volumes**
2. **Enable Docker BuildKit** for faster builds
3. **Tune Celery concurrency** based on CPU cores
4. **Increase Docker daemon resources** in `/etc/docker/daemon.json`
5. **Use Redis persistence** (AOF) for durability
6. **Enable MinIO cache** for faster artifact access

## Security Checklist

- [ ] Change all default passwords
- [ ] Enable TLS/HTTPS
- [ ] Restrict external network access
- [ ] Configure firewall rules
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Rotate access keys monthly
- [ ] Scan images for vulnerabilities
- [ ] Enable rate limiting
- [ ] Configure authentication middleware

## Support

For issues or questions:
- GitHub: https://github.com/sterna/sandbox
- Docs: https://docs.example.com/sandbox
- Email: support@example.com
