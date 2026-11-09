import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from app.config import ROLE_NAMES, ROLE_HOME
from app.database import get_db_connection
from app.extensions import limiter
from app.security import verify_password
from app.templating import templates

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["auth"])


# ============================================================
# 🔧 HELPERS
# ============================================================
def _get_client_ip(request: Request) -> str:
    """Get real client IP (handles reverse proxy)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _get_device_id(request: Request) -> str:
    """Get or create a stable device ID per browser session."""
    device_id = request.session.get("device_id")
    if not device_id:
        device_id = str(uuid.uuid4())
        request.session["device_id"] = device_id
    return device_id


def _check_user_status(user_row) -> bool:
    """Safely check user is active. Accepts '1', 1, True, 'active', etc."""
    status = user_row.get("status")
    if status is None:
        return False
    return str(status).strip().lower() in ("1", "true", "active", "enabled")


def _resolve_role(user_row):
    try:
        role_id = int(user_row.get("role_id"))
        return ROLE_NAMES.get(role_id), role_id
    except (TypeError, ValueError):
        return str(user_row.get("role_id") or "").strip().lower(), None


def _log_login_attempt(username, ip, user_agent, success, reason=""):
    """Structured log for audit trail."""
    logger.info(
        "LOGIN_ATTEMPT | user=%s | ip=%s | success=%s | reason=%s | ua=%s",
        username, ip, success, reason, (user_agent or "")[:120],
    )


def _build_session_user(user, request, device_uuid=None) -> dict:
    """Build session user dict with device + audit info."""
    role, role_id = _resolve_role(user)
    return {
        "id": user["id"],
        "role": role,
        "role_id": role_id,
        "loginName": user["login_name"],
        "stateID": user.get("stateID"),
        "districtID": user.get("districtID"),
        "townshipID": user.get("townshipID"),
        # 🔍 Audit fields for shared accounts
        "device_id": _get_device_id(request),
        "device_uuid": device_uuid,
        "login_ip": _get_client_ip(request),
        "login_ua": (request.headers.get("user-agent") or "")[:200],
        "login_at": datetime.utcnow().isoformat(),
    }


def _clean_device_uuid(value) -> str | None:
    """Return a canonical UUID string, or None when the value is missing/invalid."""
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value).strip()))
    except (ValueError, AttributeError, TypeError):
        return None


def _ensure_enumerator_device(user_id, platform, device_name=None, device_uuid=None) -> str | None:
    """Reuse or create a device UUID and link it to this enumerator account.

    The browser/mobile client keeps the UUID in local storage, so the same
    device UUID follows the user between accounts.  ``sync_devices`` is keyed by
    ``(device_id, userID)``: one physical device can therefore have one row per
    enumerator account, while an existing row for the same user is not duplicated.
    """
    existing = _clean_device_uuid(device_uuid)
    device_id = existing or str(uuid.uuid4())

    conn = cursor = None
    persisted = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM sync_devices "
            "WHERE device_id = %s AND userID = %s LIMIT 1",
            (device_id, user_id),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                "INSERT INTO sync_devices "
                "(device_id, userID, platform, device_name, status) "
                "VALUES (%s, %s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE device_id = VALUES(device_id)",
                (
                    device_id,
                    user_id,
                    platform,
                    (device_name or "")[:100] or None,
                ),
            )
            conn.commit()
        persisted = True
    except Exception:
        logger.exception(
            "Failed to register enumerator device %s for user %s", device_id, user_id
        )
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()
    # Do not ask the client to keep a UUID that was not recorded server-side;
    # the next login will try again.
    return device_id if persisted else None


def _fetch_user_by_login(username: str):
    """Fetch user row safely. Returns (user, error_type)."""
    conn = cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT userId AS id, loginName AS login_name, password, "
            "userRole AS role_id, stateID, districtID, townshipID, status "
            "FROM `user` "
            # loginName uses a case-insensitive unicode collation.  The binary
            # comparison makes login case-sensitive without changing the schema.
            "WHERE loginName = %s "
            "AND CAST(loginName AS BINARY) = CAST(%s AS BINARY) "
            "LIMIT 1",
            (username, username),
        )
        return cursor.fetchone(), None
    except Exception:
        logger.exception("Login DB query failed")
        return None, "db_error"
    finally:
        if cursor: cursor.close()
        if conn:   conn.close()


# ============================================================
# 🔑 WEB LOGIN
# ============================================================
@router.post("/api/login")
@limiter.limit("40/10 minute")
async def web_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    device_uuid: str = Form(None),
):
    username = username.strip()
    ip = _get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")

    if not username or not password:
        _log_login_attempt(username, ip, user_agent, False, "empty_credentials")
        raise HTTPException(400, "Username နှင့် Password ထည့်သွင်းပါ။")

    user, db_error = _fetch_user_by_login(username)
    if db_error:
        _log_login_attempt(username, ip, user_agent, False, db_error)
        raise HTTPException(503, "ဝန်ဆောင်မှုကို ယာယီအသုံးမပြုနိုင်ပါ။")

    if user is None:
        _log_login_attempt(username, ip, user_agent, False, "user_not_found")
        raise HTTPException(401, "Username သို့မဟုတ် Password မှားယွင်းနေပါသည်။")

    if not verify_password(password, user["password"]):
        _log_login_attempt(username, ip, user_agent, False, "wrong_password")
        raise HTTPException(401, "Username သို့မဟုတ် Password မှားယွင်းနေပါသည်။")

    if not _check_user_status(user):
        _log_login_attempt(username, ip, user_agent, False, "account_disabled")
        raise HTTPException(403, "သင့်အကောင့်ကို အသုံးပြုခွင့် ပိတ်ထားပါသည်။")

    role, _ = _resolve_role(user)

    # Enumerator clients keep a device UUID in local storage. Reuse it for the
    # current account, adding a sync_devices row only when this (device, user)
    # pair has not been recorded before.
    enumerator_device_uuid = None
    if role == "enumerator":
        enumerator_device_uuid = _ensure_enumerator_device(
            user_id=user["id"],
            platform="web",
            device_name=request.headers.get("user-agent"),
            device_uuid=device_uuid,
        )

    # Preserve device_id across session clear (same browser = same device)
    existing_device_id = request.session.get("device_id")
    request.session.clear()
    request.session["device_type"] = "web"
    if existing_device_id:
        request.session["device_id"] = existing_device_id
    request.session["user"] = _build_session_user(
        user, request, device_uuid=enumerator_device_uuid
    )

    _log_login_attempt(username, ip, user_agent, True, "web_login_success")

    return {
        "status": "success",
        "role": role,
        "redirect": ROLE_HOME.get(role, "/survey/part1"),
        "device_id": request.session.get("device_id"),
        "device_uuid": enumerator_device_uuid,
    }


# ============================================================
# 🚪 LOGOUT
# ============================================================
@router.get("/logout")
async def logout_page(request: Request):
    user = request.session.get("user") or {}
    logger.info(
        "LOGOUT | user=%s | device=%s | ip=%s",
        user.get("loginName", "?"),
        user.get("device_id", "?"),
        user.get("login_ip", "?"),
    )
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.post("/api/logout")
async def api_logout(request: Request):
    user = request.session.get("user") or {}
    logger.info(
        "LOGOUT_API | user=%s | device=%s",
        user.get("loginName", "?"), user.get("device_id", "?"),
    )
    request.session.clear()
    return {"status": "success"}


@router.post("/api/web-auto-logout")
async def web_auto_logout(request: Request):
    if request.session.get("device_type") == "web":
        request.session.clear()
        return {"status": "success"}
    return {"status": "ignored"}


# ============================================================
# 📝 REGISTER
# ============================================================
@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html", context={})