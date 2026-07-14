#!/bin/sh
set -eu

SOURCE_APP="${CIOS_SOURCE_APP_DIR:-/root/.hermes/apps/cios}"
SOURCE_PUB="${CIOS_SOURCE_PUBLIC_DIR:-/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public}"
APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
ENV_FILE="${CIOS_ENV_FILE:-/root/.hermes/cios-env}"
HOST_ENV_FILE="${CIOS_HOST_ENV_FILE:-/etc/cios-env}"
ROOT_WRAPPER="${CIOS_ROOT_WRAPPER:-/root/.hermes/scripts/cios-daily.sh}"
APP_USER="${CIOS_APP_USER:-cios}"
APP_GROUP="${CIOS_APP_GROUP:-cios}"
HERMES_GROUP="${CIOS_HERMES_GROUP:-hermes}"
SHIM_USER="${CIOS_SHIM_USER:-cios-shim}"

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
if id "$SHIM_USER" >/dev/null 2>&1; then
  usermod -aG "$HERMES_GROUP" "$SHIM_USER"
fi

install -d -o root -g root -m 0755 /opt/cios
mkdir -p "$APP" "$PUB"
if ! mountpoint -q "$APP"; then
  mount --bind "$SOURCE_APP" "$APP"
fi
if ! mountpoint -q "$PUB"; then
  mount --bind "$SOURCE_PUB" "$PUB"
fi

app_fstab="$SOURCE_APP $APP none bind 0 0"
pub_fstab="$SOURCE_PUB $PUB none bind 0 0"
grep -Fqx "$app_fstab" /etc/fstab || printf '%s\n' "$app_fstab" >> /etc/fstab
grep -Fqx "$pub_fstab" /etc/fstab || printf '%s\n' "$pub_fstab" >> /etc/fstab

# CI-OS is hosted under the Hermes home as an extension. The app user needs
# execute-only traversal through the parent directories, not read/list access.
# Prefer ACLs so Hermes can keep its home directory mode at 700.
if command -v setfacl >/dev/null 2>&1; then
  setfacl -m "u:$APP_USER:--x,m:--x" /root/.hermes /root/.hermes/apps
  if id "$SHIM_USER" >/dev/null 2>&1; then
    setfacl -m "u:$SHIM_USER:--x,m:--x" /root/.hermes /root/.hermes/apps
  fi
else
  chmod 711 /root/.hermes /root/.hermes/apps
fi

mkdir -p "$SOURCE_APP/run-queue/.state" "$SOURCE_APP/out" "$SOURCE_APP/tmp" "$SOURCE_PUB/data" "$SOURCE_PUB/v2/data"
chown -R "$APP_USER:$HERMES_GROUP" "$SOURCE_APP" "$SOURCE_PUB"
chown "$APP_USER:$APP_USER" "$APP"
chmod 755 "$APP"
for code_dir in "$APP/deploy" "$APP/scripts" "$APP/src" "$APP/.venv"; do
  if [ -d "$code_dir" ]; then
    chown -R "$APP_USER:$APP_USER" "$code_dir"
    chmod -R g-w,o-w "$code_dir"
    find "$code_dir" -type d -exec chmod u+rwx,go+rx {} +
  fi
done
chmod 2775 "$APP/out" "$APP/tmp" "$PUB" "$PUB/data" "$PUB/v2" "$PUB/v2/data"
chmod 3770 "$APP/run-queue"
chown "$APP_USER:$APP_USER" "$APP/run-queue/.state"
chmod 700 "$APP/run-queue/.state"

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
  chown "$APP_USER:$APP_USER" "$APP/deploy/cios-daily.sh"
  chmod 755 "$APP/deploy/cios-daily.sh"
fi
if [ -f "$APP/deploy/cios-daily-app.sh" ]; then
  chown "$APP_USER:$APP_USER" "$APP/deploy/cios-daily-app.sh"
  chmod 700 "$APP/deploy/cios-daily-app.sh"
fi
if [ -f "$ROOT_WRAPPER" ]; then
  chown "$APP_USER:$HERMES_GROUP" "$ROOT_WRAPPER"
  chmod 750 "$ROOT_WRAPPER"
fi
if [ -f "$APP/deploy/cios-host-runner.sh" ]; then
  chown "$APP_USER:$APP_USER" "$APP/deploy/cios-host-runner.sh"
  chmod 700 "$APP/deploy/cios-host-runner.sh"
fi
if [ -f "$APP/deploy/cios-run-finalize.sh" ]; then
  chown "$APP_USER:$APP_USER" "$APP/deploy/cios-run-finalize.sh"
  chmod 700 "$APP/deploy/cios-run-finalize.sh"
fi
if [ -f "$APP/scripts/cios_run_queue.py" ]; then
  chown "$APP_USER:$APP_USER" "$APP/scripts/cios_run_queue.py"
  chmod 755 "$APP/scripts/cios_run_queue.py"
fi
if [ -f "$ENV_FILE" ]; then
  chown "$APP_USER:$HERMES_GROUP" "$ENV_FILE"
  chmod 640 "$ENV_FILE"
  if [ "$HOST_ENV_FILE" != "$ENV_FILE" ]; then
    install -o "$APP_USER" -g "$HERMES_GROUP" -m 0640 "$ENV_FILE" "$HOST_ENV_FILE"
  fi
fi

echo "CI-OS host ownership ready: app=$APP user=$APP_USER group=$HERMES_GROUP"
