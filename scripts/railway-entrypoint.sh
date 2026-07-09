#!/bin/sh
set -eu

mkdir -p /gws-config

if [ -n "${GWS_CREDENTIALS:-}" ]; then
  printf '%s' "$GWS_CREDENTIALS" > /gws-config/credentials.json
fi

if [ -n "${GWS_CLIENT_SECRET:-}" ]; then
  printf '%s' "$GWS_CLIENT_SECRET" > /gws-config/client_secret.json
fi

exec python -m bot.main
