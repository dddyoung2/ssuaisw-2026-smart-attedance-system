"""출석 시스템 서버 실행.

    python main.py            # http://127.0.0.1:8000  (API 문서: /docs, 화면: /app/)
    python main.py --reload   # 코드 수정 시 자동 재시작 (개발용)
"""
import sys
from pathlib import Path

import uvicorn

SRC_DIR = Path(__file__).resolve().parent / "src"

if __name__ == "__main__":
    reload = "--reload" in sys.argv
    uvicorn.run(
        "backend.main:app",
        app_dir=str(SRC_DIR),
        host="127.0.0.1",
        port=8000,
        reload=reload,
        reload_dirs=[str(SRC_DIR / "backend")] if reload else None,
    )
