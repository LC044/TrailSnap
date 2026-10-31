#!/bin/bash
set -euo pipefail
umask 077
APP='@@APP@@'
IMAGE='@@IMAGE@@'
error() {
  printf '%s\n' "$1" >&2
  if [ -n "${TRIM_TEMP_LOGFILE:-}" ]; then printf '%s\n' "$1" > "$TRIM_TEMP_LOGFILE"; fi
  exit 1
}
[ -r "$TRIM_PKGVAR/installation.json" ] || error '缺少安装记录，已停止升级。'
grep -Fq '"layout": "catalog-v1"' "$TRIM_PKGVAR/installation.json" || error '旧版图库路径需迁移，请先备份并保留旧版应用。'
IFS= read -r state_path < "$TRIM_PKGVAR/data-path"
started_database=false
restore_state() {
  if [ "$started_database" = true ]; then docker stop --time 30 "$APP-fnos-postgres" >/dev/null 2>&1 || true; fi
}
trap restore_state EXIT
db_state=$(docker inspect --format '{{.State.Status}}' "$APP-fnos-postgres") || error '找不到原数据库容器。'
if [ "$db_state" != running ]; then
  docker start "$APP-fnos-postgres" >/dev/null || error '无法启动数据库备份。'
  started_database=true
fi
ready=false
for attempt in $(seq 1 30); do
  if docker exec "$APP-fnos-postgres" pg_isready -U trailsnap -d trailsnap >/dev/null 2>&1; then ready=true; break; fi
  sleep 1
done
[ "$ready" = true ] || error '数据库未就绪，已停止升级。'
if ! docker exec "$APP-fnos-postgres" pg_dumpall -U trailsnap | docker run --rm -i --network none --user 0:0 \
    --mount "type=bind,source=$state_path,target=/state" \
    --mount "type=bind,source=$TRIM_APPDEST,target=/package,readonly" \
    --entrypoint python "$IMAGE" /package/backup.py; then
  error '升级前备份失败，已停止升级，请检查应用日志。'
fi
