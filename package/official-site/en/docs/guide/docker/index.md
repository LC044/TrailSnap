---
title: Docker Deployment (Generic)
---

# Docker Deployment (Generic)

This chapter targets NAS/Home Server scenarios: Start TrailSnap's frontend, backend, database, and AI services at once using Docker Compose, and mount your photo directory.

If you haven't read the installation guide, it is recommended to read first: [/en/docs/guide/install](/en/docs/guide/install)

## 1. Directory Planning (Suggested)

Prepare a shared folder on the NAS as TrailSnap's "project directory", preferably containing two types of data:

- **Application Data**: Database and application runtime data (needs long-term persistence)
- **Photo Directory**: Your own photo library (recommended read-only mount)

Example structure (for illustration only):

```
trailsnap/
  docker-compose.yml
  data/
  pg_data/
```

## 2. Docker Compose (Recommended Template)

The compose below is consistent with the installation guide, you only need to modify two places:

- Host path for photo directory in `server.volumes`
- Modify `ports` mapping if there is a port conflict

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg18-trixie
    container_name: postgres_container
    restart: always
    environment:
      POSTGRES_DB: trailsnap
      POSTGRES_USER: trailsnap
      POSTGRES_PASSWORD: trailsnap
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=C --lc-ctype=C"
      PGDATA: /var/lib/postgresql/data/pgdata
    networks: [ app-network ]
    ports:
      - "5532:5432"
    volumes:
      - ./pg_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U trailsnap -d trailsnap -p 5432"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s

  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - /path/to/your/photos:/app/Photos/
    environment:
      - TZ=Asia/Shanghai
      - DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap
      - RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy

  ai:
    image: siyuan044/trailsnap-ai:latest
    restart: always
    expose: [ "8001" ]
    ports: [ "8801:8001" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data

  frontend:
    image: siyuan044/trailsnap-frontend:latest
    restart: always
    ports: [ "8082:80" ]
    depends_on: [ server ]
    networks: [ app-network ]

networks:
  app-network:
    driver: bridge
```

## 3. Startup and Verification

Execute in the directory where `docker-compose.yml` is located:

```bash
docker-compose up -d
```

Common entry points after startup:

- Frontend: `http://<NAS_IP>:8082`
- Backend API: `http://<NAS_IP>:8800/docs`
- AI Service: `http://<NAS_IP>:8801/docs`

## 4. GPU Acceleration Support (Optional)

If you have an NVIDIA GPU, you can enable GPU acceleration to speed up AI processing.

### Prerequisites

1. NVIDIA graphics driver installed on the host.
2. [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) installed.

**[Windows Installation Steps]** (for other systems, please search for tutorials):

**Step 1**: Open a WSL 2 Linux terminal
Find your installed Linux distribution (e.g. Ubuntu) in the Windows Start Menu and open its terminal (not Windows PowerShell).

**Step 2**: Install nvidia-docker2 in WSL 2
For Ubuntu, run:

```bash
# 1. Set up NVIDIA software source
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# 2. Update and install nvidia-docker2
sudo apt-get update
sudo apt-get install -y nvidia-docker2

# 3. Restart Docker
sudo systemctl restart docker
```

### Modify docker-compose.yml

Make the following changes to the `ai` service:

1. Change the image tag to the `-gpu` suffix (e.g. `latest-gpu`).
2. Add a `deploy` section to request GPU resources.

```yaml
  ai:
    image: siyuan044/trailsnap-ai:latest-gpu
    restart: always
    expose: [ "8001" ]
    ports: [ "8801:8001" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## 5. NAS Scenario FAQ

### 4.1 How to write the path correctly?

On NAS, please refer to the "real path of the shared folder". Different systems display paths differently, but there is only one principle: ensure that `/app/Photos/` inside the container can see your photo files.

### 4.2 Insufficient permissions causing scan failure

If the photo directory is read-only shared or permission isolated, the container may not be able to read it. Suggestions:

- Grant read permission of the shared folder to the container running account
- Or mount the photo directory as read-only and ensure host side permissions allow reading

### 4.3 Port Conflict

Common ports like 80/443/8080 are easily occupied on NAS. TrailSnap uses 8082/8800/8801/5532 by default. If there is a conflict, you can modify the mapping yourself, for example:

```yaml
ports: [ "18082:80" ]
```

## 6. NAS Specific Tutorials

- [Ugreen NAS Deployment](/en/docs/guide/docker/ugreen)
- [Zspace Deployment](/en/docs/guide/docker/zspace)
- [Fnos Deployment](/en/docs/guide/docker/fnos)
