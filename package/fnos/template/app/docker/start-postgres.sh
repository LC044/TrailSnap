#!/bin/sh
set -eu
set -a
. /fnos-runtime/postgres-shell.env
set +a
exec /usr/local/bin/docker-entrypoint.sh postgres
