# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TrailSnap is an AI-powered photo album application with three main components:
- **Frontend** (Vue 3 + TypeScript + Vite): Located in `package/website`
- **Backend** (FastAPI + SQLAlchemy): Located in `package/server`
- **AI Microservice** (FastAPI + PaddleOCR/InsightFace): Located in `package/ai`

## Development Commands

### Frontend
```bash
cd package/website
pnpm install
pnpm dev        # Dev server at http://localhost:5176
pnpm build       # Production build to dist/
```

### Backend
```bash
cd package/server
uv sync         # Install dependencies via uv
python start.py # Auto-init DB, run migrations, start server on :8000
# OR for dev with hot reload:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### AI Service
```bash
cd package/ai
uv sync --extra cpu   # CPU version
uv sync --extra gpu   # GPU version (CUDA 12.8)
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

### Database Migrations (Alembic)
```bash
cd package/server
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic current        # Check current version
alembic history        # View history
alembic downgrade -1   # Rollback
```

## Architecture

### Backend Structure (`package/server/app/`)
- `api/` - API route handlers organized by domain (user, album, photo, etc.)
- `service/` - Business logic (TaskManager, Indexer, Storage)
- `crud/` - Database CRUD operations
- `db/models` - SQLAlchemy ORM models
- `schemas/` - Pydantic request/response models

Key: Backend communicates with AI service via HTTP (`AI_API_URL=http://localhost:8001`).

### API Response Format
Backend uses a unified `BaseResponse` structure. API routes return standardized responses.

### Database
PostgreSQL with `pgvector` extension for vector search. Database URL configured via `DB_URL` env var.

## Key Files
- `package/server/start.py` - Backend startup script (runs migrations, init DB)
- `package/server/main.py` - FastAPI app entry point
- `package/ai/main.py` - AI service entry point
- `docker-compose.yml` - Full stack Docker deployment