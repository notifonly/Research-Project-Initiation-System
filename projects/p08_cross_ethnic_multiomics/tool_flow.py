"""P08: Cross-ethnic multi-omics integration.

Archetype E (Cross-Ethnic). Three parallel research lines:
  biomarker_portability, prs_transportability, causal_inference.
No divergent step needed - uses standard skill pipeline from archetype E config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from archetypes.archetype_e_cross_ethnic.skills.skill_07_cross_ethnic_card_extract import (
    CrossEthnicCardExtract,
)
from shared.core.orchestrator import Orchestrator, ProjectResult

PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "config.yaml"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


EXTRA_SKILLS: dict = {
    "s7_evidence_card_extract": CrossEthnicCardExtract,
}


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
