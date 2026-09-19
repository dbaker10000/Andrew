#!/usr/bin/env bash
# Run once as root on the target server:
#   curl -fsSL https://raw.githubusercontent.com/dbaker10000/Andrew/main/deploy/install.sh | bash
set -euo pipefail

DOMAIN="andrew.go-baker.com"
REPOSITORY="https://github.com/dbaker10000/Andrew.git"
APP_DIR="/var/www/andrew"
ENV_DIR="/etc/andrew"
APP_USER="andrew"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi
if [[ -e "$APP_DIR" ]]; then
  echo "$APP_DIR already exists. Refusing to overwrite an existing application." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3-venv python3-pip certbot python3-certbot-nginx

id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
git clone --depth 1 "$REPOSITORY" "$APP_DIR"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --no-cache-dir -r "$APP_DIR/requirements.txt"

DB_PASSWORD="$(openssl rand -hex 32)"
ADMIN_PASSWORD="$(openssl rand -base64 18 | tr -d '\n')"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='andrew'" | grep -q 1; then
  sudo -u postgres psql -c "CREATE ROLE andrew LOGIN PASSWORD '$DB_PASSWORD';"
else
  sudo -u postgres psql -c "ALTER ROLE andrew PASSWORD '$DB_PASSWORD';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='andrew'" | grep -q 1; then
  sudo -u postgres createdb --owner=andrew andrew
fi

install -d -m 750 -o "$APP_USER" -g "$APP_USER" "$ENV_DIR"
cat > "$ENV_DIR/andrew.env" <<EOF
SECRET_KEY=$(openssl rand -hex 48)
DATABASE_URL=postgresql+psycopg://andrew:${DB_PASSWORD}@127.0.0.1:5432/andrew
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PASSWORD}
FLASK_ENV=production
EOF
chown "$APP_USER":"$APP_USER" "$ENV_DIR/andrew.env"
chmod 640 "$ENV_DIR/andrew.env"
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

set -a
source "$ENV_DIR/andrew.env"
set +a
cd "$APP_DIR"
"$APP_DIR/.venv/bin/flask" --app 'app:create_app' db upgrade
"$APP_DIR/.venv/bin/flask" --app 'app:create_app' bootstrap-admin

install -m 644 "$APP_DIR/deploy/andrew.service" /etc/systemd/system/andrew.service
install -m 644 "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/andrew.go-baker.com
ln -s /etc/nginx/sites-available/andrew.go-baker.com /etc/nginx/sites-enabled/andrew.go-baker.com
nginx -t
systemctl daemon-reload
systemctl enable --now andrew
systemctl reload nginx
certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect -d "$DOMAIN"

echo
echo "Andrew is live at https://${DOMAIN}"
echo "Initial administrator username: admin"
echo "Initial administrator password: ${ADMIN_PASSWORD}"
echo "Store this password now; it will not be displayed again."
