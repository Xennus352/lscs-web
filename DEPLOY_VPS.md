# Deploying LBVD on your own VPS

This is the production path: Docker Compose runs MariaDB + the FastAPI app +
Caddy (automatic HTTPS). The root `docker-compose.yml` is a **development**
file (DEBUG on, empty DB password, port 3306 published, source bind-mount) —
do not use it on the VPS.

Tested layout here: one VPS, one domain, everything in Docker.

## 1. Requirements

- Ubuntu 22.04/24.04 (or similar), root/sudo access
- 2 GB RAM recommended (1 GB works with a 2 GB swap file; the image build is
  the heaviest step)
- A domain name with an `A` (and optionally `AAAA`) record pointing at the VPS
- Ports 22, 80 and 443 reachable; 80/443 are needed for the TLS certificate

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out/in to apply
docker compose version
```

## 3. Get the code onto the VPS

Either clone:

```bash
git clone https://github.com/Xennus352/lscs-web.git lbvd
cd lbvd
```

or copy this working tree without the local junk:

```bash
rsync -av --exclude .git --exclude .venv --exclude __pycache__ \
  ./ user@your-vps:/srv/lbvd/
```

## 4. Configure secrets

```bash
cp .env.prod.example .env.prod
sed -i "s/^SESSION_SECRET=.*/SESSION_SECRET=$(openssl rand -hex 32)/" .env.prod
sed -i "s/^JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$(openssl rand -hex 32)/" .env.prod
sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=$(openssl rand -hex 24)/" .env.prod
sed -i "s/^DB_ROOT_PASSWORD=.*/DB_ROOT_PASSWORD=$(openssl rand -hex 24)/" .env.prod
nano .env.prod   # set DOMAIN=lbvd.yourdomain.com and check everything
chmod 600 .env.prod
```

`JWT_SECRET_KEY` matters: without it the app falls back to a secret that is
published in the source code.

## 5. Open the firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Do **not** open 3306 or 5000. Compose only publishes Caddy; MariaDB and the
app are on the private Docker network.

## 6. Start it

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.prod.yml ps
docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f app
```

What happens on first start:

1. MariaDB initialises its volume and imports `deploy/seed.sql` (schema,
   reference data, demo accounts). This import runs **only when the database
   volume is empty**.
2. The app waits for the DB healthcheck, then starts on port 5000.
3. Caddy requests a certificate for `DOMAIN` and proxies HTTPS to the app.

Verify:

```bash
curl -I https://lbvd.yourdomain.com/
curl https://lbvd.yourdomain.com/api/check-update
```

The app is up when `/` returns the login page (200).

## 7. First login and immediate hardening

Seeded accounts (from `deploy/seed.sql`) — change these right away:

| Login | Password | Role |
|---|---|---|
| `admin` | `LBVDdemo#2026` | admin |
| `BagoAdmin` | `12345` | superadmin |
| `mgmg` | `12345678` | enumerator (demo) |

Use the in-app user management (`/system/users`) to set new passwords and
disable/remove demo accounts you do not need. `app/config.py` also defines
`DEFAULT_PASSWORD = "12345678"` for created users — change it before creating
real accounts if that flow is used.

## 8. Backups

```bash
./deploy/backup.sh          # -> backups/lbvd-YYYYMMDDTHHMMSSZ.sql.gz
```

Schedule it nightly (root crontab):

```
15 2 * * * /srv/lbvd/deploy/backup.sh >> /var/log/lbvd-backup.log 2>&1
```

Copy `backups/` off the VPS as well (a backup on the same disk is not a
backup). To restore: `gunzip -c file.sql.gz | docker compose ... exec -T db mariadb -u root -p"$MARIADB_ROOT_PASSWORD" lbvd`.

## 9. Updating the app

```bash
git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

The database volume is untouched, so data survives. The app applies small
schema fixes (e.g. `personcv.status`) at startup.

## 10. APK distribution

`/api/check-update`, `/api/download-latest` and `/apks/<file>.apk` are public
so the mobile app can update before login. Put files named with a version
(`lbvd-1.2.3.apk`) into the `apk_data` volume:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  cp lbvd-1.2.3.apk app:/app/assets/apk/
```

## 11. Point the Flutter app at the VPS

Rebuild with the HTTPS origin:

```bash
flutter build apk --dart-define=API_BASE_URL=https://lbvd.yourdomain.com
```

Keep HTTPS: production runs with `COOKIE_HTTPS_ONLY=true`, and Android blocks
cleartext HTTP by default anyway.

## Troubleshooting

- **Login page loads but login bounces back to login** — you are probably on
  `http://` or the IP. `COOKIE_HTTPS_ONLY=true` requires HTTPS. Use the domain.
- **App container restarts with `personcv` errors** — the DB was not seeded.
  It is only imported into an empty volume. Either start from an empty
  `db_data` volume or import manually:
  ```bash
  docker compose --env-file .env.prod -f docker-compose.prod.yml \
    exec -T db sh -c 'mariadb -u root -p"$MARIADB_ROOT_PASSWORD" lbvd' \
    < deploy/seed.sql
  ```
- **Certificate not issued** — DNS is not pointing at the VPS yet, or ports
  80/443 are blocked. Check `docker compose ... logs caddy`.
- **Build killed on a 1 GB VPS** — add swap:
  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```
- **Need the real survey data** — `deploy/seed.sql` is synthetic/demo data
  only. Import your own dump after the first start instead of relying on the
  seed.
