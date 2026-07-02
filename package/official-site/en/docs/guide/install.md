# Installation Guide

::: info Installation
TrailSnap currently supports Docker deployment only. Docker Compose is recommended for quick setup.
:::

## Docker Deployment (Recommended)

Using Docker Compose allows you to start all services with one click, including the frontend, backend, database, and AI services.

If you are deploying on a NAS (such as Ugreen, Zspace, Fnos), it is recommended to read the following as well:

- [Docker Deployment (Generic)](/en/docs/guide/docker/)
- [Ugreen NAS Deployment](/en/docs/guide/docker/ugreen)
- [Zspace Deployment](/en/docs/guide/docker/zspace)
- [Fnos Deployment](/en/docs/guide/docker/fnos)

If you have never used Docker and are using Windows, it is recommended to read the following:

- [Docker Deployment (Windows)](/en/docs/guide/docker/windows)

### One-Click Install Script (Recommended)

TrailSnap provides a one-click installation script that automatically handles Docker installation, mirror configuration, and service deployment — no manual configuration files needed.

#### Linux / macOS / WSL2

```bash
curl -fsSL https://trailsnap.cn/install.sh | bash
```

Or download and run locally:

```bash
# Interactive installation (follow the prompts)
./install.sh

# Non-interactive installation (specify photo directory, use China mirrors)
./install.sh --photo-dir /home/user/photos --china-mirrors --yes

# Enable GPU acceleration
./install.sh --photo-dir /home/user/photos --ai-mode gpu

# Specify custom ports
./install.sh --photo-dir /home/user/photos --frontend-port 8082 --server-port 8800
```

#### Windows PowerShell

```powershell
# One-click online installation
irm https://trailsnap.cn/install.ps1 | iex
```

Or download and run locally:

```powershell
# Interactive installation (follow the prompts)
.\install.ps1

# Non-interactive installation (specify photo directory, use China mirrors)
.\install.ps1 -PhotoDir "D:\Photos" -ChinaMirrors -Yes

# Enable GPU acceleration
.\install.ps1 -PhotoDir "D:\Photos" -AiMode gpu
```

#### Script Features

- ✅ Auto-detect OS and install Docker & Docker Compose
- ✅ Auto-configure China Docker registry mirrors (resolve slow image pulls in China)
- ✅ Interactive configuration collection (install directory, photo directory, ports, timezone, CPU/GPU mode)
- ✅ Auto-generate `.env` and `docker-compose.yml`
- ✅ Pull images and start services
- ✅ Post-deployment health checks
- ✅ Support for upgrade and uninstall

#### Management Commands

After installation, run the following commands in the install directory (default: `~/trailsnap`):

```bash
# Check service status
docker compose --env-file .env ps

# View logs
docker compose --env-file .env logs -f

# Stop services
docker compose --env-file .env down

# Restart services
docker compose --env-file .env restart

# Upgrade to latest version
./install.sh --upgrade

# Uninstall (keep data)
./install.sh --uninstall

# Uninstall (delete all data)
./install.sh --uninstall --purge
```

#### Full Parameter Reference

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--photo-dir` | Photo directory (comma-separated for multiple) | Required |
| `--install-dir` | Installation directory | `~/trailsnap` |
| `--frontend-port` | Frontend port | `8082` |
| `--server-port` | Backend API port | `8800` |
| `--ai-port` | AI service port | `8801` |
| `--postgres-port` | PostgreSQL port | `5532` |
| `--timezone` | Timezone | `Asia/Shanghai` |
| `--ai-mode` | AI mode (`cpu` or `gpu`) | `cpu` |
| `--tag` | Image tag (`latest` or `master`) | `latest` |
| `--china-mirrors` | Configure China Docker registry mirrors | - |
| `--yes` / `-y` | Non-interactive mode, accept all defaults | - |
| `--upgrade` | Upgrade existing installation | - |
| `--uninstall` | Uninstall | - |
| `--purge` | Delete all data (use with `--uninstall`) | - |

---

### Manual Deployment

If you prefer to configure manually, or are deploying on a NAS or other special environment, follow these steps.

#### Prerequisites

- Install [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).
- Ensure that local ports 5532, 8800, 8801, and 8082 are not in use.

#### Deployment Steps

1. **Get `docker-compose.yml`**

   Create a `docker-compose.yml` file in the project root directory with the following content:

   ```yaml
   version: '3.8'

   services:
     postgres:
       image: pgvector/pgvector:pg18-trixie
       container_name: postgres_container
       restart: always
       environment:
         TZ: Asia/Shanghai
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
         - /path/to/your/photos:/app/Photos/  # Please modify to your photo directory path
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
      environment:
        - TZ=Asia/Shanghai
       
     frontend:
      image: siyuan044/trailsnap-frontend:latest
       restart: always
       ports: [ "8082:80" ]
       depends_on: [ server ]
       networks: [ app-network ]
      environment:
        - TZ=Asia/Shanghai

   networks:
     app-network:
       driver: bridge
   ```

2. **Configure Photo Directory**

   Modify the `volumes` configuration under the `server` service, replacing `/path/to/your/photos` with the actual local directory path where your photos are stored.
   
   Windows User Example:
   ```yaml
   - F:\Photos:/app/Photos/
   ```
   
   Linux/macOS User Example:
   ```yaml
   - /home/user/photos:/app/Photos/
   ```

3. **Start Services**

   Execute the following command in the directory where `docker-compose.yml` is located:

   ```bash
   docker-compose up -d
   ```

4. **Access the Application**
   After the services start, access via browser: `http://localhost:8082`

5. **Access Backend API**
   - Backend API: `http://localhost:8800/docs`
   - AI Service Docs: `http://localhost:8801/docs`

#### Notes

::: warning
- **Data Persistence**: Database data is stored in `pg_data`, and application data in `data`. Do not delete them to avoid data loss.
- **Port Conflicts**: If default ports are occupied, modify the `ports` mappings (e.g. `8083:80`).
- **Photo Permissions**: Ensure containers can read your mounted photo directory.
- **GPU Acceleration**: If your system supports GPU, consider enabling GPU support. See [Docker Deployment](./docker/index.md).
- **Try latest features**: You can replace `latest` with `master` if you want to try the newest changes.
:::

### Get started

[How to use TrailSnap?](./user.md)

## Source Code Deployment

If you wish to participate in development or perform secondary development, you can choose source code deployment. Please refer to the [Developer Guide - Quick Start](/en/docs/dev/guide) for detailed steps.
