# syntax=docker/dockerfile:1
#
# TrailSnap Server —— 单阶段构建。
# server 的依赖（opencv-python-headless / psycopg2-binary / bcrypt / numpy / pillow /
# pillow-heif）全部为预编译 manylinux wheel，无 C 扩展编译需求，故不需要 builder stage。
# 精简手段：依赖层前置（代码变动不失效缓存）+ uv/pip 清缓存 + --no-dev 去掉 pytest。

FROM python:3.12.12-slim

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never

# 先拷依赖清单，代码变动不失效依赖层缓存
COPY pyproject.toml uv.lock ./
# --no-cache：不留 uv 下载缓存（原镜像此处占 639MB）
# --no-dev：运行时不需要 pytest / pytest-asyncio / pytest-cov
RUN pip install --no-cache-dir uv && \
    uv sync --no-dev --no-cache

# 应用代码（resources/ railway/ alembic/ reverse_geocoder/ 等运行时需要的目录都在这里）
COPY . .

EXPOSE 8000
# 核心：将虚拟环境的 bin 目录加入 PATH
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "start.py"]
