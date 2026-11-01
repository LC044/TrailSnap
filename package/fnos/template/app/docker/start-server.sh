#!/bin/sh
set -eu
set -a
. /fnos-runtime/server.env
set +a
exec python start.py
