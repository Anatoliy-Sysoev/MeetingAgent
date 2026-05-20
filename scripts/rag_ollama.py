from __future__ import annotations

import sys
from pathlib import Path

WORK_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = WORK_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from asu_june_bot.llm.ollama_common import (  # noqa: E402,F401
    OllamaUnavailableError,
    normalize_llm_answer,
    ollama_chat,
    ollama_embed,
    ollama_generate,
)
