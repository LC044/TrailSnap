#!/bin/sh
# Inject RP_BASE_PATH into the prebuilt SPA and generate the matching nginx
# rewrite. docker-entrypoint.d scripts run before nginx starts, so a single
# prebuilt image can be deployed at "/" or "/issues" without rebuilding.
set -eu

html=/usr/share/nginx/html/index.html
# Use .inc: nginx.conf auto-includes conf.d/*.conf at http level, where
# rewrite/location are illegal. This file is only read inside the server block.
conf=/etc/nginx/conf.d/rp-base-path.inc

raw=$(printf '%s' "${RP_BASE_PATH:-}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
prefix=$(printf '%s' "$raw" | sed -e 's|^/*||' -e 's|/*$||')
if [ -n "$prefix" ]; then
  prefix="/$prefix"
fi

# Only unreserved path characters are safe inside an nginx regex and <base>.
if [ -n "$prefix" ]; then
  case "$prefix" in
    *//*)
      echo "RP_BASE_PATH must not contain empty segments: $prefix" >&2
      exit 1
      ;;
  esac
  old_ifs=$IFS
  IFS='/'
  for segment in $prefix; do
    [ -z "$segment" ] && continue
    case "$segment" in
      .|..|*[!A-Za-z0-9._~-]*)
        echo "RP_BASE_PATH contains an unsafe segment: $segment" >&2
        exit 1
        ;;
    esac
  done
  IFS=$old_ifs
fi

# Rewrite the <base> href in place. Matching the href value (not just the
# placeholder) keeps this idempotent when a container is restarted.
if [ -f "$html" ]; then
  sed -i -E "s|(<base[^>]*href=\")[^\"]*(\")|\1${prefix}/\2|" "$html"
fi

if [ -z "$prefix" ]; then
  cat > "$conf" <<'EOF'
# RP_BASE_PATH is empty: the service is served from the site root.
EOF
else
  # Escape dots so "/v1.2" is matched literally by the nginx regex.
  escaped=$(printf '%s' "$prefix" | sed 's|\.|\\.|g')
  {
    printf '# Generated from RP_BASE_PATH=%s by 40-rp-base-path.sh\n' "$prefix"
    printf '# Accepts both a proxy that strips the prefix and one that forwards\n'
    printf '# the full prefixed path to this container.\n'
    printf 'rewrite ^%s(/.*)$ $1 last;\n' "$escaped"
    printf 'location = %s { return 301 %s/; }\n' "$prefix" "$prefix"
  } > "$conf"
fi
