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
    *$'\n'*|*$'\r'*|*$'\t'*|*':'*|*'"'*|*"'"*|*'\'*|*'$'*|*'`'*|*','*|*';'*) fail '目录路径包含不支持的特殊字符。' ;;
  esac
  normalized=$(realpath -m -- "$value")
  [[ "$normalized" =~ ^/vol[0-9]+/.+ ]] || fail '目录必须位于 NAS 存储空间内，不能选择系统目录或整个存储卷。'
  [ "$normalized" = "$value" ] || fail '请填写规范的绝对路径，不使用软链接、.、.. 或末尾斜杠。'
}
check_port_free() {
  if command -v ss >/dev/null && [ -n "$(ss -H -ltn "sport = :$1" 2>/dev/null)" ]; then fail '选择的端口已被占用，请换一个端口。'; fi
}
resolve_directory() {
  local value="$1" folder="$2"
  if [ -z "$value" ] || [ "$value" = "$APP/$folder" ]; then
    printf '%s/@appshare/%s/%s' "$TRIM_APPDEST_VOL" "$APP" "$folder"
  else
    printf '%s' "$value"
  fi
}
case "${1:-}" in
 install)
  validate_port "${wizard_port:-3180}"
  check_port_free "${wizard_port:-3180}"
  data_path=$(resolve_directory "${wizard_data_dir:-}" data)
  validate_path "$data_path"
  if [[ "$data_path" =~ ^/vol[0-9]+/@app ]] && [[ ! "$data_path" =~ ^/vol[0-9]+/@appshare/$APP/data$ ]]; then
    fail '请选择本应用的数据共享目录，或个人文件、共享文件中的独立目录。'
  fi
  validate_path "$(resolve_directory "${wizard_photo_dir:-}" photos)"
  ;;
 prepare)
  # fnOS passes the visible shared-directory names literally. Resolve them
  # before its docker-project starts; custom absolute paths keep interpolation.
  compose_path="$TRIM_APPDEST/docker/docker-compose.yaml"
  content=$(cat "$TRIM_APPDEST/docker/compose-template.json")
  for folder in data photos; do
    if [ "$folder" = data ]; then value="${wizard_data_dir:-}"; field=wizard_data_dir
    else value="${wizard_photo_dir:-}"; field=wizard_photo_dir; fi
    if [ -z "$value" ] || [ "$value" = "$APP/$folder" ]; then
      resolved=$(resolve_directory "$value" "$folder")
      validate_path "$resolved"
      expression='${'"$field"':-${TRIM_APPDEST_VOL}/@appshare/'"$APP/$folder"'}'
      content=${content//"$expression"/"$resolved"}
    fi
  done
  printf '%s\n' "$content" > "$compose_path.tmp"
  chmod 644 "$compose_path.tmp"
  mv -f -- "$compose_path.tmp" "$compose_path"
  ;;
 configure)
  [ -r "$TRIM_PKGVAR/data-path" ] || fail '应用还未初始化，请先启动应用。'
  IFS= read -r data_path < "$TRIM_PKGVAR/data-path"
  validate_path "$data_path"
  mounts=()
  # A native text field accepts a semicolon-separated batch of NAS paths.
  generation=$(sed -n 's/.*"wizard_generation": \([0-9][0-9]*\).*/\1/p' "$TRIM_PKGVAR/installation.json")
  addition_field="wizard_new_photo_${generation:-0}"
  addition="${!addition_field:-}"
  [[ "$addition" != *$'\n'* && "$addition" != *$'\r'* ]] || fail '多个目录请用英文分号分隔，不要换行。'
  IFS=';' read -r -a additions <<< "$addition"
  index=0
  for candidate in "${additions[@]}"; do
    candidate="${candidate#"${candidate%%[![:space:]]*}"}"
    candidate="${candidate%"${candidate##*[![:space:]]}"}"
    [ -n "$candidate" ] || continue
    validate_path "$candidate"
    mounts+=(--mount "type=bind,source=$candidate,target=/candidate/$index,readonly")
    index=$((index + 1))
  done
  native_env=()
  # fnOS provides a complete snapshot when authorizations change. Preserve the
  # distinction between an absent variable and an explicitly empty list.
  if [ "${TRIM_DATA_ACCESSIBLE_PATHS+x}" = x ]; then
    [[ "$TRIM_DATA_ACCESSIBLE_PATHS" != *$'\n'* && "$TRIM_DATA_ACCESSIBLE_PATHS" != *$'\r'* ]] || fail '授权目录列表包含不支持的换行。'
    IFS=':' read -r -a authorized <<< "$TRIM_DATA_ACCESSIBLE_PATHS"
    IFS=':' read -r -a shared <<< "${TRIM_DATA_SHARE_PATHS:-}"
    index=0
    for candidate in "${authorized[@]}"; do
      [ -n "$candidate" ] || continue
      builtin_share=false
      for share in "${shared[@]}"; do
        if [ "$candidate" = "$share" ]; then builtin_share=true; break; fi
      done
      [ "$builtin_share" = false ] || continue
      validate_path "$candidate"
      test -d "$candidate" || fail '授权目录不存在或已离线，请恢复目录后重试。'
      if [ "$(id -u)" = 0 ]; then
        runuser -u "${TRIM_USERNAME:-trailsnap}" -- test -r "$candidate" || fail '应用账号无法读取授权目录。'
        mode=ro
        if runuser -u "${TRIM_USERNAME:-trailsnap}" -- test -w "$candidate"; then mode=rw; fi
      else
        [ -r "$candidate" ] || fail '应用账号无法读取授权目录。'
        mode=ro
        if [ -w "$candidate" ]; then mode=rw; fi
      fi
      mounts+=(--mount "type=bind,source=$candidate,target=/candidate/native-$index,readonly")
      native_env+=(--env "TS_NATIVE_PATH_$index=$candidate" --env "TS_NATIVE_MODE_$index=$mode")
      index=$((index + 1))
    done
    native_env+=(--env "TS_NATIVE_COUNT=$index")
  fi
  modes=()
  while IFS= read -r name; do
    [[ "$name" =~ ^wizard_(library_action|photo_access)_[a-f0-9]{16}(_[0-9]+)?$ ]] && modes+=(--env "$name")
  done < <(compgen -e)
  docker run --rm --network none \
    --mount "type=bind,source=$TRIM_APPDEST,target=/package" \
    --mount "type=bind,source=$TRIM_PKGVAR,target=/meta" \
    --mount "type=bind,source=$data_path,target=/state" \
    --mount "type=bind,source=$(dirname "$0")/../wizard,target=/wizard" \
    "${mounts[@]}" \
    "${modes[@]}" \
    "${native_env[@]}" \
    --env "TS_ADD_PHOTOS=$addition" \
    --env "TS_ADD_MODE=${wizard_add_photo_mode:-ro}" \
    --entrypoint python "$IMAGE" /package/runtime.py configure || fail '保存配置失败，请检查目录权限，并查看应用日志。'
  docker compose -p "$APP-fnos" -f "$TRIM_APPDEST/docker/docker-compose.yaml" up -d || fail '配置文件已保存，但服务更新失败，请检查日志后重新启动应用。'
  ;;
 *) fail '未知操作。' ;;
esac
