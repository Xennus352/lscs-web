import jwt
from fastapi import Request, HTTPException, status, Depends

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM
from app.extensions import security


# ============================================================
# 🔐 AUTH DEPENDENCIES
# ============================================================
def get_signed_in_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login လုပ်ပါ။",
        )
    return user


def verify_mobile_token(credentials=Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token သက်တမ်းကုန်သွားပါပြီ။ ပြန် Login လုပ်ပါ။")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token မမှန်ကန်ပါ။")


# ============================================================
# 👨‍💻 ENUMERATOR GUARDS
# ============================================================
def _compat_session_state_id(request: Request):
    value = request.session.get("stateID")
    if isinstance(value, dict):
        return value.get("stateID")
    return value


def _require_enumerator_web(request: Request):
    user = get_signed_in_user(request)
    if str(user.get("role", "")).lower() != "enumerator":
        raise HTTPException(
            status_code=403,
            detail="Enumerator (Role 6) အကောင့်လိုအပ်ပါသည်။",
        )
    for key, label in (
        ("stateID", "တိုင်းဒေသကြီး/ပြည်နယ်"),
        ("districtID", "ခရိုင်"),
        ("townshipID", "မြို့နယ်"),
    ):
        if not user.get(key):
            raise HTTPException(
                status_code=403,
                detail=f"Enumerator အကောင့်တွင် {label} မသတ်မှတ်ရသေးပါ။",
            )
    return user


def _guard_enumerator_web_route(request: Request):
    if request.url.path.startswith("/enumerator/"):
        return _require_enumerator_web(request)
    return None