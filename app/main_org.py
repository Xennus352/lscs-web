# ============================================================
# 📦 IMPORTS
# ============================================================
import os
import re
import uuid
import json
import logging
import base64
import hashlib
import hmac
import secrets
import csv
import io
from app.models import PersonCV
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, Annotated, Dict, List
from pathlib import Path
from urllib.parse import quote

import jwt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from openpyxl import load_workbook, Workbook
from fastapi import File, UploadFile
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import (
    FastAPI, Form, HTTPException, Request, status,
    Depends, Query,
)
from fastapi.responses import (
    HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse,
)
from fastapi.templating import Jinja2Templates
from fastapi.encoders import jsonable_encoder
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from app.database import get_db_connection, engine, SessionLocal, get_db

logger = logging.getLogger(__name__)

# ============================================================
# ⚙️ ENV & CONSTANTS
# ============================================================
APP_NAME     = os.getenv("APP_NAME", "LBVD Dashboard")
APP_VERSION  = os.getenv("APP_VERSION", "1.0.0")
DEBUG        = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")
CSV_ENCODING = os.getenv("CSV_ENCODING", "utf-8")

PASSWORD_ITERATIONS = 310_000
DEFAULT_PASSWORD = "12345678"

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "lbvd-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lbvd")

FIXED_STATE_ID   = "s07"
FIXED_STATE_NAME = "ပဲခူးတိုင်းဒေသကြီး"

# ============================================================
# 🔐 PASSWORD HASHING
# ============================================================
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )

def verify_password(password: str, stored: str) -> bool:
    if not stored.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(password, stored)
    try:
        _, rounds, salt_text, digest_text = stored.split("$", 3)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(rounds)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

# ============================================================
# 🗄️ SQLAlchemy database access
# ============================================================
def init_db():
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("""
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
    """Apply the additive collection-status migration once, including existing rows."""
    with engine.begin() as connection:
        columns = inspect(connection).get_columns("personcv")
        if not any(column["name"] == "status" for column in columns):
            connection.exec_driver_sql(
                "ALTER TABLE personcv ADD COLUMN status TINYINT NOT NULL DEFAULT 0 "
                "CONSTRAINT ck_personcv_status CHECK (status IN (0, 1))"
            )
        elif not any(
            constraint["name"] == "ck_personcv_status"
            for constraint in inspect(connection).get_check_constraints("personcv")
        ):
            connection.exec_driver_sql(
                "ALTER TABLE personcv ADD CONSTRAINT ck_personcv_status "
                "CHECK (status IN (0, 1))"
            )

# ============================================================
# 🚀 APP & RATE LIMITER
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ensure_personcv_status()
    yield

# app = FastAPI(title=APP_NAME, version=APP_VERSION, debug=DEBUG, lifespan=lifespan)
app = FastAPI(title=APP_NAME, version=APP_VERSION, debug=DEBUG, lifespan=lifespan,docs_url=None,      # /docs ပိတ်
    redoc_url=None,     # /redoc ပိတ်
    openapi_url=None,   # /openapi.json ပိတ်
    )


limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "lbvd-change-this-secret-in-production"),
    same_site="lax",
    https_only=os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true",
)

current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
assets_dir = os.path.join(current_dir, "assets")
app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# ============================================================
# 📁 TEMPLATES
# ============================================================
HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

CANDIDATES = [PROJECT_ROOT / "templates", HERE / "templates", HERE / "outputs"]
_env_dir = os.getenv("TEMPLATE_DIR")
if _env_dir:
    final_template_dir = Path(_env_dir)
else:
    final_template_dir = None
    for _c in CANDIDATES:
        if _c.is_dir():
            final_template_dir = _c
            break
    if final_template_dir is None:
        final_template_dir = PROJECT_ROOT / "templates"

logger.info(f"📁 Templates dir: {final_template_dir}")
templates = Jinja2Templates(directory=str(final_template_dir))

def to_locale_string(value, default=0):
    try:
        n = int(value) if value is not None else int(default)
        return f"{n:,}"
    except (ValueError, TypeError):
        return str(default)

templates.env.filters["toLocaleString"] = to_locale_string
templates.env.filters["format_number"]  = to_locale_string

AGE_TO_KEY = {
    "atID01": {"ageID03": "u1", "ageID02": "m1_3", "ageID01": "o3"},
    "atID02": {"ageID06": "u2m", "ageID05": "m2_6m", "ageID04": "o6m"},
}

# ============================================================
# 🛡️ ROLE & AUTH HELPERS
# ============================================================
ROLE_NAMES = {
    1: "admin", 2: "union", 3: "state", 4: "district", 5: "township", 6: "enumerator",
}

ROLE_HOME = {
    "admin":       "/system/users",
    "union":       "/admin",
    "state":       "/admin",
    "district":    "/admin",
    "township":    "/admin",
    "enumerator":  "/survey/dashboard",   # ⭐ ပြောင်း
}

security = HTTPBearer()

def get_signed_in_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login လုပ်ပါ။")
    return user

def verify_mobile_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token သက်တမ်းကုန်သွားပါပြီ။ ပြန် Login လုပ်ပါ။")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token မမှန်ကန်ပါ။")

def _get_user_state_name(user):
    if not user or not user.get("stateID"):
        return ""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT stateName FROM state WHERE stateID = %s", (user["stateID"],))
            r = cursor.fetchone()
            return r["stateName"] if r else ""
        finally:
            cursor.close(); conn.close()
    except Exception as e:
        logger.warning(f"State name lookup failed: {e}")
        return ""

def _get_all_states():
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT stateID, stateName FROM state ORDER BY stateName")
            return cursor.fetchall()
        finally:
            cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_all_states: {e}")
        return []

def _get_all_large_animals():
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT animalID, animalName FROM largeanimals WHERE animalTypeID = 'atID01' ORDER BY animalID")
            return cursor.fetchall()
        finally:
            cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_all_large_animals: {e}")
        return []

def _get_all_small_animals():
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT animalID, animalName FROM younganimals WHERE animalTypeID = 'atID02' ORDER BY animalID")
            return cursor.fetchall()
        finally:
            cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_all_small_animals: {e}")
        return []

def _get_all_livestock_animals():
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT animalID, animalName FROM livestock WHERE animalTypeID = 'atID03' ORDER BY animalID")
            return cursor.fetchall()
        finally:
            cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_all_livestock_animals: {e}")
        return []

# ============================================================
# 📅 DATE FILTER HELPERS
# ============================================================
def _resolve_date_range(start_date: Optional[str] = None, end_date: Optional[str] = None):
    start_date = (start_date or "").strip()
    end_date = (end_date or "").strip()

    if not start_date and not end_date:
        return None, None

    if start_date and not end_date:
        return start_date, start_date

    if end_date and not start_date:
        return end_date, end_date

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date

# ============================================================
# ⭐ MAPPING & CONSTANTS
# ============================================================
ANIMAL_TYPES = {
    "atID01": {"table": "largeanimals",  "label": "large"},
    "atID02": {"table": "younganimals",  "label": "small"},
    "atID03": {"table": "livestock",     "label": "poultry"},
    "atID04": {"table": "breedingstock", "label": "breeding"},
}

BREEDING_ANIMAL_MAP = {
    "bsID01": "ဒေသနွား", "bsID02": "ဒေသကျွဲ", "bsID03": "နို့စားကျွဲ",
    "bsID04": "ဝက်", "bsID05": "ဆိတ်", "bsID06": "သိုး",
}

AGE_KEY_MAP = {
    "atID01": {"ageID03": "u1", "ageID02": "y1_3", "ageID01": "o3"},
    "atID02": {"ageID06": "u2m", "ageID05": "m2_6m", "ageID04": "o6m"},
    "atID03": {
        "ageID07": "young", "ageID08": "medium", "ageID09": "adult",
        "ageID10": "young_medium", "ageID11": "adult",
        "ageID12": "young", "ageID13": "medium", "ageID14": "adult",
        "ageID15": "young", "ageID16": "medium", "ageID17": "adult",
    },
}

GENDER_KEY_MAP = {"g01": "male", "g02": "castrated", "g03": "female"}

ANIMAL_TYPE_NAMES = [
    {"id": "atID01", "name": "တိရိစ္ဆာန်ကြီး"},
    {"id": "atID02", "name": "တိရိစ္ဆာန်ငယ်"},
    {"id": "atID03", "name": "ကြက်/ဘဲ/ငုံး"},
    {"id": "atID04", "name": "မျိုးတိရိစ္ဆာန်"},
]

GENDERS = [{"id": "g01", "name": "အထီး"}, {"id": "g02", "name": "သင်းကွပ်အထီး"}, {"id": "g03", "name": "အမ"}]
GENDERS_BREEDING = [{"id": "g01", "name": "အထီး"}, {"id": "g03", "name": "အမ"}]

class AnimalRecordItem(BaseModel):
    formID: str
    animalTypeID: str
    animalID: int
    speciesID: int
    ageID: str
    genderID: str
    dataCount: int


# ============================================================
# 🆔 FORM ID GENERATOR
# ============================================================
def generate_formatted_id(counter_value: int) -> str:
    """Formats an integer into a zero-padded string identifier."""
    current_year = datetime.now().year
    return f"FORM-{current_year}-{counter_value:05d}"

# ============================================================
# 📊 DASHBOARD QUERY
# ============================================================
def query_dashboard_data(user, state=None, district=None, township=None, qv=None,
                         start_date=None, end_date=None):
    role = user["role"]
    db = SessionLocal()
    region_name = ""
    animals = []
    stats = {"large": 0, "small": 0, "poultry": 0, "breeding": 0, "total": 0}

    try:
        try:
            if role == "union":
                region_name = "တစ်နိုင်ငံလုံး"
            elif role == "state":
                r = db.execute(text("SELECT stateName AS name FROM state WHERE stateID = :sid"), {"sid": user["stateID"]}).fetchone()
                region_name = r[0] if r else (user.get("stateID") or "")
            elif role == "district":
                r = db.execute(text("SELECT districtName AS name FROM district WHERE stateID = :sid AND districtID = :did"), {"sid": user["stateID"], "did": user["districtID"]}).fetchone()
                region_name = r[0] if r else (user.get("districtID") or "")
            elif role in ("township", "enumerator"):
                r = db.execute(text("SELECT townshipName AS name FROM township WHERE stateID = :sid AND districtID = :did AND townshipID = :tid"), {"sid": user["stateID"], "did": user["districtID"], "tid": user["townshipID"]}).fetchone()
                region_name = r[0] if r else (user.get("townshipID") or "")
        except SQLAlchemyError as e:
            print("Region lookup error:", e)

        q_conds = ["cd.animalTypeID IN ('atID01', 'atID02', 'atID03', 'atID04')"]
        q_params = {}

        if role == "union":
            if state and state.strip():
                q_conds.append("loc.stateID = :sid"); q_params["sid"] = state.strip()
            if district and district.strip():
                q_conds.append("loc.districtID = :did"); q_params["did"] = district.strip()
            if township and township.strip():
                q_conds.append("loc.townshipID = :tid"); q_params["tid"] = township.strip()
        elif role == "state":
            q_conds.append("loc.stateID = :sid"); q_params["sid"] = user["stateID"]
        elif role == "district":
            q_conds.extend(["loc.stateID = :sid", "loc.districtID = :did"]); q_params["sid"] = user["stateID"]; q_params["did"] = user["districtID"]
        elif role in ("township", "enumerator"):
            q_conds.extend(["loc.stateID = :sid", "loc.districtID = :did", "loc.townshipID = :tid"])
            q_params["sid"] = user["stateID"]; q_params["did"] = user["districtID"]; q_params["tid"] = user["townshipID"]

        if role in ("admin", "union") and state and state.strip():
            q_conds.append("loc.stateID = :sid"); q_params["sid"] = state.strip()
        if role in ("admin", "union", "state") and district and district.strip():
            q_conds.append("loc.districtID = :did"); q_params["did"] = district.strip()
        if role in ("admin", "union", "state", "district") and township and township.strip():
            q_conds.append("loc.townshipID = :tid"); q_params["tid"] = township.strip()
        if qv and qv.strip():
            q_conds.append("loc.QVID = :qvid"); q_params["qvid"] = qv.strip()

        s, e = _resolve_date_range(start_date, end_date)
        if s and e:
            q_conds.append("DATE(loc.interviewDate) BETWEEN :start_date AND :end_date")
            q_params["start_date"] = s
            q_params["end_date"]   = e

        where = " AND ".join(q_conds)

        sql = text(f"""
            SELECT
                COALESCE(at.animalName, cd.animalTypeID) AS animal_type,
                cd.animalTypeID AS animal_type_id,
                cd.animalID    AS animal_id,
                CASE 
                    WHEN cd.animalTypeID = 'atID01' THEN COALESCE(la.animalName, cd.animalID)
                    WHEN cd.animalTypeID = 'atID02' THEN COALESCE(ya.animalName, cd.animalID)
                    WHEN cd.animalTypeID = 'atID03' THEN COALESCE(lv.animalName, cd.animalID)
                    WHEN cd.animalTypeID = 'atID04' THEN COALESCE(bst.animalName, cd.animalID)
                    ELSE cd.animalID
                END AS animal_name,
                CASE 
                    WHEN cd.animalTypeID = 'atID04' THEN 'မျိုးတိရစ္ဆာန်'
                    WHEN cd.animalTypeID = 'atID03' THEN COALESCE(lss.speciesName, cd.speciesID)
                    ELSE COALESCE(ls.speciesName, ys.speciesName, cd.speciesID) 
                END AS species_name,
                COALESCE(atg.ageName, a.ageName, cd.ageID) AS age_name,
                COALESCE(g.genderName, cd.genderID) AS gender_name,
                SUM(cd.dataCount) AS total_count
            FROM collecteddata AS cd
            JOIN (SELECT DISTINCT formID, stateID, districtID, townshipID, QVID, interviewDate FROM personcv) AS loc ON loc.formID = cd.formID
            LEFT JOIN animaltype AS at ON at.animalTypeID = cd.animalTypeID
            LEFT JOIN largeanimals AS la ON cd.animalTypeID = 'atID01' AND la.animalID = cd.animalID
            LEFT JOIN largespecies AS ls ON cd.animalTypeID = 'atID01' AND ls.speciesID = cd.speciesID AND ls.animalID = cd.animalID
            LEFT JOIN younganimals AS ya ON cd.animalTypeID = 'atID02' AND ya.animalID = cd.animalID
            LEFT JOIN youngspecies AS ys ON cd.animalTypeID = 'atID02' AND ys.speciesID = cd.speciesID AND ys.animalID = cd.animalID
            LEFT JOIN livestock AS lv ON cd.animalTypeID = 'atID03' AND lv.animalID = cd.animalID
            LEFT JOIN livestockspecies AS lss ON cd.animalTypeID = 'atID03' AND lss.speciesID = cd.speciesID AND lss.animalID = cd.animalID
            LEFT JOIN breedingstock AS bst ON cd.animalTypeID = 'atID04' AND bst.animalID = cd.animalID
            LEFT JOIN agetype AS atg ON atg.ageID = cd.ageID AND atg.animalTypeID = cd.animalTypeID AND (atg.animalID IS NULL OR TRIM(atg.animalID) = '' OR atg.animalID = cd.animalID)
            LEFT JOIN age AS a ON a.ageID = cd.ageID
            LEFT JOIN gender AS g ON g.genderID = cd.genderID
            WHERE {where}
            GROUP BY cd.animalTypeID, at.animalName, cd.animalID, la.animalName, ya.animalName, lv.animalName, bst.animalName,
                cd.speciesID, ls.speciesName, ys.speciesName, lss.speciesName, cd.ageID, atg.ageName, a.ageName, cd.genderID, g.genderName
            ORDER BY animal_type, animal_name
        """)
        rows = db.execute(sql, q_params).mappings().all()
        animals = [dict(r) for r in rows]

        for a in animals:
            try: a["total_count"] = int(a.get("total_count") or 0)
            except (ValueError, TypeError): a["total_count"] = 0
            aid = (a.get("animal_type_id") or "").strip()
            cnt = a["total_count"]
            stats["total"] += cnt
            if aid == 'atID01': stats["large"] += cnt
            elif aid == 'atID02': stats["small"] += cnt
            elif aid == 'atID03': stats["poultry"] += cnt
            elif aid == 'atID04': stats["breeding"] += cnt
    except SQLAlchemyError as e:
        logger.error(f"Dashboard DB Error: {e}")
    finally:
        db.close()

    return region_name, animals, stats

# ============================================================
# 📊 REPORT 1 QUERIES
# ============================================================
def _query_report1_one_type(cursor, animal_type_id, role, user, state="", district="", township="", qv="",
                            start_date="", end_date=""):
    type_info = ANIMAL_TYPES.get(animal_type_id)
    if not type_info: return []

    table_name = type_info["table"]
    try:
        cursor.execute(f"SELECT animalID, animalName FROM {table_name} WHERE animalTypeID = %s ORDER BY animalID", (animal_type_id,))
        animal_names = cursor.fetchall()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ {animal_type_id} lookup: {e}")
        return []

    conds = ["cd.animalTypeID = %s"]
    params = [animal_type_id]

    if role == "state":
        conds.append("loc.stateID = %s"); params.append(user["stateID"])
    elif role == "district":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s"]); params.extend([user["stateID"], user["districtID"]])
    elif role == "township":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s", "loc.townshipID = %s"]); params.extend([user["stateID"], user["districtID"], user["townshipID"]])

    if role in ("admin", "union") and state and state.strip():
        conds.append("loc.stateID = %s"); params.append(state.strip())
    if role in ("admin", "union", "state") and district and district.strip():
        conds.append("loc.districtID = %s"); params.append(district.strip())
    if role in ("admin", "union", "state", "district") and township and township.strip():
        conds.append("loc.townshipID = %s"); params.append(township.strip())
    if qv and qv.strip():
        conds.append("loc.QVID = %s"); params.append(qv.strip())

    s, e = _resolve_date_range(start_date, end_date)
    if s and e:
        conds.append("DATE(loc.interviewDate) BETWEEN %s AND %s")
        params.extend([s, e])

    where = " AND ".join(conds)
    sql = f"""
        SELECT cd.animalID AS animal_id, cd.ageID AS age_id, cd.genderID AS gender_id, SUM(COALESCE(cd.dataCount, 0)) AS total_count
        FROM collecteddata AS cd
        JOIN (SELECT DISTINCT formID, stateID, districtID, townshipID, QVID, interviewDate FROM personcv) AS loc ON loc.formID = cd.formID
        WHERE {where}
        GROUP BY cd.animalID, cd.ageID, cd.genderID
    """
    cursor.execute(sql, tuple(params))
    raw = cursor.fetchall()

    age_map = AGE_KEY_MAP.get(animal_type_id, {})
    rows = {}

    for a in animal_names:
        aid = a["animalID"]
        row = {"animalID": aid, "animalName": a["animalName"], "total": 0}
        if age_map:
            for age_key in age_map.values():
                row[f"{age_key}_male"] = 0; row[f"{age_key}_castrated"] = 0; row[f"{age_key}_female"] = 0
        else:
            row["male"] = 0; row["castrated"] = 0; row["female"] = 0
        rows[aid] = row

    for item in raw:
        aid = str(item.get("animal_id") or "").strip()
        age_id = str(item.get("age_id") or "").strip()
        gid = str(item.get("gender_id") or "").strip()
        cnt = int(item.get("total_count") or 0)
        if aid not in rows: continue
        gkey = GENDER_KEY_MAP.get(gid)
        if gkey is None: continue
        akey = age_map.get(age_id)
        key = f"{akey}_{gkey}" if akey else gkey
        if key in rows[aid]:
            rows[aid][key] += cnt; rows[aid]["total"] += cnt

    return list(rows.values())

def _query_report1_breeding(cursor, role, user, state="", district="", township="", qv="",
                            start_date="", end_date=""):
    try:
        cursor.execute("SELECT animalID, animalName FROM breedingstock WHERE animalTypeID = %s ORDER BY animalID", ("atID04",))
        animal_names = cursor.fetchall()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ breedingstock lookup: {e}")
        return []

    conds = ["cd.animalTypeID = %s"]
    params = ["atID04"]

    if role == "state":
        conds.append("loc.stateID = %s"); params.append(user["stateID"])
    elif role == "district":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s"]); params.extend([user["stateID"], user["districtID"]])
    elif role == "township":
        conds.extend(["loc.stateID = %s", "loc.districtID = %s", "loc.townshipID = %s"]); params.extend([user["stateID"], user["districtID"], user["townshipID"]])

    if role in ("admin", "union") and state and state.strip():
        conds.append("loc.stateID = %s"); params.append(state.strip())
    if role in ("admin", "union", "state") and district and district.strip():
        conds.append("loc.districtID = %s"); params.append(district.strip())
    if role in ("admin", "union", "state", "district") and township and township.strip():
        conds.append("loc.townshipID = %s"); params.append(township.strip())
    if qv and qv.strip():
        conds.append("loc.QVID = %s"); params.append(qv.strip())

    s, e = _resolve_date_range(start_date, end_date)
    if s and e:
        conds.append("DATE(loc.interviewDate) BETWEEN %s AND %s")
        params.extend([s, e])

    where = " AND ".join(conds)
    sql = f"""
        SELECT cd.animalID AS animal_id, cd.genderID AS gender_id, SUM(COALESCE(cd.dataCount, 0)) AS total_count
        FROM collecteddata AS cd
        JOIN (SELECT DISTINCT formID, stateID, districtID, townshipID, QVID, interviewDate FROM personcv) AS loc ON loc.formID = cd.formID
        WHERE {where} GROUP BY cd.animalID, cd.genderID
    """
    cursor.execute(sql, tuple(params))
    raw = cursor.fetchall()

    rows = {}
    for a in animal_names:
        aid = a["animalID"]
        rows[aid] = {"animalID": aid, "animalName": a["animalName"], "male": 0, "castrated": 0, "female": 0, "total": 0}

    for item in raw:
        aid = str(item.get("animal_id") or "").strip()
        gid = str(item.get("gender_id") or "").strip()
        cnt = int(item.get("total_count") or 0)
        if aid not in rows: continue
        gkey = GENDER_KEY_MAP.get(gid)
        if gkey in ("male", "castrated", "female"):
            rows[aid][gkey] += cnt; rows[aid]["total"] += cnt

    return list(rows.values())

# ============================================================
# 📋 HOUSEHOLD QUERIES
# ============================================================
def _query_household_records(cursor, role, user, state="", district="", township="", qv="", search="",
                             form_id="", household_no="", head_name="", limit=None, offset=0,
                             start_date="", end_date=""):
    conds = ["1=1"]
    params = []

    if role == "state":
        conds.append("pc.stateID = %s"); params.append(user["stateID"])
    elif role == "district":
        conds.extend(["pc.stateID = %s", "pc.districtID = %s"]); params.extend([user["stateID"], user["districtID"]])
    elif role == "township":
        conds.extend(["pc.stateID = %s", "pc.districtID = %s", "pc.townshipID = %s"]); params.extend([user["stateID"], user["districtID"], user["townshipID"]])

    if role in ("admin", "union") and state and state.strip():
        conds.append("pc.stateID = %s"); params.append(state.strip())
    if role in ("admin", "union", "state") and district and district.strip():
        conds.append("pc.districtID = %s"); params.append(district.strip())
    if role in ("admin", "union", "state", "district") and township and township.strip():
        conds.append("pc.townshipID = %s"); params.append(township.strip())
    if qv and qv.strip():
        conds.append("pc.QVID = %s"); params.append(qv.strip())

    s, e = _resolve_date_range(start_date, end_date)
    if s and e:
        conds.append("DATE(pc.interviewDate) BETWEEN %s AND %s")
        params.extend([s, e])

    if search and search.strip():
        like = f"%{search.strip()}%"
        conds.append("(pc.name LIKE %s OR pc.householdNo LIKE %s OR pc.headName LIKE %s OR pc.formID LIKE %s)")
        params.extend([like, like, like, like])

    if form_id and form_id.strip():
        conds.append("pc.formID LIKE %s"); params.append(f"%{form_id.strip()}%")
    if household_no and household_no.strip():
        conds.append("pc.householdNo LIKE %s"); params.append(f"%{household_no.strip()}%")
    if head_name and head_name.strip():
        conds.append("pc.headName LIKE %s"); params.append(f"%{head_name.strip()}%")

    where = " AND ".join(conds)

    sql = f"""
            SELECT
                pc.formID, pc.householdNo, pc.name AS respondent_name, pc.gender AS respondent_gender,
                pc.age AS respondent_age, pc.eduStatus AS respondent_edu, pc.phoneNo AS respondent_phone,
                pc.interviewDate, pc.headName, pc.headGender, pc.headAge, pc.headEduStatus, pc.headPhoneNo,
                pc.Interviewer, pc.interviewerPhoneNo, pc.WardName, pc.stateID, pc.districtID,
                pc.townshipID, pc.QVID, st.stateName AS state_name, dt.districtName AS district_name,
                ts.townshipName AS township_name, qv.QVName AS qv_name,
                COALESCE(ct.large_total, 0) AS large_total, COALESCE(ct.small_total, 0) AS small_total,
                COALESCE(ct.poultry_total, 0) AS poultry_total, COALESCE(ct.breeding_total, 0) AS breeding_total
            FROM personcv AS pc
            LEFT JOIN state AS st ON st.stateID = pc.stateID
            LEFT JOIN district AS dt ON dt.stateID = pc.stateID AND dt.districtID = pc.districtID
            LEFT JOIN township AS ts ON ts.stateID = pc.stateID AND ts.districtID = pc.districtID AND ts.townshipID = pc.townshipID
            LEFT JOIN qv ON qv.stateID = pc.stateID AND qv.districtID = pc.districtID AND qv.townshipID = pc.townshipID AND qv.QVID = pc.QVID
            LEFT JOIN (
                SELECT formID,
                    SUM(CASE WHEN animalTypeID = 'atID01' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS large_total,
                    SUM(CASE WHEN animalTypeID = 'atID02' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS small_total,
                    SUM(CASE WHEN animalTypeID = 'atID03' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS poultry_total,
                    SUM(CASE WHEN animalTypeID = 'atID04' THEN CAST(dataCount AS UNSIGNED) ELSE 0 END) AS breeding_total
                FROM collecteddata GROUP BY formID
            ) AS ct ON ct.formID = pc.formID
            WHERE {where}
            ORDER BY pc.interviewDate DESC, pc.formID DESC
        """
    if limit is not None:
        sql += " LIMIT %s OFFSET %s"; params.extend([limit, offset])

    cursor.execute(sql, tuple(params))
    return cursor.fetchall()


def _query_household_detail(cursor, form_id):
    sql = """
        SELECT
            cd.animalTypeID, cd.animalID, cd.speciesID, cd.ageID, cd.genderID,
            CAST(cd.dataCount AS UNSIGNED) AS data_count,
            COALESCE(la.animalName, ya.animalName, lv.animalName, bs.animalName, cd.animalID) AS animal_name,
            COALESCE(ls.speciesName, ys.speciesName, lss.speciesName, cd.speciesID) AS species_name,
            COALESCE(atg.ageName, a.ageName, cd.ageID) AS age_name,
            COALESCE(g.genderName, cd.genderID) AS gender_name
        FROM collecteddata AS cd
        LEFT JOIN largeanimals     AS la  ON cd.animalTypeID = 'atID01' AND la.animalID = cd.animalID
        LEFT JOIN largespecies     AS ls  ON cd.animalTypeID = 'atID01' AND ls.speciesID = cd.speciesID AND ls.animalID = cd.animalID
        LEFT JOIN younganimals     AS ya  ON cd.animalTypeID = 'atID02' AND ya.animalID = cd.animalID
        LEFT JOIN youngspecies     AS ys  ON cd.animalTypeID = 'atID02' AND ys.speciesID = cd.speciesID AND ys.animalID = cd.animalID
        LEFT JOIN livestock        AS lv  ON cd.animalTypeID = 'atID03' AND lv.animalID = cd.animalID
        LEFT JOIN livestockspecies AS lss ON cd.animalTypeID = 'atID03' AND lss.speciesID = cd.speciesID AND lss.animalID = cd.animalID
        LEFT JOIN breedingstock    AS bs  ON cd.animalTypeID = 'atID04' AND bs.animalID = cd.animalID
        LEFT JOIN age              AS a   ON a.ageID = cd.ageID
        LEFT JOIN agetype          AS atg ON atg.ageID = cd.ageID 
            AND atg.animalTypeID = cd.animalTypeID 
            AND (atg.animalID IS NULL OR atg.animalID = '' OR atg.animalID = cd.animalID)
        LEFT JOIN gender           AS g   ON g.genderID = cd.genderID
        WHERE cd.formID = %s
        ORDER BY cd.animalTypeID, cd.animalID, cd.ageID, cd.genderID
    """
    cursor.execute(sql, (form_id,))
    return cursor.fetchall()

def _build_household_record(row, detail_rows):
    def _n(v):
        try: return int(v or 0)
        except (TypeError, ValueError): return 0

    POULTRY_AGE_KEY = {
        "ageID07": "young", "ageID08": "medium", "ageID09": "adult",
        "ageID10": "young", "ageID11": "adult",
        "ageID12": "young", "ageID13": "medium", "ageID14": "adult",
        "ageID15": "young", "ageID16": "medium",
    }
    GENDER_KEYS_BY_TYPE = {
        "atID01": {"g01": "male", "g02": "castrated", "g03": "female"},
        "atID02": {"g01": "male", "g02": "castrated", "g03": "female"},
        "atID03": {"g01": "male", "g03": "female"},
        "atID04": {"g01": "male", "g03": "female"},
    }

    large, small, poultry = [], [], []
    breeding = {}

    for d in detail_rows:
        atid = (d.get("animalTypeID") or "").strip()
        aid  = (d.get("animalID") or "").strip()
        age  = (d.get("ageID") or "").strip()
        gid  = (d.get("genderID") or "").strip()
        cnt  = _n(d.get("data_count"))
        age_name_val = d.get("age_name") or ""

        if atid == "atID01":
            species_id = str(d.get("speciesID") or "")
            row_ = next((x for x in large if x["animalID"] == aid and x["speciesID"] == species_id), None)
            if row_ is None:
                row_ = {"animalID": aid, "speciesID": species_id, "species": d.get("animal_name") or aid, "breed": d.get("species_name") or "", "total": 0, "age_name": age_name_val}
                large.append(row_)
            ak = AGE_TO_KEY.get(atid, {}).get(age)
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if ak and gk:
                key = f"{ak}_{gk}"
                row_[key] = row_.get(key, 0) + cnt
            row_["total"] += cnt

        elif atid == "atID02":
            species_id = str(d.get("speciesID") or "")
            row_ = next((x for x in small if x["animalID"] == aid and x["speciesID"] == species_id), None)
            if row_ is None:
                row_ = {"animalID": aid, "speciesID": species_id, "species": d.get("animal_name") or aid, "breed": d.get("species_name") or "", "total": 0, "age_name": age_name_val}
                small.append(row_)
            ak = AGE_TO_KEY["atID02"].get(age)
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if ak and gk:
                key = f"{ak}_{gk}"
                row_[key] = row_.get(key, 0) + cnt
            row_["total"] += cnt

        elif atid == "atID03":
            species_id = str(d.get("speciesID") or "")
            row_ = next((x for x in poultry if x["animalID"] == aid and x["speciesID"] == species_id), None)
            if row_ is None:
                row_ = {"animalID": aid, "speciesID": species_id, "species": d.get("animal_name") or aid, "breed": d.get("species_name") or "", "total": 0, "age_name": age_name_val}
                poultry.append(row_)
            ak = POULTRY_AGE_KEY.get(age)
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if ak and gk:
                key = f"{ak}_{gk}"
                row_[key] = row_.get(key, 0) + cnt
            row_["total"] += cnt

        elif atid == "atID04":
            gk = GENDER_KEYS_BY_TYPE.get(atid, {}).get(gid)
            if gk in ("male", "female"):
                if aid not in breeding:
                    breeding[aid] = {"animalID": aid, "male": 0, "female": 0, "species": d.get("animal_name") or aid, "age_name": age_name_val}
                breeding[aid][gk] += cnt

    return {
        "id": row.get("formID") or "", "householdNo": row.get("householdNo") or "",
        "state": row.get("state_name") or "", "district": row.get("district_name") or "",
        "township": row.get("township_name") or "", "village_tract": row.get("qv_name") or "",
        "ward_village": row.get("WardName") or "", "interview_date": str(row.get("interviewDate") or ""),
        "respondent": {"name": row.get("respondent_name") or "", "gender": row.get("respondent_gender") or "", "age": row.get("respondent_age") or "", "education": row.get("respondent_edu") or "", "phone": row.get("respondent_phone") or ""},
        "household_head": {"name": row.get("headName") or "", "gender": row.get("headGender") or "", "age": row.get("headAge") or "", "education": row.get("headEduStatus") or "", "phone": row.get("headPhoneNo") or ""},
        "has_raised_animals": "yes" if (large or small) else "no", "large_animals": large, "small_animals": small,
        "has_poultry": "yes" if poultry else "no", "poultry": poultry, "breeding": breeding,
        "interviewer": {"name": row.get("Interviewer") or "", "phone": row.get("interviewerPhoneNo") or ""},
        "large_total": _n(row.get("large_total")), "small_total": _n(row.get("small_total")),
        "poultry_total": _n(row.get("poultry_total")), "breeding_total": _n(row.get("breeding_total")),
    }

# ============================================================
# 🏠 ROOT
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request,
               state: str = Query(None), district: str = Query(None),
               township: str = Query(None), qv: str = Query(None),
               start_date: str = Query(""), end_date: str = Query("")):
    user = request.session.get("user")
    if not user: return templates.TemplateResponse(request=request, name="login.html", context={})

    role = user.get("role", "admin")
    if role == "admin": return RedirectResponse("/system/users", status_code=303)
    if role == "enumerator": return RedirectResponse("/survey/dashboard", status_code=303)
    if role == "staff": return RedirectResponse("/survey/part1", status_code=303)

    region_name, animals, stats = query_dashboard_data(
        user, state, district, township, qv,
        start_date=start_date, end_date=end_date
    )
    user_state_name = _get_user_state_name(user)

    return templates.TemplateResponse(
        request=request, name="reportDashboard.html",
        context={
            "stats": stats, "animals": animals, "role": role, "region_name": region_name,
            "user_state_id": user.get("stateID") or "", "user_state_name": user_state_name,
            "user_district_id": user.get("districtID") or "", "user_township_id": user.get("townshipID") or "",
            "filters": {
                "state": state, "district": district, "township": township, "qv": qv,
                "start_date": start_date, "end_date": end_date,
            },
            "active_page": "home",
        },
    )

# ============================================================
# 🔑 LOGIN / LOGOUT
# ============================================================
@app.post("/api/login")
@limiter.limit("30/10 minute")
async def web_login(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if not username or not password: raise HTTPException(400, "Username နှင့် Password ထည့်သွင်းပါ။")

    conn = None; cursor = None; user = None
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT userId AS id, loginName AS login_name, password, userRole AS role_id, stateID, districtID, townshipID, status FROM `user` WHERE loginName = %s LIMIT 1", (username,))
        user = cursor.fetchone()
    except Exception:
        logger.exception("Web login DB query failed"); raise HTTPException(503, "ဝန်ဆောင်မှုကို ယာယီအသုံးမပြုနိုင်ပါ။")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    if user is None or not verify_password(password, user["password"]): raise HTTPException(401, "Username သို့မဟုတ် Password မှားယွင်းနေပါသည်။")
    if str(user.get("status")) != "1": raise HTTPException(403, "သင့်အကောင့်ကို အသုံးပြုခွင့် ပိတ်ထားပါသည်။")

    try:
        role_id = int(user.get("role_id")); role = ROLE_NAMES.get(role_id)
    except (TypeError, ValueError):
        role = str(user.get("role_id") or "").strip().lower(); role_id = None

    request.session.clear()
    request.session["device_type"] = "web"
    request.session["user"] = {"id": user["id"], "role": role, "role_id": role_id, "loginName": user["login_name"], "stateID": user.get("stateID"), "districtID": user.get("districtID"), "townshipID": user.get("townshipID")}

    return {"status": "success", "role": role, "redirect": ROLE_HOME.get(role, "/survey/part1")}

@app.post("/api/mobile/login")
@limiter.limit("5/10 minute")
async def mobile_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    username = username.strip()
    if not username or not password:
        raise HTTPException(400, "Username နှင့် Password ထည့်သွင်းပါ။")

    conn = None; cursor = None; user = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT userId AS id, loginName AS login_name, password, 
                   userRole AS role_id, stateID, districtID, townshipID, status 
            FROM `user` WHERE loginName = %s LIMIT 1
        """, (username,))
        user = cursor.fetchone()
    except Exception:
        logger.exception("Mobile login DB query failed")
        raise HTTPException(503, "ဝန်ဆောင်မှုကို ယာယီအသုံးမပြုနိုင်ပါ။")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    if user is None or not verify_password(password, user["password"]):
        raise HTTPException(401, "Username သို့မဟုတ် Password မှားယွင်းနေပါသည်။")
    if str(user.get("status")) != "1":
        raise HTTPException(403, "သင့်အကောင့်ကို အသုံးပြုခွင့် ပိတ်ထားပါသည်။")

    try:
        role_id = int(user.get("role_id"))
        role = ROLE_NAMES.get(role_id)
    except (TypeError, ValueError):
        role = str(user.get("role_id") or "").strip().lower()
        role_id = None

    payload = {
        "user_id": user["id"], "role": role, "role_id": role_id,
        "login_name": user["login_name"],
        "stateID": user.get("stateID"), "districtID": user.get("districtID"), "townshipID": user.get("townshipID"),
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    return {
        "status": "success", "token": token, "role": role,
        "redirect": ROLE_HOME.get(role, "/survey/part1")
    }

@app.get("/logout")
async def logout_page(request: Request):
    request.session.clear(); return RedirectResponse("/", status_code=303)

@app.post("/api/logout")
async def api_logout(request: Request):
    request.session.clear(); return {"status": "success"}

@app.post("/api/web-auto-logout")
async def web_auto_logout(request: Request):
    if request.session.get("device_type") == "web":
        request.session.clear(); return {"status": "success"}
    return {"status": "ignored"}

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={})

# ============================================================
# 📋 SURVEY FORMS
# ============================================================
@app.get("/form", response_class=HTMLResponse)
async def form_page(request: Request, db: Session = Depends(get_db)):
    try: user = get_signed_in_user(request)
    except HTTPException: return RedirectResponse("/", status_code=303)
    if user["role"] == "enumerator": return RedirectResponse("/enumerator/part1", status_code=303)
    if user["role"] not in ("admin", "staff"): raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")
    states = _get_all_states()
    
    # ⭐ sequential form_id
    #total_records = db.query(PersonCV).count() or 0
    #next_num = total_records + 1
    #new_form_id = generate_formatted_id(next_num)
    new_form_id = "TEMP-FORM-ID-0001"
    print(f"temp form ID from form {new_form_id}")
    return templates.TemplateResponse(request=request, name="FormPart1.html", context={
        "active_page": "survey", "states": states, "user": user,
        "role": user.get("role", "staff"), "form_id": new_form_id,
        "survey_prefix": "/survey"
    })

@app.get("/survey/part1")
async def survey_part1(request: Request, db: Session = Depends(get_db)):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    if user.get("role") == "enumerator": return RedirectResponse("/enumerator/part1", status_code=303)
    states = _get_all_states()
    
    # ⭐ sequential form_id
    #total_records = db.query(PersonCV).count() or 0
    #next_num = total_records + 1
    #new_form_id = generate_formatted_id(next_num)
    new_form_id = "TEMP-FORM-ID-0001"
    print(f"temp form ID from surveyPart1{new_form_id}")
    return templates.TemplateResponse(request=request, name="FormPart1.html", context={
        "active_page": "survey", "states": states, "user": user,
        "role": user.get("role", "staff"), "form_id": new_form_id,
        "survey_prefix": "/survey"
    })


# ============================================================
# 🌐 LOCATION / DROPDOWN APIs
# ============================================================
@app.get("/api/locations")
async def get_locations(request: Request, state_id: str = Query(None), district_id: str = Query(None), township_id: str = Query(None)):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(401, "Login လုပ်ပါ။")
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township", "enumerator", "staff"): raise HTTPException(403, "ဤဒေတာကို ကြည့်ခွင့်မရှိပါ။")
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        if role == "state":
            state_id = user.get("stateID")
            if not state_id: raise HTTPException(403, "အကောင့်တွင် တိုင်းဒေသကြီး/ပြည်နယ် မသတ်မှတ်ရသေးပါ။")
        elif role == "district":
            state_id = user.get("stateID"); district_id = user.get("districtID")
            if not state_id or not district_id: raise HTTPException(403, "အကောင့်တွင် သက်ဆိုင်ရာ ခရိုင် မသတ်မှတ်ရသေးပါ။")
        elif role == "township":
            state_id = user.get("stateID"); district_id = user.get("districtID"); township_id = user.get("townshipID")
            if not state_id or not district_id or not township_id: raise HTTPException(403, "အကောင့်တွင် သက်ဆိုင်ရာ မြို့နယ် မသတ်မှတ်ရသေးပါ။")
        elif role == "enumerator":
            state_id = user.get("stateID"); district_id = user.get("districtID"); township_id = user.get("townshipID")
            if not state_id or not district_id or not township_id: raise HTTPException(403, "Enumerator အကောင့်တွင် သတ်မှတ်ထားသော Location မပြည့်စုံပါ။")

        if not state_id:
            cursor.execute("SELECT DISTINCT stateID, stateName FROM state ORDER BY stateName"); return cursor.fetchall()
        if not district_id:
            cursor.execute("SELECT DISTINCT districtID, districtName FROM district WHERE stateID = %s ORDER BY districtName", (state_id,)); return cursor.fetchall()
        if not township_id:
            cursor.execute("SELECT DISTINCT townshipID, townshipName FROM township WHERE stateID = %s AND districtID = %s ORDER BY townshipName", (state_id, district_id)); return cursor.fetchall()
        cursor.execute("SELECT DISTINCT QVID, QVName FROM qv WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName", (state_id, district_id, township_id)); return cursor.fetchall()
    finally:
        cursor.close(); conn.close()

@app.get("/fetchStates")
async def fetch_states():
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT stateID, stateName FROM state ORDER BY stateName"); return {"states": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/fetchDistricts/{stateID}")
async def fetch_districts(stateID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT districtID, districtName FROM district WHERE stateID = %s ORDER BY districtName", (stateID,)); return {"districts": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/fetchTownship/{districtID}/{stateID}")
async def fetch_townships(stateID: str, districtID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT townshipID, townshipName FROM township WHERE stateID = %s AND districtID = %s ORDER BY townshipName", (stateID, districtID)); return {"townships": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/fetchVillageTract/{townshipID}/{districtID}/{stateID}")
async def fetch_village_tracts(townshipID: str, districtID: str, stateID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT QVID AS id, QVName AS name FROM qv WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName", (stateID, districtID, townshipID)); return {"villages": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/fetchQV/{stateID}/{townshipID}/{districtID}")
async def get_QVs(stateID: str, townshipID: str, districtID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT QVID AS qvID, QVName AS qvName FROM qv WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName", (stateID, districtID, townshipID)); return {"qvs": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/sendStateValue/{stateID}")
async def getStateID(stateID: str, request: Request):
    request.session["stateID"] = {"stateID": stateID}; return {"message": "store stateID"}

@app.get("/fetchlargeAniSpecies/{largeAniID}")
async def get_largeAniSpecies(largeAniID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT speciesID, speciesName FROM largespecies WHERE animalID = %s ORDER BY speciesID", (largeAniID,)); return {"largeSpecies": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/fetchsmallAniSpecies/{youngAniID}")
async def get_youngAniSpecies(youngAniID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT speciesID, speciesName FROM youngspecies WHERE animalID = %s ORDER BY speciesID", (youngAniID,)); return {"smallSpecies": cursor.fetchall()}
    finally: cursor.close(); conn.close()

@app.get("/fetchLiveStockSpecies/{liveStockID}")
async def get_liveStockSpecies(liveStockID: str):
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try: cursor.execute("SELECT speciesID, speciesName FROM livestockspecies WHERE animalID = %s ORDER BY speciesID", (liveStockID,)); return {"liveStockSpecies": cursor.fetchall()}
    finally: cursor.close(); conn.close()

# ============================================================
# 🔗 MERGED FORM ROUTING
# ============================================================
class AnimalDataCompat(BaseModel):
    formID: str; animalTypeID: str; animalID: str; speciesID: Optional[str] = None; ageID: Optional[str] = None; genderID: Optional[str] = None; dataCount: int = 0

def _compat_session_state_id(request: Request):
    value = request.session.get("stateID")
    if isinstance(value, dict): return value.get("stateID")
    return value

def _get_all_breeding_animals():
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try: cursor.execute("SELECT animalID, animalName FROM breedingstock WHERE animalTypeID = %s ORDER BY animalID", ("atID04",)); return cursor.fetchall()
        finally: cursor.close(); conn.close()
    except Exception as exc:
        logger.warning("Breeding animal lookup failed: %s", exc); return []

def _require_enumerator_web(request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator": raise HTTPException(status_code=403, detail="Enumerator (Role 6) အကောင့်လိုအပ်ပါသည်။")
    for key, label in (("stateID", "တိုင်းဒေသကြီး/ပြည်နယ်"), ("districtID", "ခရိုင်"), ("townshipID", "မြို့နယ်")):
        if not user.get(key): raise HTTPException(status_code=403, detail=f"Enumerator အကောင့်တွင် {label} မသတ်မှတ်ရသေးပါ။")
    return user

def _guard_enumerator_web_route(request: Request):
    if request.url.path.startswith("/enumerator/"): return _require_enumerator_web(request)
    return None

@app.post("/survey/part1")
@app.post("/enumerator/part1")
async def compat_process_step_1(
    request: Request, formID: Annotated[str, Form()], districtID: Annotated[str, Form()], townshipID: Annotated[str, Form()],
    qvID: Annotated[str, Form()], wardName: Annotated[str, Form()], houseHoldNo: Annotated[str, Form()], interviewDate: Annotated[str, Form()],
    name: Annotated[str, Form()] = "", gender: Annotated[str, Form()] = "", eduStatus: Annotated[str, Form()] = "", phoneNo: Annotated[str, Form()] = "",
    age: Annotated[str, Form()] = "", headName: Annotated[str, Form()] = "", headEduStatus: Annotated[str, Form()] = "", headGender: Annotated[str, Form()] = "",
    headPhoneNo: Annotated[str, Form()] = "", headAge: Annotated[str, Form()] = "",
    collection_status: Annotated[str, Form(alias="status")] = "1",
    db: Session = Depends(get_db),
):
    print(f"formID from part1 {formID}")
    enumerator_user = _guard_enumerator_web_route(request)
    if enumerator_user:
        state_id = str(enumerator_user["stateID"])
        assigned_district = str(enumerator_user["districtID"]); assigned_township = str(enumerator_user["townshipID"])
        if str(districtID) != assigned_district or str(townshipID) != assigned_township: raise HTTPException(status_code=403, detail="သတ်မှတ်ထားသော ခရိုင်/မြို့နယ်ကိုသာ ရွေးချယ်နိုင်ပါသည်။")
        conn_check = get_db_connection(); cur_check = conn_check.cursor()
        try:
            cur_check.execute("SELECT 1 FROM qv WHERE QVID = %s AND stateID = %s AND districtID = %s AND townshipID = %s LIMIT 1", (qvID, state_id, assigned_district, assigned_township))
            if not cur_check.fetchone(): raise HTTPException(status_code=403, detail="သတ်မှတ်ထားသော မြို့နယ်အတွင်းရှိ ရပ်ကွက်/ကျေးရွာအုပ်စုကို ရွေးချယ်ပါ။")
        finally: cur_check.close(); conn_check.close()
        request.session["stateID"] = state_id
    else:
        state_id = _compat_session_state_id(request)
        if not state_id: raise HTTPException(status_code=400, detail="ပြည်နယ်/တိုင်းကို အရင်ရွေးချယ်ပါ။")

    if collection_status not in ("0", "1"):
        raise HTTPException(400, "ကောက်ယူမှုအခြေအနေ မမှန်ကန်ပါ။")
    if not enumerator_user and collection_status != "1":
        raise HTTPException(400, "ဤစာမျက်နှာမှ အချက်အလက် ကောက်ယူရန်လိုအပ်ပါသည်။")
    try:
        datetime.strptime(interviewDate, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "တွေ့ဆုံမေးမြန်းသည့်နေ့ မှန်ကန်စွာဖြည့်ပါ။")
    if not all(value.strip() for value in (wardName, houseHoldNo)):
        raise HTTPException(400, "ရပ်ကွက်/ကျေးရွာနှင့် အိမ်ထောင်စုအမှတ် ဖြည့်ပါ။")
    if collection_status == "1":
        if not all(value.strip() for value in (name, gender, eduStatus, phoneNo, age, headName, headEduStatus, headGender, headPhoneNo, headAge)):
            raise HTTPException(400, "ဖြေဆိုသူနှင့် အိမ်ထောင်ဦးစီး အချက်အလက်များ ပြည့်စုံစွာဖြည့်ပါ။")
        if not age.isdigit() or not headAge.isdigit():
            raise HTTPException(400, "အသက်ကို ကိန်းဂဏန်းဖြင့် ဖြည့်ပါ။")
    else:
        # Ignore any hidden or stale personal/animal values on a non-collection visit.
        name = gender = eduStatus = phoneNo = headName = headEduStatus = headGender = headPhoneNo = ""
        age = headAge = "0"
        for key in ("animals_data", "livestock_data", "breeding_animals_data", "interviewer", "interviewerPhoneNo"):
            request.session.pop(key, None)

    request.session["formID"] = formID
    request.session["step1"] = {
        "status": int(collection_status),
        "districtID": districtID, "townshipID": townshipID, "qvID": qvID, "wardName": wardName, "houseHoldNo": houseHoldNo,
        "interviewDate": interviewDate, "name": name, "gender": gender, "eduStatus": eduStatus, "phoneNo": phoneNo,
        "age": age, "headName": headName, "headEduStatus": headEduStatus, "headGender": headGender, "headPhoneNo": headPhoneNo, "headAge": headAge,
    }
    if collection_status == "0":
        return await compat_submit_survey(formID, request, db)
    survey_prefix = "/enumerator" if enumerator_user else "/survey"
    return RedirectResponse(f"{survey_prefix}/part2/{quote(formID, safe='')}", status_code=303)

@app.get("/survey/part2/{form_id}")
@app.get("/enumerator/part2/{form_id}")
async def get_survey_part2(form_id: str, request: Request):
    enumerator_user = _guard_enumerator_web_route(request)
    state_id = str(enumerator_user["stateID"]) if enumerator_user else _compat_session_state_id(request)
    request.session["formID"] = form_id
    return templates.TemplateResponse(request=request, name="FormPart2.html", context={"active_page": "survey", "largeAnimals": _get_all_large_animals(), "smallAnimals": _get_all_small_animals(), "form_id": form_id, "stateID": state_id, "states": _get_all_states(), "user": request.session.get("user"), "role": (request.session.get("user") or {}).get("role", "staff"), "survey_prefix": "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"})

@app.post("/survey/part2/{formID}")
@app.post("/enumerator/part2/{formID}")
async def compat_process_step_2(formID: str, records: List[List[AnimalDataCompat]], request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    large_records = records[0] if len(records) > 0 else []
    small_records = records[1] if len(records) > 1 else []
    request.session["animals_data"] = {"largeAnimalsTable": [item.model_dump() for item in large_records], "youngAnimalsTable": [item.model_dump() for item in small_records]}
    return JSONResponse(content={"status": "success", "redirect_url": f"{'/enumerator' if request.url.path.startswith('/enumerator/') else '/survey'}/part3/{formID}"})

@app.get("/survey/part3/{form_id}")
@app.get("/enumerator/part3/{form_id}")
async def compat_process_step_3(form_id: str, request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = form_id
    return templates.TemplateResponse(request=request, name="FormPart3.html", context={"active_page": "survey", "livestockAni": _get_all_livestock_animals(), "form_id": form_id, "states": _get_all_states(), "user": request.session.get("user"), "role": (request.session.get("user") or {}).get("role", "staff"), "survey_prefix": "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"})

@app.post("/survey/part4/{formID}")
@app.post("/enumerator/part4/{formID}")
async def compat_process_step_4(formID: str, data: List[AnimalDataCompat], request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    request.session["livestock_data"] = jsonable_encoder(data)
    return JSONResponse(content={"status": "success", "redirect_url": f"{'/enumerator' if request.url.path.startswith('/enumerator/') else '/survey'}/part5/{formID}"})

@app.get("/survey/part5/{formID}")
@app.get("/enumerator/part5/{formID}")
async def compat_process_part5(formID: str, request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    return templates.TemplateResponse(request=request, name="FormPart4_5.html", context={"active_page": "survey", "breedingStockAni": _get_all_breeding_animals(), "form_id": formID, "states": _get_all_states(), "user": request.session.get("user"), "role": (request.session.get("user") or {}).get("role", "staff"), "survey_prefix": "/enumerator" if request.url.path.startswith("/enumerator/") else "/survey"})

@app.post("/survey/sendForm4Data/{formID}")
@app.post("/enumerator/sendForm4Data/{formID}")
async def compat_save_breeding_data(formID: str, data: List[AnimalDataCompat], request: Request):
    _guard_enumerator_web_route(request)
    request.session["formID"] = formID
    request.session["breeding_animals_data"] = jsonable_encoder(data)
    return JSONResponse(content={"status": "success", "redirect_url": f"{'/enumerator' if request.url.path.startswith('/enumerator/') else '/survey'}/submit/{formID}"})

@app.post("/survey/sendForm5Data/{form_id}")
@app.post("/enumerator/sendForm5Data/{form_id}")
async def compat_save_interviewer_info(form_id: str, data: dict, request: Request):
    _guard_enumerator_web_route(request)
    interviewer_name = str(data.get("name") or "").strip(); interviewer_phone = str(data.get("phone") or "").strip()
    if not interviewer_name or not interviewer_phone: raise HTTPException(status_code=422, detail="အင်တာဗျူးကောက်ယူသူအမည်နှင့် ဖုန်းနံပါတ် ဖြည့်ပါ။")
    request.session["formID"] = form_id
    request.session["interviewer"] = interviewer_name
    request.session["interviewerPhoneNo"] = interviewer_phone
    return JSONResponse(content={"status": "success", "redirect_url": f"{'/enumerator' if request.url.path.startswith('/enumerator/') else '/survey'}/submit/{form_id}"})

@app.get("/survey/submit/{formID}")
@app.get("/enumerator/submit/{formID}")
async def compat_submit_survey(formID: str, request: Request,db: Session = Depends(get_db)):
    enumerator_user = _guard_enumerator_web_route(request)

    state_id = (
        str(enumerator_user["stateID"])
        if enumerator_user
        else _compat_session_state_id(request)
    )

    step1 = request.session.get("step1") or {}
    session_user = request.session.get("user") or {}
    user_id = session_user.get("id")

    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="User session မတွေ့ပါ။ ပြန် Login လုပ်ပါ။"
        )

    # Enumerator location permission
    if enumerator_user:
        if (
            str(step1.get("districtID"))
            != str(enumerator_user["districtID"])
            or str(step1.get("townshipID"))
            != str(enumerator_user["townshipID"])
        ):
            raise HTTPException(
                status_code=403,
                detail="Survey Location သည် Enumerator ၏ သတ်မှတ်ဧရိယာနှင့် မကိုက်ညီပါ။"
            )

    if not state_id or not step1:
        raise HTTPException(
            status_code=400,
            detail="Survey အချက်အလက် မပြည့်စုံပါ။"
        )

    collecting = step1.get("status", 1) == 1
    interviewer = request.session.get("interviewer") if collecting else ""
    interviewer_phone = request.session.get("interviewerPhoneNo") if collecting else ""

    if collecting and (not interviewer or not interviewer_phone):
        raise HTTPException(
            status_code=400,
            detail="အင်တာဗျူးကောက်ယူသူအချက်အလက် မရှိပါ။"
        )

    # Collect all animal records from the current session
    all_animals = []

    animals_data = request.session.get("animals_data") or {}

    if isinstance(animals_data, dict):
        all_animals.extend(
            animals_data.get("largeAnimalsTable") or []
        )
        all_animals.extend(
            animals_data.get("youngAnimalsTable") or []
        )

    all_animals.extend(
        request.session.get("livestock_data") or []
    )
    all_animals.extend(
        request.session.get("breeding_animals_data") or []
    )
    if not collecting:
        all_animals = []
    # total_records = db.query(PersonCV).count() or 0
    # next_num = total_records + 1
    # new_form_id = generate_formatted_id(next_num)
    # print(f"tempID: {formID}")
    # formID=new_form_id
    # print(f"FormID: {formID}")
    # ⬇️⬇️⬇️ ဒီ block ကို အစားထိုးပါ
    current_year = datetime.now().year
    try:
        row = db.execute(
            text("""SELECT COALESCE(MAX(CAST(SUBSTRING(formID, 11) AS UNSIGNED)), 0) + 1 AS next_num
                    FROM personcv 
                    WHERE formID LIKE :pattern"""),
            {"pattern": f"FORM-{current_year}-%"}
        ).fetchone()
        next_num = int(row[0]) if row and row[0] else 1
    except Exception as e:
        logger.error(f"Form ID generation failed: {e}")
        raise HTTPException(500, "Form ID ဖန်တီးမှု မအောင်မြင်ပါ။")

    new_form_id = generate_formatted_id(next_num)
    logger.info(f"tempID={formID}, generated FormID={new_form_id} (MAX-based)")
    formID = new_form_id

    conn = get_db_connection()
    cursor = conn.cursor()
    

    try:
        conn.start_transaction()

        # 1. Check whether this form already exists.
        # Lock the row while checking ownership and updating.
        cursor.execute(
            """
            SELECT userId
            FROM personcv
            WHERE formID = %s
            FOR UPDATE
            """,
            (formID,)
        )

        existing_form = cursor.fetchone()

        if existing_form:
            existing_user_id = existing_form[0]

            # Never allow another user to overwrite this form.
            if (
                existing_user_id is None
                or str(existing_user_id) != str(user_id)
            ):
                raise HTTPException(
                    status_code=403,
                    detail="ဤ Survey Form ကို ပြင်ဆင်ခွင့်မရှိပါ။"
                )

            # 2. Update the existing form owned by this user.
            cursor.execute(
                """
                UPDATE personcv
                SET
                    stateID = %s,
                    districtID = %s,
                    townshipID = %s,
                    QVID = %s,
                    WardName = %s,
                    householdNo = %s,
                    interviewDate = %s,
                    name = %s,
                    gender = %s,
                    eduStatus = %s,
                    phoneNo = %s,
                    age = %s,
                    headName = %s,
                    headEduStatus = %s,
                    headGender = %s,
                    headPhoneNo = %s,
                    headAge = %s,
                    Interviewer = %s,
                    interviewerPhoneNo = %s,
                    status = %s
                WHERE formID = %s
                  AND userId = %s
                """,
                (
                    state_id,
                    step1.get("districtID"),
                    step1.get("townshipID"),
                    step1.get("qvID"),
                    step1.get("wardName"),
                    step1.get("houseHoldNo"),
                    step1.get("interviewDate"),
                    step1.get("name"),
                    step1.get("gender"),
                    step1.get("eduStatus"),
                    step1.get("phoneNo"),
                    int(step1.get("age") or 0),
                    step1.get("headName"),
                    step1.get("headEduStatus"),
                    step1.get("headGender"),
                    step1.get("headPhoneNo"),
                    step1.get("headAge"),
                    interviewer,
                    interviewer_phone,
                    int(collecting),
                    formID,
                    user_id,
                )
            )

            if cursor.rowcount == 0:
                # A row may be unchanged, so verify ownership/existence.
                cursor.execute(
                    """
                    SELECT 1
                    FROM personcv
                    WHERE formID = %s AND userId = %s
                    """,
                    (formID, user_id)
                )
                if not cursor.fetchone():
                    raise HTTPException(
                        status_code=403,
                        detail="Survey Form ကို ပြင်ဆင်ခွင့်မရှိပါ။"
                    )

            # Replace old animal records within this transaction.
            cursor.execute(
                """
                DELETE FROM collecteddata
                WHERE formID = %s
                """,
                (formID,)
            )

        else:
            # 3. Insert a new form only when it does not exist.
            cursor.execute(
                """
                INSERT INTO personcv (
                    formID, userId, stateID, districtID,
                    townshipID, QVID, WardName, householdNo,
                    interviewDate, name, gender, eduStatus,
                    phoneNo, age, headName, headEduStatus,
                    headGender, headPhoneNo, headAge,
                    Interviewer, interviewerPhoneNo, status
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    formID,
                    user_id,
                    state_id,
                    step1.get("districtID"),
                    step1.get("townshipID"),
                    step1.get("qvID"),
                    step1.get("wardName"),
                    step1.get("houseHoldNo"),
                    step1.get("interviewDate"),
                    step1.get("name"),
                    step1.get("gender"),
                    step1.get("eduStatus"),
                    step1.get("phoneNo"),
                    int(step1.get("age") or 0),
                    step1.get("headName"),
                    step1.get("headEduStatus"),
                    step1.get("headGender"),
                    step1.get("headPhoneNo"),
                    step1.get("headAge"),
                    interviewer,
                    interviewer_phone,
                    int(collecting),
                )
            )

        # 4. Save the current animal records.
        for item in all_animals:
            cursor.execute(
                """
                INSERT INTO collecteddata (
                    formID, animalTypeID, animalID,
                    speciesID, ageID, genderID, dataCount
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    formID,
                    str(item.get("animalTypeID") or ""),
                    str(item.get("animalID") or ""),
                    str(item.get("speciesID") or ""),
                    str(item.get("ageID") or ""),
                    str(item.get("genderID") or ""),
                    int(item.get("dataCount") or 0),
                )
            )
        try:
            cursor.execute(
                """UPDATE householdRegister
                SET collectionStatus = %s,
                    updatedAt = NOW()
                WHERE stateID = %s
                    AND districtID = %s
                    AND townshipID = %s
                    AND QVID = %s
                    AND WardName = %s
                    AND householdNo = %s
                    AND createdBy = %s""",
                (
                    "collected" if collecting else "cannot_collect",
                    state_id,
                    step1.get("districtID"),
                    step1.get("townshipID"),
                    step1.get("qvID"),
                    step1.get("wardName"),
                    step1.get("houseHoldNo"),
                    user_id,
                ),
            )
        except Exception as e:
            # Household record မရှိရင် skip (silent — survey ကို မထိ)
            logger.warning(f"householdRegister status update skipped: {e}")

        # Commit only after both person and animal records succeed.
        conn.commit()

        # Clear the session only after a successful commit.
        for session_key in (
            "stateID",
            "formID",
            "step1",
            "animals_data",
            "livestock_data",
            "breeding_animals_data",
            "interviewer",
            "interviewerPhoneNo",
        ):
            request.session.pop(session_key, None)

        return {
            "status": "success",
            "message": "Survey saved successfully",
            "formID": formID,
            "animalRecordsSaved": len(all_animals),
            "collectionStatus": int(collecting),
            "userId": user_id,
        }

    except HTTPException:
        conn.rollback()
        raise

    except Exception:
        conn.rollback()
        logger.exception(
            "Survey submit failed for formID=%s, userId=%s",
            formID,
            user_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Survey သိမ်းဆည်းမှု မအောင်မြင်ပါ။ Server log ကို စစ်ဆေးပါ။"
        )

    finally:
        cursor.close()
        conn.close()

# ============================================================
# 📊 DASHBOARD / REPORTS
# ============================================================
@app.get("/admin")
async def admin_dashboard(request: Request,
                          state: str = Query(None), district: str = Query(None),
                          township: str = Query(None), qv: str = Query(None),
                          start_date: str = Query(""), end_date: str = Query("")):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    role = user.get("role", "admin")
    if role == "admin": return RedirectResponse("/system/users", status_code=303)
    if role == "enumerator": return RedirectResponse("/survey/dashboard", status_code=303)
    if role == "staff": return RedirectResponse("/survey/part1", status_code=303)
    if role not in ("union", "state", "district", "township"): raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    region_name, animals, stats = query_dashboard_data(
        user, state, district, township, qv,
        start_date=start_date, end_date=end_date
    )
    return templates.TemplateResponse(request=request, name="reportDashboard.html", context={
        "stats": stats, "animals": animals, "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "", "user_township_id": user.get("townshipID") or "",
        "filters": {
            "state": state, "district": district, "township": township, "qv": qv,
            "start_date": start_date, "end_date": end_date,
        },
        "active_page": "home",
    })

@app.get("/admin/records", response_class=HTMLResponse)
async def admin_records(request: Request,
                        state: str = Query(""), district: str = Query(""),
                        township: str = Query(""), qv: str = Query(""),
                        search: str = Query(""),
                        start_date: str = Query(""), end_date: str = Query("")):
    try: user = get_signed_in_user(request)
    except HTTPException: return RedirectResponse("/", status_code=303)
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"): raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    records = []; district_name_for_js = ""; township_name_for_js = ""
    try:
        if role == "district" and user.get("districtID"):
            cursor.execute("SELECT districtName FROM district WHERE stateID = %s AND districtID = %s", (user.get("stateID"), user.get("districtID")))
            d_row = cursor.fetchone(); district_name_for_js = d_row["districtName"] if d_row else ""
        elif role == "township" and user.get("townshipID"):
            cursor.execute("SELECT townshipName FROM township WHERE stateID = %s AND districtID = %s AND townshipID = %s", (user.get("stateID"), user.get("districtID"), user.get("townshipID")))
            t_row = cursor.fetchone(); township_name_for_js = t_row["townshipName"] if t_row else ""
            cursor.execute("SELECT districtName FROM district WHERE stateID = %s AND districtID = %s", (user.get("stateID"), user.get("districtID")))
            d_row = cursor.fetchone(); district_name_for_js = d_row["districtName"] if d_row else ""

        rows = _query_household_records(
            cursor, role, user, state, district, township, qv, search,
            start_date=start_date, end_date=end_date
        )
        for r in rows:
            detail = _query_household_detail(cursor, r["formID"])
            records.append(_build_household_record(r, detail))
    except SQLAlchemyError as e: logger.error(f"admin_records DB error: {e}")
    finally: cursor.close(); conn.close()
    return templates.TemplateResponse(request=request, name="reportFormData.html", context={
        "active_page": "records", "role": role, "records": records,
        "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "", "user_district_name": district_name_for_js,
        "user_township_id": user.get("townshipID") or "", "user_township_name": township_name_for_js,
        "filters": {
            "state": state, "district": district, "township": township, "qv": qv,
            "search": search, "start_date": start_date, "end_date": end_date,
        },
    })

@app.get("/api/admin/filter-options")
async def admin_filter_options(request: Request,
                               state: str = Query(""), district: str = Query(""),
                               township: str = Query(""), qv: str = Query(""),
                               start_date: str = Query(""), end_date: str = Query("")):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(status_code=401, detail="Login လုပ်ရန်လိုအပ်ပါသည်။")
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"): raise HTTPException(status_code=403, detail="ခွင့်မရှိပါ။")
    if role == "state": state = user.get("stateID") or ""
    elif role == "district": state = user.get("stateID") or ""; district = user.get("districtID") or ""
    elif role == "township": state = user.get("stateID") or ""; district = user.get("districtID") or ""; township = user.get("townshipID") or ""
    if not qv: return {"formIDs": [], "householdNos": [], "headNames": []}
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        where = ["QVID = %s"]; args = [qv]
        if state: where.append("stateID = %s"); args.append(state)
        if district: where.append("districtID = %s"); args.append(district)
        if township: where.append("townshipID = %s"); args.append(township)

        s, e = _resolve_date_range(start_date, end_date)
        if s and e:
            where.append("DATE(interviewDate) BETWEEN %s AND %s")
            args.extend([s, e])

        where_sql = " AND ".join(where)
        cursor.execute(f"SELECT DISTINCT formID AS value FROM personcv WHERE {where_sql} AND formID IS NOT NULL AND formID <> '' ORDER BY formID", tuple(args)); form_rows = cursor.fetchall()
        cursor.execute(f"SELECT DISTINCT householdNo AS value FROM personcv WHERE {where_sql} AND householdNo IS NOT NULL AND householdNo <> '' ORDER BY householdNo", tuple(args)); household_rows = cursor.fetchall()
        cursor.execute(f"SELECT DISTINCT headName AS value FROM personcv WHERE {where_sql} AND headName IS NOT NULL AND headName <> '' ORDER BY headName", tuple(args)); head_rows = cursor.fetchall()
        return {"formIDs": [{"value": r["value"], "label": r["value"]} for r in form_rows], "householdNos": [{"value": r["value"], "label": r["value"]} for r in household_rows], "headNames": [{"value": r["value"], "label": r["value"]} for r in head_rows]}
    except Exception: logger.exception("admin_filter_options database error"); raise HTTPException(status_code=500, detail="Dropdown data ရယူရာတွင် Database error ဖြစ်နေပါသည်။")
    finally: cursor.close(); conn.close()

@app.get("/api/admin/records")
async def api_admin_records(request: Request,
                            state: str = Query(""), district: str = Query(""),
                            township: str = Query(""), qv: str = Query(""),
                            search: str = Query(""), formID: str = Query(""),
                            householdNo: str = Query(""), headName: str = Query(""),
                            start_date: str = Query(""), end_date: str = Query("")):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(401, "Login လုပ်ပါ။")
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"): raise HTTPException(403, "ကြည့်ခွင့်မရှိပါ။")
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        rows = _query_household_records(
            cursor, role, user, state=state, district=district, township=township,
            qv=qv, search=search, form_id=formID, household_no=householdNo,
            head_name=headName, start_date=start_date, end_date=end_date
        )
        records = []
        for r in rows:
            detail = _query_household_detail(cursor, r["formID"])
            records.append(_build_household_record(r, detail))
        return {"status": "success", "records": records, "count": len(records)}
    except SQLAlchemyError: logger.exception("api_admin_records DB error"); raise HTTPException(500, "Database error ဖြစ်နေပါသည်။")
    finally: cursor.close(); conn.close()

@app.get("/report/1", response_class=HTMLResponse)
async def report1_page(request: Request,
                       state: str = Query(""), district: str = Query(""),
                       township: str = Query(""), qv: str = Query(""),
                       start_date: str = Query(""), end_date: str = Query("")):
    try: user = get_signed_in_user(request)
    except HTTPException: return RedirectResponse("/", status_code=303)
    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"): raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    region_name = ""; district_name_for_js = ""; township_name_for_js = ""
    try:
        if role == "union": region_name = "တစ်နိုင်ငံလုံး"
        elif role == "state":
            state = user["stateID"] or ""
            cursor.execute("SELECT stateName AS name FROM state WHERE stateID = %s", (user["stateID"],)); r = cursor.fetchone(); region_name = r["name"] if r else user["stateID"]
        elif role == "district":
            state = user["stateID"] or ""; district = user["districtID"] or ""
            cursor.execute("SELECT districtName AS name FROM district WHERE stateID = %s AND districtID = %s", (user["stateID"], user["districtID"])); r = cursor.fetchone()
            region_name = r["name"] if r else user["districtID"]; district_name_for_js = region_name
        elif role == "township":
            state = user["stateID"] or ""; district = user["districtID"] or ""; township = user["townshipID"] or ""
            cursor.execute("SELECT townshipName AS name FROM township WHERE stateID = %s AND districtID = %s AND townshipID = %s", (user["stateID"], user["districtID"], user["townshipID"])); r = cursor.fetchone()
            region_name = r["name"] if r else user["townshipID"]; township_name_for_js = region_name
            cursor.execute("SELECT districtName FROM district WHERE stateID = %s AND districtID = %s", (user["stateID"], user["districtID"])); d_row = cursor.fetchone(); district_name_for_js = d_row["districtName"] if d_row else ""

        large_rows    = _query_report1_one_type(cursor, "atID01", role, user, state, district, township, qv, start_date, end_date)
        small_rows    = _query_report1_one_type(cursor, "atID02", role, user, state, district, township, qv, start_date, end_date)
        poultry_rows  = _query_report1_one_type(cursor, "atID03", role, user, state, district, township, qv, start_date, end_date)
        breeding_rows = _query_report1_breeding(cursor, role, user, state, district, township, qv, start_date, end_date)
    except SQLAlchemyError as e: logger.error(f"Report 1 DB error: {e}"); large_rows = small_rows = poultry_rows = breeding_rows = []
    finally: cursor.close(); conn.close()

    def _sum(rows): return sum((r.get("total") or 0) for r in rows)
    stats = {"large": _sum(large_rows), "small": _sum(small_rows), "poultry": _sum(poultry_rows), "breeding": _sum(breeding_rows)}
    stats["total"] = sum(stats.values())

    return templates.TemplateResponse(request=request, name="report1.html", context={
        "active_page": "report1", "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "", "user_district_name": district_name_for_js,
        "user_township_id": user.get("townshipID") or "", "user_township_name": township_name_for_js,
        "filters": {
            "state": state, "district": district, "township": township, "qv": qv,
            "start_date": start_date, "end_date": end_date,
        },
        "large_rows": large_rows, "small_rows": small_rows,
        "poultry_rows": poultry_rows, "breeding_rows": breeding_rows, "stats": stats,
    })

# ============================================================
# 📈 REPORT 2
# ============================================================
def _get_animal_rows_by_type(animal_type_id: str):
    type_info = ANIMAL_TYPES.get(animal_type_id)
    if not type_info: return []
    table = type_info["table"]
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(f"SELECT animalID, animalName FROM {table} WHERE animalTypeID = %s ORDER BY animalID", (animal_type_id,))
            return cursor.fetchall()
        finally: cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_animal_rows_by_type({animal_type_id}): {e}")
        return []

def _get_species_options(animal_type_id: str, animal_id: str = ""):
    if animal_type_id not in ("atID01", "atID02", "atID03"): return []
    table = {"atID01": "largespecies", "atID02": "youngspecies", "atID03": "livestockspecies"}[animal_type_id]
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            if animal_id:
                cursor.execute(f"SELECT speciesID, speciesName FROM {table} WHERE animalID = %s ORDER BY speciesID", (animal_id,))
            else:
                cursor.execute(f"SELECT DISTINCT speciesID, speciesName FROM {table} ORDER BY speciesID")
            return [{"id": str(r["speciesID"]), "name": r["speciesName"]} for r in cursor.fetchall()]
        finally: cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_species_options: {e}")
        return []

def _get_age_options(animal_type_id: str):
    if animal_type_id == "atID04": return []
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT ageID, ageName FROM agetype WHERE animalTypeID = %s ORDER BY ageID", (animal_type_id,))
            rows = cursor.fetchall()
            seen, out = set(), []
            for r in rows:
                if r["ageName"] in seen: continue
                seen.add(r["ageName"]); out.append({"id": str(r["ageID"]), "name": r["ageName"]})
            return out
        finally: cursor.close(); conn.close()
    except SQLAlchemyError as e:
        logger.warning(f"⚠️ _get_age_options: {e}")
        return []

def _get_gender_options(animal_type_id: str):
    if animal_type_id == "atID04":
        return [{"id": "g01", "name": "အထီး"}, {"id": "g03", "name": "အမ"}]
    if animal_type_id == "atID03":
        return [{"id": "g01", "name": "အထီး"}, {"id": "g03", "name": "အမ"}]
    return [{"id": "g01", "name": "အထီး"}, {"id": "g02", "name": "သင်းကွပ်အထီး"}, {"id": "g03", "name": "အမ"}]

def _resolve_row_level(role: str):
    return {"union": "state", "admin": "state", "state": "district", "district": "township", "township": "qv"}.get(role, "state")

def _build_report2_data(role, user, animal_type_id, animal_id="", species_id="", age_id="", gender_id="",
                        start_date="", end_date=""):
    row_level = _resolve_row_level(role)
    try:
        conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
        pc_conds = ["1=1"]; pc_params = []
        if role == "state":
            pc_conds.append("pc.stateID = %s"); pc_params.append(user["stateID"])
        elif role == "district":
            pc_conds.extend(["pc.stateID = %s", "pc.districtID = %s"]); pc_params.extend([user["stateID"], user["districtID"]])
        elif role == "township":
            pc_conds.extend(["pc.stateID = %s", "pc.districtID = %s", "pc.townshipID = %s"]); pc_params.extend([user["stateID"], user["districtID"], user["townshipID"]])

        s, e = _resolve_date_range(start_date, end_date)
        if s and e:
            pc_conds.append("DATE(pc.interviewDate) BETWEEN %s AND %s"); pc_params.extend([s, e])
        pc_where = " AND ".join(pc_conds)

        cd_conds = ["cd.animalTypeID = %s"]; cd_params = [animal_type_id]
        if animal_id and str(animal_id).strip(): cd_conds.append("cd.animalID = %s"); cd_params.append(str(animal_id).strip())
        if species_id and str(species_id).strip(): cd_conds.append("cd.speciesID = %s"); cd_params.append(str(species_id).strip())
        if age_id and str(age_id).strip(): cd_conds.append("cd.ageID = %s"); cd_params.append(str(age_id).strip())
        if gender_id and str(gender_id).strip(): cd_conds.append("cd.genderID = %s"); cd_params.append(str(gender_id).strip())
        cd_where = " AND ".join(cd_conds)
        all_params = tuple(pc_params + cd_params)

        if row_level == "state":
            row_id_expr = "pc.stateID"; row_name_expr = "COALESCE(st.stateName, pc.stateID)"
            row_joins = "LEFT JOIN state AS st ON st.stateID = pc.stateID"
        elif row_level == "district":
            row_id_expr = "CONCAT(pc.stateID, '|', pc.districtID)"; row_name_expr = "COALESCE(dt.districtName, pc.districtID)"
            row_joins = "LEFT JOIN district AS dt ON dt.stateID = pc.stateID AND dt.districtID = pc.districtID"
        elif row_level == "township":
            row_id_expr = "CONCAT(pc.stateID, '|', pc.districtID, '|', pc.townshipID)"; row_name_expr = "COALESCE(ts.townshipName, pc.townshipID)"
            row_joins = "LEFT JOIN township AS ts ON ts.stateID = pc.stateID AND ts.districtID = pc.districtID AND ts.townshipID = pc.townshipID"
        else:
            row_id_expr = "CONCAT(pc.stateID, '|', pc.districtID, '|', pc.townshipID, '|', pc.QVID)"; row_name_expr = "COALESCE(qv.QVName, pc.QVID)"
            row_joins = "LEFT JOIN qv ON qv.stateID = pc.stateID AND qv.districtID = pc.districtID AND qv.townshipID = pc.townshipID AND qv.QVID = pc.QVID"

        col_sql = f"""
            SELECT DISTINCT cd.animalID AS animal_id, cd.speciesID AS species_id, cd.ageID AS age_id
            FROM collecteddata AS cd
            JOIN personcv AS pc ON pc.formID = cd.formID
            WHERE {pc_where} AND {cd_where}
            ORDER BY cd.animalID, cd.speciesID, cd.ageID
        """
        cursor.execute(col_sql, all_params); col_rows = cursor.fetchall()
        if not col_rows:
            cursor.close(); conn.close(); return [], [], 0, row_level

        def _lookup_animal_name(atid, aid):
            try:
                table = {"atID01": "largeanimals", "atID02": "younganimals", "atID03": "livestock"}.get(atid, "breedingstock")
                cursor.execute(f"SELECT animalName FROM {table} WHERE animalID = %s", (aid,))
                r = cursor.fetchone(); return r["animalName"] if r else str(aid)
            except Exception: return str(aid)

        def _lookup_species_name(atid, aid, spid):
            if atid not in ("atID01", "atID02", "atID03"): return str(spid)
            table = {"atID01": "largespecies", "atID02": "youngspecies", "atID03": "livestockspecies"}[atid]
            try:
                cursor.execute(f"SELECT speciesName FROM {table} WHERE speciesID = %s AND animalID = %s", (spid, aid))
                r = cursor.fetchone(); return r["speciesName"] if r else str(spid)
            except Exception: return str(spid)

        def _lookup_age_name(atid, aid, ageid):
            try:
                cursor.execute("SELECT ageName FROM agetype WHERE ageID = %s AND animalTypeID = %s AND (animalID IS NULL OR TRIM(animalID) = '' OR animalID = %s)", (ageid, atid, aid))
                r = cursor.fetchone()
                if r: return r["ageName"]
                cursor.execute("SELECT ageName FROM age WHERE ageID = %s", (ageid,))
                r = cursor.fetchone(); return r["ageName"] if r else str(ageid)
            except Exception: return str(ageid)

        genders_for_col = _get_gender_options(animal_type_id)
        gender_names = {g["id"]: g["name"] for g in genders_for_col}
        gender_order = [g["id"] for g in genders_for_col]

        column_groups = []; seen_keys = set()
        for r in col_rows:
            aid = str(r["animal_id"] or ""); spid = str(r["species_id"] or ""); ageid = str(r["age_id"] or "")
            key = (aid, spid, ageid)
            if key in seen_keys: continue
            seen_keys.add(key)
            column_groups.append({
                "animal_id": aid, "animal_name": _lookup_animal_name(animal_type_id, aid),
                "species_id": spid, "species_name": _lookup_species_name(animal_type_id, aid, spid),
                "age_id": ageid, "age_name": _lookup_age_name(animal_type_id, aid, ageid),
                "genders": [{"id": gid, "name": gender_names[gid]} for gid in gender_order],
            })

        data_sql = f"""
            SELECT {row_id_expr} AS row_id, {row_name_expr} AS row_name,
                cd.animalID AS animal_id, cd.speciesID AS species_id, cd.ageID AS age_id, cd.genderID AS gender_id,
                SUM(COALESCE(cd.dataCount, 0)) AS total_count
            FROM collecteddata AS cd
            JOIN personcv AS pc ON pc.formID = cd.formID
            {row_joins}
            WHERE {pc_where} AND {cd_where}
            GROUP BY {row_id_expr}, {row_name_expr}, cd.animalID, cd.speciesID, cd.ageID, cd.genderID
            ORDER BY row_name, cd.animalID, cd.speciesID, cd.ageID, cd.genderID
        """
        cursor.execute(data_sql, all_params); data_rows = cursor.fetchall()

        total_sql = f"""
            SELECT {row_id_expr} AS row_id, {row_name_expr} AS row_name, SUM(COALESCE(cd.dataCount, 0)) AS row_total
            FROM collecteddata AS cd
            JOIN personcv AS pc ON pc.formID = cd.formID
            {row_joins}
            WHERE {pc_where} AND {cd_where}
            GROUP BY {row_id_expr}, {row_name_expr}
            ORDER BY row_name
        """
        cursor.execute(total_sql, all_params); total_rows = cursor.fetchall()
        cursor.close(); conn.close()

        cell_map = {}; row_names = {}
        for d in data_rows:
            rid = str(d["row_id"] or ""); row_names[rid] = d["row_name"] or rid
            key = (rid, str(d["animal_id"] or ""), str(d["species_id"] or ""), str(d["age_id"] or ""))
            cell_map.setdefault(key, {})
            cell_map[key][str(d["gender_id"] or "")] = int(d["total_count"] or 0)

        row_totals = {}
        for d in total_rows:
            rid = str(d["row_id"] or ""); row_names.setdefault(rid, d["row_name"] or rid); row_totals[rid] = int(d["row_total"] or 0)

        report_rows = []; grand_total = 0
        for rid in sorted(row_names.keys(), key=lambda x: (row_names[x] or x)):
            cells = []
            for cg in column_groups:
                key = (rid, cg["animal_id"], cg["species_id"], cg["age_id"])
                gender_map = cell_map.get(key, {})
                gender_values = []; group_total = 0
                for g in cg["genders"]:
                    v = int(gender_map.get(g["id"], 0))
                    gender_values.append({"gender_id": g["id"], "value": v}); group_total += v
                cells.append({"group_total": group_total, "gender_values": gender_values})
            rt = row_totals.get(rid, 0); grand_total += rt
            report_rows.append({"row_id": rid, "row_name": row_names.get(rid, rid), "cells": cells, "row_total": rt})

        return column_groups, report_rows, grand_total, row_level
    except Exception as e:
        logger.error(f"Report2 DB Error: {e}")
        return [], [], 0, _resolve_row_level(role)

@app.get("/report/2", response_class=HTMLResponse)
async def report2_page(request: Request,
                       animal_type: str = Query("atID01"), animal: str = Query(""),
                       species: str = Query(""), age: str = Query(""), gender: str = Query(""),
                       start_date: str = Query(""), end_date: str = Query("")):
    try: user = get_signed_in_user(request)
    except HTTPException: return RedirectResponse("/", status_code=303)

    role = user["role"]
    if role not in ("admin", "union", "state", "district", "township"): raise HTTPException(403, "ဤစာမျက်နှာကို ကြည့်ခွင့်မရှိပါ။")

    if animal_type not in ANIMAL_TYPES: animal_type = "atID01"
    animal_type_name = next((a["name"] for a in ANIMAL_TYPE_NAMES if a["id"] == animal_type), "တိရိစ္ဆာန်")

    animal_rows = _get_animal_rows_by_type(animal_type)
    filter_species = _get_species_options(animal_type, animal) if animal_type != "atID04" else []
    filter_ages = _get_age_options(animal_type) if animal_type != "atID04" else []
    filter_genders = _get_gender_options(animal_type)

    column_groups, report_rows, grand_total, row_level = _build_report2_data(
        role, user, animal_type,
        animal_id=animal, species_id=species, age_id=age, gender_id=gender,
        start_date=start_date, end_date=end_date,
    )

    region_name = "တစ်နိုင်ငံလုံး" if role == "union" else _get_user_state_name(user)

    district_name_for_js = ""; township_name_for_js = ""
    try:
        conn = get_db_connection(); cur = conn.cursor(dictionary=True)
        try:
            if user.get("districtID"):
                cur.execute("SELECT districtName FROM district WHERE stateID = %s AND districtID = %s", (user.get("stateID"), user.get("districtID")))
                r = cur.fetchone(); district_name_for_js = r["districtName"] if r else ""
            if user.get("townshipID"):
                cur.execute("SELECT townshipName FROM township WHERE stateID = %s AND districtID = %s AND townshipID = %s", (user.get("stateID"), user.get("districtID"), user.get("townshipID")))
                r = cur.fetchone(); township_name_for_js = r["townshipName"] if r else ""
        finally: cur.close(); conn.close()
    except Exception as e:
        logger.warning(f"report2 names lookup failed: {e}")

    return templates.TemplateResponse(request=request, name="report2.html", context={
        "active_page": "report2", "role": role, "region_name": region_name,
        "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user),
        "user_district_id": user.get("districtID") or "", "user_district_name": district_name_for_js,
        "user_township_id": user.get("townshipID") or "", "user_township_name": township_name_for_js,
        "animal_type": animal_type, "animal_type_name": animal_type_name, "animal_types": ANIMAL_TYPE_NAMES,
        "animal_rows": animal_rows, "filter_species": filter_species, "filter_ages": filter_ages, "filter_genders": filter_genders,
        "selected_animal": animal, "selected_species": species, "selected_age": age, "selected_gender": gender,
        "column_groups": column_groups, "report_rows": report_rows, "grand_total": grand_total, "row_level": row_level,
        "filters": {"state": "", "district": "", "township": "", "qv": "", "animal_type": animal_type, "start_date": start_date, "end_date": end_date},
    })

@app.get("/api/report2/options")
async def report2_options(request: Request, animal_type: str = Query("atID01")):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(401, "Login လုပ်ပါ။")
    if animal_type not in ANIMAL_TYPES: animal_type = "atID01"
    species = _get_species_options(animal_type) if animal_type != "atID04" else []
    ages = _get_age_options(animal_type) if animal_type != "atID04" else []
    genders = _get_gender_options(animal_type)
    return {"species": species, "ages": ages, "genders": genders}

# ============================================================
# 📊 SURVEY DASHBOARD (Enumerator)
# ============================================================
@app.get("/survey/dashboard", response_class=HTMLResponse)
async def survey_dashboard(request: Request, start_date: str = Query(""), end_date: str = Query("")):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    if str(user.get("role", "")).lower() != "enumerator":
        return RedirectResponse(ROLE_HOME.get(user.get("role"), "/"), status_code=303)

    for key, label in (("stateID", "တိုင်းဒေသကြီး/ပြည်နယ်"), ("districtID", "ခရိုင်"), ("townshipID", "မြို့နယ်")):
        if not user.get(key): raise HTTPException(403, f"Enumerator အကောင့်တွင် {label} မသတ်မှတ်ရသေးပါ။")

    user_id = user.get("id")
    total_forms = total_villages = total_households = 0
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS c FROM personcv WHERE userId = %s", (user_id,)); row = cursor.fetchone(); total_forms = int(row["c"]) if row else 0
        cursor.execute("SELECT COUNT(DISTINCT QVID) AS c FROM personcv WHERE userId = %s", (user_id,)); row = cursor.fetchone(); total_villages = int(row["c"]) if row else 0
        cursor.execute("SELECT COUNT(DISTINCT householdNo) AS c FROM personcv WHERE userId = %s", (user_id,)); row = cursor.fetchone(); total_households = int(row["c"]) if row else 0
    except SQLAlchemyError as e:
        logger.error(f"Dashboard DB error: {e}")
    finally: cursor.close(); conn.close()

    # Collection counts come from the current enumerator's survey records.
    household_stats = {"total": 0, "pending": 0, "collected": 0}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 0 THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) AS collected
            FROM personcv
            WHERE userId = %s
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            household_stats = {
                "total":     int(row["total"]     or 0),
                "pending":   int(row["pending"]   or 0),
                "collected": int(row["collected"] or 0),
            }
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="formDashboard.html", context={
        "active_page": "home", "user": user,
        "total_forms": total_forms, "total_villages": total_villages, "total_households": total_households,
        "household_stats": household_stats,
        "filters": {"start_date": start_date, "end_date": end_date},
    })

# ============================================================
# 👨‍💻 ENUMERATOR WEB FLOW
# ============================================================
@app.get("/enumerator/part1", response_class=HTMLResponse)
async def enumerator_web_part1(request: Request, db: Session = Depends(get_db)):
    user = _require_enumerator_web(request)
    request.session["stateID"] = str(user["stateID"])
    
    # ⭐ sequential form_id
    #total_records = db.query(PersonCV).count() or 0
    #next_num = total_records + 1
    #new_form_id = generate_formatted_id(next_num)
    new_form_id = "TEMP-FORM-ID-0001"
    print(f"temp form ID from enuPart1{new_form_id}")
    return templates.TemplateResponse(request=request, name="FormPart1.html", context={
        "active_page": "survey", "states": _get_all_states(),
        "user": user, "role": "enumerator", "form_id": new_form_id,
        "survey_prefix": "/enumerator",
    })

@app.get("/enumerator/locations")
async def enumerator_web_locations(request: Request):
    user = _require_enumerator_web(request)
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT districtID, districtName FROM district WHERE stateID = %s AND districtID = %s", (user["stateID"], user["districtID"])); district = cursor.fetchone()
        cursor.execute("SELECT townshipID, townshipName FROM township WHERE stateID = %s AND districtID = %s AND townshipID = %s", (user["stateID"], user["districtID"], user["townshipID"])); township = cursor.fetchone()
        cursor.execute("SELECT QVID, QVName FROM qv WHERE stateID = %s AND districtID = %s AND townshipID = %s ORDER BY QVName", (user["stateID"], user["districtID"], user["townshipID"])); qvs = cursor.fetchall()
        if not district or not township: raise HTTPException(403, "Enumerator အကောင့်၏ သတ်မှတ်ထားသော Location မမှန်ကန်ပါ။")
        return {"stateID": str(user["stateID"]), "district": district, "township": township, "qvs": qvs}
    finally: cursor.close(); conn.close()

# ============================================================
# ✏️ EDIT / DELETE FORM (Enumerator)
# ============================================================
EDITABLE_PERSON_FIELDS = {
    "WardName", "householdNo", "interviewDate", "name", "gender",
    "eduStatus", "phoneNo", "age", "headName", "headEduStatus",
    "headGender", "headPhoneNo", "headAge", "Interviewer", "interviewerPhoneNo",
}
EDITABLE_ANIMAL_FIELDS = {
    "animalTypeID", "animalID", "speciesID", "ageID", "genderID", "dataCount",
}

@app.get("/enumerator/edit-form", response_class=HTMLResponse)
async def edit_form_page(request: Request):
    user = get_signed_in_user(request)
    if user.get("role") != "enumerator": raise HTTPException(403, "Enumerator role only")
    return templates.TemplateResponse(request=request, name="edit_form.html", context={"request": request, "user": user, "role": user.get("role", ""), "active_page": "edit_form"})


@app.get("/enumerator/api/forms/{formID}")
async def get_form_for_edit(formID: str, request: Request):
    user = get_signed_in_user(request)

    if not user or str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    user_id = user["id"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                pc.*,
                s.stateName AS stateName,
                d.districtName AS districtName,
                t.townshipName AS townshipName,
                q.QVName AS QVName
            FROM personcv AS pc
            LEFT JOIN state AS s
                ON pc.stateID = s.stateID
            LEFT JOIN district AS d
                ON pc.districtID = d.districtID
            LEFT JOIN township AS t
                ON pc.townshipID = t.townshipID
            LEFT JOIN qv AS q
                ON pc.stateID = q.stateID
            AND pc.districtID = q.districtID
            AND pc.townshipID = q.townshipID
            AND pc.QVID = q.QVID
            WHERE pc.formID = %s
              AND pc.userId = %s
            LIMIT 1
        """, (formID, user_id))

        person = cursor.fetchone()

        if not person:
            raise HTTPException(
                404,
                "Form မတွေ့ပါ သို့မဟုတ် မိမိပိုင်ဒေတာ မဟုတ်ပါ။"
            )

        cursor.execute("""
            SELECT
                pc.*,
                s.stateName AS stateName,
                d.districtName AS districtName,
                t.townshipName AS townshipName,
                q.QVName AS QVName
            FROM personcv AS pc
            LEFT JOIN state AS s
                ON pc.stateID = s.stateID
            LEFT JOIN district AS d
                ON pc.stateID = d.stateID
            AND pc.districtID = d.districtID
            LEFT JOIN township AS t
                ON pc.stateID = t.stateID
            AND pc.districtID = t.districtID
            AND pc.townshipID = t.townshipID
            LEFT JOIN qv AS q
                ON pc.stateID = q.stateID
            AND pc.districtID = q.districtID
            AND pc.townshipID = q.townshipID
            AND pc.QVID = q.QVID
            WHERE pc.formID = %s
            AND pc.userId = %s
            LIMIT 1
        """, (formID, user_id))

        person = cursor.fetchone()
        collected = cursor.fetchall()
        lookup = load_animal_lookup(cursor)

        return {
            "formID": formID,
            "personcv": person,
            "collecteddata": collected,
            "lookup": lookup
        }

    finally:
        cursor.close()
        conn.close()


@app.put("/enumerator/api/forms/{formID}")
async def update_existing_form(formID: str, request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator": raise HTTPException(403, "Enumerator role only")
    user_id = user["id"]
    try: payload = await request.json()
    except Exception: raise HTTPException(400, "Request JSON မမှန်ကန်ပါ။")
    if not isinstance(payload, dict): raise HTTPException(400, "Request data မမှန်ကန်ပါ။")
    person_data = payload.get("personcv") or {}; animal_data = payload.get("collecteddata") or []
    if not isinstance(person_data, dict) or not isinstance(animal_data, list): raise HTTPException(400, "personcv သို့မဟုတ် collecteddata ပုံစံ မမှန်ပါ။")
    if any(not isinstance(row, dict) for row in animal_data): raise HTTPException(400, "တိရစ္ဆာန်ဒေတာ row မမှန်ပါ။")

    person_values = {k: v for k, v in person_data.items() if k in EDITABLE_PERSON_FIELDS}
    for key in ("age", "headAge"):
        if key in person_values and str(person_values[key]).strip() != "":
            try:
                person_values[key] = int(person_values[key])
                if person_values[key] < 0: raise ValueError
            except (TypeError, ValueError): raise HTTPException(422, f"{key} သည် သုည သို့မဟုတ် အပေါင်းကိန်း ဖြစ်ရပါမည်။")
    if "interviewDate" in person_values and not person_values["interviewDate"]: person_values["interviewDate"] = None

    cleaned_animals = []
    for row in animal_data:
        clean = {k: row.get(k) for k in EDITABLE_ANIMAL_FIELDS}
        if not any(str(v or "").strip() for v in clean.values()): continue
        try:
            count_int = int(str(clean.get("dataCount") or "0").strip())
            if count_int < 0: raise ValueError
        except ValueError: raise HTTPException(422, "အရေအတွက်သည် သုည သို့မဟုတ် အပေါင်းကိန်း ဖြစ်ရပါမည်။")
        clean["dataCount"] = str(count_int); cleaned_animals.append(clean)

    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("SELECT formID FROM personcv WHERE formID = %s AND userId = %s LIMIT 1 FOR UPDATE", (formID, user_id))
        if not cursor.fetchone():
            conn.rollback(); raise HTTPException(404, "ဤ Form ID အတွက် သင့်အကောင့်ပိုင် ဒေတာမတွေ့ပါ။")

        if person_values:
            assignments = ", ".join(f"`{key}` = %s" for key in person_values)
            cursor.execute(f"UPDATE personcv SET {assignments} WHERE formID = %s AND userId = %s", tuple(list(person_values.values()) + [formID, user_id]))

        cursor.execute("DELETE FROM collecteddata WHERE formID = %s", (formID,))
        for row in cleaned_animals:
            cursor.execute("INSERT INTO collecteddata (formID, animalTypeID, animalID, speciesID, ageID, genderID, dataCount) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                           (formID, row.get("animalTypeID"), row.get("animalID"), row.get("speciesID"), row.get("ageID"), row.get("genderID"), row.get("dataCount", "0")))
        conn.commit()
        return {"status": "success", "message": "ပြင်ဆင်ချက်များ သိမ်းဆည်းပြီးပါပြီ။", "formID": formID, "animalRecordsSaved": len(cleaned_animals)}
    except HTTPException: raise
    except Exception:
        conn.rollback(); logger.exception("Existing survey update failed")
        raise HTTPException(500, "ဒေတာ Update မအောင်မြင်ပါ။ Database schema နှင့် log ကို စစ်ဆေးပါ။")
    finally: cursor.close(); conn.close()

@app.delete("/enumerator/api/forms/{formID}")
async def delete_existing_form(formID: str, request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator": raise HTTPException(403, "Enumerator role only")
    user_id = user["id"]
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        cursor.execute("SELECT formID FROM personcv WHERE formID = %s AND userId = %s LIMIT 1 FOR UPDATE", (formID, user_id))
        if not cursor.fetchone():
            conn.rollback(); raise HTTPException(404, "ဤ Form ID အတွက် သင့်အကောင့်ပိုင် ဒေတာမတွေ့ပါ။")
        cursor.execute("DELETE FROM collecteddata WHERE formID = %s", (formID,)); deleted_animals = cursor.rowcount
        cursor.execute("DELETE FROM personcv WHERE formID = %s AND userId = %s", (formID, user_id)); deleted_person = cursor.rowcount
        conn.commit()
        return {"status": "success", "message": "ဒေတာကို ဖျက်ပြီးပါပြီ။", "formID": formID, "deletedAnimals": deleted_animals, "deletedPerson": deleted_person}
    except HTTPException: raise
    except Exception:
        conn.rollback(); logger.exception("Delete form failed")
        raise HTTPException(500, "ဒေတာဖျက်ခြင်း မအောင်မြင်ပါ။ Database log ကို စစ်ဆေးပါ။")
    finally: cursor.close(); conn.close()

# ============================================================
# 🔍 ANIMAL LOOKUP
# ============================================================
LOOKUP_TABLES = {
    "animalTypes": "animalType", "largeAnimals": "largeAnimals", "youngAnimals": "youngAnimals",
    "liveStock": "liveStock", "breedingstock": "breedingstock", "species": "liveStockSpecies",
    "ages": "ageType", "genders": "gender",
}
LOOKUP_ID_CANDIDATES = {
    "animalTypes": ["atID", "animalTypeID", "animalTypeId"],
    "largeAnimals": ["laID", "animalID", "largeAnimalID"],
    "youngAnimals": ["yaID", "animalID", "youngAnimalID"],
    "liveStock": ["lsID", "animalID", "liveStockID"],
    "breedingstock": ["bsID", "animalID", "breedingstockID"],
    "species": ["speciesID", "spID", "lsSpeciesID"],
    "ages": ["ageID"], "genders": ["genderID", "gID"],
}
LOOKUP_NAME_CANDIDATES = {
    "animalTypes": ["animalTypeName", "atName", "animalType"],
    "largeAnimals": ["largeAnimalName", "laName", "animalName"],
    "youngAnimals": ["youngAnimalName", "yaName", "animalName"],
    "liveStock": ["liveStockName", "lsName", "animalName"],
    "breedingstock": ["breedingstockName", "bsName", "animalName"],
    "species": ["speciesName", "spName", "liveStockSpecies"],
    "ages": ["ageName", "ageTypeName", "ageType"],
    "genders": ["genderName", "gName", "gender"],
}

def get_lookup_rows(cursor, lookup_key):
    if lookup_key not in LOOKUP_TABLES: raise ValueError("Invalid lookup key")
    table_name = LOOKUP_TABLES[lookup_key]
    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    columns = [row["Field"] for row in cursor.fetchall()]
    if not columns: return []
    id_column = next((col for col in LOOKUP_ID_CANDIDATES[lookup_key] if col in columns), None)
    name_column = next((col for col in LOOKUP_NAME_CANDIDATES[lookup_key] if col in columns), None)
    if id_column is None:
        id_column = next((col for col in columns if col.lower().endswith("id") and col.lower() not in ("formid", "userid")), None)
    if name_column is None:
        name_column = next((col for col in columns if "name" in col.lower() or col.lower() in ("animaltype", "agetype", "gender")), None)
    if id_column is None or name_column is None:
        raise ValueError(f"Lookup schema မကိုက်ညီပါ: {table_name}; columns={columns}")
    cursor.execute(f"SELECT * FROM `{table_name}` ORDER BY `{id_column}`")
    result = []
    for row in cursor.fetchall():
        item = {"id": row.get(id_column), "name": row.get(name_column)}
        item.update(row); result.append(item)
    return result

def load_animal_lookup(cursor):
    lookup = {"animalTypes": get_lookup_rows(cursor, "animalTypes"), "animals": []}
    animal_sources = [("atID01", "largeAnimals"), ("atID02", "youngAnimals"), ("atID03", "liveStock"), ("atID04", "breedingstock")]
    for type_id, source_key in animal_sources:
        for item in get_lookup_rows(cursor, source_key):
            animal = dict(item); animal["animalTypeID"] = type_id; lookup["animals"].append(animal)

    lookup["species"] = []
    try:
        cursor.execute("SELECT * FROM largespecies")
        for row in cursor.fetchall():
            lookup["species"].append({"id": row.get("speciesID"), "name": row.get("speciesName"), "animalID": row.get("animalID"), "animalTypeID": "atID01", **row})
    except Exception as e: logger.warning(f"largespecies lookup failed: {e}")
    try:
        cursor.execute("SELECT * FROM youngspecies")
        for row in cursor.fetchall():
            lookup["species"].append({"id": row.get("speciesID"), "name": row.get("speciesName"), "animalID": row.get("animalID"), "animalTypeID": "atID02", **row})
    except Exception as e: logger.warning(f"youngspecies lookup failed: {e}")
    try:
        cursor.execute("SELECT * FROM livestockspecies")
        for row in cursor.fetchall():
            lookup["species"].append({"id": row.get("speciesID"), "name": row.get("speciesName"), "animalID": row.get("animalID"), "animalTypeID": "atID03", **row})
    except Exception as e: logger.warning(f"livestockspecies lookup failed: {e}")

    lookup["ages"] = get_lookup_rows(cursor, "ages")
    lookup["genders"] = get_lookup_rows(cursor, "genders")
    return lookup

@app.get("/enumerator/api/lookups")
async def get_animal_lookups(request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator": raise HTTPException(403, "Enumerator role only")
    conn = get_db_connection(); cursor = conn.cursor(dictionary=True)
    try:
        return {"status": "success", "lookup": load_animal_lookup(cursor)}
    except Exception:
        logger.exception("Failed to load animal lookup data")
        raise HTTPException(500, "Lookup data မရပါ။ Database Column အမည်များကို စစ်ဆေးပါ။")
    finally: cursor.close(); conn.close()

# ============================================================
# ⚙️ SETTINGS / USERSETTINGS
# ============================================================
@app.get("/settings")
async def settings_page(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    fresh_user = user
    try:
        db = SessionLocal()
        try:
            row = db.execute(text("SELECT userId, userName, loginName, phone, userRole, stateID, districtID, townshipID FROM `user` WHERE userId = :uid"), {"uid": user.get("id")}).mappings().first()
            if row:
                fresh_user = {**user, **dict(row), "id": row["userId"]}
                request.session["user"] = fresh_user
        finally: db.close()
    except SQLAlchemyError as e: logger.warning(f"settings_page user lookup: {e}")
    return templates.TemplateResponse(request=request, name="settings.html", context={
        "active_page": "settings", "user_state_id": fresh_user.get("stateID") or "",
        "user": fresh_user, "role": fresh_user.get("role") or "admin",
        "user_state_name": _get_user_state_name(fresh_user),
        "user_district_id": fresh_user.get("districtID") or "", "user_township_id": fresh_user.get("townshipID") or "",
    })

@app.get("/usersettings", response_class=HTMLResponse)
async def usersettings_page(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    fresh_user = user
    try:
        db = SessionLocal()
        try:
            row = db.execute(text("SELECT userId, userName, loginName, phone, userRole, stateID, districtID, townshipID FROM `user` WHERE userId = :uid"), {"uid": user.get("id")}).mappings().first()
            if row:
                fresh_user = {**user, **dict(row), "id": row["userId"]}
                request.session["user"] = fresh_user
        finally: db.close()
    except SQLAlchemyError as e: logger.warning(f"usersettings_page user lookup: {e}")
    return templates.TemplateResponse(request=request, name="usersettings.html", context={
        "active_page": "usersettings", "user_state_id": fresh_user.get("stateID") or "",
        "user": fresh_user, "role": fresh_user.get("role") or "admin",
        "user_state_name": _get_user_state_name(fresh_user),
        "user_district_id": fresh_user.get("districtID") or "", "user_township_id": fresh_user.get("townshipID") or "",
    })

@app.get("/api/settings/profile")
async def api_get_profile(request: Request):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(401, "Login လုပ်ပါ။")
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT userId, userName, loginName, phone, userRole FROM `user` WHERE userId = :uid"), {"uid": user.get("id")}).mappings().first()
        if not row: raise HTTPException(404, "User မတွေ့ပါ။")
        return {"status": "success", "data": {"id": row["userId"], "name": row["userName"], "phone": row["phone"] or "", "loginName": row["loginName"] or "", "roleId": row["userRole"]}}
    finally: db.close()

@app.post("/api/settings/profile")
async def api_update_profile(request: Request):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(401, "Login လုပ်ပါ။")
    try: payload = await request.json()
    except Exception: raise HTTPException(400, "Invalid JSON body.")
    name = str(payload.get("name") or "").strip(); phone = str(payload.get("phone") or "").strip()
    if not name: raise HTTPException(400, "အမည် ထည့်ပါ။")
    if len(name) < 2: raise HTTPException(400, "အမည် အနည်းဆုံး ၂ လုံး ရှိရမည်။")
    if len(name) > 100: raise HTTPException(400, "အမည် ၁၀၀ လုံးထက် မကျော်ရပါ။")
    if not phone: raise HTTPException(400, "ဖုန်းနံပါတ် ထည့်ပါ။")
    if not re.match(r"^09\d{7,9}$", phone): raise HTTPException(400, "ဖုန်းနံပါတ်ပုံစံ မှားနေသည်။ (ဥပမာ - 09421234567)")
    db = SessionLocal()
    try:
        existing = db.execute(text("SELECT userId FROM `user` WHERE phone = :phone AND userId != :uid"), {"phone": phone, "uid": user["id"]}).fetchone()
        if existing: raise HTTPException(409, "ဤဖုန်းနံပါတ်ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")
        db.execute(text("UPDATE `user` SET userName = :name, phone = :phone WHERE userId = :uid"), {"name": name, "phone": phone, "uid": user["id"]})
        db.commit()
        session_user = request.session.get("user") or {}; session_user["userName"] = name; session_user["phone"] = phone; request.session["user"] = session_user
        return {"status": "success", "message": "ကိုယ်ရေးအချက်အလက် သိမ်းဆည်းပြီးပါပြီ။"}
    except HTTPException: db.rollback(); raise
    except IntegrityError: db.rollback(); raise HTTPException(409, "ဤဖုန်းနံပါတ်ကို အသုံးပြုပြီးသားပါ။")
    except SQLAlchemyError as e: db.rollback(); logger.error(f"update profile error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/settings/password")
async def api_change_password(request: Request):
    try: user = get_signed_in_user(request)
    except HTTPException: raise HTTPException(401, "Login လုပ်ပါ။")
    try: payload = await request.json()
    except Exception: raise HTTPException(400, "Invalid JSON body.")
    current_pwd = str(payload.get("current") or ""); new_pwd = str(payload.get("new") or ""); confirm_pwd = str(payload.get("confirm") or "")
    if not current_pwd: raise HTTPException(400, "လက်ရှိ လျှို့ဝှက်နံပါတ် ထည့်ပါ။")
    if not new_pwd: raise HTTPException(400, "လျှို့ဝှက်နံပါတ် အသစ် ထည့်ပါ။")
    if len(new_pwd) < 8: raise HTTPException(400, "လျှို့ဝှက်နံပါတ် အနည်းဆုံး ၈ လုံး ရှိရမည်။")
    if new_pwd == current_pwd: raise HTTPException(400, "လျှို့ဝှက်နံပါတ် အသစ်က လက်ရှိနှင့် မတူရပါ။")
    if new_pwd != confirm_pwd: raise HTTPException(400, "လျှို့ဝှက်နံပါတ် နှစ်ခု မတူညီပါ။")
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT password FROM `user` WHERE userId = :uid"), {"uid": user["id"]}).fetchone()
        if not row: raise HTTPException(404, "User မတွေ့ပါ။")
        if not verify_password(current_pwd, row[0]): raise HTTPException(400, "လက်ရှိ လျှို့ဝှက်နံပါတ် မှားနေသည်။")
        db.execute(text("UPDATE `user` SET password = :pwd WHERE userId = :uid"), {"pwd": hash_password(new_pwd), "uid": user["id"]})
        db.commit()
        return {"status": "success", "message": "လျှို့ဝှက်နံပါတ် ပြောင်းလဲပြီးပါပြီ။"}
    except HTTPException: db.rollback(); raise
    except SQLAlchemyError as e: db.rollback(); logger.error(f"change password error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

# ============================================================
# 👥 SYSTEM ADMIN
# ============================================================
@app.get("/system/users", response_class=HTMLResponse)
async def system_users_page(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    if user.get("role") != "admin": raise HTTPException(403, "Admin သာ ဝင်ရောက်နိုင်ပါသည်။")
    return templates.TemplateResponse(request=request, name="systemUserCreate.html", context={"active_page": "sys_users", "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user)})

@app.get("/api/system/roles")
async def get_system_roles():
    return {"roles": [{"id": 1, "name": "admin"}, {"id": 2, "name": "union"}, {"id": 3, "name": "state"}, {"id": 4, "name": "district"}, {"id": 5, "name": "township"}, {"id": 6, "name": "enumerator"}]}

@app.get("/api/system/users")
async def api_get_system_users(request: Request, role_filter: str = Query(""), state: str = Query(""), district: str = Query(""), township: str = Query("")):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ ကြည့်ရှုနိုင်ပါသည်။")
    db = SessionLocal()
    try:
        conds = ["1=1"]; params = {}
        if role_filter: conds.append("u.userRole = :role"); params["role"] = role_filter
        if state: conds.append("u.stateID = :sid"); params["sid"] = state
        if district: conds.append("u.districtID = :did"); params["did"] = district
        if township: conds.append("u.townshipID = :tid"); params["tid"] = township
        where = " AND ".join(conds)
        sql = text(f"""
            SELECT u.userId, u.userName, u.loginName AS email, u.phone, u.userRole, u.status,
                   u.stateID, st.stateName, u.districtID, dt.districtName, u.townshipID, ts.townshipName, ur.roleName
            FROM `user` u
            LEFT JOIN state st ON st.stateID = u.stateID
            LEFT JOIN district dt ON dt.stateID = u.stateID AND dt.districtID = u.districtID
            LEFT JOIN township ts ON ts.stateID = u.stateID AND ts.districtID = u.districtID AND ts.townshipID = u.townshipID
            LEFT JOIN userrole ur ON ur.roleId = u.userRole
            WHERE {where} ORDER BY u.userId DESC
        """)
        rows = db.execute(sql, params).mappings().all()
        return {"status": "success", "users": [dict(r) for r in rows]}
    except SQLAlchemyError as e: logger.error(f"System users API error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.get("/api/system/users/search")
async def api_search_system_users(
    request: Request, q: str = Query(""), role_filter: str = Query(""),
    state: str = Query(""), district: str = Query(""), township: str = Query(""),
    page: int = Query(1, ge=1), per_page: int = Query(10, ge=1, le=100),
):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ ကြည့်ရှုနိုင်ပါသည်။")
    db = SessionLocal()
    try:
        conds = ["1=1"]; params = {}
        if q and q.strip(): conds.append("(u.userName LIKE :q OR u.loginName LIKE :q)"); params["q"] = f"%{q.strip()}%"
        if role_filter: conds.append("u.userRole = :role"); params["role"] = role_filter
        if state: conds.append("u.stateID = :sid"); params["sid"] = state
        if district: conds.append("u.districtID = :did"); params["did"] = district
        if township: conds.append("u.townshipID = :tid"); params["tid"] = township
        where = " AND ".join(conds)
        total = db.execute(text(f"SELECT COUNT(*) AS total FROM `user` u WHERE {where}"), params).scalar() or 0
        offset = (page - 1) * per_page
        sql = text(f"""
            SELECT u.userId, u.userName, u.loginName AS email, u.phone, u.userRole, u.status,
                   u.stateID, st.stateName, u.districtID, dt.districtName, u.townshipID, ts.townshipName, ur.roleName
            FROM `user` u
            LEFT JOIN state st ON st.stateID = u.stateID
            LEFT JOIN district dt ON dt.stateID = u.stateID AND dt.districtID = u.districtID
            LEFT JOIN township ts ON ts.stateID = u.stateID AND ts.districtID = u.districtID AND ts.townshipID = u.townshipID
            LEFT JOIN userrole ur ON ur.roleId = u.userRole
            WHERE {where} ORDER BY u.userId DESC LIMIT :limit OFFSET :offset
        """)
        params["limit"] = per_page; params["offset"] = offset
        rows = db.execute(sql, params).mappings().all()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        return {"status": "success", "users": [dict(r) for r in rows], "total": total, "page": page, "per_page": per_page, "total_pages": total_pages}
    except SQLAlchemyError as e: logger.error(f"Search users error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/system/users/action")
async def api_system_user_action(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ လုပ်ဆောင်နိုင်ပါသည်။")
    data = await request.json(); target_uid = data.get("userId"); action = data.get("action"); new_status = data.get("status")
    db = SessionLocal()
    try:
        if action == "toggle":
            db.execute(text("UPDATE `user` SET status = :st WHERE userId = :uid"), {"st": new_status, "uid": target_uid})
        db.commit()
        return {"status": "success", "message": "အောင်မြင်ပါသည်။"}
    except SQLAlchemyError: db.rollback(); raise HTTPException(500, "Database error")
    finally: db.close()

@app.post("/api/system/users/create")
async def api_create_system_user(request: Request, username: str = Form(...), role_id: int = Form(...), email: str = Form(...), phone: str = Form(""), stateID: str = Form(""), districtID: str = Form(""), townshipID: str = Form("")):
    admin_user = request.session.get("user")
    if not admin_user or admin_user.get("role") not in ("admin", "union"): raise HTTPException(403, "Admin သာ ဖန်တီးနိုင်ပါသည်။")
    if not username or not username.strip(): raise HTTPException(400, "❌ အသုံးပြုသူအမည် (Username) ထည့်သွင်းရန် လိုအပ်ပါသည်။")
    db = SessionLocal()
    try:
        existing_email = db.execute(text("SELECT userId FROM `user` WHERE loginName = :email"), {"email": email}).fetchone()
        if existing_email: raise HTTPException(409, "❌ ဒီအီးမေးလ် (Login Name) ကို အသုံးပြုပြီးသားပါ။")
        phone_val = phone.strip() if phone else ""
        if phone_val:
            existing_phone = db.execute(text("SELECT userId FROM `user` WHERE phone = :phone"), {"phone": phone_val}).fetchone()
            if existing_phone: raise HTTPException(409, "❌ ဒီဖုန်းနံပါတ်ကို အသုံးပြုပြီးသားပါ။")
        if role_id in (1, 2): stateID, districtID, townshipID = None, None, None
        elif role_id == 3:
            if not stateID: raise HTTPException(400, "တိုင်းဒေသကြီး ရွေးပါ။")
            districtID, townshipID = None, None
        elif role_id == 4:
            if not stateID or not districtID: raise HTTPException(400, "တိုင်းနှင့် ခရိုင် ရွေးပါ။")
            townshipID = None
        elif role_id in (5, 6):
            if not stateID or not districtID or not townshipID: raise HTTPException(400, "တိုင်း၊ ခရိုင်၊ မြို့နယ် အားလုံး ရွေးပါ။")
        db.execute(text("""
                INSERT INTO `user` (userName, userRole, loginName, password, stateID, districtID, townshipID, status, phone)
                VALUES (:uname, :role, :email, :pwd, :sid, :did, :tid, 1, :phone)
            """), {"uname": username.strip(), "role": role_id, "email": email, "pwd": hash_password(DEFAULT_PASSWORD), "sid": stateID or None, "did": districtID or None, "tid": townshipID or None, "phone": phone_val if phone_val else None})
        db.commit()
        return {"status": "success", "message": "အကောင့်အသစ် ဖန်တီးပြီးပါပြီ။ (လျှို့ဝှက်နံပါတ်: 12345678)"}
    except IntegrityError: db.rollback(); raise HTTPException(409, "❌ အချက်အလက်တူညီနေပါသည်။")
    except SQLAlchemyError as e: db.rollback(); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/system/users/update")
async def api_update_system_user(request: Request, userId: int = Form(...), username: str = Form(...), role_id: int = Form(...), email: str = Form(...), phone: str = Form(""), stateID: str = Form(""), districtID: str = Form(""), townshipID: str = Form("")):
    admin_user = request.session.get("user")
    if not admin_user or admin_user.get("role") not in ("admin", "union"): raise HTTPException(403, "Admin သာ ပြင်ဆင်နိုင်ပါသည်။")
    if not username or not username.strip(): raise HTTPException(400, "❌ အသုံးပြုသူအမည် (Username) ထည့်သွင်းရန် လိုအပ်ပါသည်။")
    db = SessionLocal()
    try:
        existing_email = db.execute(text("SELECT userId FROM `user` WHERE loginName = :email AND userId != :uid"), {"email": email, "uid": userId}).fetchone()
        if existing_email: raise HTTPException(409, "❌ ဒီအီးမေးလ်ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")
        phone_val = phone.strip() if phone else ""
        if phone_val:
            existing_phone = db.execute(text("SELECT userId FROM `user` WHERE phone = :phone AND userId != :uid"), {"phone": phone_val, "uid": userId}).fetchone()
            if existing_phone: raise HTTPException(409, "❌ ဒီဖုန်းနံပါတ်ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")
        if role_id in (1, 2): stateID, districtID, townshipID = None, None, None
        elif role_id == 3:
            if not stateID: raise HTTPException(400, "တိုင်းဒေသကြီး ရွေးပါ။")
            districtID, townshipID = None, None
        elif role_id == 4:
            if not stateID or not districtID: raise HTTPException(400, "တိုင်းနှင့် ခရိုင် ရွေးပါ။")
            townshipID = None
        elif role_id in (5, 6):
            if not stateID or not districtID or not townshipID: raise HTTPException(400, "တိုင်း၊ ခရိုင်၊ မြို့နယ် အားလုံး ရွေးပါ။")
        db.execute(text("""
                UPDATE `user` SET userName = :uname, userRole = :role, loginName = :email,
                    stateID = :sid, districtID = :did, townshipID = :tid, phone = :phone
                WHERE userId = :uid
            """), {"uname": username.strip(), "role": role_id, "email": email, "sid": stateID or None, "did": districtID or None, "tid": townshipID or None, "phone": phone_val if phone_val else None, "uid": userId})
        db.commit()
        return {"status": "success", "message": "အချက်အလက်များ ပြင်ဆင်ပြီးပါပြီ။"}
    except IntegrityError: db.rollback(); raise HTTPException(409, "❌ အချက်အလက်တူညီနေပါသည်။")
    except SQLAlchemyError as e: db.rollback(); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/system/users/import-excel")
async def api_import_users_excel(request: Request, file: UploadFile = File(...)):
    admin_user = request.session.get("user")
    if not admin_user or admin_user.get("role") not in ("admin", "union"): raise HTTPException(403, "Admin သာ လုပ်ဆောင်နိုင်ပါသည်။")
    if not file.filename.endswith(('.xlsx', '.xls')): raise HTTPException(400, "❌ ကျေးဇူးပြု၍ .xlsx သို့မဟုတ် .xls ဖိုင်သာ တင်ပါ။")
    hashed_pwd = hash_password(DEFAULT_PASSWORD)
    db = SessionLocal(); success_count = 0; failed_rows = []
    try:
        contents = await file.read()
        wb = load_workbook(filename=io.BytesIO(contents), data_only=True)
        if len(wb.sheetnames) > 1: raise HTTPException(400, "❌ ဖိုင်ထဲတွင် Sheet တစ်ခုထက်ပို၍ ပါဝင်နေပါသည်။")
        ws = wb.active
        header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
        headers = [str(h).strip() for h in header_row if h is not None]
        required_cols = ['userName', 'userRole', 'loginName']
        missing_cols = [col for col in required_cols if col not in headers]
        if missing_cols: raise HTTPException(400, f"❌ လိုအပ်သော Column များ ပျောက်နေပါသည်: {', '.join(missing_cols)}")
        idx_name = headers.index('userName'); idx_role = headers.index('userRole'); idx_login = headers.index('loginName')
        idx_state = headers.index('stateID') if 'stateID' in headers else -1
        idx_district = headers.index('districtID') if 'districtID' in headers else -1
        idx_township = headers.index('townshipID') if 'townshipID' in headers else -1
        idx_phone = headers.index('phone') if 'phone' in headers else -1
        def get_val(row, idx):
            if idx == -1 or idx >= len(row): return ""
            val = row[idx]; return str(val).strip() if val is not None else ""
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(cell is None for cell in row): continue
            username = get_val(row, idx_name); role_str = get_val(row, idx_role); email = get_val(row, idx_login)
            state_id = get_val(row, idx_state); district_id = get_val(row, idx_district); township_id = get_val(row, idx_township); phone = get_val(row, idx_phone)
            try: role_id = int(float(role_str)) if role_str else 0
            except ValueError: role_id = 0
            if role_id not in (1, 2, 3, 4, 5, 6):
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "Role မမှန်ကန်ပါ။ (1-6 အတွင်းသာ ဖြစ်ရမည်)"}); continue
            if role_id == 3 and not state_id:
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "Role 3 အတွက် stateID လိုအပ်ပါသည်။"}); continue
            if role_id == 4 and (not state_id or not district_id):
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "Role 4 အတွက် stateID နှင့် districtID လိုအပ်ပါသည်။"}); continue
            if role_id in (5, 6) and (not state_id or not district_id or not township_id):
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "Role 5,6 အတွက် stateID, districtID, townshipID အားလုံး လိုအပ်ပါသည်။"}); continue
            if not username:
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "အသုံးပြုသူအမည် မပါဝင်ပါ။"}); continue
            if not email or not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "Email Format မှားယွင်းနေပါသည်။"}); continue
            if phone and not re.match(r"^(09|\+959)\d{7,9}$", phone):
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "ဖုန်းနံပါတ် Format မှားယွင်းနေပါသည်။"}); continue
            if db.execute(text("SELECT userId FROM `user` WHERE loginName = :email"), {"email": email}).fetchone():
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "ဤအီးမေးလ်ကို အသုံးပြုပြီးသားဖြစ်ပါသည်။"}); continue
            if phone and db.execute(text("SELECT userId FROM `user` WHERE phone = :phone"), {"phone": phone}).fetchone():
                failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "ဤဖုန်းနံပါတ်ကို အသုံးပြုပြီးသားဖြစ်ပါသည်။"}); continue
            final_sid = final_did = final_tid = None
            if role_id == 3: final_sid = state_id
            elif role_id == 4: final_sid, final_did = state_id, district_id
            elif role_id in (5, 6): final_sid, final_did, final_tid = state_id, district_id, township_id
            try:
                db.execute(text("""
                        INSERT INTO `user` (userName, userRole, loginName, password, stateID, districtID, townshipID, status, phone)
                        VALUES (:uname, :role, :email, :pwd, :sid, :did, :tid, 1, :phone)
                    """), {"uname": username, "role": role_id, "email": email, "pwd": hashed_pwd, "sid": final_sid or None, "did": final_did or None, "tid": final_tid or None, "phone": phone if phone else None})
                db.commit(); success_count += 1
            except IntegrityError: db.rollback(); failed_rows.append({"row": row_idx, "email": email, "username": username, "reason": "Database တွင် အချက်အလက် ထပ်နေပါသည်။"})
        return {"status": "success", "message": "အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ။", "success_count": success_count, "duplicate_count": len(failed_rows), "duplicate_emails": failed_rows, "default_password": DEFAULT_PASSWORD}
    except HTTPException: db.rollback(); raise
    except Exception as e: db.rollback(); raise HTTPException(500, f"❌ Excel ဖတ်ရာတွင် အမှားအယွင်း ရှိနေပါသည်။ ({str(e)})")
    finally: db.close()

@app.get("/api/system/users/export-data")
async def api_export_users_data(request: Request, roles: str = Query("")):
    admin_user = request.session.get("user")
    if not admin_user or admin_user.get("role") != "admin": raise HTTPException(403, "Admin သာ လုပ်ဆောင်နိုင်ပါသည်။")
    if not roles: return {"status": "success", "users": []}
    role_list = [r.strip() for r in roles.split(",") if r.strip()]
    if not role_list: return {"status": "success", "users": []}
    db = SessionLocal()
    try:
        placeholders = ", ".join([f":r{i}" for i in range(len(role_list))])
        params = {f"r{i}": r for i, r in enumerate(role_list)}
        sql = text(f"""
            SELECT u.userId, u.userName, u.userRole, u.loginName AS email,
                   u.stateID, st.stateName, u.districtID, dt.districtName,
                   u.townshipID, ts.townshipName, u.phone, u.status
            FROM `user` u
            LEFT JOIN state st ON st.stateID = u.stateID
            LEFT JOIN district dt ON dt.stateID = u.stateID AND dt.districtID = u.districtID
            LEFT JOIN township ts ON ts.stateID = u.stateID AND ts.districtID = u.districtID AND ts.townshipID = u.townshipID
            WHERE u.userRole IN ({placeholders}) ORDER BY u.userRole, u.userName
        """)
        rows = db.execute(sql, params).mappings().all()
        return {"status": "success", "users": [dict(r) for r in rows]}
    except SQLAlchemyError as e: logger.error(f"Export users data error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/system/users/import-excel/errors")
async def api_download_error_excel(request: Request):
    data = await request.json(); errors = data.get("errors", [])
    if not errors: raise HTTPException(400, "❌ Download လုပ်ရန် Error မရှိပါ။")
    wb = Workbook(); ws = wb.active; ws.title = "Error Emails"
    ws.append(["Row နံပါတ်", "အသုံးပြုသူအမည်", "အီးမေးလ် (Login Name)", "အကြောင်းရင်း"])
    for err in errors:
        reason = err.get("reason") or "အမှားအယွင်း ရှိနေပါသည်။"
        ws.append([err.get("row"), err.get("username"), err.get("email"), reason])
    ws.column_dimensions['A'].width = 15; ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 35; ws.column_dimensions['D'].width = 50
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=Import_Errors.xlsx"})

@app.post("/api/system/users/reset-password")
async def api_reset_user_password(request: Request):
    admin_user = request.session.get("user")
    if not admin_user or admin_user.get("role") != "admin": raise HTTPException(403, "Admin သာ လုပ်ဆောင်နိုင်ပါသည်။")
    try: data = await request.json()
    except Exception: raise HTTPException(400, "Invalid JSON body.")
    target_uid = data.get("userId")
    if not target_uid: raise HTTPException(400, "userId လိုအပ်ပါသည်။")
    db = SessionLocal()
    try:
        existing = db.execute(text("SELECT userId, userName FROM `user` WHERE userId = :uid"), {"uid": target_uid}).fetchone()
        if not existing: raise HTTPException(404, "အသုံးပြုသူ မတွေ့ပါ။")
        db.execute(text("UPDATE `user` SET password = :pwd WHERE userId = :uid"), {"pwd": hash_password(DEFAULT_PASSWORD), "uid": target_uid})
        db.commit()
        return {"status": "success", "message": f"'{existing[1]}' ရဲ့ Password ကို default ({DEFAULT_PASSWORD}) ပြန်ပြောင်းပြီးပါပြီ။", "default_password": DEFAULT_PASSWORD}
    except HTTPException: db.rollback(); raise
    except SQLAlchemyError as e: db.rollback(); logger.error(f"Reset password error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.get("/system/dashboard", response_class=HTMLResponse)
async def system_dashboard_page(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    if user.get("role") != "admin": raise HTTPException(403, "Admin သာ ဝင်ရောက်နိုင်ပါသည်။")
    db = SessionLocal()
    role_counts = {"state": 0, "district": 0, "township": 0, "enumerator": 0, "union": 0}
    total_users = total_animals = total_records = 0
    active_counts = {"state": 0, "district": 0, "township": 0, "enumerator": 0, "union": 0}
    try:
        rows = db.execute(text("SELECT userRole, stateID, COUNT(*) AS cnt FROM `user` WHERE userRole != 1 GROUP BY userRole, stateID")).fetchall()
        for row in rows:
            rid = int(row[0]); sid = (row[1] or "").strip(); cnt = int(row[2]); role_name = ROLE_NAMES.get(rid)
            if role_name == "state" and sid == "s15": role_counts["union"] += cnt
            elif role_name in role_counts: role_counts[role_name] += cnt
        total_users = sum(role_counts.values())
        active_rows = db.execute(text("SELECT userRole, stateID, COUNT(*) AS cnt FROM `user` WHERE userRole != 1 AND status = 1 GROUP BY userRole, stateID")).fetchall()
        for row in active_rows:
            rid = int(row[0]); sid = (row[1] or "").strip(); cnt = int(row[2]); role_name = ROLE_NAMES.get(rid)
            if role_name == "state" and sid == "s15": active_counts["union"] += cnt
            elif role_name in active_counts: active_counts[role_name] += cnt
        r = db.execute(text("SELECT COUNT(*) FROM animaltype")).fetchone(); total_animals = int(r[0]) if r else 0
        r = db.execute(text("SELECT COUNT(*) FROM personcv")).fetchone(); total_records = int(r[0]) if r else 0
    except SQLAlchemyError as e: logger.error(f"system_dashboard error: {e}")
    finally: db.close()
    return templates.TemplateResponse(request=request, name="systemAdminDashboard.html", context={
        "active_page": "sys_home", "user": user,
        "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user),
        "role_counts": role_counts, "active_counts": active_counts,
        "total_users": total_users, "total_animals": total_animals, "total_records": total_records,
    })

@app.get("/system/animals", response_class=HTMLResponse)
async def system_animals_page(request: Request):
    user = request.session.get("user")
    if not user: return RedirectResponse("/", status_code=303)
    if user.get("role") != "admin": raise HTTPException(403, "Admin သာ ဝင်ရောက်နိုင်ပါသည်။")
    return templates.TemplateResponse(request=request, name="systemAnimals.html", context={"active_page": "sys_animals", "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user)})

@app.post("/api/system/animals/create")
async def api_create_animal(request: Request):
    admin_user = request.session.get("user")
    if not admin_user or admin_user.get("role") != "admin": raise HTTPException(403, "Admin သာ ဖန်တီးနိုင်ပါသည်။")
    try: payload = await request.json()
    except Exception: raise HTTPException(400, "Invalid JSON body.")
    category = (payload.get("category") or "").strip(); animal_name = (payload.get("animalName") or "").strip()
    needs_breed = bool(payload.get("needsBreed")); raw_breeds = payload.get("breeds") or []
    if not animal_name: raise HTTPException(400, "တိရစ္ဆာန်အမည် ထည့်ပါ။")
    if len(animal_name) > 30: raise HTTPException(400, "တိရစ္ဆာန်အမည်သည် ၃၀ လုံးထက် မကျော်ရပါ။")
    if not isinstance(raw_breeds, list): raise HTTPException(400, "မျိုးစိတ်စာရင်း ပုံစံ မမှန်ကန်ပါ။")
    cleaned_breeds = []; seen_breeds = set()
    for b in raw_breeds:
        b = str(b).strip()
        if not b: continue
        if len(b) > 30: raise HTTPException(400, f"မျိုးစိတ်အမည် '{b[:20]}...' သည် ၃၀ လုံးထက် ကျော်နေပါသည်။")
        key = b.lower()
        if key in seen_breeds: continue
        seen_breeds.add(key); cleaned_breeds.append(b)
    if needs_breed and not cleaned_breeds: raise HTTPException(400, "မျိုးစိတ် အနည်းဆုံး တစ်ခု ထည့်ပါ။")
    CATEGORY_MAP = {
        "large": ("atID01", "largeanimals", "largespecies", "speciesName", "laID", "laSID"),
        "small": ("atID02", "younganimals", "youngspecies", "speciesName", "yaID", "yaSID"),
        "poultry": ("atID03", "livestock", "livestockspecies", "speciesName", "lsID", "lsSID"),
        "breeder": ("atID04", "breedingstock", None, None, "bsID", None),
    }
    if category not in CATEGORY_MAP: raise HTTPException(400, "အမျိုးအစား မမှန်ကန်ပါ။")
    (animal_type_id, animal_table, species_table, species_name_col, animal_prefix, species_prefix) = CATEGORY_MAP[category]
    db = SessionLocal()
    try:
        existing = db.execute(text(f"SELECT animalID FROM `{animal_table}` WHERE animalTypeID = :tid AND animalName = :name"), {"tid": animal_type_id, "name": animal_name}).fetchone()
        if existing: raise HTTPException(409, "ဤတိရစ္ဆာန်အမည် ရှိပြီးသားပါ။")
        new_animal_id = _next_numeric_id(db, animal_table, "animalID", animal_prefix, 2)
        db.execute(text(f"INSERT INTO `{animal_table}` (animalTypeID, animalID, animalName) VALUES (:tid, :aid, :name)"), {"tid": animal_type_id, "aid": new_animal_id, "name": animal_name})
        inserted_breeds = []
        if needs_breed and species_table:
            for breed in cleaned_breeds:
                new_species_id = _next_species_id(db, species_table, species_prefix, new_animal_id, animal_prefix)
                db.execute(text(f"INSERT INTO `{species_table}` (animalID, speciesID, `{species_name_col}`) VALUES (:aid, :sid, :name)"), {"aid": new_animal_id, "sid": new_species_id, "name": breed})
                inserted_breeds.append({"speciesID": new_species_id, "name": breed})
        db.commit()
        return {"status": "success", "message": "တိရစ်ဆာန်အမျိုးအစား ထည့်သွင်းပြီးပါပြီ။", "animalID": new_animal_id, "animalName": animal_name, "animalTypeID": animal_type_id, "breeds": inserted_breeds, "breedsInserted": len(inserted_breeds)}
    except HTTPException: db.rollback(); raise
    except IntegrityError: db.rollback(); raise HTTPException(409, "အချက်အလက် ထပ်နေပါသည်။")
    except SQLAlchemyError as e: db.rollback(); raise HTTPException(500, f"Database error: {e}")
    except Exception as e: db.rollback(); raise HTTPException(500, f"Unexpected error: {e}")
    finally: db.close()

def _next_numeric_id(db, table, id_col, prefix, width):
    try:
        rows = db.execute(text(f"SELECT `{id_col}` FROM `{table}` WHERE `{id_col}` LIKE :p"), {"p": f"{prefix}%"}).fetchall()
    except SQLAlchemyError as e: logger.error(f"_next_numeric_id lookup failed ({table}.{id_col}): {e}"); raise HTTPException(500, f"ID ဖန်တီးရာတွင် Database error: {e}")
    max_n = 0
    for row in rows:
        s = str(row[0] or "")
        if not s.startswith(prefix): continue
        digits = re.sub(r"\D", "", s[len(prefix):])
        if not digits: continue
        try: n = int(digits)
        except ValueError: continue
        if n > max_n: max_n = n
    return f"{prefix}{(max_n + 1):0{width}d}"

def _next_species_id(db, species_table, species_prefix, animal_id, animal_prefix, width=4):
    try:
        rows = db.execute(text(f"SELECT `speciesID` FROM `{species_table}` WHERE `speciesID` LIKE :p"), {"p": f"{species_prefix}%"}).fetchall()
    except SQLAlchemyError as e: logger.error(f"_next_species_id lookup failed ({species_table}): {e}"); raise HTTPException(500, f"မျိုးစိတ် ID ဖန်တီးရာတွင် Database error: {e}")
    max_n = 0
    for row in rows:
        s = str(row[0] or "")
        if not s.startswith(species_prefix): continue
        digits = re.sub(r"\D", "", s[len(species_prefix):])
        if not digits: continue
        try: n = int(digits)
        except ValueError: continue
        if n > max_n: max_n = n
    return f"{species_prefix}{(max_n + 1):0{width}d}"

@app.get("/system/profile", response_class=HTMLResponse)
async def system_profile_page(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ ဝင်ရောက်နိုင်ပါသည်။")
    return templates.TemplateResponse(request=request, name="systemAdminProfile.html", context={"active_page": "sys_profile", "user_state_id": user.get("stateID") or "", "user_state_name": _get_user_state_name(user)})

@app.get("/api/system/profile")
async def api_get_admin_profile(request: Request):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ ကြည့်ရှုနိုင်ပါသည်။")
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT userId, userName, loginName, phone, userRole, status FROM `user` WHERE userId = :uid"), {"uid": user["id"]}).mappings().first()
        if not row: raise HTTPException(404, "အကောင့် မတွေ့ပါ။")
        return {"status": "success", "profile": dict(row)}
    except HTTPException: raise
    except SQLAlchemyError as e: logger.error(f"Get profile error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/system/profile/update-info")
async def api_update_admin_info(request: Request, username: str = Form(...), email: str = Form(...), phone: str = Form(""), old_credential: str = Form("")):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ ပြင်ဆင်နိုင်ပါသည်။")
    db = SessionLocal()
    try:
        current = db.execute(text("SELECT userId, userName, loginName, password FROM `user` WHERE userId = :uid"), {"uid": user["id"]}).mappings().first()
        if not current: raise HTTPException(404, "အကောင့် မတွေ့ပါ။")
        changed_credential = (str(current["userName"]).strip() != username.strip() or str(current["loginName"]).strip() != email.strip())
        if changed_credential:
            if not old_credential.strip(): raise HTTPException(400, "အသုံးပြုသူအမည် သို့မဟုတ် အီးမေးလ် ပြောင်းရန် လက်ရှိ Login သို့မဟုတ် Password ကို ရိုက်ထည့်ပါ။")
            cred = old_credential.strip()
            if not (cred == str(current["loginName"]).strip() or verify_password(cred, current["password"])):
                raise HTTPException(401, "လက်ရှိ အီးမေးလ် သို့မဟုတ် စကားဝှက် မှားနေပါသည်။")
        if str(current["userName"]).strip() != username.strip():
            if db.execute(text("SELECT userId FROM `user` WHERE userName = :u AND userId != :uid"), {"u": username.strip(), "uid": user["id"]}).fetchone():
                raise HTTPException(409, "❌ ဤအသုံးပြုသူအမည်ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")
        if str(current["loginName"]).strip() != email.strip():
            if db.execute(text("SELECT userId FROM `user` WHERE loginName = :e AND userId != :uid"), {"e": email.strip(), "uid": user["id"]}).fetchone():
                raise HTTPException(409, "❌ ဤအီးမေးလ် (Login) ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")
        if phone.strip():
            if db.execute(text("SELECT userId FROM `user` WHERE phone = :p AND userId != :uid"), {"p": phone.strip(), "uid": user["id"]}).fetchone():
                raise HTTPException(409, "❌ ဤဖုန်းနံပါတ်ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")
        db.execute(text("UPDATE `user` SET userName = :uname, loginName = :login, phone = :phone WHERE userId = :uid"),
                   {"uname": username.strip(), "login": email.strip(), "phone": phone.strip() or None, "uid": user["id"]})
        db.commit()
        request.session["user"]["loginName"] = email.strip()
        return {"status": "success", "message": "ကိုယ်ရေးအချက်အလက် ပြင်ဆင်ပြီးပါပြီ။"}
    except HTTPException: db.rollback(); raise
    except IntegrityError: db.rollback(); raise HTTPException(409, "❌ အချက်အလက်တူညီနေပါသည်။")
    except SQLAlchemyError as e: db.rollback(); logger.error(f"Update admin info error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

@app.post("/api/system/profile/change-password")
async def api_change_admin_password(request: Request, old_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
    user = request.session.get("user")
    if not user or user.get("role") != "admin": raise HTTPException(403, "Admin သာ လုပ်ဆောင်နိုင်ပါသည်။")
    if not old_password or not new_password or not confirm_password: raise HTTPException(400, "ချက်အလက်အားလုံး ဖြည့်ပါ။")
    if new_password != confirm_password: raise HTTPException(400, "Password အသစ်နှစ်ခု မတူညီပါ။")
    if len(new_password) < 8: raise HTTPException(400, "Password အသစ်သည် အနည်းဆုံး ၈ လုံး ရှိရပါမည်။")
    if new_password == old_password: raise HTTPException(400, "Password အသစ်နှင့် အဟောင်း မတူညီရပါ။")
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT password FROM `user` WHERE userId = :uid"), {"uid": user["id"]}).fetchone()
        if not row: raise HTTPException(404, "အကောင့် မတွေ့ပါ။")
        if not verify_password(old_password, row[0]): raise HTTPException(401, "လျှို့ဝှက်နံပါတ် အဟောင်း မှားနေပါသည်။")
        db.execute(text("UPDATE `user` SET password = :pwd WHERE userId = :uid"), {"pwd": hash_password(new_password), "uid": user["id"]})
        db.commit()
        return {"status": "success", "message": "လျှို့ဝှက်နံပါတ် ပြောင်းပြီးပါပြီ။"}
    except HTTPException: db.rollback(); raise
    except SQLAlchemyError as e: db.rollback(); logger.error(f"Change password error: {e}"); raise HTTPException(500, f"Database error: {e}")
    finally: db.close()

# ============================================================
# 📥 CSV / EXPORT HELPERS
# ============================================================
def make_csv_response(rows: list, headers: list, filename: str) -> StreamingResponse:
    buf = io.StringIO(); buf.write('\ufeff')
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator='\r\n')
    writer.writerow(headers)
    for r in rows: writer.writerow(r)
    content = buf.getvalue(); buf.close()
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    safe_name = f"{filename}_{stamp}.csv"
    return StreamingResponse(
        iter([content.encode(CSV_ENCODING)]),
        media_type=f"text/csv; charset={CSV_ENCODING}",
        headers={"Content-Disposition": f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{safe_name}", "Cache-Control": "no-store"},
    )

@app.get("/export/report1/csv")
async def export_report1_csv(state: Optional[str] = Query(None), district: Optional[str] = Query(None), township: Optional[str] = Query(None), village: Optional[str] = Query(None)):
    demo = [
        ["ရန်ကုန်တိုင်းဒေသကြီး", "ခရိုင် ၁", "မြို့နယ် ၁", "ကျေးရွာအုပ်စု ၁", 45, 18, 17, 122, 24],
        ["ရန်ကုန်တိုင်းဒေသကြီး", "ခရိုင် ၁", "မြို့နယ် ၂", "ကျေးရွာအုပ်စု ၂", 32, 7, 10, 25, 10],
    ]
    def _m(r):
        if state and r[0] != state: return False
        if district and r[1] != district: return False
        if township and r[2] != township: return False
        if village and r[3] != village: return False
        return True
    filtered = [r for r in demo if _m(r)]
    rows = [[i, r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[5]+r[6]+r[7]+r[8]] for i, r in enumerate(filtered, 1)]
    headers = ["စဉ်", "တိုင်း/ပြည်နယ်", "ခရိုင်", "မြို့နယ်", "ကျေးရွာအုပ်စု", "အိမ်ထောင်စု", "တိရိစ္ဆာန်ကြီး", "တိရိစ္ဆာန်ငယ်", "ကြက်/ဘဲ/ငုံး", "မျိုးတိရိစ္ဆာန်", "စုစုပေါင်း"]
    return make_csv_response(rows, headers, "report1_နယ်မြေဒေသအလိုက်")

@app.get("/export/report2/csv")
async def export_report2_csv(group: Optional[str] = Query(None), state: Optional[str] = Query(None)):
    demo = [["large", "တိရိစ္ဆာန်ကြီး", "နွား", "ဒေသရင်း", 12, 25, 8, 45]]
    filtered = [r for r in demo if (not group or group == "all" or r[0] == group)]
    rows = [[i, r[1], r[2], r[3], r[4], r[5], r[6], r[7]] for i, r in enumerate(filtered, 1)]
    headers = ["စဉ်", "အုပ်စု", "တိရိစ္ဆာန်အမျိုးအစား", "မျိုး (Breed)", "အထီး", "အမ", "သင်းကွပ်", "စုစုပေါင်း"]
    return make_csv_response(rows, headers, "report2_တိရိစ္ဆာန်အမျိုးအစားအလိုက်")

@app.post("/api/survey/part4")
async def submit_part4_api(request: Request, breeding_json: str = Form(...)):
    try: breeding = json.loads(breeding_json)
    except (json.JSONDecodeError, TypeError): raise HTTPException(400, "Invalid breeding data.")
    if not isinstance(breeding, dict): raise HTTPException(400, "Breeding data must be an object.")
    FORM_ID = "6"; GENDER_MALE = "g01"; GENDER_FEMALE = "g03"
    FIELD_MAP = {
        "local_cattle": {"animalTypeID": "atID04", "animalID": "bsID01"},
        "local_buffalo": {"animalTypeID": "atID04", "animalID": "bsID02"},
        "dairy_buffalo": {"animalTypeID": "atID04", "animalID": "bsID03"},
        "pig": {"animalTypeID": "atID04", "animalID": "bsID04"},
        "goat": {"animalTypeID": "atID04", "animalID": "bsID05"},
        "sheep": {"animalTypeID": "atID04", "animalID": "bsID06"},
    }
    rows_to_insert = []
    for key, m in FIELD_MAP.items():
        data = breeding.get(key) or {}
        if not isinstance(data, dict): continue
        try:
            male_n = int(data.get("male") or 0); female_n = int(data.get("female") or 0)
        except (ValueError, TypeError): continue
        if male_n > 0: rows_to_insert.append((FORM_ID, m["animalTypeID"], m["animalID"], None, None, GENDER_MALE, male_n))
        if female_n > 0: rows_to_insert.append((FORM_ID, m["animalTypeID"], m["animalID"], None, None, GENDER_FEMALE, female_n))
    if not rows_to_insert: raise HTTPException(400, "တိရိစ္ဆာန် အရေအတွက် အနည်းဆုံးတစ်ခု ဖြည့်ပါ။")
    conn = get_db_connection(); cursor = conn.cursor()
    inserted = 0
    try:
        conn.start_transaction()
        for row in rows_to_insert:
            cursor.execute("INSERT INTO collecteddata (formID, animalTypeID, animalID, speciesID, ageID, genderID, dataCount) VALUES (%s, %s, %s, %s, %s, %s, %s)", row)
            inserted += 1
        conn.commit()
    except SQLAlchemyError as e:
        conn.rollback(); raise HTTPException(500, f"Database error: {e}")
    finally: cursor.close(); conn.close()
    return {"status": "success", "inserted": inserted, "formID": FORM_ID}

@app.get("/report", response_class=HTMLResponse)
async def report_page_redirect(request: Request):
    try: get_signed_in_user(request)
    except HTTPException: return RedirectResponse("/", status_code=303)
    return RedirectResponse("/admin", status_code=303)

@app.get("/survey/part3")
async def survey_part3_get(request: Request):
    return templates.TemplateResponse(request=request, name="FormPart2.html", context={"active_page": "survey", "largeAnimals": _get_all_large_animals(), "smallAnimals": _get_all_small_animals()})

@app.get("/survey/part4_5")
async def survey_part4_5(request: Request):
    return templates.TemplateResponse(request=request, name="FormPart4_5.html", context={"active_page": "survey"})



# ------------------------------------------------------------
# Existing survey data edit API (owner-restricted)
# ------------------------------------------------------------
EDITABLE_PERSON_FIELDS = {
    "WardName", "householdNo", "interviewDate", "name", "gender",
    "eduStatus", "phoneNo", "age", "headName", "headEduStatus",
    "headGender", "headPhoneNo", "headAge", "Interviewer",
    "interviewerPhoneNo",
}
EDITABLE_ANIMAL_FIELDS = {
    "animalTypeID", "animalID", "speciesID", "ageID", "genderID", "dataCount",
}

@app.get("/enumerator/edit-form", response_class=HTMLResponse)
async def edit_form_page(request: Request):
    user = get_signed_in_user(request)

    if user.get("role") != "enumerator":
        raise HTTPException(
            status_code=403,
            detail="Enumerator role only"
        )

    return templates.TemplateResponse(
        request=request,
        name="edit_form.html",
        context={
            "request": request,
            "user": user,
            "role": user.get("role", ""),
            "active_page": "edit_form",
        },
    )

@app.get("/enumerator/api/forms/{formID}")
async def get_form_for_edit(formID: str, request: Request):
    user = get_signed_in_user(request)

    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    user_id = user["id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Form ပိုင်ရှင်ကို စစ်ဆေးရန် (JOIN ဖြင့် နာမည်များပါ တွဲဆွဲမယ်)
        cursor.execute(
            """
            SELECT p.*,
                   s.stateName,
                   d.districtName,
                   t.townshipName,
                   q.QVName
            FROM personcv p
            LEFT JOIN state s ON s.stateID = p.stateID
            LEFT JOIN district d ON d.stateID = p.stateID AND d.districtID = p.districtID
            LEFT JOIN township t ON t.stateID = p.stateID AND t.districtID = p.districtID AND t.townshipID = p.townshipID
            LEFT JOIN qv q ON q.stateID = p.stateID AND q.districtID = p.districtID AND q.townshipID = p.townshipID AND q.QVID = p.QVID
            WHERE p.formID = %s AND p.userId = %s
            LIMIT 1
            """,
            (formID, user_id),
        )
        person = cursor.fetchone()

        if not person:
            raise HTTPException(
                status_code=404,
                detail="Form မတွေ့ပါ သို့မဟုတ် မိမိပိုင်ဒေတာ မဟုတ်ပါ။"
            )

        # collecteddata ကို ဆွဲထုတ်မယ်
        cursor.execute(
            """
            SELECT animalTypeID, animalID, speciesID,
                   ageID, genderID, dataCount
            FROM collecteddata
            WHERE formID = %s
            """,
            (formID,),
        )
        collected = cursor.fetchall()

        lookup = load_animal_lookup(cursor)

        return {
            "formID": formID,
            "personcv": person,
            "collecteddata": collected,
            "lookup": lookup,
        }

    finally:
        cursor.close()
        conn.close()

# ------------------------------------------------------------
# Enumerator lookup API for Animal dropdowns
# ------------------------------------------------------------
LOOKUP_TABLES = {
    "animalTypes": "animaltype",
    "largeAnimals": "largeanimals",
    "youngAnimals": "younganimals",
    "liveStock": "livestock",
    "breedingstock": "breedingstock",
    "species": "livestockspecies",
    "ages": "agetype",
    "genders": "gender",
}

LOOKUP_ID_CANDIDATES = {
    "animalTypes": ["atID", "animalTypeID", "animalTypeId"],
    "largeAnimals": ["laID", "animalID", "largeAnimalID"],
    "youngAnimals": ["yaID", "animalID", "youngAnimalID"],
    "liveStock": ["lsID", "animalID", "liveStockID"],
    "breedingstock": ["bsID", "animalID", "breedingstockID"],
    "species": ["speciesID", "spID", "lsSpeciesID"],
    "ages": ["ageID"],
    "genders": ["genderID", "gID"],
}

LOOKUP_NAME_CANDIDATES = {
    "animalTypes": ["animalTypeName", "atName", "animalType"],
    "largeAnimals": ["largeAnimalName", "laName", "animalName"],
    "youngAnimals": ["youngAnimalName", "yaName", "animalName"],
    "liveStock": ["liveStockName", "lsName", "animalName"],
    "breedingstock": ["breedingstockName", "bsName", "animalName"],
    "species": ["speciesName", "spName", "liveStockSpecies"],
    "ages": ["ageName", "ageTypeName", "ageType"],
    "genders": ["genderName", "gName", "gender"],
}

def get_lookup_rows(cursor, lookup_key):
    """Database lookup rows များကို {id, name} ပုံစံ ပြောင်းပေးမည်။"""
    if lookup_key not in LOOKUP_TABLES:
        raise ValueError("Invalid lookup key")

    table_name = LOOKUP_TABLES[lookup_key]

    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    columns = [row["Field"] for row in cursor.fetchall()]

    if not columns:
        return []

    id_column = next(
        (col for col in LOOKUP_ID_CANDIDATES[lookup_key] if col in columns),
        None,
    )

    name_column = next(
        (col for col in LOOKUP_NAME_CANDIDATES[lookup_key] if col in columns),
        None,
    )

    # Schema မတူပါက ID နှင့် Name Column ကို fallback ဖြင့် ရှာမည်
    if id_column is None:
        id_column = next(
            (col for col in columns if col.lower().endswith("id") and col.lower() not in ("formid", "userid")),
            None,
        )

    if name_column is None:
        name_column = next(
            (col for col in columns if "name" in col.lower() or col.lower() in ("animaltype", "agetype", "gender")),
            None,
        )

    if id_column is None or name_column is None:
        raise ValueError(f"Lookup schema မကိုက်ညီပါ: {table_name}; columns={columns}")

    cursor.execute(f"SELECT * FROM `{table_name}` ORDER BY `{id_column}`")
    rows = cursor.fetchall()

    result = []
    for row in rows:
        item = {
            "id": row.get(id_column),
            "name": row.get(name_column),
        }
        item.update(row)
        result.append(item)

    return result

def load_animal_lookup(cursor):
    lookup = {}

    # Animal Types
    lookup["animalTypes"] = get_lookup_rows(cursor, "animalTypes")

    # Animals (4 မျိုး ပေါင်း)
    lookup["animals"] = []
    animal_sources = [
        ("atID01", "largeAnimals"),
        ("atID02", "youngAnimals"),
        ("atID03", "liveStock"),
        ("atID04", "breedingstock"),
    ]
    for type_id, source_key in animal_sources:
        for item in get_lookup_rows(cursor, source_key):
            animal = dict(item)
            animal["animalTypeID"] = type_id
            lookup["animals"].append(animal)

    # Species — table ၃ ခုလုံးက ပေါင်းယူ
    lookup["species"] = []

    # 1. largespecies
    try:
        cursor.execute("SELECT * FROM largespecies")
        for row in cursor.fetchall():
            lookup["species"].append({
                "id": row.get("speciesID"),
                "name": row.get("speciesName"),
                "animalID": row.get("animalID"),
                "animalTypeID": "atID01",
                **row,
            })
    except Exception as e:
        logger.warning(f"largespecies lookup failed: {e}")

    # 2. youngspecies
    try:
        cursor.execute("SELECT * FROM youngspecies")
        for row in cursor.fetchall():
            lookup["species"].append({
                "id": row.get("speciesID"),
                "name": row.get("speciesName"),
                "animalID": row.get("animalID"),
                "animalTypeID": "atID02",
                **row,
            })
    except Exception as e:
        logger.warning(f"youngspecies lookup failed: {e}")

    # 3. livestockspecies
    try:
        cursor.execute("SELECT * FROM livestockspecies")
        for row in cursor.fetchall():
            lookup["species"].append({
                "id": row.get("speciesID"),
                "name": row.get("speciesName"),
                "animalID": row.get("animalID"),
                "animalTypeID": "atID03",
                **row,
            })
    except Exception as e:
        logger.warning(f"livestockspecies lookup failed: {e}")

    # Ages
    lookup["ages"] = get_lookup_rows(cursor, "ages")

    # Genders
    lookup["genders"] = get_lookup_rows(cursor, "genders")

    return lookup

@app.get("/enumerator/api/lookups")
async def get_animal_lookups(request: Request):
    user = get_signed_in_user(request)

    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(
            status_code=403,
            detail="Enumerator role only",
        )

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        return {
            "status": "success",
            "lookup": load_animal_lookup(cursor),
        }
    except Exception:
        logger.exception("Failed to load animal lookup data")
        raise HTTPException(
            status_code=500,
            detail="Lookup data မရပါ။ Database Column အမည်များကို စစ်ဆေးပါ။",
        )
    finally:
        cursor.close()
        conn.close()

@app.put("/enumerator/api/forms/{formID}")
async def update_existing_form(formID: str, request: Request):
    user = get_signed_in_user(request)

    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    user_id = user["id"]

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Request JSON မမှန်ကန်ပါ။"
        )

    if not isinstance(payload, dict):
        raise HTTPException(400, "Request data မမှန်ကန်ပါ။")

    person_data = payload.get("personcv") or {}
    animal_data = payload.get("collecteddata") or []

    if not isinstance(person_data, dict) or not isinstance(animal_data, list):
        raise HTTPException(
            400,
            "personcv သို့မဟုတ် collecteddata ပုံစံ မမှန်ပါ။"
        )

    if any(not isinstance(row, dict) for row in animal_data):
        raise HTTPException(400, "တိရစ္ဆာန်ဒေတာ row မမှန်ပါ။")

    # ခွင့်ပြုထားသော personcv fields များကိုသာ Update လုပ်မည်
    person_values = {
        key: value
        for key, value in person_data.items()
        if key in EDITABLE_PERSON_FIELDS
    }

    for key in ("age", "headAge"):
        if key in person_values and str(person_values[key]).strip() != "":
            try:
                person_values[key] = int(person_values[key])
                if person_values[key] < 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=422,
                    detail=f"{key} သည် သုည သို့မဟုတ် အပေါင်းကိန်း ဖြစ်ရပါမည်။"
                )

    if "interviewDate" in person_values and not person_values["interviewDate"]:
        person_values["interviewDate"] = None

    # Animal rows များကို စစ်ဆေးခြင်း
    cleaned_animals = []

    for row in animal_data:
        clean = {
            key: row.get(key)
            for key in EDITABLE_ANIMAL_FIELDS
        }

        if not any(str(value or "").strip() for value in clean.values()):
            continue

        count = str(clean.get("dataCount") or "0").strip()

        try:
            count_int = int(count)
            if count_int < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="အရေအတွက်သည် သုည သို့မဟုတ် အပေါင်းကိန်း ဖြစ်ရပါမည်။"
            )

        clean["dataCount"] = str(count_int)
        cleaned_animals.append(clean)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        conn.start_transaction()

        # ပထမဆုံး Form ပိုင်ရှင်ကို စစ်ပြီး lock ချမည်
        cursor.execute(
            """
            SELECT formID
            FROM personcv
            WHERE formID = %s
              AND userId = %s
            LIMIT 1
            FOR UPDATE
            """,
            (formID, user_id),
        )

        if not cursor.fetchone():
            conn.rollback()
            raise HTTPException(
                status_code=404,
                detail="ဤ Form ID အတွက် သင့်အကောင့်ပိုင် ဒေတာမတွေ့ပါ။"
            )

        # PersonCV Update
        if person_values:
            assignments = ", ".join(
                f"`{key}` = %s"
                for key in person_values
            )

            values = list(person_values.values()) + [formID, user_id]

            cursor.execute(
                f"""
                UPDATE personcv
                SET {assignments}
                WHERE formID = %s
                  AND userId = %s
                """,
                tuple(values),
            )

        # collecteddata အဟောင်းများကို ဖျက်ပြီး အသစ်ပြန်ထည့်မည်
        cursor.execute(
            "DELETE FROM collecteddata WHERE formID = %s",
            (formID,),
        )

        for row in cleaned_animals:
            cursor.execute(
                """
                INSERT INTO collecteddata
                    (
                        formID,
                        animalTypeID,
                        animalID,
                        speciesID,
                        ageID,
                        genderID,
                        dataCount
                    )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    formID,
                    row.get("animalTypeID"),
                    row.get("animalID"),
                    row.get("speciesID"),
                    row.get("ageID"),
                    row.get("genderID"),
                    row.get("dataCount", "0"),
                ),
            )

        conn.commit()

        return {
            "status": "success",
            "message": "ပြင်ဆင်ချက်များ သိမ်းဆည်းပြီးပါပြီ။",
            "formID": formID,
            "animalRecordsSaved": len(cleaned_animals),
        }

    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        logger.exception("Existing survey update failed")
        raise HTTPException(
            status_code=500,
            detail="ဒေတာ Update မအောင်မြင်ပါ။ Database schema နှင့် log ကို စစ်ဆေးပါ။"
        )
    finally:
        cursor.close()
        conn.close()

@app.delete("/enumerator/api/forms/{formID}")
async def delete_existing_form(formID: str, request: Request):
    """
    Enumerator ပိုင်ဆိုင်သော Form ကို ဖျက်ခြင်း။
    personcv နှင့် collecteddata နှစ်ခုလုံးမှ ဖျက်မည်။
    """
    user = get_signed_in_user(request)

    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    user_id = user["id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        conn.start_transaction()

        # Form ပိုင်ရှင်ဟုတ်/မဟုတ် စစ်ဆေးပြီး lock ချမည်
        cursor.execute(
            """
            SELECT formID
            FROM personcv
            WHERE formID = %s
              AND userId = %s
            LIMIT 1
            FOR UPDATE
            """,
            (formID, user_id),
        )

        if not cursor.fetchone():
            conn.rollback()
            raise HTTPException(
                status_code=404,
                detail="ဤ Form ID အတွက် သင့်အကောင့်ပိုင် ဒေတာမတွေ့ပါ။"
            )

        # collecteddata ကို အရင် ဖျက်မည်
        cursor.execute(
            "DELETE FROM collecteddata WHERE formID = %s",
            (formID,),
        )
        deleted_animals = cursor.rowcount

        # personcv ကို ဖျက်မည်
        cursor.execute(
            "DELETE FROM personcv WHERE formID = %s AND userId = %s",
            (formID, user_id),
        )
        deleted_person = cursor.rowcount

        conn.commit()

        return {
            "status": "success",
            "message": "ဒေတာကို ဖျက်ပြီးပါပြီ။",
            "formID": formID,
            "deletedAnimals": deleted_animals,
            "deletedPerson": deleted_person,
        }

    except HTTPException:
        raise
    except Exception:
        conn.rollback()
        logger.exception("Delete form failed")
        raise HTTPException(
            status_code=500,
            detail="ဒေတာဖျက်ခြင်း မအောင်မြင်ပါ။ Database log ကို စစ်ဆေးပါ။"
        )
    finally:
        cursor.close()
        conn.close()

@app.get("/enumerator/api/my-forms")
async def get_my_forms(
    request: Request,
    qv: str = Query(""),
    interviewer: str = Query(""),
    head_name: str = Query(""),
    household_no: str = Query(""),
    form_id: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    collection_status: str = Query("")
):
    user = get_signed_in_user(request)

    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    if collection_status not in ("", "0", "1"):
        raise HTTPException(422, "ကောက်ယူမှုအခြေအနေ မမှန်ကန်ပါ။")

    user_id = user["id"]
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT p.formID, p.name, p.householdNo, p.interviewDate,
                   p.WardName, q.QVName, p.Interviewer, p.headName, p.status
            FROM personcv p
            LEFT JOIN qv q ON q.QVID = p.QVID AND q.stateID = p.stateID AND q.districtID = p.districtID AND q.townshipID = p.townshipID
            WHERE p.userId = %s
        """
        params = [user_id]

        if collection_status != "":
            sql += " AND p.status = %s"
            params.append(int(collection_status))

        if qv.strip():
            sql += " AND p.QVID = %s"
            params.append(qv.strip())
        
        if interviewer.strip():
            sql += " AND p.Interviewer LIKE %s"
            params.append(f"%{interviewer.strip()}%")
            
        if head_name.strip():
            sql += " AND p.headName LIKE %s"
            params.append(f"%{head_name.strip()}%")
            
        if household_no.strip():
            sql += " AND p.householdNo LIKE %s"
            params.append(f"%{household_no.strip()}%")

        if form_id.strip():
            sql += " AND p.formID LIKE %s"
            params.append(f"%{form_id.strip()}%")

        if date_from.strip():
            sql += " AND p.interviewDate >= %s"
            params.append(date_from.strip())

        if date_to.strip():
            sql += " AND p.interviewDate <= %s"
            params.append(date_to.strip())

        sql += " ORDER BY p.interviewDate DESC, p.formID DESC"
        
        cursor.execute(sql, tuple(params))
        forms = cursor.fetchall()
        return {"status": "success", "forms": forms}
    except SQLAlchemyError:
        logger.exception("Failed to load enumerator forms for userId=%s", user_id)
        raise HTTPException(503, "ဒေတာ ရယူမရပါ။ ခဏစောင့်ပြီး ပြန်လည်ကြိုးစားပါ။")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# Filter တွေအတွက် Data သီးသန့် ဆွဲထုတ်ပေးမယ့် API
@app.get("/enumerator/api/my-forms-filters")
async def get_my_forms_filters(request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")
    
    user_id = user["id"]
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # ၁။ ကျေးရွာအုပ်စု စာရင်း
        cursor.execute("""
            SELECT DISTINCT p.QVID, q.QVName 
            FROM personcv p 
            LEFT JOIN qv q ON q.QVID = p.QVID AND q.stateID = p.stateID AND q.districtID = p.districtID AND q.townshipID = p.townshipID
            WHERE p.userId = %s AND p.QVID IS NOT NULL AND p.QVID != ''
        """, (user_id,))
        qvs = cursor.fetchall()

        # ၂။ စာရင်းကောက်သူ စာရင်း
        cursor.execute("""
            SELECT DISTINCT Interviewer 
            FROM personcv 
            WHERE userId = %s AND Interviewer IS NOT NULL AND Interviewer != ''
        """, (user_id,))
        interviewers = [r['Interviewer'] for r in cursor.fetchall()]

        # ၃။ အိမ်ထောင်ဦးစီးအမည် စာရင်း
        cursor.execute("""
            SELECT DISTINCT headName 
            FROM personcv 
            WHERE userId = %s AND headName IS NOT NULL AND headName != ''
        """, (user_id,))
        headNames = [r['headName'] for r in cursor.fetchall()]

        # ၄။ အိမ်ထောင်စုအမှတ် စာရင်း
        cursor.execute("""
            SELECT DISTINCT householdNo 
            FROM personcv 
            WHERE userId = %s AND householdNo IS NOT NULL AND householdNo != ''
        """, (user_id,))
        householdNos = [r['householdNo'] for r in cursor.fetchall()]

        # ၅။ Form ID စာရင်း
        cursor.execute("""
            SELECT DISTINCT formID 
            FROM personcv 
            WHERE userId = %s AND formID IS NOT NULL AND formID != ''
        """, (user_id,))
        formIDs = [r['formID'] for r in cursor.fetchall()]

        return {
            "status": "success", 
            "qvs": qvs, 
            "interviewers": interviewers,
            "headNames": headNames,
            "householdNos": householdNos,
            "formIDs": formIDs
        }
    finally:
        cursor.close()
        conn.close()
# ============================================================
# household Registraction
# ============================================================
@app.get("/enumerator/household-register", response_class=HTMLResponse)
async def household_register(request: Request):
    _require_enumerator_web(request)
    return RedirectResponse("/enumerator/part1", status_code=303)

@app.post("/api/enumerator/households")
async def create_household(request: Request):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")

    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(403, "Enumerator role only")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body.")

    qv_id        = str(payload.get("QVID") or "").strip()
    ward_name    = str(payload.get("WardName") or "").strip()
    household_no = str(payload.get("householdNo") or "").strip()

    # ✅ collectionStatus / remarks
    collection_status = str(payload.get("collectionStatus") or "pending").strip().lower()
    remarks           = str(payload.get("remarks") or "").strip() or None

    if not qv_id:
        raise HTTPException(400, "ကျေးရွာအုပ်စု ရွေးချယ်ပါ။")
    if not ward_name:
        raise HTTPException(400, "ရပ်ကွက်အမည် ဖြည့်ပါ။")
    if not household_no:
        raise HTTPException(400, "အိမ်ထောင်စုအမှတ် ဖြည့်ပါ။")

    if collection_status not in ("pending", "cannot_collect"):
        raise HTTPException(400, "ကောက်ယူမှုအခြေအနေ မမှန်ကန်ပါ။")
    if collection_status == "cannot_collect" and not remarks:
        raise HTTPException(400, "ကောက်ယူလို့မရနိုင်သည့် အကြောင်းပြချက် ဖြည့်ပါ။")
    if collection_status == "pending":
        remarks = None  # pending အတွက် remark မသိမ်း

    user_id     = user["id"]
    state_id    = user.get("stateID")
    district_id = user.get("districtID")
    township_id = user.get("townshipID")

    if not all([state_id, district_id, township_id]):
        raise HTTPException(400, "Enumerator ၏ တည်နေရာ မပြည့်စုံပါ။")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()

        # (1) QVID က Enumerator ၏ မြို့နယ်အတွင်း ဟုတ်/မဟုတ် စစ်
        cursor.execute(
            "SELECT 1 FROM qv WHERE QVID = %s "
            "AND stateID = %s AND districtID = %s AND townshipID = %s LIMIT 1",
            (qv_id, state_id, district_id, township_id),
        )
        if not cursor.fetchone():
            conn.rollback()
            raise HTTPException(403, "သတ်မှတ်ထားသော မြို့နယ်အတွင်းရှိ ကျေးရွာအုပ်စု ကို ရွေးပါ။")

        # (2) Duplicate စစ်
        cursor.execute(
            """SELECT householdID FROM householdRegister
               WHERE stateID = %s AND districtID = %s AND townshipID = %s
                 AND QVID = %s AND WardName = %s AND householdNo = %s
               LIMIT 1""",
            (state_id, district_id, township_id, qv_id, ward_name, household_no),
        )
        if cursor.fetchone():
            conn.rollback()
            raise HTTPException(
                409,
                "ဤကျေးရွာအုပ်စု+ရပ်ကွက်+အိမ်ထောင်စုအမှတ် ပေါင်းစပ်မှု ရှိပြီးသားဖြစ်ပါသည်။",
            )

        # (3) Insert (collectionStatus + collectionRemark)
                # (3) Insert (collectionStatus + remarks)
        cursor.execute(
            """INSERT INTO householdRegister
               (stateID, districtID, townshipID, QVID, WardName, householdNo,
                collectionStatus, remarks, createdBy)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (state_id, district_id, township_id, qv_id, ward_name, household_no,
             collection_status, remarks, user_id),
        )
        new_id = cursor.lastrowid
        conn.commit()

        return {
            "status": "success",
            "message": (
                "အိမ်ထောင်စုစာရင်း (ကောက်ယူလို့မရနိုင်) သိမ်းဆည်းပြီးပါပြီ။"
                if collection_status == "cannot_collect"
                else "အိမ်ထောင်စုစာရင်း သိမ်းဆည်းပြီးပါပြီ။"
            ),
            "householdID": new_id,
            "collectionStatus": collection_status,
        }

    except HTTPException:
        raise
    except IntegrityError:
        conn.rollback()
        raise HTTPException(409, "ဤအိမ်ထောင်စု ရှိပြီးသားဖြစ်ပါသည်။")
    except Exception:
        conn.rollback()
        logger.exception("household create failed")
        raise HTTPException(500, "ဒေတာသိမ်းဆည်းမှု မအောင်မြင်ပါ။")
    finally:
        cursor.close()
        conn.close()


# ===============================================================
# house hold list display
# ===============================================================


# ============================================================
# 🚀 RUN
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app",
                host=os.getenv("HOST", "127.0.0.1"),
                port=int(os.getenv("PORT", "8000")),
                reload=DEBUG)
