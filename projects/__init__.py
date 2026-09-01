"""Project registry: maps project_id -> async run_project entry point."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from shared.core.orchestrator import ProjectResult

RunProjectFn = Callable[..., Awaitable[ProjectResult]]


def _p01(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p01_gwas_perturb_seq.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p02(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p02_gwas_spatial.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p03(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p03_gwas_scatac.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p04(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p04_prs_advance.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p05(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p05_sc_multiomics_ai.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p06(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p06_digital_immune.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p07(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p07_aging_clock.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p08(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p08_cross_ethnic_multiomics.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


def _p09(global_semaphore: Any = None, breakpoint_handler: Any = None) -> Awaitable[ProjectResult]:
    from projects.p09_spatial_gwas_network.tool_flow import run_project
    return run_project(global_semaphore=global_semaphore, breakpoint_handler=breakpoint_handler)


PROJECTS: dict[str, RunProjectFn] = {
    "p01_gwas_perturb_seq": _p01,
    "p02_gwas_spatial": _p02,
    "p03_gwas_scatac": _p03,
    "p04_prs_advance": _p04,
    "p05_sc_multiomics_ai": _p05,
    "p06_digital_immune": _p06,
    "p07_aging_clock": _p07,
    "p08_cross_ethnic_multiomics": _p08,
    "p09_spatial_gwas_network": _p09,
}

ARCHETYPE_MAP: dict[str, str] = {
    "p01_gwas_perturb_seq": "archetype_a_v2g",
    "p02_gwas_spatial": "archetype_a_v2g",
    "p03_gwas_scatac": "archetype_a_v2g",
    "p04_prs_advance": "archetype_b_prs",
    "p05_sc_multiomics_ai": "archetype_c_sc_ai",
    "p06_digital_immune": "archetype_d_omics_score",
    "p07_aging_clock": "archetype_d_omics_score",
    "p08_cross_ethnic_multiomics": "archetype_e_cross_ethnic",
    "p09_spatial_gwas_network": "archetype_f_spatial_gwas",
}

__all__ = ["PROJECTS", "ARCHETYPE_MAP", "RunProjectFn"]
