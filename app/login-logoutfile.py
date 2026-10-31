
# ============================================================
# 🏠 ROOT (Role အလိုက် ညွှန်းခြင်း)
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def root(request: Request,
               state: str = Query(None), district: str = Query(None),
               township: str = Query(None), qv: str = Query(None)):
    user = request.session.get("user")
    if not user:
        return templates.TemplateResponse(request=request, name="login.html", context={})

    role = user.get("role", "admin")

    if role == "admin":
        return RedirectResponse("/system/users", status_code=303)
    if role == "enumerator":
        return RedirectResponse("/enumerator/part1", status_code=303)
    if role == "staff":
        return RedirectResponse("/survey/part1", status_code=303)

    region_name, animals, stats = query_dashboard_data(user, state, district, township, qv)
    user_state_name = _get_user_state_name(user)

    return templates.TemplateResponse(
        request=request, name="reportDashboard.html",
        context={
            "stats": stats, "animals": animals, "role": role,
            "region_name": region_name,
            "user_state_id":    user.get("stateID") or "",
            "user_state_name":  user_state_name,
            "user_district_id": user.get("districtID") or "",
            "user_township_id": user.get("townshipID") or "",
            "filters": {"state": state, "district": district,
                        "township": township, "qv": qv},
            "active_page": "home",
        },
    )

logger = logging.getLogger(__name__)

# ============================================================
# ⚙️ ENV & CONSTANTS (JWT & Rate Limit အတွက်)
# ============================================================
# ⭐ JWT အတွက် သတ်မှတ်ချက်များ
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "lbvd-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7 # Mobile Token သက်တမ်း ၇ ရက်

# ⭐ Rate Limiter ဖန်တီးခြင်း
limiter = Limiter(key_func=get_remote_address)

# ⭐ Token စစ်ဆေးရန်
security = HTTPBearer()

def verify_mobile_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Mobile App ရဲ့ JWT Token ကို စစ်ဆေးတဲ့ Function"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token သက်တမ်းကုန်သွားပါပြီ။ ပြန် Login လုပ်ပါ။")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token မမှန်ကန်ပါ။")

def get_signed_in_user(request: Request):
    """Web Session မှ User ကို ယူခြင်း"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login လုပ်ပါ။")
    return user

# ============================================================
# 🔑 LOGIN APIs (WEB & MOBILE)
# ============================================================

@app.post("/api/login")
@limiter.limit("5/10 minute")  # ⭐ Rate Limit - ၁၀ မိနစ် ၅ ခါ
async def web_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Web Browser အတွက် Login (Cookie Session သုံးမယ်)"""
    username = username.strip()

    if not username or not password:
        raise HTTPException(400, "Username နှင့် Password ထည့်သွင်းပါ။")

    conn = None
    cursor = None
    user = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT userId AS id, loginName AS login_name, password,
                   userRole AS role_id, stateID, districtID, townshipID, status
            FROM `user` WHERE loginName = %s LIMIT 1
            """,
            (username,)
        )
        user = cursor.fetchone()
    except Exception:
        logger.exception("Web login DB query failed")
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

    # ⭐ Web အတွက် Session ကိုပဲ သုံးမယ်
    request.session.clear()
    request.session["device_type"] = "web"
    request.session["user"] = {
        "id": user["id"],
        "role": role,
        "role_id": role_id,
        "loginName": user["login_name"],
        "stateID": user.get("stateID"),
        "districtID": user.get("districtID"),
        "townshipID": user.get("townshipID"),
    }

    return {
        "status": "success",
        "role": role,
        "redirect": ROLE_HOME.get(role, "/survey/part1")
    }


@app.post("/api/mobile/login")
@limiter.limit("30/10 minute")  # ⭐ Rate Limit - ၁၀ မိနစ် ၅ ခါ
async def mobile_login(
    request: Request,  # ⭐ Rate Limit အတွက် request မဖြစ်မနေ ပါရမယ်
    username: str = Form(...),
    password: str = Form(...)
):
    """Mobile App အတွက် သီးသန့် Login (JWT Token ထုတ်ပေးမယ်)"""
    username = username.strip()

    if not username or not password:
        raise HTTPException(400, "Username နှင့် Password ထည့်သွင်းပါ။")

    conn = None
    cursor = None
    user = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT userId AS id, loginName AS login_name, password,
                   userRole AS role_id, stateID, districtID, townshipID, status
            FROM `user` WHERE loginName = %s LIMIT 1
            """,
            (username,)
        )
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

    # ⭐ Mobile အတွက် JWT Token ထုတ်မယ် (၇ ရက် သက်တမ်း)
    payload = {
        "user_id": user["id"],
        "role": role,
        "role_id": role_id,
        "login_name": user["login_name"],
        "stateID": user.get("stateID"),
        "districtID": user.get("districtID"),
        "townshipID": user.get("townshipID"),
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    return {
        "status": "success",
        "token": token,
        "role": role,
        "redirect": ROLE_HOME.get(role, "/survey/part1")
    }


# ============================================================
# 🚪 LOGOUT APIs
# ============================================================
@app.get("/logout")
async def logout_page(request: Request):
    """Web User ကိုယ်တိုင် Logout နှိပ်တဲ့အခါ"""
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.post("/api/logout")
async def api_logout(request: Request):
    """Web API ကနေ Logout လုပ်တဲ့အခါ (Frontend က ခေါ်ရင်)"""
    request.session.clear()
    return {"status": "success"}


@app.post("/api/web-auto-logout")
async def web_auto_logout(request: Request):
    """Web Browser အတွက် သီးသန့် Auto Logout (၁၀ မိနစ် မလှုပ်ရှားရင်)"""
    if request.session.get("device_type") == "web":
        request.session.clear()
        return {"status": "success", "message": "Web session auto-logged out."}
    return {"status": "ignored", "message": "Not a web session."}


@app.post("/api/mobile/logout")
async def mobile_logout(payload: dict = Depends(verify_mobile_token)):
    """Mobile App အတွက် Logout API (Token Blacklist လုပ်ချင်ရင် ဒီနေရာမှာ လုပ်နိုင်တယ်)"""
    # ဒီနေရာမှာ Token ကို Blacklist ထဲ ထည့်တာမျိုး လုပ်နိုင်ပါတယ်
    return {"status": "success", "message": "Mobile logged out successfully."}