from __future__ import annotations

import uuid
from datetime import datetime, timezone


def gen_id(prefix: str = "") -> str:
    base = uuid.uuid4().hex[:12]
    return f"{prefix}_{base}" if prefix else base


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_str(s: str | None, max_len: int = 200) -> str:
    if s is None:
        return ""
    return s[:max_len]
