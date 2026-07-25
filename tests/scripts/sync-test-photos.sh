#!/usr/bin/env bash
#
# 拉取 TrailSnap 测试照片夹具（独立 LFS 仓库）。
# 等价于 Windows 版的 tests/scripts/sync-test-photos.ps1。
#
# 用法：./tests/scripts/sync-test-photos.sh

set -euo pipefail

REPO_URL="${TS_TEST_PHOTOS_REPO:-https://github.com/LC044/trailsnap-test-photos.git}"
TARGET_DIR="${1:-tests/fixtures/e2e-photos}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
TARGET_ABS="$(realpath -m "$REPO_ROOT/$TARGET_DIR")"

echo "Repo:   $REPO_URL"
echo "Target: $TARGET_ABS"

# 1) 前置检查
command -v git >/dev/null || { echo "git 未安装"; exit 1; }
command -v git-lfs >/dev/null || {
  echo "git-lfs 未安装。请到 https://git-lfs.github.com 安装后再运行。"
  exit 1
}

mkdir -p "$TARGET_ABS"

# 2) clone 或 pull
if [ -d "$TARGET_ABS/.git" ]; then
  echo "Pulling latest..."
  git -C "$TARGET_ABS" fetch --prune
  git -C "$TARGET_ABS" pull --rebase --autostash
elif [ -z "$(ls -A "$TARGET_ABS" 2>/dev/null | grep -v '^\.gitkeep$')" ]; then
  echo "Cloning (with LFS)..."
  git clone "$REPO_URL" "$TARGET_ABS"
else
  echo "目标目录 $TARGET_ABS 非空且不是 git repo，无法处理。请先手动清空。" >&2
  exit 1
fi

# 3) LFS pull
echo "Pulling LFS objects..."
git -C "$TARGET_ABS" lfs pull

# 4) 校验结构
for d in fixtures/smoke fixtures/p0; do
  if [ ! -d "$TARGET_ABS/$d" ]; then
    echo "警告：缺少目录 $TARGET_ABS/$d（远端 fixture 仓库结构不完整）" >&2
  fi
done

echo "Done. fixtures 已就绪。"

