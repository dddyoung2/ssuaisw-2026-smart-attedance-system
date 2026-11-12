"""서버 진입점.

    (저장소 루트에서) python main.py
    또는          uvicorn backend.main:app --app-dir src --reload --reload-dir src/backend
"""
import logging

from .config import get_settings
from .factory import create_app

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = create_app()
