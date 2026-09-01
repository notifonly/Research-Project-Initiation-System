"""P09: scGWAS × Spatial Transcriptomics Network Module Discovery.

Archetype F (Spatial GWAS Network). Single focused candidate:
  Apply scGWAS dual-weight module search to spatial transcriptomics microdomain
  GSS scores, replacing PPI topology with spatial neighborhood graph.

Seeded with 3 reference papers: scGWAS (Jia 2022), gsMap (Song 2025),
Spatial GWAS Atlas (Kang 2026).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shared.core.orchestrator import Orchestrator, ProjectResult

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.yaml"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


EXTRA_SKILLS: dict = {}


async def run_project(
    global_semaphore: Any = None,
    breakpoint_handler: Any = None,
) -> ProjectResult:
    cfg = load_config()
    orch = Orchestrator(
        project_id=cfg["project_id"],
        project_dir=PROJECT_DIR,
        archetype_id=cfg["archetype_id"],
        research_direction=cfg["research_direction"],
        global_semaphore=global_semaphore,
        breakpoint_handler=breakpoint_handler,
        project_config=cfg,
        extra_skills=EXTRA_SKILLS,
    )
    return await orch.run()
