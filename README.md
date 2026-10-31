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

## Container deployment (all-in-one demo)

The `Dockerfile` can run the web app and a MariaDB database in one container:

- `DATABASE_URL` **unset** → an embedded MariaDB starts and is seeded once from
  `deploy/seed.sql`.
- `DATABASE_URL` **set** → the embedded database is skipped and that external
  database is used instead (this is how `docker-compose.yml` runs it).

Demo login: `admin` / `LBVDdemo#2026` — change it after first login.

`deploy/seed.sql` holds the schema, administrative reference data and synthetic
enumerator records only; it contains no real survey rows, names or phone
numbers. Embedded data is lost on every redeploy/restart, so use the external
database mode for real survey data.
