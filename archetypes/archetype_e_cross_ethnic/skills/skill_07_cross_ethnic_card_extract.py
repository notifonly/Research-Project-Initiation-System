"""S7 CrossEthnicCardExtract (Archetype E-specific) - extract structured
cross-ethnic multi-omics evidence cards from screened papers with
domain-specific prompts.

Mirrors the archetype C SCFMCardExtract design: a domain prompt tuned for
cross-population multi-omics research (biomarker portability, PRS
transportability, causal inference) plus heuristic enum extraction for the
five coverage axes (ancestry_comparison x omics_layers x trait x method x
portability)."""

from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from shared.core.logging_setup import get_logger
from shared.core.token_budget import BudgetPhase
from shared.evidence.base_card import BaseEvidenceCard, SourceLocation, SourcePaper
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput

logger = get_logger("skill.s7_cross_ethnic_extract")

# 明显与跨种族多组学无关的论文关键词(如护理量表信效度研究)
CROSS_ETHNIC_IRRELEVANT_KEYWORDS = [
    "content validity", "face validity", "CVI", "nursing",
    "psychometric", "questionnaire", "scale validation",
    "Delphi", "focus group", "qualitative interview",
]

CROSS_ETHNIC_DOMAIN_PROMPT = """You are a bioinformatics evidence extractor specializing in cross-ethnic
(cross-ancestry) multi-omics research. Extract up to {max_findings} distinct findings from this paper.

For each finding, identify how the study compares populations/ancestries and which omics layers,
traits, and methods are involved.

=== FIELD DESCRIPTIONS ===

ancestry_comparison: The pair/group of ancestries compared, formatted as "A_vs_B" using codes:
  EUR (European), EAS (East Asian, incl. Chinese/Japanese/Korean), AFR (African),
  SAS (South Asian), AMR (Admixed American/Hispanic). e.g. "EUR_vs_EAS", "EUR_vs_AFR".
  If only one ancestry is studied, return that code (e.g. "EAS").

population_cohorts: List of named cohorts/biobanks used
  (e.g. ["UK Biobank", "China Kadoorie Biobank", "FinnGen", "Biobank Japan"]).

omics_layers: List of omics modalities analyzed. Choose from:
  genomics, transcriptomics, proteomics, metabolomics, epigenomics, lipidomics, glycomics.

primary_omics_layer: The single most central omics layer of the finding.

trait: The phenotype/disease studied (e.g. "type 2 diabetes", "coronary artery disease", "LDL cholesterol").
trait_efo: EFO/MONDO ontology id if mentioned.

method: The core analytic method. Choose from:
  PRS-CSx, LDpred2, PRS-CS, mendelian_randomization, colocalization, PWAS, TWAS,
  fine_mapping, meta_analysis, pQTL_mapping, GWAS, admixture_mapping.
method_family: Broader family (e.g. polygenic_score, causal_inference, association, integration).

cross_ethnic_replication (bool): true if a signal/biomarker/score was explicitly replicated or
  validated in a second ancestry; false if the paper says it was NOT replicated / not transferable;
  omit if not addressed.
portability_score: Numeric portability/transferability metric if reported (e.g. R2 ratio, correlation).

sample_size_pop1 / sample_size_pop2: Integer sample sizes of the two populations if stated.
effect_size_pop1 / effect_size_pop2: Effect sizes (beta/OR) per population if stated.
eval_metric_name / eval_metric_value: Evaluation metric name and numeric value.

harmonization_method: Cross-cohort harmonization approach if described.
biobank_source: Primary biobank/data source.
code_available (bool): true if code repository is provided.
data_available (bool): true if data/summary stats are publicly available.
raw_data_accession: GWAS Catalog / dbGaP / EGA / GEO accession if mentioned.

=== IMPORTANT ===
- Every finding MUST have an ancestry_comparison OR at least one omics_layer.
- For numeric fields extract exact numbers when stated; leave null when not reported.
- For boolean fields, return true/false strictly based on explicit paper statements; omit if unstated.
- If a field is not mentioned, leave it null/empty — do NOT guess.
- If the paper does NOT concern cross-ethnic / cross-ancestry multi-omics research, return an empty list []."""


def _try_parse_float(raw: str) -> Optional[float]:
    if not raw:
        return None
    match = re.search(r'-?[\d]+\.?[\d]*(?:[eE][+-]?\d+)?', str(raw).replace(",", ""))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _try_parse_int(raw: str) -> Optional[int]:
    if not raw:
        return None
    match = re.search(r'-?[\d]+', str(raw).replace(",", ""))
    if match:
        try:
            return int(match.group())
        except ValueError:
            return None
    return None


class ExtractTarget(BaseModel):
    paper_id: str = ""
    title: str = ""
    doi: Optional[str] = None
    pmid: Optional[str] = None
    abstract: str = ""
    year: Optional[int] = None
    authors: list[str] = Field(default_factory=list)
    venue: str = ""
    url: str = ""
    full_text: Optional[str] = None


class CrossEthnicExtractInput(SkillInput):
    targets: list[ExtractTarget] = Field(default_factory=list)
    archetype: str = ""
    max_findings_per_paper: int = 5
    max_targets: int = 20
    extraction_text_truncate: int = 8000
    normalized_traits: list[dict[str, str]] = Field(default_factory=list)
    normalized_genes: list[dict[str, Any]] = Field(default_factory=list)
    deep_read_notes: list[dict[str, Any]] = Field(default_factory=list)


class CrossEthnicExtractOutput(SkillOutput):
    cards: list[BaseEvidenceCard] = Field(default_factory=list)
    paper_count: int = 0
    findings_count: int = 0
    irrelevant_count: int = 0


class CrossEthnicCardExtract(BaseSkill):
    """S7 (Archetype E): Extract structured cross-ethnic multi-omics evidence cards.

    Overrides the shared EvidenceCardExtract with a domain-specific prompt tuned for
    cross-population multi-omics papers, and heuristic enum extraction for the five
    coverage axes so the coverage matrix no longer collapses to a single "unknown" cell.
    """

    name = "s7_evidence_card_extract"
    description = "Extract per-finding cross-ethnic multi-omics evidence cards with domain-specific prompts"
    uses_llm = True
    budget_phase = BudgetPhase.EXTRACTION
    input_schema = CrossEthnicExtractInput
    output_schema = CrossEthnicExtractOutput

    def _resolve_card_class(self, ctx: SkillContext) -> type[BaseEvidenceCard]:
        arch_cfg = ctx.archetype_config or {}
        if "_evidence_card_class" in arch_cfg:
            return arch_cfg["_evidence_card_class"]
        from shared.evidence.base_card import BaseEvidenceCard
        return BaseEvidenceCard

    @staticmethod
    def _is_irrelevant(title: str, abstract: str) -> bool:
        combined = (title + " " + abstract).lower()
        for kw in CROSS_ETHNIC_IRRELEVANT_KEYWORDS:
            if kw.lower() in combined:
                return True
        return False

    async def execute(self, inp: CrossEthnicExtractInput, ctx: SkillContext) -> CrossEthnicExtractOutput:
        card_class = self._resolve_card_class(ctx)
        cards: list[BaseEvidenceCard] = []
        irrelevant = 0
        topic_id = ctx.scratch.get("_candidate_topic_id", "")

        notes_by_paper = self._index_deep_read_notes(inp.deep_read_notes)

        max_papers = inp.max_targets
        targets = inp.targets[:max_papers]
        if len(inp.targets) > max_papers:
            logger.info(f"Capping targets from {len(inp.targets)} to {max_papers}")

        deep_read_count = 0
        tasks = []
        for t in targets:
            if self._is_irrelevant(t.title, t.abstract):
                logger.info(f"Skipping irrelevant paper: {t.title[:80]}...")
                irrelevant += 1
                continue
            note = notes_by_paper.get(t.paper_id) or notes_by_paper.get(t.pmid or "")
            if note:
                deep_read_count += 1
                tasks.append(self._extract_from_deep_read(t, note, card_class, topic_id))
            else:
                tasks.append(self._extract_from_paper(t, inp, ctx, card_class, topic_id))

        self._metrics["deep_read_enriched"] = deep_read_count
        paper_count = len(tasks)
        logger.info(
            f"S7 routing: {deep_read_count}/{paper_count} papers via deep_read, "
            f"{paper_count - deep_read_count} via paper extraction "
            f"(notes_indexed={len(notes_by_paper)}, irrelevant_skipped={irrelevant})"
        )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for paper_cards in results:
            if isinstance(paper_cards, BaseException):
                logger.warning(f"Extract failed: {paper_cards}")
                continue
            cards.extend(paper_cards)
            for c in paper_cards:
                if ctx.card_store:
                    try:
                        ctx.card_store.add(c)
                    except Exception as e:
                        logger.warning(f"card store add failed: {e}")

        self._metrics.update({
            "papers": len(targets),
            "cards": len(cards),
            "irrelevant_skipped": irrelevant,
            "avg_findings": round(len(cards) / max(1, len(targets) - irrelevant), 2),
        })
        return CrossEthnicExtractOutput(
            skill_name=self.name,
            cards=cards,
            paper_count=len(targets),
            findings_count=len(cards),
            irrelevant_count=irrelevant,
        )

    @staticmethod
    def _index_deep_read_notes(notes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for note in notes:
            if isinstance(note, dict):
                pid = note.get("paper_id", "")
                if pid:
                    index[pid] = note
        return index

    # ── 跨种族领域枚举值集合 (启发式抽取) ──────────────────────────────
    _ANCESTRY_VALUES = {"EUR", "EAS", "AFR", "SAS", "AMR"}
    _ANCESTRY_SYNONYMS = {
        "EUR": ["european", "eur ", "caucasian", "white british", "uk biobank",
                "finngen", "estonian", "ukb"],
        "EAS": ["east asian", "east-asian", "chinese", "han chinese", "kadoorie",
                "biobank japan", "japanese", "korean", "ckb", "bbj"],
        "AFR": ["african", "african american", "african-american", "afr ", "yoruba"],
        "SAS": ["south asian", "south-asian", "indian", "pakistani", "bangladeshi", "sas "],
        "AMR": ["admixed american", "hispanic", "latino", "amerindian", "amr "],
    }
    _OMICS_VALUES = {
        "genomics", "transcriptomics", "proteomics", "metabolomics",
        "epigenomics", "lipidomics", "glycomics",
    }
    _OMICS_SYNONYMS = {
        "genomics": ["genomic", "genotype", "gwas", "snp", "variant", "dna sequence"],
        "transcriptomics": ["transcriptom", "rna-seq", "rna seq", "gene expression",
                             "mrna", "eqtl"],
        "proteomics": ["proteomic", "protein", "olink", "somascan", "pqtl", "plasma protein"],
        "metabolomics": ["metabolom", "metabolite", "mqtl", "nmr metabol"],
        "epigenomics": ["epigenom", "methylation", "dna methylation", "epigenetic",
                        "atac-seq", "chip-seq", "histone"],
        "lipidomics": ["lipidom", "lipid species", "lipid profil"],
        "glycomics": ["glycom", "glycan", "glycosylation"],
    }
    _METHOD_VALUES = {
        "PRS-CSx", "LDpred2", "PRS-CS", "mendelian_randomization", "colocalization",
        "PWAS", "TWAS", "fine_mapping", "meta_analysis", "pQTL_mapping", "GWAS",
        "admixture_mapping",
    }
    _METHOD_SYNONYMS = {
        "PRS-CSx": ["prs-csx", "prscsx", "prs csx"],
        "PRS-CS": ["prs-cs", "prscs"],
        "LDpred2": ["ldpred2", "ldpred-2", "ldpred 2", "ldpred"],
        "mendelian_randomization": ["mendelian randomization", "mendelian randomisation",
                                    "mr analysis", "two-sample mr", "instrumental variable"],
        "colocalization": ["colocalization", "colocalisation", "coloc", "coloc.abf"],
        "PWAS": ["pwas", "proteome-wide association", "proteome wide association"],
        "TWAS": ["twas", "transcriptome-wide association", "transcriptome wide association"],
        "fine_mapping": ["fine-mapping", "fine mapping", "finemapping", "susie", "credible set"],
        "meta_analysis": ["meta-analysis", "meta analysis", "metaanalysis", "fixed-effect meta",
                          "random-effect meta"],
        "pQTL_mapping": ["pqtl", "protein qtl", "protein quantitative trait"],
        "GWAS": ["genome-wide association", "genome wide association", "gwas"],
        "admixture_mapping": ["admixture mapping", "local ancestry", "admixed analysis"],
    }
    _COHORT_VALUES = {
        "UK Biobank", "China Kadoorie Biobank", "FinnGen", "Biobank Japan",
        "All of Us", "Million Veteran Program", "Estonian Biobank",
        "Taiwan Biobank", "Genes & Health",
    }
    _COHORT_SYNONYMS = {
        "UK Biobank": ["uk biobank", "ukbiobank", "ukb"],
        "China Kadoorie Biobank": ["china kadoorie", "kadoorie", "ckb"],
        "FinnGen": ["finngen"],
        "Biobank Japan": ["biobank japan", "bbj"],
        "All of Us": ["all of us"],
        "Million Veteran Program": ["million veteran", "mvp"],
        "Estonian Biobank": ["estonian biobank"],
        "Taiwan Biobank": ["taiwan biobank"],
        "Genes & Health": ["genes & health", "genes and health"],
    }
    _TRAIT_SYNONYMS = {
        "type 2 diabetes": ["type 2 diabetes", "t2d", "type-2 diabetes", "diabetes mellitus type 2"],
        "coronary artery disease": ["coronary artery disease", "cad", "coronary heart disease", "chd"],
        "LDL cholesterol": ["ldl cholesterol", "ldl-c", "low-density lipoprotein"],
        "body mass index": ["body mass index", "bmi", "obesity"],
        "blood pressure": ["blood pressure", "hypertension", "systolic", "diastolic"],
        "stroke": ["stroke", "ischemic stroke", "cerebrovascular"],
        "breast cancer": ["breast cancer"],
        "prostate cancer": ["prostate cancer"],
        "asthma": ["asthma"],
        "Alzheimer disease": ["alzheimer", "alzheimer's disease", "dementia"],
        "rheumatoid arthritis": ["rheumatoid arthritis"],
        "chronic kidney disease": ["chronic kidney disease", "ckd", "egfr", "renal function"],
    }

    @classmethod
    def _match_enum(cls, text_lower: str, enum_set: set[str],
                    synonyms: dict[str, list[str]] | None = None) -> str:
        for val in enum_set:
            key = val.lower().replace("_", " ").replace("-", "")
            if key in text_lower:
                return val
            if val.lower() in text_lower:
                return val
        if synonyms:
            for val, syns in synonyms.items():
                if val not in enum_set:
                    continue
                for s in syns:
                    if s in text_lower:
                        return val
        return ""

    @classmethod
    def _match_all(cls, text_lower: str, enum_set: set[str],
                   synonyms: dict[str, list[str]] | None = None) -> list[str]:
        """Return ALL matching enum values (for list-valued fields)."""
        found: list[str] = []
        for val in enum_set:
            key = val.lower().replace("_", " ").replace("-", "")
            if key in text_lower or val.lower() in text_lower:
                found.append(val)
                continue
            if synonyms and val in synonyms:
                for s in synonyms[val]:
                    if s in text_lower:
                        found.append(val)
                        break
        return found

    @classmethod
    def _extract_ancestry_comparison(cls, text_lower: str) -> str:
        found = cls._match_all(text_lower, cls._ANCESTRY_VALUES, cls._ANCESTRY_SYNONYMS)
        if not found:
            return ""
        # 去重并按固定顺序排列,形成 "A_vs_B" 形式
        order = ["EUR", "EAS", "AFR", "SAS", "AMR"]
        uniq = [a for a in order if a in found]
        if len(uniq) >= 2:
            return "_vs_".join(uniq[:2])
        return uniq[0]

    @classmethod
    def _extract_trait(cls, text_lower: str) -> str:
        for canonical, syns in cls._TRAIT_SYNONYMS.items():
            for s in syns:
                if s in text_lower:
                    return canonical
        return ""

    @classmethod
    def _extract_fields_from_facts(cls, facts_text: str) -> dict[str, Any]:
        text_lower = facts_text.lower()
        omics = cls._match_all(text_lower, cls._OMICS_VALUES, cls._OMICS_SYNONYMS)
        cohorts = cls._match_all(text_lower, cls._COHORT_VALUES, cls._COHORT_SYNONYMS)
        replicated: Optional[bool] = None
        if re.search(r"\b(replicat|validated in|transferable|generaliz)", text_lower):
            replicated = True
        if re.search(r"\b(not replicat|failed to replicat|not transferable|poor transferab|"
                     r"did not generaliz)", text_lower):
            replicated = False
        return {
            "ancestry_comparison": cls._extract_ancestry_comparison(text_lower),
            "population_cohorts": cohorts,
            "omics_layers": omics,
            "primary_omics_layer": omics[0] if omics else "",
            "trait": cls._extract_trait(text_lower),
            "method": cls._match_enum(text_lower, cls._METHOD_VALUES, cls._METHOD_SYNONYMS),
            "cross_ethnic_replication": replicated,
        }

    async def _llm_extract_missing_fields(
        self, title: str, text: str, missing_keys: list[str]
    ) -> dict[str, Any]:
        """Lightweight LLM extraction for coverage-critical fields heuristics missed."""
        from shared.core.llm_client import llm_complete, _parse_json

        prompt = f"""Extract ONLY the following fields from this cross-ethnic multi-omics paper.
Return a JSON object with exactly the requested fields (empty string if unknown).

Title: {title}

Text:
{text}

Fields to extract: {', '.join(missing_keys)}

Valid values:
- ancestry_comparison: "A_vs_B" using EUR, EAS, AFR, SAS, AMR (e.g. "EUR_vs_EAS")
- omics_layers: list from genomics, transcriptomics, proteomics, metabolomics, epigenomics, lipidomics, glycomics
- method: PRS-CSx, LDpred2, PRS-CS, mendelian_randomization, colocalization, PWAS, TWAS, fine_mapping, meta_analysis, pQTL_mapping, GWAS, admixture_mapping
- trait: free-text phenotype/disease name

Return ONLY the JSON object, no prose."""
        try:
            raw = await llm_complete(
                prompt,
                system="Extract structured fields from bioinformatics papers. Output valid JSON only.",
                budget=None,
                phase=self.budget_phase,
            )
            result = _parse_json(raw)
            if isinstance(result, dict):
                out: dict[str, Any] = {}
                for k in missing_keys:
                    v = result.get(k, "")
                    if k in ("omics_layers", "population_cohorts"):
                        out[k] = v if isinstance(v, list) else ([v] if v else [])
                    else:
                        out[k] = str(v) if v is not None else ""
                return out
        except Exception as e:
            logger.warning(f"LLM supplement failed for missing fields {missing_keys}: {e}")
        return {}

    async def _extract_from_deep_read(
        self,
        target: ExtractTarget,
        note: dict[str, Any],
        card_class: type[BaseEvidenceCard],
        topic_id: str = "",
    ) -> list[BaseEvidenceCard]:
        """Build cross-ethnic evidence cards from a deep-read note's structured facts."""
        cards: list[BaseEvidenceCard] = []
        paper_id = target.paper_id or ""

        source_paper = SourcePaper(
            title=target.title,
            doi=target.doi,
            pmid=target.pmid,
            year=target.year,
            venue=target.venue,
            authors=target.authors or [],
            url=target.url,
        )

        facts = note.get("facts", [])
        judgments = note.get("judgments", [])
        judg_by_claim = {j.get("claim_id", ""): j for j in judgments if isinstance(j, dict)}

        all_facts_text = " ".join(
            f.get("statement", "") for f in facts if isinstance(f, dict) and f.get("statement")
        )
        dr_fields = self._extract_fields_from_facts(all_facts_text)

        # 标题作为补充信号
        title_lower = target.title.lower()
        if not dr_fields.get("ancestry_comparison"):
            dr_fields["ancestry_comparison"] = self._extract_ancestry_comparison(title_lower)
        if not dr_fields.get("trait"):
            dr_fields["trait"] = self._extract_trait(title_lower)

        # LLM 补全启发式仍缺失的覆盖关键字段
        critical_fields = ["ancestry_comparison", "omics_layers", "trait", "method"]
        missing = [k for k in critical_fields if not dr_fields.get(k)]
        if missing and all_facts_text:
            paper_text = target.full_text or target.abstract or target.title
            if len(paper_text) > 50:
                llm_fields = await self._llm_extract_missing_fields(
                    target.title, paper_text[:3000], missing)
                for k, v in llm_fields.items():
                    if v:
                        dr_fields[k] = v
                        if k == "omics_layers" and isinstance(v, list) and v and not dr_fields.get("primary_omics_layer"):
                            dr_fields["primary_omics_layer"] = v[0]

        for i, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            statement = fact.get("statement", "")
            if not statement:
                continue
            loc = fact.get("source_locator", {})
            loc_text = loc.get("section", "") if isinstance(loc, dict) else ""

            evidence_status = fact.get("evidence_status", "author_claim")
            evidence_strength = "partially_supported" if judgments else "insufficient"
            claims_for_judgment = [j for _, j in judg_by_claim.items() if j.get("subject", "") in statement]
            if claims_for_judgment:
                evidence_strength = claims_for_judgment[0].get("verdict", "insufficient")

            fields = {
                "card_id": f"card_dr_{paper_id}_{i:03d}",
                "source_type": "paper",
                "source_paper": source_paper,
                "source_location": SourceLocation(section=loc_text),
                "reliability_flag": "medium" if target.doi or target.pmid else "unverified",
                "key_finding": statement,
                "method_brief": "",
                "archetype": "cross_ethnic",
                "tags": [f"candidate:{topic_id}"] if topic_id else [],
                "evidence_status": evidence_status,
                "evidence_strength": evidence_strength,
                "deep_read_source": note.get("paper_id", ""),
                # 注入启发式抽取的覆盖关键字段
                "ancestry_comparison": dr_fields.get("ancestry_comparison") or None,
                "population_cohorts": dr_fields.get("population_cohorts") or [],
                "omics_layers": dr_fields.get("omics_layers") or [],
                "primary_omics_layer": dr_fields.get("primary_omics_layer") or None,
                "trait": dr_fields.get("trait") or None,
                "method": dr_fields.get("method") or None,
                "cross_ethnic_replication": dr_fields.get("cross_ethnic_replication"),
            }
            try:
                card = card_class(**fields)
                cards.append(card)
            except Exception as e:
                logger.warning(
                    f"Deep-read card validation failed for paper={paper_id} "
                    f"finding_idx={i}: {e}"
                )

        if cards:
            logger.info(
                f"Deep-read: {len(cards)} cards from {target.title[:80]}; "
                f"ancestry={dr_fields.get('ancestry_comparison','?')}, "
                f"omics={dr_fields.get('omics_layers','?')}, method={dr_fields.get('method','?')}"
            )
        return cards

    async def _extract_from_paper(
        self,
        target: ExtractTarget,
        inp: CrossEthnicExtractInput,
        ctx: SkillContext,
        card_class: type[BaseEvidenceCard],
        topic_id: str = "",
    ) -> list[BaseEvidenceCard]:
        text = target.full_text or target.abstract or target.title
        if not text or len(text.strip()) < 100:
            return []

        truncate_len = inp.extraction_text_truncate
        prompt = CROSS_ETHNIC_DOMAIN_PROMPT.format(max_findings=inp.max_findings_per_paper)
        prompt += f"""

=== PAPER ===
Title: {target.title}
DOI: {target.doi or 'N/A'} | PMID: {target.pmid or 'N/A'} | Year: {target.year or ''}
Venue: {target.venue or ''}
Authors: {', '.join(target.authors[:5]) if target.authors else ''}

Abstract/Text:
{text[:truncate_len]}

Return a JSON list of finding objects. Each object MUST have: key_finding, method_brief,
and at least one of (ancestry_comparison, omics_layers).
The "ancestry_comparison" field uses codes EUR, EAS, AFR, SAS, AMR (e.g. "EUR_vs_EAS").
The "omics_layers" field is a list from: genomics, transcriptomics, proteomics, metabolomics,
epigenomics, lipidomics, glycomics.
The "method" field SHOULD be one of: PRS-CSx, LDpred2, PRS-CS, mendelian_randomization,
colocalization, PWAS, TWAS, fine_mapping, meta_analysis, pQTL_mapping, GWAS, admixture_mapping.
Return [] only if the paper has NO relevance to cross-ethnic/cross-ancestry multi-omics research.

Return ONLY the JSON array, no prose or markdown."""

        from shared.core.llm_client import llm_complete, _parse_json
        raw = await llm_complete(
            prompt,
            system="You are a bioinformatics evidence extractor. Output valid JSON only.",
            budget=ctx.budget,
            phase=self.budget_phase,
        )
        result = _parse_json(raw)
        if isinstance(result, dict):
            for v in result.values():
                if isinstance(v, list):
                    result = v
                    break
        if not isinstance(result, list):
            return []

        cards: list[BaseEvidenceCard] = []
        for finding in result:
            if not isinstance(finding, dict) or not finding.get("key_finding"):
                continue
            card = self._build_card(target, finding, card_class, topic_id)
            cards.append(card)

        if cards:
            first_card = cards[0]
            logger.info(
                f"Extracted {len(cards)} findings from {target.title[:80]}; "
                f"ancestry={getattr(first_card, 'ancestry_comparison', None)}, "
                f"omics={getattr(first_card, 'omics_layers', None)}, "
                f"method={getattr(first_card, 'method', None)}"
            )
        return cards

    @staticmethod
    def _coerce_str(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return ", ".join(str(x) for x in v if x)
        if isinstance(v, str):
            return v
        return str(v)

    @staticmethod
    def _coerce_opt_str(v: Any) -> Optional[str]:
        result = CrossEthnicCardExtract._coerce_str(v)
        return result if result else None

    @staticmethod
    def _coerce_list(v: Any) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return [str(v)]

    @staticmethod
    def _coerce_int(v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return _try_parse_int(v)
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_float(v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            return _try_parse_float(v)
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_bool(v: Any) -> Optional[bool]:
        if v is None or v == "":
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.lower().strip()
            if s in ("yes", "true", "1", "y", "replicated", "transferable"):
                return True
            if s in ("no", "false", "0", "n", "not_replicated", "not transferable"):
                return False
        return None

    def _build_card(self, target: ExtractTarget, finding: dict[str, Any],
                    card_class: type[BaseEvidenceCard], topic_id: str = "") -> BaseEvidenceCard:
        paper = SourcePaper(
            doi=target.doi,
            pmid=target.pmid,
            title=target.title,
            authors=target.authors,
            year=target.year,
            venue=target.venue,
            url=target.url,
        )
        location = SourceLocation(
            section=finding.get("section", "abstract"),
            excerpt=(finding.get("key_finding", "") or "")[:500],
        )
        reliability = "medium" if (target.doi or target.pmid) else "unverified"

        fields: dict[str, Any] = {
            "card_id": f"card_{uuid.uuid4().hex[:12]}",
            "source_type": "paper",
            "source_paper": paper,
            "source_location": location,
            "reliability_flag": reliability,
            "key_finding": self._coerce_str(finding.get("key_finding")),
            "method_brief": self._coerce_str(finding.get("method_brief")),
            "limitation_explicit": self._coerce_opt_str(finding.get("limitation_explicit")),
            "limitation_implicit": self._coerce_opt_str(finding.get("limitation_implicit")),
            "archetype": "cross_ethnic",
            "tags": finding.get("tags", []) if isinstance(finding.get("tags"), list) else [],
        }
        if topic_id:
            fields["tags"].append(f"candidate:{topic_id}")

        int_fields = {"sample_size_pop1", "sample_size_pop2"}
        float_fields = {
            "effect_size_pop1", "effect_size_pop2", "portability_score", "eval_metric_value",
        }
        bool_fields = {"cross_ethnic_replication", "code_available", "data_available"}
        list_fields = {"omics_layers", "population_cohorts"}

        model_fields = set(card_class.model_fields.keys())
        for k, v in finding.items():
            if k in model_fields and k not in fields:
                if k in int_fields:
                    fields[k] = self._coerce_int(v)
                elif k in float_fields:
                    fields[k] = self._coerce_float(v)
                elif k in bool_fields:
                    fields[k] = self._coerce_bool(v)
                elif k in list_fields:
                    fields[k] = self._coerce_list(v)
                else:
                    fields[k] = self._coerce_str(v)

        # primary_omics_layer 缺失时从 omics_layers 补齐
        if not fields.get("primary_omics_layer") and fields.get("omics_layers"):
            fields["primary_omics_layer"] = fields["omics_layers"][0]

        return card_class(**fields)

    async def quality_gate(self, output: CrossEthnicExtractOutput, ctx: SkillContext) -> bool:
        cards = output.cards
        findings_count = output.findings_count
        paper_count = output.paper_count

        if findings_count < 1:
            logger.error(
                f"S7 quality gate FAILED: 0 findings extracted (paper_count={paper_count})"
            )
            return False

        identity_empty = sum(1 for c in cards if not getattr(c, "key_finding", ""))
        if identity_empty > 0:
            logger.error(
                f"S7 quality gate FAILED (identity): {identity_empty}/{len(cards)} cards "
                f"have empty key_finding"
            )
            return False

        deep_read_cards = [c for c in cards if getattr(c, "deep_read_source", None)]
        if deep_read_cards:
            evidence_linked = sum(1 for c in deep_read_cards if getattr(c, "evidence_status", None))
            evidence_rate = evidence_linked / len(deep_read_cards)
            if evidence_rate < 0.6:
                logger.error(
                    f"S7 quality gate FAILED (evidence): only {evidence_linked}/{len(deep_read_cards)} "
                    f"deep-read cards have evidence_status (rate={evidence_rate:.1%}, threshold=60%)"
                )
                return False

        # 覆盖填充率: ancestry_comparison / omics_layers / trait 任一非空
        filled = sum(
            1 for c in cards
            if getattr(c, "ancestry_comparison", None)
            or getattr(c, "omics_layers", None)
            or getattr(c, "trait", None)
        )
        fill_rate = filled / max(findings_count, 1)
        min_fill = 0.15 if paper_count <= 1 else 0.40
        if paper_count > 3 and fill_rate < min_fill:
            logger.error(
                f"S7 quality gate FAILED (domain): only {filled}/{findings_count} cards "
                f"have ancestry/omics/trait info (fill_rate={fill_rate:.1%}, threshold={min_fill:.0%}, "
                f"paper_count={paper_count})"
            )
            return False

        if paper_count > 0:
            avg_cards = findings_count / paper_count
            if avg_cards > 10:
                logger.warning(
                    f"S7 cardinality WARNING: {avg_cards:.1f} avg cards/paper "
                    f"({findings_count} cards from {paper_count} papers)"
                )

        dr_info = ""
        if deep_read_cards:
            rate = sum(1 for c in deep_read_cards if getattr(c, 'evidence_status', None)) / len(deep_read_cards)
            dr_info = f", evidence_rate={rate:.1%}"
        logger.info(
            f"S7 quality gate passed: fill_rate={fill_rate:.1%}{dr_info}, "
            f"cards={findings_count}, papers={paper_count}"
        )
        return True


__all__ = [
    "CrossEthnicCardExtract",
    "CrossEthnicExtractInput",
    "CrossEthnicExtractOutput",
    "ExtractTarget",
]
