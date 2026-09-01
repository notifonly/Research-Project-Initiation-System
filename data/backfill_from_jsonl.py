#!/usr/bin/env python
"""
backfill_from_jsonl.py — 从项目输出文件回填 knowledge.db

读取:
  - data/decompose_pilot_results.json → projects, candidates
  - projects/{p}/output/summary.json   → runs (主管道运行)
  - projects/{p}/output/final_report.json → gaps, gap_evidence_links, hypotheses
  - projects/{p}/output/evidence_cards.jsonl → evidence_cards, sources, card_evidence_states, card_candidate_links
  - data/p05_harness_output/runs/     → harness 运行记录 (额外 runs)
  - data/p05_harness_output/harness_result.json → 聚合 harness 数据

用法:
  python data/backfill_from_jsonl.py                    # 所有项目
  python data/backfill_from_jsonl.py --project p05      # 仅 p05
  python data/backfill_from_jsonl.py --fresh             # 删除旧 DB 重建
"""

import json
import os
import re
import sqlite3
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "knowledge.db"
PROJECTS_DIR = ROOT / "projects"

PROJECT_MAP = {
    "p01_gwas_perturb_seq":     "archetype_c_sc_ai",
    "p02_gwas_spatial":         "archetype_b_gwas_spatial",
    "p03_gwas_scatac":          "archetype_b_gwas_spatial",
    "p04_prs":                  "archetype_d_prs",
    "p05_sc_multiomics_ai":     "archetype_c_sc_ai",
    "p06_gwas_digital_twin":    "archetype_d_prs",
    "p07_aging_clock":          "archetype_d_prs",
}

ARCHETYPE_TO_CARD_ARCHETYPE = {
    "archetype_c_sc_ai":        "sc_fm",
    "archetype_b_gwas_spatial": "v2g",
    "archetype_d_prs":          "v2g",
}

# EvidenceState fields per archetype
EVIDENCE_STATE_FIELDS = {
    "sc_fm": [
        "held_out_cell_types", "held_out_tissues", "batch_correction_evaluated",
        "transfer_evaluated", "interpretability_assessed", "code_available",
        "weights_available", "dataset_available",
    ],
    "v2g": [
        "has_fine_mapping", "has_colocalization", "has_replication",
        "has_functional_validation", "has_population_stratification",
        "code_available", "dataset_available",
    ],
}

# Core card fields (non-payload)
CORE_FIELDS = {
    "card_id", "source_type", "extracted_at", "reliability_flag", "key_finding",
    "method_brief", "limitation_explicit", "limitation_implicit", "archetype",
    "tags", "evidence_status", "evidence_strength", "deep_read_source",
    "paper_doi", "paper_pmid", "paper_title", "paper_authors", "paper_year",
    "paper_venue", "paper_url", "loc_section", "loc_excerpt",
    "source_database", "source_location",
}


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]", " ", text.lower()).strip()


def make_source_paper(card: dict) -> dict:
    return {
        "doi": card.get("paper_doi"),
        "pmid": card.get("paper_pmid"),
        "title": card.get("paper_title", ""),
        "authors": card.get("paper_authors", []),
        "year": card.get("paper_year"),
        "venue": card.get("paper_venue", ""),
        "url": card.get("paper_url", ""),
    }


def make_source_location(card: dict) -> dict:
    return {
        "section": card.get("loc_section", ""),
        "excerpt": (card.get("loc_excerpt", "") or "")[:2000],
        "page": "",
        "table_or_figure": "",
    }


def ensure_source(conn: sqlite3.Connection, paper: dict) -> str:
    doi = paper.get("doi") or ""
    pmid = paper.get("pmid") or ""
    title = paper.get("title") or ""
    title_norm = slugify(title)[:500]

    if doi:
        cur = conn.execute("SELECT paper_id FROM sources WHERE doi = ?", (doi,))
        row = cur.fetchone()
        if row:
            return row[0]

    if title_norm:
        cur = conn.execute(
            "SELECT paper_id FROM sources WHERE title_norm = ? AND year = ?",
            (title_norm, paper.get("year")),
        )
        row = cur.fetchone()
        if row:
            if doi and not cur.fetchone():
                conn.execute("UPDATE sources SET doi = ? WHERE paper_id = ?", (doi, row[0]))
            return row[0]

    paper_id = "src_" + re.sub(r"[^a-z0-9]", "", title_norm)[:20]
    if not paper_id:
        paper_id = "src_" + (doi or pmid or "").replace("/", "_")[-24:]
    if not paper_id:
        paper_id = "src_" + os.urandom(8).hex()

    source_type = "paper"
    conn.execute(
        """INSERT OR IGNORE INTO sources (paper_id, source_type, title, title_norm, doi, pmid,
        authors, year, venue, abstract, paper_url, source_quality, extracted_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
        (
            paper_id, source_type, title, title_norm, doi, pmid,
            json.dumps(paper.get("authors", [])), paper.get("year"), paper.get("venue", ""),
            "", paper.get("url", ""), "unknown",
        ),
    )
    return paper_id


def load_candidates(conn: sqlite3.Connection, projects_to_load: set):
    decomp_file = ROOT / "data" / "decompose_pilot_results.json"
    if not decomp_file.exists():
        print("  [skip] decompose_pilot_results.json not found")
        return

    with open(decomp_file, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    proj_count = cand_count = 0
    for entry in all_data:
        pid = entry["project_id"]
        if pid not in projects_to_load:
            continue

        archetype_id = PROJECT_MAP.get(pid, "")
        conn.execute(
            "INSERT OR REPLACE INTO projects (project_id, archetype, name, name_en) VALUES (?,?,?,?)",
            (pid, archetype_id, pid, pid),
        )
        proj_count += 1

        for c in entry.get("candidates", []):
            conn.execute(
                """INSERT OR REPLACE INTO candidates
                (candidate_id, project_id, research_question, dimensions, scores,
                literature_count, search_query, rationale, research_line, extracted_at)
                VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (
                    c.get("topic_id", ""),
                    pid,
                    c.get("research_question", ""),
                    json.dumps(c.get("dimensions", {})),
                    json.dumps(c.get("scores", {})),
                    c.get("literature_count", 0),
                    c.get("search_query", ""),
                    c.get("rationale", ""),
                    c.get("rationale", "").replace("Custom decomposition: ", ""),
                ),
            )
        cand_count += len(entry.get("candidates", []))

    print(f"  Projects: {proj_count}, Candidates: {cand_count}")


def load_pipeline_run(conn: sqlite3.Connection, project_id: str):
    output_dir = PROJECTS_DIR / project_id / "output"
    summary_file = output_dir / "summary.json"
    if not summary_file.exists():
        return None

    with open(summary_file, "r", encoding="utf-8") as f:
        summary = json.load(f)

    run_id = f"{project_id}_main"
    conn.execute(
        """INSERT OR REPLACE INTO runs
        (run_id, project_id, converged, total_cards, total_rounds, total_candidates,
        duration_s, budget_used, started_at, finished_at)
        VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))""",
        (
            run_id, project_id,
            1 if summary.get("converged") else 0,
            summary.get("total_cards", 0),
            0,  # rounds not stored
            summary.get("candidate_count", 0),
            summary.get("duration_s", 0),
            str(summary.get("budget_used", "")),
            "",
        ),
    )
    return run_id


def load_evidence_cards(conn: sqlite3.Connection, project_id: str, run_id: str):
    output_dir = PROJECTS_DIR / project_id / "output"
    cards_file = output_dir / "evidence_cards.jsonl"
    if not cards_file.exists():
        cards_file = ROOT / "data" / "l1_warm" / project_id / "cards.jsonl"
    if not cards_file.exists():
        print(f"    [skip] no cards.jsonl for {project_id}")
        return

    with open(cards_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sources_added = 0
    cards_added = 0
    states_added = 0
    links_added = 0
    archetype = ARCHETYPE_TO_CARD_ARCHETYPE.get(
        PROJECT_MAP.get(project_id, ""), "unknown"
    )

    for line in lines:
        try:
            card = json.loads(line)
        except json.JSONDecodeError:
            continue

        card_id = card.get("card_id", "")
        if not card_id:
            continue

        # source
        paper = make_source_paper(card)
        paper_id = ensure_source(conn, paper)
        if paper_id:
            sources_added += 1

        # build core + payload
        # paper fields map to source_paper JSON
        source_paper_json = make_source_paper(card)
        source_location_json = make_source_location(card)

        # payload: all archetype-specific fields
        payload = {}
        for k, v in card.items():
            if k not in CORE_FIELDS and not k.startswith("paper_") and not k.startswith("loc_"):
                payload[k] = v

        conn.execute(
            """INSERT OR REPLACE INTO evidence_cards
            (card_id, archetype, schema_version, source_type, source_paper, source_location,
            extracted_at, reliability_flag, key_finding, method_brief,
            limitation_explicit, limitation_implicit, tags,
            evidence_status, evidence_strength, deep_read_source, payload)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                card_id,
                card.get("archetype", archetype),
                "1.0",
                card.get("source_type", "paper"),
                json.dumps(source_paper_json, ensure_ascii=False),
                json.dumps(source_location_json, ensure_ascii=False),
                card.get("extracted_at", ""),
                card.get("reliability_flag", "unverified"),
                card.get("key_finding", ""),
                card.get("method_brief", ""),
                card.get("limitation_explicit", ""),
                card.get("limitation_implicit", ""),
                json.dumps(card.get("tags", []), ensure_ascii=False),
                card.get("evidence_status"),
                card.get("evidence_strength"),
                card.get("deep_read_source"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        cards_added += 1

        # evidence states
        state_fields = EVIDENCE_STATE_FIELDS.get(card.get("archetype", archetype), [])
        for sf in state_fields:
            val = card.get(sf)
            if val is not None:
                conn.execute(
                    """INSERT OR REPLACE INTO card_evidence_states
                    (card_id, state_field, state_value) VALUES (?,?,?)""",
                    (card_id, sf, str(val)),
                )
                states_added += 1

        # card-candidate links (from tags)
        for tag in card.get("tags", []):
            if tag.startswith("candidate:"):
                candidate_id = tag.replace("candidate:", "")
                conn.execute(
                    """INSERT OR IGNORE INTO card_candidate_links
                    (card_id, candidate_id, relevance_score, matched_criterion)
                    VALUES (?,?,0.5,'tag_inference')""",
                    (card_id, candidate_id),
                )
                links_added += 1

    print(f"    Cards: {cards_added}, Sources from cards: {sources_added}, States: {states_added}, Links: {links_added}")


def load_gaps_and_hypotheses(conn: sqlite3.Connection, project_id: str, run_id: str):
    output_dir = PROJECTS_DIR / project_id / "output"
    report_file = output_dir / "final_report.json"
    if not report_file.exists():
        print(f"    [skip] no final_report.json for {project_id}")
        return

    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    # update run with rounds
    conn.execute(
        "UPDATE runs SET total_rounds = ?, total_candidates = ? WHERE run_id = ?",
        (
            report.get("rounds_completed", 0),
            len(report.get("candidates", [])),
            run_id,
        ),
    )

    gaps_added = 0
    for g in report.get("gaps", []):
        gap_id = g.get("gap_id", "")

        # get pattern info from gap_patterns if available
        pattern_id = g.get("pattern_id", "")

        conn.execute(
            """INSERT OR REPLACE INTO gaps
            (gap_id, run_id, pattern_id, pattern_name, pattern_description,
            axis, description, score, feasibility, competition, cross_archetype,
            gap_confidence, coverage_denominator, coverage_numerator)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                gap_id, run_id, pattern_id,
                g.get("pattern_name", ""),
                g.get("pattern_description", ""),
                g.get("axis", ""),
                g.get("description", ""),
                g.get("score", 0),
                g.get("feasibility", 0.5),
                g.get("competition", 0.5),
                g.get("cross_archetype", 0),
                g.get("gap_confidence", 0),
                g.get("coverage_denominator", 0),
                g.get("coverage_numerator", 0),
            ),
        )
        gaps_added += 1

        # gap evidence links
        for card_id in g.get("supporting_cards", []):
            conn.execute(
                """INSERT OR REPLACE INTO gap_evidence_links
                (gap_id, card_id, link_type, matched_field, matched_rule, weight, rationale)
                VALUES (?,?,'supporting','','',1.0,'')""",
                (gap_id, card_id),
            )
        for card_id in g.get("contradicting_card_ids", []):
            conn.execute(
                """INSERT OR REPLACE INTO gap_evidence_links
                (gap_id, card_id, link_type, matched_field, matched_rule, weight, rationale)
                VALUES (?,?,'contradicting','','',1.0,'')""",
                (gap_id, card_id),
            )
        for card_id in g.get("uncertain_card_ids", []):
            conn.execute(
                """INSERT OR REPLACE INTO gap_evidence_links
                (gap_id, card_id, link_type, matched_field, matched_rule, weight, rationale)
                VALUES (?,?,'uncertain','','',1.0,'')""",
                (gap_id, card_id),
            )

        # detailed evidence links
        for el in g.get("evidence_links", []):
            if isinstance(el, dict):
                conn.execute(
                    """INSERT OR REPLACE INTO gap_evidence_links
                    (gap_id, card_id, link_type, matched_field, matched_rule, weight, rationale)
                    VALUES (?,?,?,?,?,?,?)""",
                    (
                        gap_id,
                        el.get("card_id", ""),
                        el.get("link_type", "supporting"),
                        el.get("matched_field", ""),
                        el.get("matched_rule", ""),
                        el.get("weight", 1.0),
                        el.get("rationale", ""),
                    ),
                )

    hyps_added = 0
    for h in report.get("hypotheses", []):
        conn.execute(
            """INSERT OR REPLACE INTO hypotheses
            (hypothesis_id, run_id, statement, addresses_gap, rationale,
            required_methods, required_datasets, novelty_score, feasibility_score, expected_impact)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                h.get("hypothesis_id", ""),
                run_id,
                h.get("statement", ""),
                h.get("addresses_gap", ""),
                h.get("rationale", ""),
                json.dumps(h.get("required_methods", []), ensure_ascii=False),
                json.dumps(h.get("required_datasets", []), ensure_ascii=False),
                h.get("novelty_score", 0.5),
                h.get("feasibility_score", 0.5),
                h.get("expected_impact", "Medium"),
            ),
        )
        hyps_added += 1

    print(f"    Gaps: {gaps_added}, Hypotheses: {hyps_added}")


def load_harness_runs(conn: sqlite3.Connection, project_id: str):
    harness_dir = ROOT / "data" / "p05_harness_output" / "runs"
    if not harness_dir.exists():
        return

    # also allow aggregate harness_result.json
    aggregate_file = ROOT / "data" / "p05_harness_output" / "harness_result.json"
    run_id = f"{project_id}_harness_main"

    if aggregate_file.exists():
        with open(aggregate_file, "r", encoding="utf-8") as f:
            result = json.load(f)

        conn.execute(
            """INSERT OR REPLACE INTO runs
            (run_id, project_id, converged, total_cards, total_rounds, total_candidates,
            duration_s, budget_used, started_at, finished_at)
            VALUES (?,?,0,?,?,?,?,?,?,datetime('now'))""",
            (
                run_id, project_id,
                result.get("total_cards", 0), 0,
                result.get("total_llm_calls", 0) + result.get("total_mcp_calls", 0),
                result.get("total_duration_s", 0), "",
                "",
            ),
        )

    # per-run harness data
    runs_added = 0
    for run_dir in sorted(harness_dir.glob("run_*")):
        hr = run_dir / "harness_result.json"
        if not hr.exists():
            hr = run_dir / "checkpoint.json"
        if not hr.exists():
            continue

        try:
            with open(hr, "r", encoding="utf-8") as f:
                result = json.load(f)
        except Exception:
            continue

        if isinstance(result, dict) and "passed_count" in result:
            sub_run_id = run_dir.name
            conn.execute(
                """INSERT OR REPLACE INTO runs
                (run_id, project_id, converged, total_cards, total_rounds,
                total_candidates, duration_s, budget_used, started_at, finished_at)
                VALUES (?,?,0,?,?,?,?,?,?,datetime('now'))""",
                (
                    sub_run_id, project_id,
                    0, 0,
                    result.get("total_llm_calls", 0) + result.get("total_mcp_calls", 0),
                    result.get("total_duration_s", 0), "",
                    "",
                ),
            )
            runs_added += 1

    print(f"    Harness runs: {runs_added + (1 if aggregate_file.exists() else 0)}")


def main():
    parser = argparse.ArgumentParser(description="Backfill knowledge.db from project outputs")
    parser.add_argument("--project", "-p", help="Only process specific project (e.g. p05)")
    parser.add_argument("--fresh", action="store_true", help="Delete existing DB and rebuild")
    args = parser.parse_args()

    if args.fresh and DB_PATH.exists():
        DB_PATH.unlink()
        print("Deleted existing knowledge.db")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # ensure schema
    schema_file = ROOT / "data" / "schema.sql"
    with open(schema_file, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()

    # determine projects
    if args.project:
        pid = args.project
        if not pid.startswith("p"):
            pid = f"p{int(pid):02d}"
        # try to find exact match in PROJECT_MAP
        matched = [k for k in PROJECT_MAP if k.startswith(pid)]
        projects_to_load = set(matched or [pid])
    else:
        projects_to_load = set(PROJECT_MAP.keys())

    print(f"\nBackfilling {len(projects_to_load)} projects into {DB_PATH}")
    print("=" * 60)

    # Step 1: candidates + projects
    print("\n[1] Loading candidates...")
    load_candidates(conn, projects_to_load)

    for pid in sorted(projects_to_load):
        print(f"\n--- {pid} ---")

        # Step 2: pipeline run
        run_id = load_pipeline_run(conn, pid)
        if run_id:
            print(f"  Run: {run_id}")

            # Step 3: evidence cards
            print("  Loading evidence cards...")
            load_evidence_cards(conn, pid, run_id)

            # Step 4: gaps + hypotheses
            print("  Loading gaps & hypotheses...")
            load_gaps_and_hypotheses(conn, pid, run_id)

        # Step 5: harness runs (p05 only)
        if pid == "p05_sc_multiomics_ai":
            print("  Loading harness runs...")
            load_harness_runs(conn, pid)

    conn.commit()

    # print summary
    print("\n" + "=" * 60)
    print(" DB Summary")
    print("=" * 60)
    tables = [
        "projects", "candidates", "sources", "evidence_cards",
        "card_evidence_states", "card_candidate_links",
        "runs", "gaps", "gap_evidence_links", "hypotheses",
    ]
    for t in tables:
        cnt = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
        print(f"  {t:30s} {cnt:6d}")

    conn.close()
    print(f"\nDone. DB: {DB_PATH} ({DB_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
