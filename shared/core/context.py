from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from shared.core.config import settings


class L0ColdStore:
    def __init__(self, project_id: str) -> None:
        self.root = settings.l0_cold_dir / project_id
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / key

    def save_bytes(self, key: str, data: bytes) -> Path:
        p = self.path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def save_text(self, key: str, text: str) -> Path:
        return self.save_bytes(key, text.encode("utf-8"))

    def load_bytes(self, key: str) -> Optional[bytes]:
        p = self.path_for(key)
        return p.read_bytes() if p.exists() else None

    def load_text(self, key: str) -> Optional[str]:
        b = self.load_bytes(key)
        return b.decode("utf-8") if b else None

    def exists(self, key: str) -> bool:
        return self.path_for(key).exists()

    def keys(self) -> list[str]:
        if not self.root.exists():
            return []
        return [str(p.relative_to(self.root)).replace("\\", "/") for p in self.root.rglob("*") if p.is_file()]


class L2WorkingMemory:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def update(self, d: dict[str, Any]) -> None:
        self._data.update(d)

    def pop(self, key: str, default: Any = None) -> Any:
        return self._data.pop(key, default)

    def clear(self) -> None:
        self._data.clear()

    def snapshot(self) -> dict[str, Any]:
        snap: dict[str, Any] = {}
        for k, v in self._data.items():
            try:
                json.dumps(v)
                snap[k] = v
            except (TypeError, ValueError):
                snap[k] = str(v)
        return snap

    def has(self, key: str) -> bool:
        return key in self._data


class ContextManager:
    """3-tier context: L0 cold disk, L1 warm LanceDB (cards), L2 hot working memory."""

    def __init__(self, project_id: str, l1_store: Any | None = None) -> None:
        self.project_id = project_id
        self.l0 = L0ColdStore(project_id)
        self.l1 = l1_store
        self.l2 = L2WorkingMemory()

    def warm_to_l2(self, key: str, value: Any) -> None:
        self.l2.set(key, value)

    def cold_to_l2(self, key: str) -> Optional[str]:
        return self.l0.load_text(key)

    def flush_l2_snapshot(self, key: str) -> Path:
        return self.l0.save_text(f"l2_snapshots/{key}.json", json.dumps(self.l2.snapshot(), ensure_ascii=False, indent=2))
