import logging
import os
from contextlib import asynccontextmanager
from fastapi import Request, FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from app.config import (
    APP_NAME, APP_VERSION, COOKIE_HTTPS_ONLY, DEBUG, SESSION_SECRET,
)
from app.constants import APK_DIR
from app.database import engine
from app.extensions import limiter
from app.routers import (
    auth, dashboard, enumerator, exports, households, locations,
    reports, settings, survey, system_admin, update,
)
from fastapi.responses import JSONResponse

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_personcv_status()
    yield


app = FastAPI(
    title=APP_NAME, version=APP_VERSION, debug=DEBUG, lifespan=lifespan,
    docs_url=None,      # /docs ပိတ်
    redoc_url=None,     # /redoc ပိတ်
    
)
# ⭐ Extra protection — block docs paths even if someone guesses them
@app.middleware("http")
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
    max_age=None,                  # 8 hours (working day)
    same_site="lax",
    https_only=COOKIE_HTTPS_ONLY,         # production: True
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
app.include_router(update.router)   # public: /api/check-update, /api/download-latest

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        reload=DEBUG,
    )
