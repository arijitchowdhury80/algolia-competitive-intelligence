#!/bin/sh
set -eu

APP="${CIOS_APP_DIR:-/root/.hermes/apps/cios}"
PUB="${CIOS_PUBLIC_DIR:-/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public}"
ENV_FILE="${CIOS_ENV_FILE:-/root/.hermes/cios-env}"
ROOT_WRAPPER="${CIOS_ROOT_WRAPPER:-/root/.hermes/scripts/cios-daily.sh}"
APP_USER="${CIOS_APP_USER:-cios}"
APP_GROUP="${CIOS_APP_GROUP:-cios}"
HERMES_GROUP="${CIOS_HERMES_GROUP:-hermes}"

if [ "$(id -u)" -ne 0 ]; then
  echo "cios-host-permissions.sh must run as root" >&2
  exit 1
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "/var/lib/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
fi

if ! getent group "$HERMES_GROUP" >/dev/null 2>&1; then
  echo "missing required Hermes group: $HERMES_GROUP" >&2
  exit 1
fi

usermod -aG "$HERMES_GROUP" "$APP_USER"

# CI-OS is hosted under the Hermes home as an extension. The app user needs
# execute-only traversal through the parent directories, not read/list access.
chmod 711 /root/.hermes /root/.hermes/apps

mkdir -p "$APP/run-queue" "$APP/out" "$APP/tmp" "$PUB/data" "$PUB/v2/data"
chown -R "$APP_USER:$HERMES_GROUP" "$APP" "$PUB"
chmod 2775 "$APP" "$APP/run-queue" "$APP/out" "$APP/tmp" "$PUB" "$PUB/data" "$PUB/v2" "$PUB/v2/data"

PRODUCT_MARKET_WORKDIR="${CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market}"
mkdir -p "$PRODUCT_MARKET_WORKDIR"
chown -R "$APP_USER:$HERMES_GROUP" "$PRODUCT_MARKET_WORKDIR"
chmod 2775 "$PRODUCT_MARKET_WORKDIR"

LEGACY_PRODUCT_MARKET_TMP="${CIOS_LEGACY_PRODUCT_MARKET_TMP:-/tmp/cios-product-market}"
if [ -e "$LEGACY_PRODUCT_MARKET_TMP" ]; then
  chown -R "$APP_USER:$HERMES_GROUP" "$LEGACY_PRODUCT_MARKET_TMP"
  chmod -R u+rwX,g+rwX,o-rwx "$LEGACY_PRODUCT_MARKET_TMP"
fi

if [ -f "$APP/deploy/cios-daily.sh" ]; then
  chmod 750 "$APP/deploy/cios-daily.sh"
fi
if [ -f "$ROOT_WRAPPER" ]; then
  chown "$APP_USER:$HERMES_GROUP" "$ROOT_WRAPPER"
  chmod 750 "$ROOT_WRAPPER"
fi
if [ -f "$APP/deploy/cios-host-runner.sh" ]; then
  chmod 755 "$APP/deploy/cios-host-runner.sh"
fi
if [ -f "$ENV_FILE" ]; then
  chown "$APP_USER:$HERMES_GROUP" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
fi

echo "CI-OS host ownership ready: app=$APP user=$APP_USER group=$HERMES_GROUP"
