# syntax=docker/dockerfile:1
#
# TrailSnap Server —— 编码器、Python依赖、资源准备与运行镜像分离。
# Python依赖使用预编译wheel；uv及FFmpeg编译工具仅存在于构建阶段。
# Docker通过FFmpeg读取视频，不重复打包OpenCV及其编码库；桌面依赖保持独立。

ARG PYTHON_IMAGE=python:3.12.12-slim-trixie
FROM ${PYTHON_IMAGE} AS media-builder

# Build only software media support. Keep all built-in decoders, demuxers and
# filters, but do not pull the distro's GUI/device/GPU dependency graph.
ARG FFMPEG_VERSION=7.1.5
ARG FFMPEG_SHA256=de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f
ARG NOTO_REVISION=f8d157532fbfaeda587e826d4cd5b21a49186f7c
ARG NOTO_SHA256=2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config nasm curl ca-certificates \
    libx264-dev libdav1d-dev libssl-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN curl -fsSL --retry 3 "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o ffmpeg.tar.xz && \
    echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - && \
    tar -xf ffmpeg.tar.xz && cd "ffmpeg-${FFMPEG_VERSION}" && \
    ./configure --prefix=/opt/ffmpeg --enable-shared --disable-static \
      --disable-autodetect --disable-debug --disable-doc --disable-ffplay \
      --disable-avdevice --disable-postproc --disable-hwaccels \
      --enable-gpl --enable-version3 --enable-libx264 --enable-libdav1d --enable-openssl --enable-zlib && \
    make -j"$(nproc)" && make install && \
    rm -rf /opt/ffmpeg/include /opt/ffmpeg/lib/pkgconfig /opt/ffmpeg/share && \
    mkdir -p /opt/ffmpeg/share/licenses && \
    cp COPYING.GPLv3 /opt/ffmpeg/share/licenses/ && \
    printf 'FFmpeg %s source: https://ffmpeg.org/releases/ffmpeg-%s.tar.xz\n' \
      "$FFMPEG_VERSION" "$FFMPEG_VERSION" > /opt/ffmpeg/share/licenses/SOURCE
RUN mkdir -p /opt/fonts && \
    curl -fsSL --retry 3 "https://raw.githubusercontent.com/notofonts/noto-cjk/${NOTO_REVISION}/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf" \
      -o /opt/fonts/NotoSansCJKsc-Regular.otf && \
    echo "${NOTO_SHA256}  /opt/fonts/NotoSansCJKsc-Regular.otf" | sha256sum -c - && \
    curl -fsSL --retry 3 "https://raw.githubusercontent.com/notofonts/noto-cjk/${NOTO_REVISION}/Sans/LICENSE" -o /opt/fonts/LICENSE

FROM ${PYTHON_IMAGE} AS python-builder
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
# NumPy's testing helpers are imported by SciPy's array API compatibility.
RUN pip install --no-cache-dir uv && \
    uv export --frozen --no-dev --no-emit-project --no-emit-package opencv-python-headless -o /tmp/runtime.txt && \
    uv venv /app/.venv && \
    uv pip sync --python /app/.venv/bin/python --no-cache --require-hashes /tmp/runtime.txt && \
    find /app/.venv -type d -name __pycache__ -prune -exec rm -rf {} + && \
    find /app/.venv/lib/python3.12/site-packages/scipy \
         /app/.venv/lib/python3.12/site-packages/sklearn \
         -type d -name tests -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE} AS app-builder
WORKDIR /app
COPY . .
# Keep the offline geocoder data; expand it into the persistent volume on first
# startup. The uncompressed seed never enters a final-image layer.
RUN python -c "import gzip,pathlib; p=pathlib.Path('resources/rg_data/CN.csv'); pathlib.Path(str(p)+'.gz').write_bytes(gzip.compress(p.read_bytes(),compresslevel=9,mtime=0)); p.unlink()"

FROM ${PYTHON_IMAGE} AS runtime

WORKDIR /app

# Shared libraries used by our media build; no compilers, uv or full font suite.
RUN apt-get update && apt-get install -y --no-install-recommends libx264-164 libdav1d7 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=media-builder /opt/ffmpeg /opt/ffmpeg
COPY --from=media-builder /opt/fonts /opt/fonts
COPY --from=python-builder /app/.venv /app/.venv
RUN echo /opt/ffmpeg/lib > /etc/ld.so.conf.d/trailsnap-ffmpeg.conf && ldconfig
ENV TS_VIDEO_FONT=/opt/fonts/NotoSansCJKsc-Regular.otf \
    PYTHONDONTWRITEBYTECODE=1

# 应用代码（resources/ railway/ alembic/ reverse_geocoder/ 等运行时需要的目录都在这里）
COPY --from=app-builder /app /app

EXPOSE 8000
# 核心：将虚拟环境的 bin 目录加入 PATH
ENV PATH="/app/.venv/bin:/opt/ffmpeg/bin:$PATH"
RUN python -c "from scipy.spatial import cKDTree; from sklearn.cluster import DBSCAN; from app.service.daily_frame_render import capabilities; result=capabilities(); assert result['available'], result"
CMD ["python", "start.py"]
