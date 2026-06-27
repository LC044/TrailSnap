# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

TrailSnap (行影集) is an AI-powered self-hosted photo album application. Four packages live under `package/`:

- **`website/`** — Frontend SPA (Vue 3 + TypeScript + Vite + Element Plus + Pinia). Dev port **5176**.
- **`server/`** — Main backend (FastAPI + SQLAlchemy + Alembic). Port **8000**. Drives the database, business logic, and async task pipeline.
- **`ai/`** — GPU-optional AI microservice (FastAPI + PaddleOCR / InsightFace / RapidOCR / CLIP). Port **8001**. The server calls it over HTTP via `AI_API_URL`.
- **`official-site/`** — VitePress documentation site (Chinese + English, `docs/` and `en/`).
- **`trailsnap-cli/`** — Node CLI published to npm as `trailsnap-cli`. Allows AI agents to query photo / album / tag / location / person data.

Additional top-level items: `skills/` (CLI skill bundled for Codex / OpenClaw), `doc/` (architecture & developer docs in Chinese), `docker-compose.yml` (full-stack deploy), `.github/workflows/` (Docker build & push for each component).

## Development Commands

### Frontend (`package/website`)
```bash
pnpm install
pnpm dev        # http://localhost:5176 (proxies /api -> 127.0.0.1:8000)
pnpm build      # outputs to dist/
pnpm preview
pnpm test:e2e           # Playwright headless
pnpm test:e2e:ui        # Playwright UI mode
pnpm test:e2e:headed    # Playwright with browser visible
```
E2E tests live in `package/website/tests/e2e/`. The dev server proxies `/api/*` to the backend (see `vite.config.js`), so the frontend can be developed against a locally running server.

### Backend (`package/server`)
```bash
uv sync                          # Install deps (uses Tsinghua mirror via pyproject.toml)
python start.py                  # Auto-init DB + run migrations + start on :8000
uvicorn main:app --host 0.0.0.0 --port 8000 --reload   # Dev mode with hot reload
```
`start.py` performs: connect to Postgres → create DB if missing → enable `vector` extension → run `alembic upgrade head` → import 5A scenic-spot CSV → `os.execvp` to uvicorn.

**Run a single test:**
```bash
cd package/server
python -m pytest tests/test_api_integration.py -v
# or against the unittest-style file
python -m unittest tests.test_api_integration -v
```

### AI Service (`package/ai`)
```bash
uv sync --extra cpu        # CPU only
uv sync --extra gpu        # GPU (CUDA 12.8)
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```
On non-Windows, the AI service runs an idle-check task that calls `sys.exit(0)` after `IDLE_TIMEOUT` (default 600s) so the container orchestrator can restart it and free memory. LLM is managed as a subprocess via `app/services/llm_manager.py` (port 8002, default 5-min idle).

### Database Migrations

Note: Avoid modifying the database schema unless absolutely necessary. If changes are required, you must carefully assess the impact of database migrations, including compatibility between old and new versions, to prevent any data loss or corruption.

Migration file naming convention: `12-character-hash_sequence-number_description.py`, for example: `0a3b98f751d6_0007_add_face_foreign.py`

```bash
cd package/server
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic current
alembic history
alembic downgrade -1
```

## Environment Variables

Each Python component reads from `data/.env` (created on first run by `start.py` / `main.py` if missing).

**`package/server/data/.env`**
- `DB_URL` — PostgreSQL DSN (pgvector must be installed; auto-enabled by `start.py`).
- `RAILWAY_DB_URL` — separate Postgres for the railway sub-app.
- `AI_API_URL` — base URL of the AI service (default `http://localhost:8001`).

**`package/ai/data/.env`** (optional)
- `MODEL_PATH` — defaults to `data/models`.
- `LLM_MODEL_PATH`, `LLM_SERVER_PORT`, `LLM_IDLE_TIMEOUT`.

## Architecture

### Multiprocess backend (`package/server`)

The FastAPI server is **not** single-process. `app/main.py` lifespan spawns (and stops) a separate worker process via `app/service/task_manager.py` → `app/worker.py` → `app/service/task_worker.py`. This separation is critical:

- **API process** (`main:app` on :8000) — handles HTTP, creates `Task` rows, exposes `/tasks/*` status endpoints, pauses/resumes via `SystemState`.
- **Worker process** (`app.worker.run_worker`) — claims pending tasks, runs them, updates rows. Independent event loop; restarted on crash by the API process.

Tasks are organized by `TaskType` and registered handlers live in `app/service/tasks/` (one module per category: `face.py`, `ocr.py`, `tickets.py`, `metadata.py`, `classification.py`, `image_embedding.py`, `thumbnail.py`, `scan.py`, `organize.py`, `rename.py`, `time_from_filename.py`, `similar.py`, `duplicate.py`, `album.py`).

### Backend layering (`package/server/app/`)

- **`api/`** — thin FastAPI routers, one file per domain (`photo`, `album`, `face`, `ocr`, `agent`, `auth`, `toolbox`, `search`, `train_ticket`, `flight_ticket`, `annual_report`, `tasks`, `system`, `media`, `metadata`, `index`, `deps`, `login`, `classification`, `stats`, `settings`, `user`, `agent_token`). All routers are mounted in `main.py` with explicit prefixes/tags.
- **`schemas/`** — Pydantic request/response models. **All API responses are wrapped in `BaseResponse`** (see `app/schemas/response.py`); handlers return `BaseResponse.success(data=...)` or `BaseResponse.fail(...)`.
- **`crud/`** — SQLAlchemy CRUD helpers, one module per aggregate.
- **`db/models/`** — ORM models. Migrate with Alembic after every change.
- **`service/`** — cross-domain business logic: `storage.py` (file IO), `indexer.py`, `similar_photo.py`, `face_cluster.py`, plus the task subsystem above.
- **`service/agent/`** — LangChain + LangGraph agent (see "AI Agent" below).
- **`service/live_photo/`** — per-vendor Live Photo parsers (`apple.py`, `android.py`, `vivo.py`).
- **`core/`** — config, JSON-queue logger with daily rolling, system config.
- **`railway/`** — independent sub-app with its own `api.py`, `crud.py`, `schemas.py`, `db/`, and `build_database.py`. Mounted at `/railway` in `main.py`. This handles train timetable / ticket data and is functionally separate from the main app.
- **`utils/`** — EXIF parsing, filename utilities.

要求：后端所有新增api都才用

```json
{
  code: 0,
  msg: "success",
  data: {}
}
```

### AI microservice (`package/ai/app/`)

- **`routers/`** — `face`, `ocr`, `object_detection`, `tickets`, `image_classification`, `embedding`, `llm` (OpenAI-compatible `/v1/...`), `ai_config`, `system`.
- **`services/`** — lazy-loaded model wrappers (`face_service.py`, `ocr_service.py`, `image_classification_service.py`, `embedding_service.py`, `ticket_service.py`, `fly_ticket_parser.py`, `ticket_parser.py`). `model_manager.py` handles resource release; `model_downloader.py` pre-downloads weights on startup; `llm_manager.py` runs an LLM server subprocess and tears it down on idle.
- **`core/logger.py`** — same JSON-queue logger as the server.

### AI Agent (LangChain / LangGraph)

`package/server/app/service/agent/service.py` is a LangChain agent backed by LangGraph. The agent is exposed via `app/api/agent.py` (mounted at `/agent`) and authenticated through `app/api/agent_token.py` (mounted at `/tokens`) — **agent tokens are separate from user JWTs** so AI clients can be granted scoped access without a user account.

`service/agent/tools.py` defines the tools the agent can call (photo/album/search/stats/face/etc.). Streaming responses are returned as SSE; the client UI lives at `package/website/src/views/agent/AgentChat.vue`.

### Frontend structure (`package/website/src/`)

- **`api/`** — Axios clients, one per backend domain. `config.ts` defines multi-API configs (the main app uses Vite's `/api` proxy, but `railway`/`user`/`payment` keys can point to other services).
- **`router/index.ts`** — central route table. Routes declare a `meta.layout` (`'main' | 'blank'`) that `App.vue` uses to choose between `MainLayout.vue` and a blank layout. The annual-report and login pages use the blank layout.
- **`stores/`** — Pinia stores (`photoStore`, `albumStore`, `ticketStore`, `locationStore`, `user`, `selectionStore`).
- **`components/`** — large feature components: `PhotoGallery`, `PhotoLightbox`, `FlatPhotoGallery`, `UnifiedPhotoPage`, `TrainTicket`, `TicketFormModal`, `OnThisDay`, `MultiFileUpload`, `AlbumTimeline`, `PersonAvatar`, `FolderSelectionDialog`. Most are stateful and tied to specific views.
- **`views/`** — page-level components, grouped by feature folder (`album/`, `ticket/`, `toolbox/`, `search/`, `agent/`, `annual-report/`, `login/`, `settings/`). Toolbox pages are full photo-management utilities (rename, organize, dedup, similar, time-from-filename, cleanup).
- **`layouts/`** — `MainLayout.vue` (sidebar + content).
- **`composables/`**, **`utils/`**, **`types/`** — shared TS helpers.
- **`assets/`** — Tailwind base styles in `main.css`; global `style.css` registers Mingcute icons.

The dev server (`vite.config.js`) listens on `0.0.0.0:5176` and proxies `/api` to `http://127.0.0.1:8000/`. `@` is aliased to `src/`.

### CLI & Skills

- **`package/trailsnap-cli/`** — Node CLI (`bin/`). Build with `pnpm build`; the GitHub workflow `build-publish-cli.yml` publishes it to npm. Allows external AI agents to query TrailSnap data without a browser.
- **`skills/trailsnap-cli/`** — Bundled Codex / OpenClaw skill so agents can invoke the CLI from a prompt.

### Docker deployment

`docker-compose.yml` at repo root runs `postgres` (pgvector), `server`, `ai`, and `frontend` (nginx serving the Vite build). Mount the host photo directory into the `server` container (see `F:\Photos:/app/Photos/` in `README.md`). Each component has its own `Dockerfile` in its subdir; the AI service has `Dockerfile` (CPU) and `Dockerfile.gpu`. The GitHub workflows in `.github/workflows/` build and push images to Docker Hub on tag pushes or commits containing `-latest` / "构建后端".

## Conventions

- **API responses**: every endpoint returns `BaseResponse[T]` (`{code, message, data, ...}`). New endpoints must follow this pattern.
- **Backend logging**: use `logging.getLogger("app.<module>")`. The `app.middleware` logger records `{operation, params, result, duration_ms}` for every non-`/medias` request — keep paths that would flood logs out of the request log.
- **Frontend**: components use `<script setup lang="ts">`; state goes in Pinia stores; HTTP through `src/api/*` modules.
  - **Theme**: For anything that should follow the user's chosen brand color, use the `primary-*` utility classes defined in `src/style.css` (`bg-primary-{500,600}`, `text-primary-{500,600}`, `border-primary-500`, `hover:bg-primary-{500,600,700}`, `shadow-primary-500{,\/20,\/30,\/40}`, `ring-primary-500`/etc.) — they map to `var(--theme-primary)` / `var(--theme-rgb)` and the 5 themes in `src/composables/useTheme.ts` (sky / emerald / violet / rose / amber) swap for free. **Never** hardcode Tailwind brand colors (`blue-500/600/700`, `purple-500`, `emerald-500`, ...) for accent elements — they will not follow the theme. In non-utility contexts (Tianditu, ECharts, dynamic styles), call `injectTheme()` from `@/composables/useTheme` and read `currentTheme.value.primary` (hex string) / `currentTheme.value.rgb` (for `rgba()`). When the theme changes, re-run any imperative drawing code (e.g., `map.drawTrajectory()`) — the utility classes react automatically, but JS-driven visuals do not.
  - **Dark mode**: Every `text-gray-*` and `bg-white` must be paired with a `dark:` variant. The recurring patterns `text-gray-500 dark:text-gray-400` and `text-gray-400 dark:text-gray-500` cover most cases — copy them. Element Plus components (`el-dialog`, `el-select`, `el-slider`, `el-dropdown`, `el-message-box`, etc.) inherit dark mode through `html.dark` + `--el-bg-color: #111827` (set in `src/style.css` L18); do not override their internal colors per-instance.
  - **Focus ring**: Interactive elements (buttons, links, clickable cards, custom dropdown items) must include `focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 focus-visible:outline-none` for keyboard accessibility. The ring color is already mapped to `var(--theme-primary)` in `style.css`, so no extra work is needed to make it follow the theme.
  - **One gray family per component**: Stick to `gray-*` (or `slate-*`) — do not mix the two within a single surface. `MainLayout.vue` mixes `bg-slate-50 dark:bg-slate-900` (outer) with `dark:bg-gray-900` (inner content), which produces a visible dark-mode seam. Pick one and apply it consistently to the root + main + modals of the same layout.
- **Migrations**: edit ORM models in `app/db/models/`, then `alembic revision --autogenerate` and commit the generated file. Never delete a model field without a migration step.
- **Commit messages**: Conventional Commits (`feat(scope):`, `fix(scope):`, `refactor(scope):`). Certain keywords in commit messages trigger GitHub Actions CI pipelines — **only include these when you intentionally want to build and push Docker images or publish packages**, as they consume CI resources and push to Docker Hub / npm / GitHub Releases:
  - `构建后端` — triggers **Server** Docker build & push (`.github/workflows/docker-build-push-server.yml`), only when `package/server/` files changed.
  - `构建前端` — triggers **Frontend** Docker build & push (`.github/workflows/docker-build-push-frontend.yml`), only when `package/website/` files changed.
  - `构建ai` or `构建AI` — triggers **AI service** Docker build & push (`.github/workflows/docker-build-push-ai.yml`), only when `package/ai/` files changed.
  - `构建cli` — triggers **CLI** binary build & npm publish (`.github/workflows/build-publish-cli.yml`), only when `package/trailsnap-cli/` files changed.
  - All pipelines also trigger on `v*.*.*` tag pushes regardless of commit message.
  - **Rule of thumb**: for routine code changes (UI tweaks, bug fixes, docs), do NOT include these keywords. Only add them when the change is significant enough to warrant a new Docker image or package release (e.g., new feature, breaking change, version bump).
- **PR template**: see `.github/pull_request_template.md`. CLA confirmation ("I have read and agree to the CLA") is required in PR comments (AGPLv3).

## Key Files

- `package/server/main.py` — backend entry; lifespan, middleware, router mounting.
- `package/server/start.py` — DB init + migration + uvicorn exec.
- `package/server/app/worker.py` + `app/service/task_manager.py` + `app/service/task_worker.py` — the async pipeline.
- `package/server/app/service/agent/service.py` — LangChain agent entry.
- `package/ai/main.py` — AI service entry, idle restart, LLM subprocess lifecycle.
- `package/website/vite.config.js` — port + `/api` proxy.
- `package/website/src/router/index.ts` — all routes + layout hints.
- `docker-compose.yml` — full-stack deployment.
- `CONTRIBUTING.md` — dev env, commit conventions, PR template, CLA.
- `doc/architecture_design.md` — Chinese architecture overview with diagrams.
