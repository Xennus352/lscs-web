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

For the three-server deployment (web / API / database on separate VMs), see
[`DEPLOY_3VM.md`](DEPLOY_3VM.md).

`/docs`, `/redoc` and `/openapi.json` return 404 by design. The Flutter LBVD adapter
checks authenticated `/api/locations` and discovers the submission contract from
the server's own HTML forms. A 404 from the documentation URL alone does not mean
the backend is offline.

## Records Excel export

On `/admin/records`, apply the filters and click **Excel ထုတ်ယူရန်**. The
export includes all matching rows across all pages and respects the signed-in
user's location permissions. `openpyxl` fills the 255-column sample layout in
`app/excel_templates/records.xlsx`, preserving its Burmese headers and formatting.
Multiple breeds use additional rows; household breeding counts appear once.

The **Animal details** sheet contains every source animal record with lookup
names and IDs, including categories absent from the sample. Large and small
animals outside its named categories use the sample's **Other** columns.

Run export tests with `python -m unittest discover -s tests -v`.

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



===========================read me KNO===================
=========================================================
# LBVD Project – Docker Local Run Guide

**Project:** `lscs-web`  
**Technology:** FastAPI + MySQL 8.0 + Redis 7 + Docker Compose  
**Local URL:** http://localhost:5000

## Step 1. Docker Desktop ဖွင့်ပါ

Windows မှာ Docker Desktop ကို ဖွင့်ပါ။

Docker Engine Running ဖြစ်ကြောင်း စစ်ဆေးပါ။

```powershell
docker version
docker compose version
```

## Step 2. Project Folder ကို ဝင်ပါ

PowerShell ဖွင့်ပြီး—

```powershell
cd C:\Users\khinn\LBVDProject\lscs-web
```

## Step 3. Environment File ရှိကြောင်း စစ်ပါ

```powershell
Test-Path .env.docker.local
```

`True` ဖြစ်ရပါမယ်။

**သတိ:** `.env.docker.local` ထဲက Password နဲ့ Secret တွေကို မဖျက်ပါနှင့်။ GitHub ပေါ်လည်း မတင်ပါနှင့်။

## Step 4. Docker Containers များ စတင်ပါ

ပုံမှန်နေ့စဉ် အသုံးပြုတဲ့အခါ ဒီ Command တစ်ခုတည်းနဲ့ စတင်နိုင်ပါတယ်။

```powershell
docker compose --env-file .env.docker.local -f docker-compose.local.yml up -d
```

ဒီ Command က MySQL, Redis နဲ့ FastAPI ကို စတင်ပေးပါမယ်။

## Step 5. Container Status စစ်ပါ

```powershell
docker compose --env-file .env.docker.local -f docker-compose.local.yml ps
```

မျှော်မှန်းထားတဲ့ Status—

- `lbvd-local-app` – Up
- `lbvd-local-mysql` – Up (healthy)
- `lbvd-local-redis` – Up (healthy)

## Step 6. Application Logs စစ်ပါ

```powershell
docker compose --env-file .env.docker.local -f docker-compose.local.yml logs --tail=50 app
```

အောက်ပါစာသားတွေ တွေ့ရရင် ကောင်းပါတယ်။

```text
Database indexes ensured.
Redis connected successfully
Application startup complete.
Uvicorn running on http://0.0.0.0:5000
```

## Step 7. Browser မှာ ဖွင့်ပါ

http://localhost:5000

သို့မဟုတ်

http://127.0.0.1:5000

## Step 8. Redis စစ်ဆေးရန် (Optional)

```powershell
docker exec lbvd-local-redis redis-cli ping
```

မျှော်မှန်းထားသော Result—

```text
PONG
```

## Step 9. MySQL စစ်ဆေးရန် (Optional)

```powershell
docker exec -it lbvd-local-mysql mysql -uroot -p -D lbvd
```

Password ရိုက်ထည့်ပြီး—

```sql
SHOW TABLES;
SELECT COUNT(*) FROM personcv;
```

ထွက်ရန်—

```sql
exit;
```

## Step 10. အသုံးပြုပြီး ရပ်နားရန်

Container တွေကို ရပ်ထားချင်ရင်—

```powershell
docker compose --env-file .env.docker.local -f docker-compose.local.yml stop
```

နောက်တစ်ခါ ပြန်စချင်ရင်—

```powershell
docker compose --env-file .env.docker.local -f docker-compose.local.yml start
```

---

## Important Notes

1. နေ့စဉ် Run ရုံသာဆိုရင် `up -d` ကို သုံးပါ။
2. Python Code ပြင်ပြီးရင် App ကို ပြန် Build လုပ်ပါ။
3. `docker compose down -v` ကို မသုံးပါနှင့်။ Database Volume ပျက်သွားနိုင်ပါတယ်။
4. MySQL Database ကို `lbvd_local_db_data` Volume မှာ သိမ်းထားပါတယ်။
5. Redis Data ကို `lbvd_local_redis_data` Volume မှာ သိမ်းထားပါတယ်။
6. Docker Container ရပ်သွားခြင်းနဲ့ Database Data ပျက်သွားခြင်းဟာ မတူပါ။

**နေ့စဉ်အသုံးပြုရန် အဓိက Command**

```powershell
cd C:\Users\khinn\LBVDProject\lscs-web

docker compose --env-file .env.docker.local -f docker-compose.local.yml up -d

docker compose --env-file .env.docker.local -f docker-compose.local.yml ps
```
