#!/bin/bash
set -euo pipefail
APP='@@APP@@'
IMAGE='@@IMAGE@@'
fail() {
  printf '%s\n' "$1" >&2
  if [ -n "${TRIM_TEMP_LOGFILE:-}" ]; then printf '%s\n' "$1" > "$TRIM_TEMP_LOGFILE"; fi
  exit 1
}
validate_port() {
  [[ "$1" =~ ^[0-9]+$ ]] && [ "${#1}" -le 5 ] && [ "$1" -ge 1024 ] && [ "$1" -le 65535 ] || fail '端口须为 1024–65535 之间的整数。'
}
validate_path() {
  local value="$1" normalized
  case "$value" in
    *$'\n'*|*$'\r'*|*$'\t'*|*':'*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*|*','*) fail '目录路径包含不支持的特殊字符。' ;;
  esac
  normalized=$(realpath -m -- "$value")
  [[ "$normalized" =~ ^/vol[0-9]+/.+ ]] || fail '目录必须位于 NAS 存储空间内，不能选择系统目录或整个存储卷。'
  [ "$normalized" = "$value" ] || fail '请填写规范的绝对路径，不使用软链接、.、.. 或末尾斜杠。'
}
check_port_free() {
  if command -v ss >/dev/null && [ -n "$(ss -H -ltn "sport = :$1" 2>/dev/null)" ]; then fail '选择的端口已被占用，请换一个端口。'; fi
}
case "${1:-}" in
 install)
  validate_port "${wizard_port:-3180}"
  check_port_free "${wizard_port:-3180}"
  [ -n "${wizard_data_dir:-}" ] || fail '请选择用户数据目录，用于保存上传的照片。'
  validate_path "$wizard_data_dir"
  [[ ! "$wizard_data_dir" =~ ^/vol[0-9]+/@app ]] || fail '请选择个人文件或共享文件中的独立目录。'
  if [ -n "${wizard_photo_dir:-}" ]; then validate_path "$wizard_photo_dir"; fi
  ;;
 configure)
  [ -r "$TRIM_PKGVAR/data-path" ] || fail '应用还未初始化，请先启动应用。'
  IFS= read -r data_path < "$TRIM_PKGVAR/data-path"
  validate_path "$data_path"
  mounts=()
  if [ -n "${wizard_add_photo_dir:-}" ]; then
    validate_path "$wizard_add_photo_dir"
    mounts+=(--mount "type=bind,source=$wizard_add_photo_dir,target=/candidate,readonly")
  fi
  docker run --rm --network none \
    --mount "type=bind,source=$TRIM_APPDEST,target=/package" \
    --mount "type=bind,source=$TRIM_PKGVAR,target=/meta" \
    --mount "type=bind,source=$data_path,target=/state" \
    "${mounts[@]}" \
    --env "TS_ADD_PHOTO=${wizard_add_photo_dir:-}" \
    --entrypoint python "$IMAGE" /package/runtime.py configure || fail '保存配置失败，请检查目录或端口，并查看应用日志。'
  docker compose -p "$APP-fnos" -f "$TRIM_APPDEST/docker/docker-compose.yaml" up -d || fail '配置文件已保存，但服务更新失败，请检查日志后重新启动应用。'
  ;;
 *) fail '未知操作。' ;;
esac
