#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
集中管理运行时可写数据路径。

TrailSnap 的可写数据统一放在 ``DATA_DIR`` 下：
  - Docker：``/app/data``（docker-compose 里 ``./data:/app/data`` 挂载为持久卷）
  - 本地开发：``package/server/data``（已被 .gitignore 忽略）

路径锚定在 SERVER_ROOT（本文件所在位置向上三层），不依赖当前工作目录，
因此无论从哪个 CWD 启动（``python start.py`` / ``uvicorn main:app`` / alembic 子进程）
都能解析到同一目录。

离线反向地理编码数据（rg_data）分为两部分：
  - ``RG_SEED_DIR``：镜像内置的只读种子（``resources/rg_data``），含 countries.json
    与默认 CN.csv，由 Dockerfile 的 ``COPY . .`` 打进镜像。
  - ``RG_DATA_DIR``：用户下载/上传的城市 CSV，位于 DATA_DIR 下，持久化。
首次启动时 ``ensure_rg_seed()`` 会把默认 CN.csv 从种子目录拷进数据目录，
保证开箱即用中国反向编码；之后该目录归用户所有（删除不再自动恢复）。
"""
import os
import shutil
import logging

logger = logging.getLogger(__name__)

# <server>/  —— Docker 里为 /app，本地开发为 package/server
SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 统一的可写数据目录（Docker 挂载卷）
DATA_DIR = os.path.join(SERVER_ROOT, 'data')

# 反向地理编码的可写数据目录：用户下载/上传的 CSV，持久化
RG_DATA_DIR = os.path.join(DATA_DIR, 'rg_data')

# 反向地理编码的只读种子目录：镜像内置，含 countries.json 与默认 CN.csv
RG_SEED_DIR = os.path.join(SERVER_ROOT, 'resources', 'rg_data')

# 国家下拉框元数据：只读，始终从镜像内置种子读取
COUNTRIES_JSON_FILE = os.path.join(RG_SEED_DIR, 'countries.json')

# 首次播种完成哨兵。带版本号，将来若要调整种子集合，把版本号 +1 即可重新播种缺失项。
_SEED_SENTINEL = os.path.join(RG_DATA_DIR, '.seeded.v1')


def ensure_rg_seed() -> None:
    """确保可写的反向地理编码数据目录存在，并在首次运行时播种默认 CN.csv。

    首次启动（哨兵不存在）时，将镜像内置的 ``CN.csv`` 从 ``RG_SEED_DIR`` 拷进
    ``RG_DATA_DIR``，使开箱即用的中国离线反向编码无需用户手动下载。
    哨兵使该行为具有粘性：用户之后删除的文件不会在重启时被自动恢复。

    幂等且无副作用依赖，可从任意进程入口（API / worker / start.py）安全调用。
    """
    os.makedirs(RG_DATA_DIR, exist_ok=True)
    if os.path.exists(_SEED_SENTINEL):
        return

    seed_cn = os.path.join(RG_SEED_DIR, 'CN.csv')
    if os.path.exists(seed_cn):
        target_cn = os.path.join(RG_DATA_DIR, 'CN.csv')
        if not os.path.exists(target_cn):
            tmp_cn = target_cn + '.tmp'
            try:
                shutil.copy2(seed_cn, tmp_cn)
                os.replace(tmp_cn, target_cn)  # 同文件系统下原子替换
                logger.info("Seeded default reverse-geocoder data (CN.csv) into %s", RG_DATA_DIR)
            except OSError as e:
                logger.warning("Failed to seed CN.csv into %s: %s", RG_DATA_DIR, e)
                if os.path.exists(tmp_cn):
                    try:
                        os.remove(tmp_cn)
                    except OSError:
                        pass
    else:
        logger.warning("Seed CN.csv not found at %s; skipping seed", seed_cn)

    try:
        # 标记首次播种完成（粘性）。
        with open(_SEED_SENTINEL, 'w'):
            pass
    except OSError as e:
        logger.warning("Failed to write seed sentinel at %s: %s", _SEED_SENTINEL, e)
