# Step 1: Install Docker Desktop
Docker Compose is already integrated into Docker Desktop, so install it first:
1. Go to the Docker official website to download: https://www.docker.com/products/docker-desktop/
2. Double-click the downloaded installer and keep clicking **Next** (check **Use WSL 2 instead of Hyper-V**).
3. Restart your computer after installation.
4. Launch Docker Desktop (the first startup may take a few minutes; a Docker icon will appear in the system tray).
5. If this is your first use, a command prompt window will pop up asking you to install **Windows Subsystem for Linux**. Follow the instructions to install it.
6. Configure a registry mirror:
   Open **Settings → Docker Engine**, and paste the following JSON:
   ```json
   {
     "builder": {
       "gc": {
         "defaultKeepStorage": "20GB",
         "enabled": true
       }
     },
     "experimental": false,
     "registry-mirrors": ["https://docker.1ms.run"]
   }
   ```
   Click **Apply & Restart** to restart Docker Desktop.

7. Verify installation:
   Press `Win + R`, type `cmd` to open Command Prompt, then run:
   ```bash
   docker --version
   docker-compose --version
   ```
   If version numbers are displayed, the installation is successful.

---

# Step 2: Prepare the `docker-compose.yml` File
1. Create a new empty folder, e.g., `D:\TrailSnap`.
2. Inside the folder, create a file named `docker-compose.yml`.
3. Open it with a text editor and paste the content below:

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
      - ./photos:/app/Photos/
    environment:
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

## Modify Photo Volume Mounts
Find the `volumes` section under the `server` service and change `./photos:/app/Photos/` to your **local photo directory**.

Example (if your photos are in `D:\TrailSnap\photos`):
```yml
  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - D:\TrailSnap\photos:/app/Photos/
    environment:
      - DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/trailsnap
      - RAILWAY_DB_URL=postgresql://trailsnap:trailsnap@postgres:5432/railway
      - AI_API_URL=http://ai:8001
    depends_on:
      postgres:
        condition: service_healthy
```

If you have **multiple photo folders** (e.g., `D:\TrailSnap\photos1`, `D:\TrailSnap\photos2`):
```yml
  server:
    image: siyuan044/trailsnap-server:latest
    restart: always
    expose: [ "8000" ]
    ports: [ "8800:8000" ]
    networks: [ app-network ]
    volumes:
      - ./data:/app/data
      - D:\TrailSnap\photos:/app/Photos/
      - D:\TrailSnap\photos1:/app/Photos1/
      - D:\TrailSnap\photos2:/app/Photos2/
```
- Left side of `:` = local folder path
- Right side of `:` = path used inside TrailSnap

---

# Step 3: Run Deployment Commands
1. Open Command Prompt (`Win + R` → `cmd`), then navigate to the folder containing `docker-compose.yml`:
   ```bash
   # Example: if the file is in D:\TrailSnap
   cd /d D:\TrailSnap
   ```
2. Start all services (core command):
   ```bash
   docker-compose up -d
   ```
   - `up`: start all services defined in the compose file
   - `-d`: run in detached/background mode

3. Wait for completion.
Docker will automatically pull images, create containers, and start services.

Sample success output:
```bash
PS C:\ProgramData\TrailSnap> docker-compose up -d
time="2026-03-06T17:42:03+08:00" level=warning msg="C:\\ProgramData\\TrailSnap\\docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
[+] up 51/51
 ✔ Image siyuan044/trailsnap-frontend:latest Pulled                                                               38.2s
 ✔ Image siyuan044/trailsnap-ai:latest       Pulled                                                              155.8s
 ✔ Image pgvector/pgvector:pg18-trixie       Pulled                                                               76.8s
 ✔ Image siyuan044/trailsnap-server:latest   Pulled                                                              112.8s
 ✔ Network trailsnap_app-network             Created                                                                0.1s
 ✔ Container postgres_container              Healthy                                                                28.0s
 ✔ Container trailsnap-ai-1                  Created                                                                1.1s
 ✔ Container trailsnap-server-1              Created                                                                0.1s
 ✔ Container trailsnap-frontend-1            Created                                                                0.1s
```

---

# Step 4: Verify Deployment
Open your browser and go to:`http://localhost:8082`

You will see the TrailSnap web interface.

Go to **More → Settings → External Library** and add:
`/app/Photos/`

If you have multiple volumes, add:
`/app/Photos1/`, `/app/Photos2/`, etc.

---

# Troubleshooting (For Beginners)
1. **“docker-compose.yml not found”**
   Make sure your Command Prompt is in the same folder as the file.
   Or run:
   ```bash
   docker-compose -f "full\path\to\docker-compose.yml" up -d
   ```

2. **Port conflict / Port in use**
   Change the **host port** (the number before `:`) in the `ports` section of `docker-compose.yml`, then run `docker-compose up -d` again.

---

# Summary
1. **Prerequisite**: Install Docker Desktop and verify with `docker --version`.
2. **Key step**: Place `docker-compose.yml` in a folder, `cd` into it, then run `docker-compose up -d`.
3. **Management commands**:
   - `docker-compose ps` – view running services
   - `docker-compose logs` – check logs for errors
   - `docker-compose down` – stop and remove containers