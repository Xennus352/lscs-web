import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APP_NAME     = os.getenv("APP_NAME", "LBVD Dashboard")
APP_VERSION  = os.getenv("APP_VERSION", "1.0.0")
DEBUG        = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")
CSV_ENCODING = os.getenv("CSV_ENCODING", "utf-8")

PASSWORD_ITERATIONS = 310_000
DEFAULT_PASSWORD    = "12345678"

JWT_SECRET_KEY      = os.getenv("JWT_SECRET_KEY", "lbvd-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM       = "HS256"
JWT_EXPIRATION_DAYS = 7

SESSION_SECRET       = os.getenv("SESSION_SECRET", "lbvd-change-this-secret-in-production")
COOKIE_HTTPS_ONLY    = os.getenv("COOKIE_HTTPS_ONLY", "false").lower() == "true"
SESSION_MAX_AGE_HOURS = int(os.getenv("SESSION_MAX_AGE_HOURS", "8"))

FIXED_STATE_ID   = "s07"
FIXED_STATE_NAME = "ပဲခူးတိုင်းဒေသကြီး"

ROLE_NAMES = {
    1: "admin", 2: "union", 3: "state",
    4: "district", 5: "township", 6: "enumerator",
}
ROLE_HOME = {
    "admin":      "/system/users",
    "union":      "/admin",
    "state":      "/admin",
    "district":   "/admin",
    "township":   "/admin",
    "enumerator": "/survey/dashboard",
}