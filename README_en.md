<div align="center">
    <a href="https://github.com/LC044/TrailSnap/stargazers">
        <img src="https://img.shields.io/github/stars/LC044/TrailSnap.svg" />
    </a>
    <a href="https://trailsnap.cn/" target="_blank">
        <img alt="GitHub forks" src="https://img.shields.io/github/forks/LC044/TrailSnap?color=eb6ea5">
    </a>
    <!-- <a href="https://trailsnap.cn/" target="_blank">
        <img src="https://img.shields.io/badge/TrailSnap-TrailSnap-blue.svg">
    </a> -->
    <a href="https://atomgit.com/LC044/TrailSnap" target="_blank">
      <img alt="Docker Pulls" src="https://atomgit.com/LC044/TrailSnap/star/badge.svg">
    </a>
    <a target="_blank" href="https://trailsnap.cn/">
        <img alt="Hits" src="https://hits.b3log.org/LC044/trailsnap.svg">
    </a>
    <a href="https://trailsnap.cn/" target="_blank">
        <img src="https://img.shields.io/github/license/LC044/TrailSnap" />
    </a>
    <a href="https://github.com/LC044/TrailSnap/releases" target="_blank">
        <img alt="GitHub release (with filter)" src="https://img.shields.io/github/v/release/LC044/TrailSnap">
    </a>
    <a href="https://trailsnap.cn/" target="_blank">
      <img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/siyuan044/trailsnap-frontend?color=3eb370">
    </a>

**English** | [中文](README_zh.md)

</div>

---

> TrailSnap is an intelligent AI-powered photo album application that helps users effortlessly record, organize, and reminisce about their travel experiences. Through powerful AI processing capabilities, every photo and journey becomes a **treasured memory**.

> In the future, everyone (at least every family) will have their own AI data center, and the photo album is an important data source for this center. It preserves many moments from your life. TrailSnap is dedicated to transforming these moments into **valuable memories** — it can silently record train tickets and attraction tickets from your album, help you **record what you saw and heard during your travels**, automatically organize photos perfect for sharing on social media (even preparing the captions for you), and help you edit a 15-second short video······.

> Transforming travel from "just took photos" to "worth reminiscing, sharing, and cherishing." What TrailSnap aims to do is make every journey worth treasuring.

> That's why I named this project **"TrailSnap"** — where your data truly belongs to you.

<br/>
  <a href="https://trailsnap.cn">
    <img src="doc/image/demo.png" title="Main Screenshot">
  </a>
<br/>

## ✨ Key Features

- **📷 Smart Album**: Footprint map, person recognition, smart categorization, OCR, intelligent search.
- **🚆 Trip Recording**: Unique train ticket and itinerary management with automatic ticket information recognition. (In development)
- **🤖 AI Empowerment**: Let AI generate your travel diary with just one sentence. (Planned)
  - AI auto-editing videos to generate VLOGs
  - AI photo enhancement, automatically identifying high-quality photos

![homepage](doc/image/homepage.png)

## 🧭 Feature Overview

| Feature | Status | Description |
| --- | --- | --- |
| **Agent** | √ | Chat with AI models to generate travel diaries with one click |
| **CLI** | √ | Command-line interface for convenient AI operations |
| **SKILL** | √ | Support for OpenClaw, Claude Code and other platforms for automated task execution |
| **Train Ticket Recognition** | √ | Recognize train tickets and itineraries in photos, automatically extracting travel information |
| **Annual Report** | √ | Auto-generate 2025 travel statistics report, including photo walls, cities visited, attractions, timeline, mileage, etc. |
| **AI Analysis** | √ | Use AI models to analyze photo content, generate descriptions and ratings, creating an electronic gallery |
| **On This Day** | √ | View photos from this day in previous years, sorted by rating, with auto-play for memorable moments |
| **Travel Journal** | Planned | Support manual input or AI-recognized trip information to generate travel journals |
| **Visited Cities** | √ | View all cities that appear in uploaded photos, click to see all photos from that city |
| **Visited Attractions** | √ | Statistics for visited 5A-level scenic spots, click to view all photos, or customize location to auto-filter photos within the area |
| External Folders | √ | Add external folders as data sources, TrailSnap will automatically scan and index photos and videos |
| Live Photo | √ | Support for iPhone, Vivo, Oppo, Xiaomi and other phone models |
| **Timeline** | √ | Smooth timeline scrolling experience |
| Footprint Album | √ | View all uploaded photos on a map, click for details, also viewable by province, city, district (supports list view, map view, timeline view, route view) |
| Face Recognition | √ | Automatically recognize people in photos and add person tags |
| Scene Classification | √ | Auto-categorize photos by scene: night scenes, pets, food, selfies, etc. |
| Smart Search | √ | Search by person, image content, time, etc. |
| Tags | √ | Manual tag addition/deletion, auto-tags from AI recognition |
| Smart Albums | √ | Create albums based on photo content, e.g., "Selfie of me and my girlfriend at the beach" |

### Todo List

- [x] Support recycle bin, users can restore deleted photos.
- [ ] Support MCP protocol, users can communicate with TrailSnap via MCP.
- [x] Support skills, can connect to OpenClaw, Claude Code and other platforms.
- [ ] More comprehensive trip management: concert tickets, attraction tickets, hotel bookings, movie tickets, etc.
- [ ] More comprehensive AI capabilities: AI auto-editing videos for VLOGs, AI photo enhancement, AI-generated travel journals, etc.

## 2025 Annual Report

2025 Photo Album Annual Report

[View Preview](https://siyuan.ink/annual-report)

![年度报告](./doc/image/年度报告.jpg)

## 🚀 Quick Start

### One-Click Install Script (Recommended)

TrailSnap provides a one-click installation script that automatically handles Docker installation, mirror configuration, and service deployment.

**Linux / macOS / WSL2:**

```bash
curl -fsSL https://trailsnap.cn/install.sh | bash
```

**Windows PowerShell:**

```powershell
irm https://trailsnap.cn/install.ps1 | iex
```

For more options (non-interactive mode, GPU acceleration, custom ports, etc.), see the [Installation Guide](https://trailsnap.cn/en/docs/guide/install.html).

### Docker Manual Setup

1. Ensure Docker and Docker Compose are installed.

2. docker-compose

docker-compose.yml configuration (note: modify the mount path to a local path, otherwise local photo directories cannot be scanned)
```yml
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
      - ./data:/app/data        # Data directory mount
      - F:\Photos:/app/Photos/  # Local photo directory mount
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
      - ./data:/app/data        # Data directory mount
    environment:
      - TZ: Asia/Shanghai

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

3. Start services

```bash
docker-compose up -d
```

### Source Code Deployment

[Source Code Deployment](http://localhost:5173/docs/dev/guide.html)


## 📂 Project Structure

```
TrailSnap/
├── package/
│   ├── server/      # Backend FastAPI service
│   └── website/     # Frontend Vue application
│   └── ai/          # AI microservice (OCR/Face)
├── doc/             # Project documentation
└── ...
```

## 📚 Documentation

For more detailed technical documentation, please refer to the `doc/` directory (documentation may not be updated in time, for reference only):
- [Architecture Design](doc/architecture_design.md)
- [Frontend Framework Analysis](doc/frontend_analysis.md)
- [Backend Framework Analysis](doc/backend_analysis.md)
- [Developer Guide](doc/developer_guide.md)
- [User Guide](doc/user_guide.md)

## 🔍 More

### QQ Group

<img src="./doc/image/QQ1.jpg" alt="QQ Group" width="200px">

### Related Projects

- [InkTime](https://github.com/dai-hongtao/InkTime) InkTime is a self-hostable e-ink photo frame. It uses AI to analyze your photo library, score photos by reminiscing value, and automatically generate daily most memorable photos based on "On This Day in History," bringing dormant memories back to life.

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=LC044/TrailSnap&type=Date)](https://star-history.com/?utm_source=bestxtools.com#LC044/TrailSnap&Date)

## 🤝 Contributors

<a href="https://github.com/lc044/TrailSnap/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=lc044/TrailSnap" />
</a>
