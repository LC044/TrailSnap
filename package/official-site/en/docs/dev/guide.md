# TrailSnap Developer Documentation

This document aims to provide developers with a guide to the TrailSnap project, covering environment setup, project structure, development process, etc.

## Table of Contents

- [TrailSnap Developer Documentation](#trailsnap-developer-documentation)
  - [Table of Contents](#table-of-contents)
  - [1. Project Introduction \& Tech Stack](#1-project-introduction--tech-stack)
  - [2. Development Environment Preparation](#2-development-environment-preparation)
  - [3. Project Structure Detail](#3-project-structure-detail)
  - [4. Backend Development Guide](#4-backend-development-guide)
    - [4.1 Start Database](#41-start-database)
    - [4.2 Install Dependencies](#42-install-dependencies)
    - [4.3 Configuration File](#43-configuration-file)
    - [4.4 Run Service](#44-run-service)
  - [5. Frontend Development Guide](#5-frontend-development-guide)
    - [5.1 Install Dependencies](#51-install-dependencies)
    - [5.2 Run Development Server](#52-run-development-server)
    - [5.3 Build](#53-build)
  - [6. AI Service Development Guide](#6-ai-service-development-guide)
    - [6.1 Install Dependencies](#61-install-dependencies)
    - [6.2 Run Service](#62-run-service)
  - [7. Database Migration](#7-database-migration)
  - [8. Build Docker Image](#8-build-docker-image)

---

## 1. Project Introduction & Tech Stack

TrailSnap is a project with separated frontend and backend, integrating AI capabilities.

- **Frontend**: Vue 3, TypeScript, Vite, Element Plus, TailwindCSS
- **Backend**: Python (FastAPI), SQLAlchemy, Alembic
- **Database**: PostgreSQL (requires enabling pgvector extension to support vector search)
- **AI Service**: Independent microservice, based on FastAPI, integrating models like PaddleOCR, InsightFace, YOLO.

## 2. Development Environment Preparation

Before starting development, please ensure that the following tools are installed on your machine:

- **Git**: Version control
- **Python**: 3.10+ (Recommended 3.12)
- **Node.js**: v18+ (Recommended v20 or v22)
- **pnpm**: Frontend package manager (`npm install -g pnpm`)
- **Docker & Docker Compose**: Used to quickly start the database

## 3. Project Structure Detail

```
TrailSnap/
├── doc/                 # Project documentation
├── package/
│   ├── ai/              # AI Microservice
│   │   ├── app/         # AI Core Logic
│   │   └── ...
│   ├── server/          # Backend Main Service
│   │   ├── app/         # FastAPI Application
│   │   │   ├── api/     # API Routes
│   │   │   ├── core/    # Config & Logger
│   │   │   ├── crud/    # Database Operations
│   │   │   ├── db/      # Model Definitions
│   │   │   ├── schemas/ # Pydantic Models
│   │   │   └── service/ # Business Logic
│   │   └── ...
│   └── website/         # Frontend Application
│       ├── src/         # Source Code
│       └── ...
└── ...
```

## 4. Backend Development Guide

The backend is located in `package/server`.

### 4.1 Start Database
The project depends on PostgreSQL and the pgvector extension. It is recommended to use Docker to start it: due to documentation deployment restrictions, please refer directly to the `package/server/README.md` file in the project source code.

### 4.2 Install Dependencies
It is recommended to use `uv` for package management.

```bash
cd package/server
# Install uv
pip install uv
# Use uv
uv sync
```

### 4.3 Configuration File
Create a `.env` file in the `package/server/data` directory (refer to README or configure directly):
```env
DB_URL=postgresql://user:password@localhost:5432/trailsnap
RAILWAY_DB_URL=postgresql://user:password@localhost:5432/railway
AI_URL=http://localhost:8001
```

### 4.4 Run Service
```bash
# First run requires initializing the database
python start.py

# Start in development mode
uvicorn main:app --reload --port 8000
```
API Documentation Address: `http://localhost:8000/docs`

## 5. Frontend Development Guide

The frontend is located in `package/website`.

### 5.1 Install Dependencies
```bash
cd package/website
pnpm install
```

### 5.2 Run Development Server
```bash
pnpm dev
```
Access Address: `http://localhost:5176`

### 5.3 Build
```bash
pnpm build
```

## 6. AI Service Development Guide

The AI service is located in `package/ai`, providing OCR and face recognition capabilities for the backend.

### 6.1 Install Dependencies
```bash
cd package/ai

pip install uv

# Install dependencies (CPU version)
uv sync --extra cpu

# Install dependencies (GPU version)
uv sync --extra gpu
```

### 6.2 Run Service
```bash
uvicorn app.main:app --reload --port 8001
```

## 7. Database Migration

The backend uses Alembic to manage database migrations.

**Note**: After modifying models under `db/models`, you must execute migration for it to take effect.

1. **Generate Migration Script**
   ```bash
   cd package/server
   alembic revision --autogenerate -m "Description of changes"
   ```

2. **Execute Migration**
   ```bash
   alembic upgrade head
   ```

3. **Common Commands**
   - `alembic current`: View current version
   - `alembic history`: View version history
   - `alembic downgrade -1`: Rollback to previous version

## 8. Build Docker Image

```bash
cd TrailSnap
# One-click build docker image
docker-compose up -d --build
```

```bash
# Build frontend image
docker build -t crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-frontend:master -f package/website/Dockerfile .

# Build backend image
docker build -t crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-backend:master -f package/server/Dockerfile .

# Build AI image
docker build -t crpi-d7wuvvdylhqugyu2.cn-hangzhou.personal.cr.aliyuncs.com/siyuan044/trailsnap-ai:master -f package/ai/Dockerfile .
```
