import logging
import os
from contextlib import asynccontextmanager
from fastapi import Request, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from fastapi.responses import JSONResponse
from app.redis_client import redis_client, check_redis, close_redis


from app.config import (
    APP_NAME,
    APP_VERSION,
    COOKIE_HTTPS_ONLY,
    DEBUG,
    SESSION_SECRET,
    SESSION_MAX_AGE_HOURS,
)
from app.constants import APK_DIR
from app.database import engine
from app.extensions import limiter
from app.routers import (
    auth, dashboard, enumerator, exports, households, locations,
    reports, settings, survey, system_admin, updates, villages,
)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lbvd")


def init_db():
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    role ENUM('admin', 'staff') NOT NULL
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
        logger.info("users table ready")
    except SQLAlchemyError as e:
        logger.warning("init_db: %s", e)



def ensure_indexes():
    index_specs = [
        ("district", "idx_district_state", ["stateID", "districtID"]),
        (
            "township",
            "idx_township_state_district",
            ["stateID", "districtID", "townshipID"],
        ),
        (
            "personcv",
            "idx_personcv_state_district_township",
            ["stateID", "districtID", "townshipID"],
        ),
    ]

    try:
        with engine.begin() as conn:
            for table, index_name, columns in index_specs:
                inspector = inspect(conn)

                if table not in inspector.get_table_names():
                    logger.warning(
                        "ensure_indexes: table %s does not exist",
                        table,
                    )
                    continue

                existing_indexes = {
                    index["name"]
                    for index in inspector.get_indexes(table)
                }

                if index_name not in existing_indexes:
                    column_sql = ", ".join(f"`{c}`" for c in columns)

                    conn.exec_driver_sql(
                        f"CREATE INDEX `{index_name}` "
                        f"ON `{table}` ({column_sql})"
                    )

                    logger.info("Created index: %s", index_name)
                else:
                    logger.info("Index already exists: %s", index_name)

        logger.info("Database indexes ensured.")

    except SQLAlchemyError as e:
        logger.warning("ensure_indexes: %s", e)


def ensure_personcv_status():
    with engine.begin() as conn:
        columns = inspect(conn).get_columns("personcv")
        if not any(c["name"] == "status" for c in columns):
            conn.exec_driver_sql(
                "ALTER TABLE personcv ADD COLUMN status TINYINT NOT NULL DEFAULT 0 "
                "CONSTRAINT ck_personcv_status CHECK (status IN (0, 1))"
            )
        elif not any(
            c["name"] == "ck_personcv_status"
            for c in inspect(conn).get_check_constraints("personcv")
        ):
            conn.exec_driver_sql(
                "ALTER TABLE personcv ADD CONSTRAINT ck_personcv_status "
                "CHECK (status IN (0, 1))"
            )


def ensure_village_table():
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS village (
                    stateID VARCHAR(30) NOT NULL,
                    districtID VARCHAR(30) NOT NULL,
                    townshipID VARCHAR(30) NOT NULL,
                    QVID VARCHAR(30) NOT NULL,
                    villageID VARCHAR(30) NOT NULL,
                    villageName TEXT DEFAULT NULL,
                    PRIMARY KEY (stateID, districtID, townshipID, QVID, villageID),
                    KEY villageindex (stateID, districtID, townshipID, QVID, villageID)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
        logger.info("village table ready")
    except SQLAlchemyError as e:
        logger.warning("ensure_village_table: %s", e)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     init_db()
#     ensure_personcv_status()
#     ensure_indexes()
#     ensure_village_table()
#     yield
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_personcv_status()
    ensure_indexes()
    ensure_village_table()

    try:
        await check_redis()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning("Redis connection failed: %s", e)

    yield

    await close_redis()

app = FastAPI(
    title=APP_NAME, version=APP_VERSION, debug=DEBUG, lifespan=lifespan,
    docs_url=None,      # /docs ပိတ်
    redoc_url=None,     # /redoc ပိတ်
    
)
# ⭐ Extra protection — block docs paths even if someone guesses them
# @app.middleware("http")

async def block_docs_endpoints(request: Request, call_next):
    blocked_exact = {"/docs", "/redoc", "/openapi.json"}
    blocked_prefixes = ("/docs/", "/redoc/")
    path = request.url.path
    if path in blocked_exact or any(path.startswith(p) for p in blocked_prefixes):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return await call_next(request)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="lbvd_session",       # custom cookie name
    max_age=SESSION_MAX_AGE_HOURS * 60 * 60,                  # 8 hours (working day)
    same_site="lax",
    https_only=COOKIE_HTTPS_ONLY,         # production: True
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=256,
)

# ---------- Routers ----------
app.include_router(auth.router)
app.include_router(locations.router)
app.include_router(survey.router)
app.include_router(enumerator.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(households.router)
app.include_router(settings.router)
app.include_router(system_admin.router)
app.include_router(exports.router)
app.include_router(updates.router)   # public: /api/check-update, /api/download-latest
app.include_router(villages.router)

# ---------- Static ----------
_current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_assets_dir = os.path.join(_current_dir, "assets")
app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

# APK downloads (public, referenced by /api/check-update)
try:
    APK_DIR.mkdir(parents=True, exist_ok=True)
except OSError as exc:
    logger.warning("Cannot create APK directory %s: %s", APK_DIR, exc)
app.mount(
    "/apks",
    StaticFiles(directory=str(APK_DIR), check_dir=False),
    name="apks",
)

@app.get("/test-redis")
async def test_redis():
    await redis_client.set("lbvd_test", "Redis is working")
    value = await redis_client.get("lbvd_test")

    return {
        "redis": "connected",
        "value": value
    }
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        reload=DEBUG,
    )
