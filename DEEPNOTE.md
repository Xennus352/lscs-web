# Running LBVD on Deepnote (demo only)

Deepnote is a notebook platform, not a web host. It **can** serve this app on
the one port it exposes (8080) while the project's machine is running, but it
is not a production deployment:

| Limitation | Effect |
|---|---|
| Free plan shuts hardware down after **15 min idle** (8 h max continuous) | The site goes offline whenever you're not actively using the project. Terminal processes do not prevent shutdown. |
| Only port **8080** is exposed, on `<uuid>.deepnoteproject.com` | No custom domain, no control over TLS. |
| No MySQL server | You run MariaDB inside the machine or connect an external MySQL. |
| `~/work` persists; everything else resets | apt packages, `/var/lib/mysql`, processes and `/tmp` are gone after a restart. |
| Incoming connections are **public** | Anyone with the URL can reach the app, including the survey data behind login. |

For real use, deploy on a VPS (see `DEPLOY_VPS.md`), or on a container host
(Railway/Render/Fly.io) with a managed MySQL.

## Demo setup

1. **Allow incoming connections** (workspace admin): *Settings & Members →
   Project settings → Allow incoming connections in projects*.
2. **Enable it for this project**: *Settings (top right) → Machine → More
   options (next to Start machine) → Incoming connections*.
3. **Start the machine** and open a terminal.
4. Clone the repo into the persistent `~/work` folder:

   ```bash
   cd ~/work
   git clone https://github.com/Xennus352/lscs-web.git lbvd
   cd lbvd
   ```

5. **Set secrets** in *Environment → Environment variables* (they persist):

   ```
   SESSION_SECRET=<openssl rand -hex 32>
   JWT_SECRET_KEY=<openssl rand -hex 32>
   DEBUG=false
   COOKIE_HTTPS_ONLY=false
   ```

6. **Start it**:

   ```bash
   bash deploy/deepnote/start.sh
   ```

   The script installs MariaDB, creates a venv in `~/work/.lbvd-venv`, keeps
   the database in `~/work/.lbvd-mysql` (so it survives machine restarts),
   imports `deploy/seed.sql` on first run, and serves the app on `0.0.0.0:8080`.

7. Open the URL Deepnote shows for the project (`https://<uuid>.deepnoteproject.com`).

## Auto-start on machine boot (optional)

Rename/create a notebook called exactly **Init** (it gets the lightning icon)
and run:

```python
import os, subprocess
repo = os.path.expanduser("~/work/lbvd")
subprocess.Popen(
    ["bash", os.path.join(repo, "deploy/deepnote/start.sh")],
    cwd=repo,
    start_new_session=True,
)
```

Adjust the folder name to where you cloned the repo. This starts the server
whenever the hardware boots — but the hardware still shuts down after 15
minutes of inactivity, and visiting the URL does **not** start it again. You
have to open the project.

## Data

- Demo/seed data is fine, but it is **not** production data.
- Change the seeded logins immediately (`admin / LBVDdemo#2026`,
  `BagoAdmin / 12345`, `mgmg / 12345678`).
- For real data, point `DATABASE_URL` at a managed MySQL/MariaDB (Aiven,
  Clever Cloud, Railway, etc.) and remove the local MariaDB part of the
  script. That is the only way the data is safe if the machine is destroyed.
- Back up `~/work/.lbvd-mysql` or `mariadb-dump` regularly; Deepnote is not a
  backup service.

## Why not the Dockerfile?

Deepnote custom environments are Docker images used as a *notebook runtime*;
you cannot run `docker-compose` or give the container your own `CMD`. So the
`Dockerfile` / `docker-compose.prod.yml` route applies to a VPS or container
host, not Deepnote.
