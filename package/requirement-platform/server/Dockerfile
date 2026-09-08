FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY requirement_platform ./requirement_platform
COPY alembic.ini ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

RUN useradd --system --uid 10001 --create-home requirement && mkdir -p /app/data && chown -R requirement:requirement /app
USER requirement

EXPOSE 8010 8012
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn requirement_platform.main:app --host 0.0.0.0 --port 8010"]
