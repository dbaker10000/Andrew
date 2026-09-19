# Andrew Tasks

Andrew is a focused task-tracking application built with Flask and PostgreSQL. It provides individual task management, authenticated access, and an administrator area for managing users.

## Local setup

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
.venv/bin/flask --app 'app:create_app' db upgrade
.venv/bin/flask --app 'app:create_app' bootstrap-admin
.venv/bin/flask --app 'app:create_app' run --debug
```

Visit `http://127.0.0.1:5000`. Set a strong `SECRET_KEY`, PostgreSQL password, and initial administrator password in `.env`; it is deliberately excluded from Git.

## Server deployment

The intended conventional deployment is Gunicorn behind the server's existing Nginx configuration, with PostgreSQL running on the host. The supplied server will be inspected before any configuration is changed, to preserve its existing services. The production environment requires:

- `DATABASE_URL` pointing to the host PostgreSQL database
- `SECRET_KEY` set to a unique, long random value
- `FLASK_ENV=production`
- `ADMIN_USERNAME` and `ADMIN_PASSWORD` for the one-time initial administrator bootstrap

Run `flask --app 'app:create_app' db upgrade` and the initial-admin command only once after provisioning the database. Use the included systemd and Nginx configuration once they are tailored to the server's existing layout.

## Security notes

Passwords are stored using Werkzeug password hashes; every state-changing form is protected with CSRF tokens. Sessions use secure, HTTP-only cookies in production. The admin view prevents an administrator from revoking their own access or deleting another administrator.
