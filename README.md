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
