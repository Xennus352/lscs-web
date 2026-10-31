from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from packaging.version import InvalidVersion, Version

from app.constants import APK_DIR
from app.extensions import limiter
from app.utils import find_latest_apk, sha256_of_file

# ⚠️ auth guard မထည့်ရ — public route ဖြစ်ရမယ်
router = APIRouter(prefix="/api", tags=["updates"])


@router.get("/check-update")
@limiter.limit("60/minute")
def check_update(request: Request, current_version: str | None = None):
    latest = find_latest_apk()
    if latest is None:
        return {"update_available": False, "reason": "no_apks"}

    filename, version, st = latest

    try:
        client_ver = Version(current_version) if current_version else None
    except InvalidVersion:
        raise HTTPException(400, detail="invalid current_version")

    update_available = client_ver is None or version > client_ver

    # ★ ETag ကို SHA-256 မတွက်ခင် စစ်တယ် — 304 မှာ body မပါရ
    etag = f'W/"{filename}-{st.st_size}-{int(st.st_mtime)}"'
    if_none_match = request.headers.get("if-none-match", "")
    if etag in {tag.strip() for tag in if_none_match.split(",")}:
        return Response(status_code=304, headers={"ETag": etag})

    payload = {
        "update_available": update_available,
        "version": str(version),
        "file_name": filename,
        "size": st.st_size,
        "sha256": sha256_of_file(APK_DIR / filename),
        "download_url": str(request.url_for("apks", path=filename)),
    }

    return JSONResponse(
        content=payload,
        headers={"ETag": etag, "Cache-Control": "public, max-age=60"},
    )


@router.get("/download-latest")
def download_latest(request: Request):
    """Latest APK ကို 302 redirect နဲ့ တိုက်ရိုက် download ပေးတယ်။"""
    latest = find_latest_apk()
    if latest is None:
        raise HTTPException(404, detail="No APK available")

    filename, version, _ = latest
    return RedirectResponse(
        url=str(request.url_for("apks", path=filename)),
        status_code=302,
        headers={
            "Cache-Control": "no-store",
            "X-APK-Version": str(version),
        },
    )