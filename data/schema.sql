-- ============================================================
-- AIscience 文献/知识管理数据库
-- Engine: SQLite 3.40+ (JSON1 + FTS5)
-- Design: 全局知识层 + 项目研究层 双层架构
-- ============================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ============================================================
-- 1. 全局知识层 (Global Knowledge Layer)
--    跨项目永久存储: 来源、深读笔记、证据卡
-- ============================================================

-- 统一来源表 (论文/数据集/代码库)
CREATE TABLE IF NOT EXISTS sources (
    paper_id       TEXT PRIMARY KEY,           -- 来源唯一标识 (DOI或生成ID)
    source_type    TEXT NOT NULL DEFAULT 'paper',  -- paper/dataset/code_repo/benchmark
    title          TEXT NOT NULL,
    title_norm     TEXT NOT NULL,              -- 标准化标题 (小写+去标点, 用于去重)
    doi            TEXT UNIQUE,
    pmid           TEXT,
    authors        TEXT DEFAULT '[]',          -- JSON: [{"name":"...", "affiliation":"..."}]
    year           INTEGER,
    venue          TEXT,                       -- 期刊/会议名
    abstract       TEXT,
    paper_url      TEXT,
    code_url       TEXT,
    data_url       TEXT,
    source_quality TEXT DEFAULT 'unknown',     -- high/medium/low/unknown
    extracted_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sources_doi ON sources(doi);
CREATE INDEX IF NOT EXISTS idx_sources_title_year ON sources(title_norm, year);
CREATE INDEX IF NOT EXISTS idx_sources_type ON sources(source_type);

-- 全文搜索 (title + abstract)
CREATE VIRTUAL TABLE IF NOT EXISTS sources_fts USING fts5(
    title, abstract, content='sources', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS sources_ai AFTER INSERT ON sources BEGIN
    INSERT INTO sources_fts(rowid, title, abstract)
    VALUES (new.rowid, new.title, new.abstract);
END;

CREATE TRIGGER IF NOT EXISTS sources_ad AFTER DELETE ON sources BEGIN
    INSERT INTO sources_fts(sources_fts, rowid, title, abstract)
    VALUES ('delete', old.rowid, old.title, old.abstract);
END;

CREATE TRIGGER IF NOT EXISTS sources_au AFTER UPDATE ON sources BEGIN
    INSERT INTO sources_fts(sources_fts, rowid, title, abstract)
    VALUES ('delete', old.rowid, old.title, old.abstract);
    INSERT INTO sources_fts(rowid, title, abstract)
    VALUES (new.rowid, new.title, new.abstract);
END;

-- S6C 深读笔记
CREATE TABLE IF NOT EXISTS deep_read_notes (
    note_id            TEXT PRIMARY KEY,       -- {paper_id}_{run_id}
    paper_id           TEXT NOT NULL REFERENCES sources(paper_id) ON DELETE CASCADE,
    run_id             TEXT NOT NULL,
    reading_depth      TEXT NOT NULL DEFAULT 'tier1',  -- tier1/tier2
    facts              TEXT DEFAULT '[]',      -- JSON: [ExtractedFact]
    claims             TEXT DEFAULT '[]',      -- JSON: [AuthorClaim]
    judgments          TEXT DEFAULT '[]',      -- JSON: [ClaimJudgment]
    formulas           TEXT DEFAULT '[]',      -- JSON: [FormulaAnalysis]
    experiments        TEXT DEFAULT '[]',      -- JSON: [ExperimentAnalysis]
    critical_assessment TEXT DEFAULT '{}',     -- JSON: CriticalAssessment
    quality_gate       TEXT DEFAULT '{}',      -- JSON: quality gate result
    extracted_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notes_paper ON deep_read_notes(paper_id);
CREATE INDEX IF NOT EXISTS idx_notes_run ON deep_read_notes(run_id);

-- S7 证据卡 (核心表, 原型特定字段放入 payload JSON)
CREATE TABLE IF NOT EXISTS evidence_cards (
    card_id            TEXT PRIMARY KEY,       -- 全局唯一 card ID
    archetype          TEXT NOT NULL,          -- sc_fm/v2g/sc_spatial/...
    schema_version     TEXT NOT NULL DEFAULT '1.0',

    -- 共有元数据 (来源于 BaseEvidenceCard)
    source_type        TEXT,                   -- literature_search/citation_snowball/deep_read/...
    source_paper       TEXT DEFAULT '{}',      -- JSON: {doi,pmid,title,authors,year,venue,url}
    source_location    TEXT DEFAULT '{}',      -- JSON: {section,excerpt,page,table_or_figure}
    extracted_at       TEXT NOT NULL DEFAULT (datetime('now')),
    reliability_flag   TEXT DEFAULT 'unverified',  -- verified/partial/unverified/warning
    key_finding        TEXT,
    method_brief       TEXT,
    limitation_explicit TEXT,
    limitation_implicit TEXT,
    tags               TEXT DEFAULT '[]',      -- JSON: [str]

    -- 深读富集字段
    evidence_status    TEXT,                   -- directly_stated/inferred/author_claim/unresolved
    evidence_strength  TEXT,                   -- fully_supported/partially_supported/insufficient/conflicting
    deep_read_source   TEXT,                   -- 来源 note_id

    -- 原型特定字段 (所有扩展字段)
    -- archetype=sc_fm: task,task_category,modality_omics,modalities_integrated,
    --   tissue,cell_type,model_architecture,model_family,pretext_task,
    --   pretext_objective,downstream_task,n_cells_pretrain,n_cells_finetune,
    --   n_features_input,n_parameters,embedding_dim,eval_metric_name,
    --   eval_metric_value,baseline_method,baseline_metric_value,
    --   improvement_over_baseline,raw_data_accession,model_hub,
    --   gwas_trait,gwas_locus,coloc_method,coloc_score,gwas_dataset, ...
    -- archetype=v2g: has_fine_mapping,has_colocalization,has_replication, ...
    payload            TEXT DEFAULT '{}'       -- JSON: 原型特定字段全集
);
CREATE INDEX IF NOT EXISTS idx_cards_archetype ON evidence_cards(archetype);
CREATE INDEX IF NOT EXISTS idx_cards_extracted ON evidence_cards(extracted_at);

-- EvidenceState 拆行表 (SQL-native gap 检测)
-- 每个 card 的 state 字段拆为独立行, 可直接用 WHERE state_value = 'confirmed' 统计
CREATE TABLE IF NOT EXISTS card_evidence_states (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id      TEXT NOT NULL REFERENCES evidence_cards(card_id) ON DELETE CASCADE,
    state_field  TEXT NOT NULL,              -- held_out_cell_types/batch_correction_evaluated/transfer_evaluated/...
    state_value  TEXT NOT NULL,              -- confirmed/reported_not_done/not_reported/conflicting/not_applicable
    evidence_status   TEXT,
    evidence_strength TEXT,
    UNIQUE(card_id, state_field)
);
CREATE INDEX IF NOT EXISTS idx_states_field_value ON card_evidence_states(state_field, state_value);

-- ============================================================
-- 2. 项目研究层 (Project Research Layer)
--    每个项目的研究进程, 按 run 版本化
-- ============================================================

CREATE TABLE IF NOT EXISTS projects (
    project_id     TEXT PRIMARY KEY,         -- p01_gwas_perturb_seq / p05_sc_multiomics_ai / ...
    archetype      TEXT NOT NULL,            -- archetype_c_sc_ai / archetype_b_gwas_spatial / ...
    name           TEXT NOT NULL,
    name_en        TEXT
);

-- 研究方向候选 (S1 分解输出)
CREATE TABLE IF NOT EXISTS candidates (
    candidate_id      TEXT PRIMARY KEY,      -- p05_sc_multiomics_ai_T023
    project_id        TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    research_question TEXT NOT NULL,
    dimensions        TEXT DEFAULT '{}',     -- JSON: {architecture_family, modality_combination, ...}
    scores            TEXT DEFAULT '{}',     -- JSON: {combined, density, novelty, feasibility, competitiveness}
    literature_count  INTEGER DEFAULT 0,
    search_query      TEXT,
    rationale         TEXT,                  -- "Custom decomposition: scfm_depth" / "agent_line"
    research_line     TEXT,                  -- scfm_depth / agent_line
    extracted_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_candidates_project ON candidates(project_id);

-- 卡片-候选关联 (替代 tag 中的 candidate:{id} 字符串匹配)
CREATE TABLE IF NOT EXISTS card_candidate_links (
    card_id        TEXT NOT NULL REFERENCES evidence_cards(card_id) ON DELETE CASCADE,
    candidate_id   TEXT NOT NULL REFERENCES candidates(candidate_id) ON DELETE CASCADE,
    relevance_score REAL DEFAULT 0.5,
    matched_criterion TEXT,                  -- "inner_loop_search" / "citation_snowball" / "deep_read"
    PRIMARY KEY (card_id, candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_links_candidate ON card_candidate_links(candidate_id);

-- 管道运行记录
CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,      -- 时间戳或命名 run
    project_id        TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    converged         INTEGER DEFAULT 0,     -- 0/1
    total_cards       INTEGER DEFAULT 0,
    total_rounds      INTEGER DEFAULT 0,
    total_candidates  INTEGER DEFAULT 0,
    duration_s        REAL DEFAULT 0,
    budget_used       TEXT,                  -- LLM budget info
    started_at        TEXT,
    finished_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);

-- S11 缺口分析
CREATE TABLE IF NOT EXISTS gaps (
    gap_id               TEXT PRIMARY KEY,   -- {project}_{pattern_id} 或 全局唯一
    run_id               TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    pattern_id           TEXT NOT NULL,      -- C1/C2/.../P3/P9/P10
    pattern_name         TEXT,
    pattern_description  TEXT,
    axis                 TEXT,               -- 缺口所属维度
    description          TEXT NOT NULL,      -- 具体检测结果描述
    score                REAL DEFAULT 0,
    feasibility          REAL DEFAULT 0.5,
    competition          REAL DEFAULT 0.5,
    cross_archetype      REAL DEFAULT 0,
    gap_confidence       REAL DEFAULT 0.5,
    coverage_denominator INTEGER DEFAULT 0,
    coverage_numerator   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_gaps_run ON gaps(run_id);
CREATE INDEX IF NOT EXISTS idx_gaps_pattern ON gaps(pattern_id);

-- 缺口-卡片关联 (保留 matched_field/matched_rule/weight/rationale)
CREATE TABLE IF NOT EXISTS gap_evidence_links (
    gap_id         TEXT NOT NULL REFERENCES gaps(gap_id) ON DELETE CASCADE,
    card_id        TEXT NOT NULL REFERENCES evidence_cards(card_id) ON DELETE CASCADE,
    link_type      TEXT NOT NULL DEFAULT 'supporting',  -- supporting/contradicting/uncertain
    matched_field  TEXT,                   -- 匹配的卡片字段名
    matched_rule   TEXT,                   -- 匹配规则/条件
    weight         REAL DEFAULT 1.0,
    rationale      TEXT,                   -- 匹配理由
    PRIMARY KEY (gap_id, card_id, link_type)
);
CREATE INDEX IF NOT EXISTS idx_gel_card ON gap_evidence_links(card_id);

-- S12 假设
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id      TEXT PRIMARY KEY,    -- H1/H2/... 或全局唯一
    run_id             TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    statement          TEXT NOT NULL,
    addresses_gap      TEXT NOT NULL REFERENCES gaps(gap_id) ON DELETE CASCADE,
    rationale          TEXT,
    required_methods   TEXT DEFAULT '[]',   -- JSON: [str]
    required_datasets  TEXT DEFAULT '[]',   -- JSON: [str]
    novelty_score      REAL DEFAULT 0.5,
    feasibility_score  REAL DEFAULT 0.5,
    expected_impact    TEXT DEFAULT 'Medium' -- Low/Medium/High
);
CREATE INDEX IF NOT EXISTS idx_hyp_run ON hypotheses(run_id);
CREATE INDEX IF NOT EXISTS idx_hyp_gap ON hypotheses(addresses_gap);

-- ============================================================
-- 3. 视图: 常用查询
-- ============================================================

-- 已确认 EvidenceState 的卡片概览
CREATE VIEW IF NOT EXISTS v_confirmed_states AS
SELECT ces.state_field, ces.state_value, COUNT(*) AS cnt
FROM card_evidence_states ces
WHERE ces.state_value = 'confirmed'
GROUP BY ces.state_field, ces.state_value
ORDER BY cnt DESC;

-- 每次运行的缺口汇总
CREATE VIEW IF NOT EXISTS v_gap_summary AS
SELECT r.run_id, r.project_id, g.pattern_id, g.pattern_name,
       COUNT(*) OVER (PARTITION BY r.run_id) AS gaps_total,
       g.score, g.gap_confidence
FROM gaps g
JOIN runs r ON g.run_id = r.run_id
ORDER BY r.run_id, g.score DESC;

-- 每次运行的假设列表
CREATE VIEW IF NOT EXISTS v_hypothesis_list AS
SELECT r.run_id, r.project_id, h.hypothesis_id, h.statement,
       h.novelty_score, h.feasibility_score, g.pattern_id AS addresses_gap_pattern
FROM hypotheses h
JOIN runs r ON h.run_id = r.run_id
JOIN gaps g ON h.addresses_gap = g.gap_id
ORDER BY r.run_id, (h.novelty_score + h.feasibility_score) DESC;
