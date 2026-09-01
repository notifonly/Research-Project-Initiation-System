from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from shared.core.config import settings


class CheckpointState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Checkpoint:
    project_id: str
    step_name: str
    step_index: int
    state: CheckpointState
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    token_usage: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class CheckpointManager:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.dir = settings.l1_warm_dir / project_id / "checkpoints"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, step_name: str) -> Path:
        return self.dir / f"{step_name}.json"

    def save(self, cp: Checkpoint) -> Path:
        p = self._path(cp.step_name)
        data = {
            "project_id": cp.project_id,
            "step_name": cp.step_name,
            "step_index": cp.step_index,
            "state": cp.state.value,
            "context_snapshot": cp.context_snapshot,
            "token_usage": cp.token_usage,
            "created_at": cp.created_at,
            "metadata": cp.metadata,
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def load(self, step_name: str) -> Checkpoint | None:
        p = self._path(step_name)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return Checkpoint(
            project_id=data["project_id"],
            step_name=data["step_name"],
            step_index=data["step_index"],
            state=CheckpointState(data["state"]),
            context_snapshot=data.get("context_snapshot", {}),
            token_usage=data.get("token_usage", {}),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )

    def load_latest(self) -> Checkpoint | None:
        files = sorted(self.dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        return self.load(files[0].stem)

    def is_step_done(self, step_name: str) -> bool:
        cp = self.load(step_name)
        return cp is not None and cp.state == CheckpointState.COMPLETED

    def list_all(self) -> list[Checkpoint]:
        cps: list[Checkpoint] = []
        for p in sorted(self.dir.glob("*.json"), key=lambda x: x.stem):
            cp = self.load(p.stem)
            if cp:
                cps.append(cp)
        return cps

    def clear(self) -> None:
        for p in self.dir.glob("*.json"):
            p.unlink()
