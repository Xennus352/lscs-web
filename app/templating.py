import logging, os
from pathlib import Path
from fastapi.templating import Jinja2Templates

from app.lookups import get_user_header_info

logger = logging.getLogger("lbvd")

HERE         = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent

CANDIDATES = [PROJECT_ROOT / "templates", HERE / "templates", HERE / "outputs"]
_env_dir = os.getenv("TEMPLATE_DIR")
if _env_dir:
    final_template_dir = Path(_env_dir)
else:
    final_template_dir = next((c for c in CANDIDATES if c.is_dir()), PROJECT_ROOT / "templates")

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

# Role label + district/township line for the shared top bar.
templates.env.globals["get_user_header_info"] = get_user_header_info