# Architecture Design Document

## 1. Overall Architecture Diagram

TrailSnap adopts a typical separated frontend and backend architecture, consisting of a frontend presentation layer, a backend service layer, an AI microservice layer, and a data storage layer.

1. **Frontend Presentation Layer**: Provides a unified entry point through Nginx reverse proxy, supports HTTP/HTTPS access, and delivers the interactive frontend interface to users.
2. **Backend Service Layer**: Built on FastAPI as the core, with a security authentication module for JWT identity verification and multi-user permission isolation, ensuring safe family multi-user usage; separates business logic services from the task manager, achieving decoupling of synchronous business and async AI tasks; connects to PostgreSQL via SQLAlchemy ORM for metadata storage, and interfaces with the NAS local file system via file services for image storage — fully adapted to NAS storage architecture.
3. **AI Microservice Layer**: Uses a unified entry dispatch with a built-in model manager implementing intelligent lifecycle management — lazy loading on demand, automatic unloading when idle, and automatic download when needed — significantly reducing NAS memory and compute usage; integrates PaddleOCR, InsightFace, YOLO+OCR, CLIP, and other AI capabilities, covering OCR recognition, face recognition, ticket recognition, vector search, and other core album functions; also supports connecting to external LLMs like Qwen and GPT for good extensibility.
4. **Data Storage Layer**: Metadata and files are stored separately, with all data stored locally to ensure family data privacy and security.

```mermaid
flowchart TD
    User[👨‍💻 User Browser] -->|⚡ HTTP/HTTPS| FE[Frontend App<br/>Vue 3 + Vite]

    subgraph Frontend_Layer[🖥️ Frontend Presentation Layer]
      FE -->|📡 Axios / REST| API8000
      FE -->|💾 Pinia| Store[Global State Management]
      FE -->|🎨 ElementPlus| UI[UI Component Library]
    end

    subgraph Backend_Layer[⚙️ Backend Service Layer]
      API8001[Backend Service<br/>FastAPI :8000] --> Routers[API Route Dispatch]
      Routers --> Services[Business Logic Services]
      Services -->|🗄️ ORM Mapping| DBConn[SQLAlchemy]
      Services -->|📂 File IO| FS[File System]
      Services -->|⏳ Async Scheduling| TM[Task Manager]
      TM -->|🔗 HTTP Call| AI8001
    end

    subgraph AI_Service[🤖 AI Microservice Layer]
      AI8001[AI Microservice<br/>FastAPI :8001] --> OCR[PaddleOCR Text Recognition]
      AI8001 --> Face[InsightFace Face Recognition]
      AI8001 --> OD[Object Detection]
      AI8001 --> Ticket[Ticket Recognition<br/>YOLO + OCR]
    end

    subgraph Data_Layer[💽 Data Persistence Layer]
      DBConn --> DB[(PostgreSQL Database)]
      FS --> Storage[Local/Mounted Storage]
    end
```

```mermaid
flowchart TD
    User[👨‍💻 User Browser] -->|⚡ HTTP/HTTPS| FE[Frontend App<br/>Vue 3 + Vite]
```

## 2. Technology Stack & Versions

### 2.1 Frontend Stack

### 2.2 Backend Stack
- **Programming Language**: Python 3.12+
- **Web Framework**: FastAPI 0.122.0
- **ASGI Server**: Uvicorn 0.38.0
- **ORM**: SQLAlchemy 2.0.44
- **Database Migration**: Alembic 1.17.2
- **Database Driver**: psycopg2 (PostgreSQL)
- **Task/Async**: APScheduler, `aiohttp`
- **AI/CV (AI Microservice)**:
  - PaddleOCR ==3.3.2
  - PaddlePaddle-GPU `==3.2.0` (Optional GPU)
  - OpenCV `opencv-python-headless >=4.9.0`
  - Torch `>=2.0.0`, TorchVision `>=0.15.0` (Some models available)
  - InsightFace (Face)
- **Logger**: Custom JSON queue logger + daily capacity rolling (built-in for both server and ai)

### 2.3 Database
- **PostgreSQL (PgVector)**: Relational database, stores users, albums, photo metadata, system settings, etc.

## 3. Directory Structure & Module Description

### 3.1 Root Directory
- `package/server`: Backend service code
- `package/website`: Frontend application code
- `doc`: Project documentation

### 3.2 Backend Structure (`package/server`)
- **app/**: Core application code
  - `api/`: API route definitions (EndPoints), divided by functional modules (user, album, photo, etc.)
  - `core/`: Core configuration and tools (Logger, Config)
  - `crud/`: Database CRUD operation encapsulation
  - `db/`: Database models (Models) and session management (Session)
  - `schemas/`: Pydantic data models (Request/Response schemas)
  - `service/`: Complex business logic and background services (TaskManager, Indexer, Storage)
  - `utils/`: Common utility functions (Exif parsing, filename processing)
- **railway/**: Railway related functional modules (independent data processing and synchronization logic)
- **yolo_ocr/**: OCR and ticket recognition related models and scripts
- **main.py**: Application entry, route mounting, CORS, middleware, and port configuration (default `:8000`)

### 3.3 Frontend Structure (`package/website`)
- **src/**: Source code
  - `api/`: Backend interface encapsulation
  - `assets/`: Static resources (images, CSS)
  - `components/`: Common Vue components (PhotoGallery, TrainTicket, etc.)
  - `composables/`: Composable functions (Hooks)
  - `layouts/`: Page layout components
  - `router/`: Route configuration
  - `stores/`: Pinia state management store
  - `types/`: TypeScript type definitions
  - `views/`: Page views (Pages)
  - `package.json`: Dependency and version management, including scripts `dev/build/preview`

### 3.4 AI Microservice Structure (`package/ai`)
- **app/main.py**: AI service entry (default `:8001`), mounting `ocr/face/object-detection/tickets` routes
- **app/services/**: Model services (`ocr_service.py`, `face_service.py`, `model_manager.py` lazy loading and resource release)
- **app/core/logger.py**: JSON queue logger, daily capacity rolling
- **requirements.txt**: Dependencies and version constraints (PaddleOCR, PaddlePaddle-GPU, Torch, OpenCV, etc.)

## 4. Key Interactions & Call Chain

```mermaid
sequenceDiagram
  participant FE as Frontend (Vue)
  participant S as Backend Service :8000
  participant AI as AI Microservice :8001
  participant DB as PostgreSQL
  participant FS as File System

  FE->>S: GET /api/ocr?photo_id=...
  S->>DB: Query ocr_results
  DB-->>S: Normalized polygon/text
  S-->>FE: JSON Response

  S->>AI: POST /ocr/predict (Async Task)
  AI->>AI: PaddleOCR Inference
  AI-->>S: rec_texts/rec_scores/rec_polys
  S->>DB: Write ocr_results (Coordinates normalized 0~1)

  FE->>S: Media Operations/Album Management
  S->>FS: Read/Write Media Files
  S->>DB: Write/Query Metadata
```
