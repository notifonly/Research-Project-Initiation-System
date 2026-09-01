"""P05 consistency validation: checks dimensions, coverage fields, and config-data alignment.

Run with:
    python scripts/validate_p05_consistency.py
    python scripts/validate_p05_consistency.py --all   # also check JS alignment
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ERROR: {e}")
        return None


def load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def check_harness_dimensions() -> list[str]:
    """Check harness_result.json has all dimensions from config.yaml."""
    errors: list[str] = []
    config = load_yaml(PROJECT_ROOT / "scripts" / "p05_harness" / "config.yaml")
    if not config:
        return ["Cannot load harness config.yaml"]

    rubric = config.get("rubric", {})
    expected_dims = set(rubric.keys())

    result = load_json(PROJECT_ROOT / "data" / "p05_harness_output" / "harness_result.json")
    if not result:
        return ["Cannot load harness_result.json"]

    actual_dims = set(result.get("dimension_averages", {}).keys())
    missing = expected_dims - actual_dims
    extra = actual_dims - expected_dims

    if missing:
        errors.append(f"harness_result.json MISSING dimensions: {sorted(missing)}")
    if extra:
        errors.append(f"harness_result.json has EXTRA dimensions: {sorted(extra)}")

    for candidate in result.get("candidates", []):
        cid = candidate.get("candidate_id", "?")
        for it in candidate.get("iterations", []):
            it_scores = set(it.get("scores", {}).keys())
            it_missing = expected_dims - it_scores
            if it_missing:
                errors.append(f"  {cid} iter {it.get('iteration', '?')} missing dims: {sorted(it_missing)}")

    if not errors:
        print(f"  OK harness dimensions: {sorted(expected_dims)}")
    return errors


def check_coverage_fields() -> list[str]:
    """Check coverage_map.json doesn't have V2G-only fields for sc_fm archetype."""
    errors: list[str] = []
    cmap = load_json(PROJECT_ROOT / "projects" / "p05_sc_multiomics_ai" / "output" / "coverage_map.json")
    if not cmap:
        return ["Cannot load p05 coverage_map.json (may not exist yet)"]

    v2g_fields = {"has_fine_mapping", "has_colocalization", "has_replication"}
    if not isinstance(cmap, list) or not cmap:
        return []

    first_cell = cmap[0]
    found_v2g = v2g_fields & set(first_cell.keys())
    if found_v2g:
        errors.append(f"coverage_map.json has V2G-specific fields: {sorted(found_v2g)}")

    if not errors:
        axes = [k for k in first_cell if k not in ('card_count',)]
        print(f"  OK coverage_map: {len(cmap)} cells, axes: {axes}")
    return errors


def check_js_dimensions() -> list[str]:
    """Check p05.js DIM_KEYS match harness config rubric dimensions."""
    errors: list[str] = []
    config = load_yaml(PROJECT_ROOT / "scripts" / "p05_harness" / "config.yaml")
    if not config:
        return ["Cannot load harness config.yaml"]

    expected_dims = set(config.get("rubric", {}).keys())

    js_path = PROJECT_ROOT / "dashboard" / "js" / "tabs" / "p05.js"
    if not js_path.exists():
        return ["p05.js not found"]

    js_text = js_path.read_text(encoding="utf-8")
    import re
    match = re.search(
        r"DIM_KEYS\s*[:=]\s*\[([^\]]+)\]",
        js_text.replace("'", "").replace('"', ''),
    )
    if not match:
        # Try normalized init fallback
        match = re.search(
            r"This\.DIM_KEYS\s*=\s*\[([^\]]+)\]",
            js_text.replace("'", "").replace('"', '').replace("this.", "this."),
        )
    if match:
        js_keys_raw = match.group(1)
        js_keys = {k.strip() for k in js_keys_raw.split(",") if k.strip()}
        missing = expected_dims - js_keys
        extra = js_keys - expected_dims
        if missing:
            errors.append(f"p05.js MISSING dimensions: {sorted(missing)}")
        if extra:
            errors.append(f"p05.js has EXTRA dimensions: {sorted(extra)}")
    else:
        errors.append("Cannot extract DIM_KEYS from p05.js")

    if not errors:
        print(f"  OK JS dimensions: {sorted(expected_dims)}")
    return errors


def check_report_dimensions() -> list[str]:
    """Check final_report.json gap/hypothesis quality."""
    errors: list[str] = []
    report = load_json(PROJECT_ROOT / "projects" / "p05_sc_multiomics_ai" / "output" / "final_report.json")
    if not report:
        return ["Cannot load p05 final_report.json (may not exist yet)"]

    gaps = report.get("gaps", [])
    if gaps:
        unique_supporting = set()
        for g in gaps:
            sc = g.get("supporting_cards", [])
            for cid in sc:
                unique_supporting.add(cid)
        if len(unique_supporting) < len(gaps) * 2:
            errors.append(
                f"final_report.json: only {len(unique_supporting)} unique supporting_cards "
                f"across {len(gaps)} gaps (may indicate identical lists)"
            )

    if not errors:
        conv = report.get("convergence", {})
        print(f"  OK report: converged={conv.get('converged')}, gaps={len(gaps)}")
    return errors


def main():
    print("P05 Consistency Validation")
    print("=" * 40)

    all_errors: list[str] = []
    checks = [
        ("Harness dimension completeness", check_harness_dimensions),
        ("Coverage map archetype fields", check_coverage_fields),
        ("Final report gap quality", check_report_dimensions),
    ]

    if "--all" in sys.argv:
        checks.append(("JS dimension alignment", check_js_dimensions))

    for label, check_fn in checks:
        print(f"\n[{label}]")
        errors = check_fn()
        for e in errors:
            print(f"  FAIL: {e}")
        all_errors.extend(errors)

    print(f"\n{'=' * 40}")
    if all_errors:
        print(f"FAILED: {len(all_errors)} issues found")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
