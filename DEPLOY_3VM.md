# LBVD ကို VM ၃ လုံးပေါ်မှာ Deploy လုပ်ခြင်း

ဒီစာရွက်စာတမ်းက အောက်ပါ VM ၃ လုံးအတွက် အဆင်သင့် configuration ဖြစ်ပါတယ်။
VM တစ်လုံးချင်းစီမှာ **32 vCPU / 64 GB RAM / 1 TB SSD** ရှိတယ်လို့ သတ်မှတ်ထားပါတယ်။

| VM | IP | တာဝန် | Port |
|---|---|---|---|
| Web server | `192.168.111.50` | Nginx (reverse proxy + static cache) | 80 (HTTPS အတွက် 443) |
| API server | `192.168.111.200` | FastAPI/Uvicorn နှင့် Redis | 5000 (web server ကသာ ဝင်ခွင့်) |
| DB server | `192.168.111.100` | MariaDB 11 | 3306 (API server ကသာ ဝင်ခွင့်) |

```
Browser / APK
     │  http://192.168.111.50
     ▼
┌─────────────────┐        ┌──────────────────────┐        ┌──────────────────┐
│ Web  .50        │ ─────► │ API  .200            │ ─────► │ DB   .100        │
│ Nginx + cache   │  5000  │ Uvicorn x16 + Redis  │  3306  │ MariaDB 11       │
└─────────────────┘        └──────────────────────┘        └──────────────────┘
```

ဒီ project ရဲ့ code က host name တွေကို hardcode မလုပ်ထားပါဘူး။
`DB_HOST`, `REDIS_URL`, `FORWARDED_ALLOW_IPS` စတဲ့ environment variable တွေနဲ့
ချိတ်ထားတဲ့အတွက် VM ခွဲထားလည်း application code ပြင်ရန် မလိုပါဘူး။

---

## 0. VM အားလုံးမှာ ကြိုတင်လုပ်ရန်

Ubuntu 22.04/24.04 ကို အသုံးပြုပါ။ IP ၃ ခုကို static သတ်မှတ်ပြီး၊ VM တွေက
တစ်ခုနဲ့တစ်ခု ping/SSH ရနိုင်ကြောင်း သေချာပါ။

```bash
sudo apt update
sudo apt install -y git curl ca-certificates ufw chrony
sudo timedatectl set-timezone Asia/Yangon
sudo systemctl enable --now chrony

# Docker + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"     # log out/in ပြန်ဝင်ပါ
docker compose version
```

Code ကို VM တစ်လုံးချင်းစီမှာ clone လုပ်ပါ (web VM မှာ nginx config ပဲလိုပေမယ့်
တူတူ clone လုပ်ထားရင် update လုပ်ရလွယ်ပါတယ်)။

```bash
sudo mkdir -p /srv && sudo chown "$USER":"$USER" /srv
git clone https://github.com/Xennus352/lscs-web.git /srv/lbvd
cd /srv/lbvd
```

> **1 TB disk ကို သီးသန့် mount လုပ်မယ်ဆိုရင်** (VM အသစ်ဖြစ်ပြီး disk ပေါ်မှာ
> data မရှိကြောင်း သေချာပြီးမှသာ လုပ်ပါ) Docker data ကို အဲဒီ disk ပေါ်
> ထားနိုင်ပါတယ်။
>
> ```bash
> sudo mkfs.ext4 /dev/sdb          # device name ကို lsblk နဲ့စစ်ပါ
> sudo mkdir -p /var/lib/docker
> echo '/dev/sdb /var/lib/docker ext4 defaults,noatime 0 2' | sudo tee -a /etc/fstab
> sudo mount -a
> ```
>
> မလုပ်ခင် `/var/lib/docker` ထဲမှာ data ရှိမရှိ စစ်ပါ။ ရှိရင် ဒီအဆင့်ကို မလုပ်ပါနဲ့။

---

## 1. DB server — `192.168.111.100`

```bash
cd /srv/lbvd
cp .env.db.example .env.db
sed -i "s|^DB_PASSWORD=.*|DB_PASSWORD=$(openssl rand -hex 24)|" .env.db
sed -i "s|^DB_ROOT_PASSWORD=.*|DB_ROOT_PASSWORD=$(openssl rand -hex 24)|" .env.db
chmod 600 .env.db
```

နောက် `.env.api` မှာ ထည့်ရမယ့် `DB_PASSWORD` ကို ဒီဖိုင်ထဲက တန်ဖိုးနဲ့ တူအောင်
မှတ်ထားပါ။

Start လုပ်ပါ။

```bash
docker compose --env-file .env.db -f docker-compose.db.yml up -d
docker compose --env-file .env.db -f docker-compose.db.yml ps
docker compose --env-file .env.db -f docker-compose.db.yml logs -f db
```

ပထမဆုံး start မှာ `deploy/seed.sql` (schema + demo data) ကို အလိုအလျောက်
import လုပ်ပါတယ်။ Import က data volume အလွတ်နေချိန်မှာသာ ဖြစ်ပါတယ်။

### ကိုယ်ပိုင် data (real dump) ထည့်မယ်ဆိုရင်

Demo data မလိုဘူးဆိုရင် API ကို မစခင် dump ကို import လုပ်ပါ။

```bash
# DB VM ပေါ်မှာ
gunzip -c /path/to/lbvd-real.sql.gz | \
  docker compose --env-file .env.db -f docker-compose.db.yml exec -T db \
  sh -c 'exec mariadb -u root -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"'
```

Demo data နဲ့ စပြီးသားဆိုရင် ကိုယ့် dump က `DROP TABLE` ပါတဲ့ dump ဖြစ်ရင်
အစားထိုးသွားပါလိမ့်မယ်။ မဟုတ်ရင် ပထမဆုံး `docker compose ... down -v` လုပ်ပြီး
volume အသစ်နဲ့ ပြန်စပါ (data အားလုံး ပျက်မယ် — သေချာစစ်ပါ)။

### DB ကို စစ်ဆေးခြင်း

```bash
# API VM ကနေ
mysql -h 192.168.111.100 -P 3306 -u lbvd -p lbvd -e "SELECT VERSION();"
# သို့မဟုတ်
nc -z -w 5 192.168.111.100 3306 && echo "mysql reachable"
```

### Backup (နေ့စဉ်)

```bash
cd /srv/lbvd
./deploy/three-tier/backup-db.sh
```

Root cron:

```cron
15 2 * * * /srv/lbvd/deploy/three-tier/backup-db.sh >> /var/log/lbvd-backup.log 2>&1
```

`backups/` ကို တစ်ခြား machine/disk ကို ကူးထားပါ။

### DB tuning

`deploy/three-tier/mariadb/99-lbvd.cnf` မှာ 64 GB RAM အတွက်
`innodb_buffer_pool_size = 40G`, `max_connections = 600`, SSD I/O setting တွေ
ထည့်ထားပါတယ်။ 64 GB မပြည့်တဲ့ VM မှာ စမ်းမယ်ဆိုရင် buffer pool ကို
(available RAM ၏ 60–65%) လောက်ထိ လျှော့ပါ။ Config ပြင်ပြီးရင်:

```bash
docker compose --env-file .env.db -f docker-compose.db.yml restart db
```

---

## 2. API server — `192.168.111.200`

```bash
cd /srv/lbvd
cp .env.api.example .env.api
nano .env.api
```

အနည်းဆုံး အောက်ပါတို့ကို ပြင်ပါ:

- `SESSION_SECRET` → `openssl rand -hex 32`
- `DB_PASSWORD` → `.env.db` ထဲက တန်ဖိုးအတိအကျ
- `WEB_CONCURRENCY` → default `16` (32 vCPU အတွက် သင့်တော်)
- `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` → `8` / `8`

Connection အရေအတွက် တွက်နည်း:

```
workers × (DB_POOL_SIZE + DB_MAX_OVERFLOW) ≤ MariaDB max_connections
16 × (8 + 8) = 256  ≤ 600  ✅
```

Worker တွေ တင်မယ်ဆိုရင် (ဥပမာ 24) DB pool ကို လျှော့ပါ။ ဒါမှမဟုတ်
MariaDB `max_connections` ကို တင်ပါ။

```bash
chmod 600 .env.api
docker compose --env-file .env.api -f docker-compose.api.yml up -d --build
docker compose --env-file .env.api -f docker-compose.api.yml ps
docker compose --env-file .env.api -f docker-compose.api.yml logs -f app
```

စစ်ဆေးရန်:

```bash
curl -fsS http://127.0.0.1:5000/api/check-update
docker compose --env-file .env.api -f docker-compose.api.yml exec app \
  python -c "import socket; print(socket.gethostbyname('192.168.111.100'))"
```

API start ချိန်မှာ `personcv.version`, `form_sequence`, `sync_operations` စတဲ့
schema fix တွေကို အလိုအလျောက် လုပ်ပါတယ်။ Log မှာ error မရှိကြောင်း စစ်ပါ။

### APK upload

```bash
docker compose --env-file .env.api -f docker-compose.api.yml \
  cp lbvd-1.2.3.apk app:/app/assets/apk/
docker compose --env-file .env.api -f docker-compose.api.yml \
  exec app ls -lh /app/assets/apk/
```

APK file တွေက `apk_data` volume ထဲမှာ ရှိတဲ့အတွက် image rebuild လုပ်လည်း
မပျက်ပါဘူး။

### Redis

Redis က API VM ပေါ်မှာ sidecar အနေနဲ့ run ပြီး host ပေါ် publish မလုပ်ပါဘူး။
Survey draft တွေ သိမ်းဖို့သာ သုံးပါတယ်။ Redis ပျက်ရင် app က session fallback
သုံးပြီး ဆက်အလုပ်လုပ်ပါတယ်။

---

## 3. Web server — `192.168.111.50`

```bash
cd /srv/lbvd
docker compose -f docker-compose.web.yml up -d
docker compose -f docker-compose.web.yml ps
docker compose -f docker-compose.web.yml logs -f nginx
```

စစ်ဆေးရန်:

```bash
curl -fsS http://127.0.0.1/healthz          # ok
curl -fsS http://127.0.0.1/api/check-update
curl -I  http://127.0.0.1/                  # 200/302
```

ပြီးရင် client ဘရောက်ဇာကနေ `http://192.168.111.50/` ကို ဖွင့်ပါ။

Nginx က `/assets`, `/static`, `/apks` တွေကို 7 ရက် cache လုပ်ထားတာကြောင့်
image/APK တွေကို API ဆီ ထပ်ခါထပ်ခါ မတောင်းတော့ပါဘူး။ Cache size က
အများဆုံး 8 GB ဖြစ်ပါတယ်။

### HTTPS (နောက်ပိုင်း domain/cert ရှိရင်)

1. Cert ဖိုင်တွေကို web VM ရဲ့ `deploy/three-tier/certs/` ထဲ ထည့်ပါ။
2. `docker-compose.web.yml` မှာ `"443:443"` နဲ့ cert volume ကို
   comment ဖြုတ်ပါ။
3. `nginx/three-tier.conf` ထဲက HTTPS server block ကို comment ဖြုတ်ပြီး
   `server_name` ကို ပြင်ပါ။
4. `.env.api` မှာ `COOKIE_HTTPS_ONLY=true` လုပ်ပြီး API ကို restart ပါ။

```bash
docker compose -f docker-compose.web.yml up -d
docker compose --env-file .env.api -f docker-compose.api.yml up -d
```

> LAN မှာ HTTP နဲ့သုံးနေချိန် `COOKIE_HTTPS_ONLY=true` ဖြစ်နေရင် login
> ဝင်လို့မရပါဘူး (cookie ကို browser က မသိမ်းပါ)။ HTTP အတွက် `false` ထားပါ။

---

## 4. Firewall

အောက်ပါ rule တွေကို သက်ဆိုင်ရာ VM မှာ ထည့်ပါ။ Docker က port ကို
publish လုပ်တဲ့အခါ UFW ကို ကျော်သွားတတ်တာကြောင့် `DOCKER-USER` chain
ကိုပါ သုံးရပါတယ်။ (Network switch/VLAN ACL ရှိရင် အဲဒါက ပိုကောင်းပါတယ်။)

**Web VM (`.50`)**

```bash
sudo ufw allow from 192.168.111.0/24 to any port 22 proto tcp
sudo ufw allow 80/tcp
# HTTPS သုံးရင်: sudo ufw allow 443/tcp
sudo ufw enable
```

**API VM (`.200`)** — 5000 ကို web server တစ်ခုတည်း ဝင်ခွင့်ပြု

```bash
sudo ufw allow from 192.168.111.0/24 to any port 22 proto tcp
sudo ufw enable

IFACE=$(ip route | awk '/default/ {print $5; exit}')
sudo iptables -I DOCKER-USER 1 -i "$IFACE" -p tcp --dport 5000 -j DROP
sudo iptables -I DOCKER-USER 1 -i "$IFACE" -p tcp --dport 5000 \
  -s 192.168.111.50 -j ACCEPT
```

**DB VM (`.100`)** — 3306 ကို API server တစ်ခုတည်း ဝင်ခွင့်ပြု

```bash
sudo ufw allow from 192.168.111.0/24 to any port 22 proto tcp
sudo ufw enable

IFACE=$(ip route | awk '/default/ {print $5; exit}')
sudo iptables -I DOCKER-USER 1 -i "$IFACE" -p tcp --dport 3306 -j DROP
sudo iptables -I DOCKER-USER 1 -i "$IFACE" -p tcp --dport 3306 \
  -s 192.168.111.200 -j ACCEPT
```

Rule တွေကို reboot ပြီးလည်း ကျန်စေချင်ရင်:

```bash
sudo apt install -y iptables-persistent
sudo netfilter-persistent save
```

စစ်ဆေးရန် — web VM ကနေ API ကို ရပြီး၊ တခြား machine ကနေ API/DB ကို
မရသင့်ပါ။

```bash
# web VM: ရရမယ်
curl -fsS http://192.168.111.200:5000/api/check-update

# တခြား VM: မရရဘူး (timeout/refused)
nc -z -w 3 192.168.111.200 5000
nc -z -w 3 192.168.111.100 3306
```

---

## 5. အားလုံးအတူ စစ်ဆေးခြင်း

Web VM ကနေ:

```bash
cd /srv/lbvd
./deploy/three-tier/smoke-test.sh
```

လက်ဖြင့်:

```bash
curl -fsS http://192.168.111.50/healthz
curl -fsS http://192.168.111.50/api/check-update
curl -I  http://192.168.111.50/
```

ပြီးရင် browser မှာ `http://192.168.111.50/` ဖွင့်၊ login ဝင်ပြီး
survey တစ်ခု စမ်းပါ။

Demo account တွေ (`deploy/seed.sql`) ပါလာရင် ချက်ချင်း password ပြောင်းပါ:

| Login | Password | Role |
|---|---|---|
| `admin` | `LBVDdemo#2026` | admin |
| `BagoAdmin` | `12345` | superadmin |
| `mgmg` | `12345678` | enumerator (demo) |

`app/config.py` ထဲက `DEFAULT_PASSWORD = "12345678"` ကိုလည်း လိုအပ်ရင်
ပြောင်းပါ။

### APK base URL

Flutter app ကို web server ကို ညွှန်ပြီး build ပါ:

```bash
flutter build apk --dart-define=API_BASE_URL=http://192.168.111.50
```

Release APK က cleartext HTTP ကို block လုပ်တတ်တာကြောင့် ဒီ LAN setup မှာ
Android network-security-config ဖွင့်ထားဖို့ လိုနိုင်ပါတယ်။ ဒါမှမဟုတ်
HTTPS သုံးပါ။

---

## 6. Update လုပ်ခြင်း

အစဉ်တောက် DB backup အရင်ယူပါ။

```bash
# DB VM
cd /srv/lbvd && ./deploy/three-tier/backup-db.sh

# API VM
cd /srv/lbvd
git pull
docker compose --env-file .env.api -f docker-compose.api.yml up -d --build
docker compose --env-file .env.api -f docker-compose.api.yml logs --tail=100 app

# Web VM (config ပြောင်းရင်)
cd /srv/lbvd
git pull
docker compose -f docker-compose.web.yml up -d
```

DB volume ကို မဖျက်ပါနဲ့။ `docker compose down -v` က data ကို ဖျက်ပါတယ်။

---

## 7. Troubleshooting

| ပြဿနာ | စစ်ဆေးရန် |
|---|---|
| Login ဝင်ပြီး login page ပြန်ရောက် | `.env.api` မှာ `COOKIE_HTTPS_ONLY=false` ဖြစ်ရဲ့လား (HTTP အတွက်)၊ `SESSION_SECRET` ပြောင်းမထားရဲ့လား |
| Web မှာ 502 Bad Gateway | API container run နေရဲ့လား၊ `.50` ကနေ `.200:5000` ရရဲ့လား၊ firewall |
| API log: `Can't connect to MySQL` | DB container healthy ဖြစ်ရဲ့လား၊ `.env.api` ရဲ့ `DB_HOST/DB_PASSWORD` မှန်ရဲ့လား၊ DB VM firewall |
| `Access denied for user 'lbvd'` | `.env.db` နဲ့ `.env.api` ရဲ့ password တူရဲ့လား။ DB ကို ပထမ start လုပ်ချိန် password ပြောင်းထားရင် volume အဟောင်း သုံးနေနိုင်တယ် |
| Upload/export မရ | Nginx `client_max_body_size 64m`, `proxy_read_timeout 180s` |
| Cookie size ကြီးလာတယ် | Redis healthy ဖြစ်ရဲ့လား (`docker compose ... logs redis`)။ Redis မရရင် session fallback သုံးတဲ့အတွက် cookie ပြန်ကြီးနိုင်တယ် |
| MariaDB memory မလုံလောက် | `99-lbvd.cnf` ထဲက `innodb_buffer_pool_size` ကို လျှော့ပါ |
| `mbind: Operation not permitted` | MariaDB log ထဲက ဒီစာ ကို လျစ်လျူရှုနိုင်ပါတယ် (container numa limitation) |
| Export နှေးတယ် | Nginx timeout 180s ရှိပါတယ်။ DB slow log (`/var/lib/mysql/slow.log`) ကို စစ်ပါ |

---

## 8. ဒီ setup ရဲ့ resource အသုံးပြုမှု

| VM | အဓိက resource |
|---|---|
| Web `.50` | Nginx worker 32 (auto), cache ≤ 8 GB, connections 16k |
| API `.200` | Uvicorn worker 16 (~5–8 GB), Redis ≤ 2 GB, image/assets ~1 GB |
| DB `.100` | InnoDB buffer pool 40 GB, log buffer 64 MB, max 600 connections |

လိုအပ်ရင် `.env.api` ထဲက `WEB_CONCURRENCY` နဲ့ DB pool ကို ချိန်ညှိနိုင်ပါတယ်။
Worker တစ်ခုစီမှာ SQLAlchemy pool ရှိတာကြောင့် **worker × pool** ကို
DB `max_connections` အောက် ထားဖို့ အရေးကြီးပါတယ်။
