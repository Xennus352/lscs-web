import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.database import SessionLocal
from app.dependencies import get_signed_in_user
from app.lookups import _get_user_state_name
from app.security import hash_password, verify_password
from app.templating import templates

logger = logging.getLogger("lbvd")
router = APIRouter(tags=["settings"])


def _fresh_user(user):
    try:
        db = SessionLocal()
        try:
            row = db.execute(
                text("SELECT userId, userName, loginName, phone, userRole, "
                     "stateID, districtID, townshipID FROM `user` WHERE userId = :uid"),
                {"uid": user.get("id")},
            ).mappings().first()
            if row:
                return {**user, **dict(row), "id": row["userId"]}
        finally:
            db.close()
    except SQLAlchemyError as e:
        logger.warning("fresh_user lookup: %s", e)
    return user


@router.get("/settings")
async def settings_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=303)
    fresh = _fresh_user(user)
    request.session["user"] = fresh
    return templates.TemplateResponse(request=request, name="settings.html", context={
        "active_page": "settings",
        "user_state_id": fresh.get("stateID") or "",
        "user": fresh,
        "role": fresh.get("role") or "admin",
        "user_state_name": _get_user_state_name(fresh),
        "user_district_id": fresh.get("districtID") or "",
        "user_township_id": fresh.get("townshipID") or "",
    })


@router.get("/usersettings", response_class=HTMLResponse)
async def usersettings_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/", status_code=303)
    fresh = _fresh_user(user)
    request.session["user"] = fresh
    return templates.TemplateResponse(request=request, name="usersettings.html", context={
        "active_page": "usersettings",
        "user_state_id": fresh.get("stateID") or "",
        "user": fresh,
        "role": fresh.get("role") or "admin",
        "user_state_name": _get_user_state_name(fresh),
        "user_district_id": fresh.get("districtID") or "",
        "user_township_id": fresh.get("townshipID") or "",
    })


@router.get("/api/settings/profile")
async def api_get_profile(request: Request):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT userId, userName, loginName, phone, userRole "
                 "FROM `user` WHERE userId = :uid"),
            {"uid": user.get("id")},
        ).mappings().first()
        if not row:
            raise HTTPException(404, "User မတွေ့ပါ။")
        return {"status": "success", "data": {
            "id": row["userId"], "name": row["userName"],
            "phone": row["phone"] or "", "loginName": row["loginName"] or "",
            "roleId": row["userRole"],
        }}
    finally:
        db.close()


@router.post("/api/settings/profile")
async def api_update_profile(request: Request):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body.")

    name = str(payload.get("name") or "").strip()
    phone = str(payload.get("phone") or "").strip()
    if not name:
        raise HTTPException(400, "အမည် ထည့်ပါ။")
    if len(name) < 2:
        raise HTTPException(400, "အမည် အနည်းဆုံး ၂ လုံး ရှိရမည်။")
    if len(name) > 100:
        raise HTTPException(400, "အမည် ၁၀၀ လုံးထက် မကျော်ရပါ။")
    if not phone:
        raise HTTPException(400, "ဖုန်းနံပါတ် ထည့်ပါ။")
    if not re.match(r"^09\d{7,9}$", phone):
        raise HTTPException(400, "ဖုန်းနံပါတ်ပုံစံ မှားနေသည်။ (ဥပမာ - 09421234567)")

    db = SessionLocal()
    try:
        existing = db.execute(
            text("SELECT userId FROM `user` WHERE phone = :phone AND userId != :uid"),
            {"phone": phone, "uid": user["id"]},
        ).fetchone()
        if existing:
            raise HTTPException(409, "ဤဖုန်းနံပါတ်ကို အခြားသူတစ်ဦး အသုံးပြုနေပါသည်။")

        db.execute(
            text("UPDATE `user` SET userName = :name, phone = :phone WHERE userId = :uid"),
            {"name": name, "phone": phone, "uid": user["id"]},
        )
        db.commit()

        session_user = request.session.get("user") or {}
        session_user["userName"] = name
        session_user["phone"] = phone
        request.session["user"] = session_user
        return {"status": "success", "message": "ကိုယ်ရေးအချက်အလက် သိမ်းဆည်းပြီးပါပြီ။"}
    except HTTPException:
        db.rollback(); raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "ဤဖုန်းနံပါတ်ကို အသုံးပြုပြီးသားပါ။")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("update profile error: %s", e)
        raise HTTPException(500, f"Database error: {e}")
    finally:
        db.close()


@router.post("/api/settings/password")
async def api_change_password(request: Request):
    try:
        user = get_signed_in_user(request)
    except HTTPException:
        raise HTTPException(401, "Login လုပ်ပါ။")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body.")

    current_pwd = str(payload.get("current") or "")
    new_pwd = str(payload.get("new") or "")
    confirm_pwd = str(payload.get("confirm") or "")

    if not current_pwd:
        raise HTTPException(400, "လက်ရှိ လျှို့ဝှက်နံပါတ် ထည့်ပါ။")
    if not new_pwd:
        raise HTTPException(400, "လျှို့ဝှက်နံပါတ် အသစ် ထည့်ပါ။")
    if len(new_pwd) < 8:
        raise HTTPException(400, "လျှို့ဝှက်နံပါတ် အနည်းဆုံး ၈ လုံး ရှိရမည်။")
    if new_pwd == current_pwd:
        raise HTTPException(400, "လျှို့ဝှက်နံပါတ် အသစ်က လက်ရှိနှင့် မတူရပါ။")
    if new_pwd != confirm_pwd:
        raise HTTPException(400, "လျှို့ဝှက်နံပါတ် နှစ်ခု မတူညီပါ။")

    db = SessionLocal()
    try:
        row = db.execute(text("SELECT password FROM `user` WHERE userId = :uid"),
                         {"uid": user["id"]}).fetchone()
        if not row:
            raise HTTPException(404, "User မတွေ့ပါ။")
        if not verify_password(current_pwd, row[0]):
            raise HTTPException(400, "လက်ရှိ လျှို့ဝှက်နံပါတ် မှားနေသည်။")

        db.execute(text("UPDATE `user` SET password = :pwd WHERE userId = :uid"),
                   {"pwd": hash_password(new_pwd), "uid": user["id"]})
        db.commit()
        return {"status": "success", "message": "လျှို့ဝှက်နံပါတ် ပြောင်းလဲပြီးပါပြီ။"}
    except HTTPException:
        db.rollback(); raise
    except SQLAlchemyError as e:
        db.rollback()
        logger.error("change password error: %s", e)
        raise HTTPException(500, f"Database error: {e}")
    finally:
        db.close()