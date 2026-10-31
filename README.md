# Local backend for Flutter

The Linux Flutter app defaults to `http://localhost:5000`. Both backend launch
methods use port 5000 unless `PORT` is set:

```bash
cd /home/kazue/Projects/Personal/lscs/LBVDProject
bash run.sh
# Alternatively: python3 -m app.main
```

MySQL must be running with the imported LBVD schema. The existing database
container can be started with `docker start lbvd-mysql`. For a first-time setup,
see `../lbvd-db/up.sh`; keep existing database volumes intact.

In another terminal:

```bash
cd /home/kazue/Projects/Personal/lscs/flutter_app
flutter run -d linux --dart-define=API_BASE_URL=http://localhost:5000
```

Restart Flutter after changing `API_BASE_URL`; hot reload does not change a
compile-time define. Use the same origin to retain access to that origin's saved
drafts and pending uploads.

`/docs`, `/redoc` and `/openapi.json` return 404 by design. The Flutter LBVD adapter
checks authenticated `/api/locations` and discovers the submission contract from
the server's own HTML forms. A 404 from the documentation URL alone does not mean
the backend is offline.

## APK updates

The mobile app can check for a newer APK without logging in:

- `GET /api/check-update?current_version=1.0.0` — returns the latest version,
  size, SHA-256 and a `download_url`. It returns `update_available: false`
  when the installed version is current, and `304` when the client's `ETag`
  still matches.
- `GET /api/download-latest` — `302` redirect to the newest APK.
- `GET /apks/<file>.apk` — serves the APK files themselves.

Drop APKs into `assets/apk/` (or set `APK_DIR` to another folder). Filenames
must contain a version, for example `lbvd-1.2.3.apk`; the highest version wins.
These routes are intentionally public so the app can update before login.

## Deploy FastAPI on Render

The `Dockerfile` runs only FastAPI with Uvicorn. The database runs separately.

1. Create a Render **Web Service** from this repository and select **Docker**
   as the runtime. Use the repository root as the build context and `./Dockerfile`
   as the Dockerfile path. Leave the Docker command unset to use the image default.
2. Set these environment variables in Render:

   ```text
   DATABASE_URL=mysql+pymysql://USER:PASSWORD@DB_HOST:3306/lbvd?charset=utf8mb4
   SESSION_SECRET=<a long random secret>
   JWT_SECRET_KEY=<a different long random secret>
   COOKIE_HTTPS_ONLY=true
   DEBUG=false
   ```

   URL-encode special characters in database credentials. The database must be
   reachable from Render and have the LBVD schema imported before startup
   (including `personcv`). The container does not start or seed a database.
   Provider URLs beginning with `mysql://` or `mariadb://` automatically use
   the installed PyMySQL driver; explicitly selected drivers are preserved.
   Aiven's `ssl-mode=REQUIRED` parameter is translated to PyMySQL TLS settings.
   This encrypts the connection; for certificate verification, also configure
   `ssl_ca` with the provider CA file path and `ssl_check_hostname=true`.
3. Deploy. Uvicorn binds to `0.0.0.0` and Render's `PORT` environment variable.
   Locally, the default port remains `5000` for Docker Compose.

The image includes the templates and static assets used by the FastAPI routes.
For APK uploads that must survive redeploys, attach a persistent disk and set
`APK_DIR` to a directory on that disk.
