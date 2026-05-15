from __future__ import annotations

import argparse
import sys
from pathlib import Path


WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Asu June Bot FastAPI server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("uvicorn не установлен. Установи: .\\.venv\\Scripts\\python.exe -m pip install fastapi uvicorn") from exc

    uvicorn.run("asu_june_bot.api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
