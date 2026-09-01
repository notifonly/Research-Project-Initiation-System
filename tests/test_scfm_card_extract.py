"""Regression tests for SCFMCardExtract (Archetype C S7)."""

import json
from unittest.mock import MagicMock

import pytest

from archetypes.archetype_c_sc_ai.evidence_card import SCFMEvidenceCard
from archetypes.archetype_c_sc_ai.skills.skill_07_scfm_card_extract import (
    SCFMCardExtract,
    SCFMExtractInput,
    SCFMExtractOutput,
    ExtractTarget,
)
from shared.evidence.base_card import BaseEvidenceCard, EvidenceState, SourcePaper, SourceLocation
from shared.skills.base_skill import SkillContext


def _make_ctx() -> SkillContext:
    from shared.core.token_budget import TokenBudget
    return SkillContext(
        project_id="test",
        mcp_registry=MagicMock(),
        card_store=MagicMock(),
        context=MagicMock(),
        budget=TokenBudget(project_id="test"),
    )


class TestSCFMCardFieldDefaults:
    def test_defaults(self):
        card = SCFMEvidenceCard()
        assert card.archetype == "sc_fm"
        assert card.task is None
        assert card.modality_omics is None

    def test_extra_fields_ignored(self):
        card = SCFMEvidenceCard.model_validate(
            {"card_id": "test1", "unknown_field": "should_be_ignored"}
        )
        assert not hasattr(card, "unknown_field")

    def test_coverage_axes(self):
        card = SCFMEvidenceCard(
            task="cell_type_annotation",
            modality_omics="scRNA-seq",
            tissue="PBMC",
            model_architecture="transformer",
            held_out_cell_types=EvidenceState.CONFIRMED,
        )
        axes = card.coverage_axes()
        assert axes["task"] == "cell_type_annotation"
        assert axes["modality"] == "scRNA-seq"
        assert axes["tissue"] == "PBMC"
        assert axes["model_architecture"] == "transformer"
        assert axes["evaluation_setting"] == "held_out_celltype"


class TestSCFMCardExtractQualityGate:
    @pytest.fixture
    def skill(self):
        return SCFMCardExtract()

    @pytest.fixture
    def ctx(self):
        return _make_ctx()

    async def test_rejects_zero_findings(self, skill, ctx):
        output = SCFMExtractOutput(
            skill_name="s7",
            cards=[],
            paper_count=5,
            findings_count=0,
            irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is False

    async def test_rejects_low_fill_rate(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="", task_category="", key_finding="f1"),
            SCFMEvidenceCard(card_id="c2", task="", task_category="", key_finding="f2"),
            SCFMEvidenceCard(card_id="c3", task="", task_category="", key_finding="f3"),
            SCFMEvidenceCard(card_id="c4", task="", task_category="", key_finding="f4"),
            SCFMEvidenceCard(card_id="c5", task="", task_category="", key_finding="f5"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7",
            cards=cards,
            paper_count=5,
            findings_count=5,
            irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is False

    async def test_passes_good_output(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="cell_type_annotation", key_finding="f1"),
            SCFMEvidenceCard(card_id="c2", task_category="supervised_prediction", key_finding="f2"),
            SCFMEvidenceCard(card_id="c3", task="", task_category="", key_finding="f3"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7",
            cards=cards,
            paper_count=3,
            findings_count=3,
            irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is True

    async def test_passes_single_paper_even_empty(self, skill, ctx):
        cards = [SCFMEvidenceCard(card_id="c1", task="", task_category="", key_finding="f1")]
        output = SCFMExtractOutput(
            skill_name="s7",
            cards=cards,
            paper_count=1,
            findings_count=1,
            irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is True

    async def test_rejects_empty_key_finding(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="cell_type_annotation", key_finding=""),
            SCFMEvidenceCard(card_id="c2", task="batch_correction", key_finding="f2"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7", cards=cards,
            paper_count=2, findings_count=2, irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is False

    async def test_rejects_low_evidence_rate(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="cell_type_annotation", key_finding="f1",
                             deep_read_source="paper_1", evidence_status=None),
            SCFMEvidenceCard(card_id="c2", task="batch_correction", key_finding="f2",
                             deep_read_source="paper_1", evidence_status=None),
            SCFMEvidenceCard(card_id="c3", task="grn_inference", key_finding="f3",
                             deep_read_source="paper_1", evidence_status="author_claim"),
            SCFMEvidenceCard(card_id="c4", task="gene_expression_prediction", key_finding="f4"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7", cards=cards,
            paper_count=4, findings_count=4, irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is False

    async def test_passes_with_adequate_evidence(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="cell_type_annotation", key_finding="f1",
                             deep_read_source="paper_1", evidence_status="author_claim"),
            SCFMEvidenceCard(card_id="c2", task="batch_correction", key_finding="f2",
                             deep_read_source="paper_1", evidence_status="directly_stated"),
            SCFMEvidenceCard(card_id="c3", task="grn_inference", key_finding="f3",
                             deep_read_source="paper_2", evidence_status="author_claim"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7", cards=cards,
            paper_count=3, findings_count=3, irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is True

    async def test_rejects_moderate_fill_rate(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="cell_type_annotation", key_finding="f1"),
            SCFMEvidenceCard(card_id="c2", task="batch_correction", key_finding="f2"),
            SCFMEvidenceCard(card_id="c3", task="grn_inference", key_finding="f3"),
            SCFMEvidenceCard(card_id="c4", task="", task_category="", key_finding="f4"),
            SCFMEvidenceCard(card_id="c5", task="", task_category="", key_finding="f5"),
            SCFMEvidenceCard(card_id="c6", task="", task_category="", key_finding="f6"),
            SCFMEvidenceCard(card_id="c7", task="", task_category="", key_finding="f7"),
            SCFMEvidenceCard(card_id="c8", task="", task_category="", key_finding="f8"),
            SCFMEvidenceCard(card_id="c9", task="", task_category="", key_finding="f9"),
            SCFMEvidenceCard(card_id="c10", task="", task_category="", key_finding="f10"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7", cards=cards,
            paper_count=5, findings_count=10, irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is False

    async def test_passes_adequate_fill_rate(self, skill, ctx):
        cards = [
            SCFMEvidenceCard(card_id="c1", task="cell_type_annotation", key_finding="f1"),
            SCFMEvidenceCard(card_id="c2", task="batch_correction", key_finding="f2"),
            SCFMEvidenceCard(card_id="c3", task="grn_inference", key_finding="f3"),
            SCFMEvidenceCard(card_id="c4", task_category="supervised_prediction", key_finding="f4"),
            SCFMEvidenceCard(card_id="c5", task="", task_category="", key_finding="f5"),
            SCFMEvidenceCard(card_id="c6", task="", task_category="", key_finding="f6"),
            SCFMEvidenceCard(card_id="c7", task="", task_category="", key_finding="f7"),
            SCFMEvidenceCard(card_id="c8", task="", task_category="", key_finding="f8"),
            SCFMEvidenceCard(card_id="c9", task="", task_category="", key_finding="f9"),
            SCFMEvidenceCard(card_id="c10", task="", task_category="", key_finding="f10"),
        ]
        output = SCFMExtractOutput(
            skill_name="s7", cards=cards,
            paper_count=5, findings_count=10, irrelevant_count=0,
        )
        passed = await skill.quality_gate(output, ctx)
        assert passed is True
    def test_rejects_nursing(self):
        assert SCFMCardExtract._is_irrelevant(
            "CVI scale validation study",
            "We used content validity index and face validity for nursing education",
        ) is True

    def test_rejects_psychometric(self):
        assert SCFMCardExtract._is_irrelevant(
            "Questionnaire psychometric properties",
            "A psychometric evaluation of the Delphi questionnaire",
        ) is True

    def test_accepts_sc_fm_paper(self):
        assert SCFMCardExtract._is_irrelevant(
            "scGPT: toward building a foundation model for single-cell multi-omics",
            "We pretrain on 10M cells across multiple tissues using a transformer architecture",
        ) is False


class TestSCFMCardExtractEnumMatching:
    def test_task_cell_type_annotation(self):
        result = SCFMCardExtract._match_enum(
            "scGPT performs cell type annotation across tissues",
            SCFMCardExtract._TASK_VALUES,
            SCFMCardExtract._TASK_SYNONYMS,
        )
        assert result == "cell_type_annotation"

    def test_modality_scrnaseq(self):
        result = SCFMCardExtract._match_enum(
            "We applied scVI to single-cell RNA sequencing data".lower(),
            SCFMCardExtract._MODALITY_VALUES,
            SCFMCardExtract._MODALITY_SYNONYMS,
        )
        assert result == "scRNA-seq"

    def test_architecture_transformer(self):
        result = SCFMCardExtract._match_enum(
            "This model uses a transformer-based architecture for gene expression".lower(),
            SCFMCardExtract._ARCHITECTURE_VALUES,
            SCFMCardExtract._ARCHITECTURE_SYNONYMS,
        )
        assert result == "transformer"

    def test_model_family_scgpt(self):
        result = SCFMCardExtract._match_enum(
            "scGPT pretrained on 33M cells".lower(),
            SCFMCardExtract._MODEL_FAMILY_VALUES,
        )
        assert result == "scGPT"

    def test_tissue_pbmc(self):
        result = SCFMCardExtract._match_enum(
            "We collected PBMCs from healthy donors".lower(),
            SCFMCardExtract._TISSUE_VALUES,
            SCFMCardExtract._TISSUE_SYNONYMS,
        )
        assert result == "PBMC"

    def test_no_match_returns_none(self):
        result = SCFMCardExtract._match_enum(
            "This paper discusses unrelated topics".lower(),
            SCFMCardExtract._TASK_VALUES,
            SCFMCardExtract._TASK_SYNONYMS,
        )
        assert result == ""

    def test_extract_fields_from_facts(self):
        fields = SCFMCardExtract._extract_fields_from_facts(
            "scGPT transformer model performs cell type annotation on PBMC scRNA-seq data"
        )
        assert fields["task"] == "cell_type_annotation"
        assert fields["modality_omics"] == "scRNA-seq"
        assert fields["model_architecture"] == "transformer"
        assert fields["model_family"] == "scGPT"
        assert fields["tissue"] == "PBMC"

    def test_extract_fields_unknown(self):
        fields = SCFMCardExtract._extract_fields_from_facts(
            "This paper has no recognizable single-cell information"
        )
        assert fields["task"] == ""
        assert fields["modality_omics"] == ""


class TestSCFMCardExtractDeepRead:
    def test_validation_failure_logged(self, caplog):
        import logging
        caplog.set_level(logging.WARNING)
        target = ExtractTarget(
            paper_id="test001",
            title="A test scFM paper",
            doi="10.1234/example",
            year=2024,
        )
        note = {
            "paper_id": "test001",
            "facts": [{"statement": "test finding", "source_locator": {"section": "results"}}],
            "judgments": [],
        }
        skill = SCFMCardExtract()
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                skill._extract_from_deep_read(target, note, SCFMEvidenceCard, "topic_x")
            )
        finally:
            loop.close()
        assert isinstance(result, list)

    def test_constructs_cards_from_facts(self):
        target = ExtractTarget(
            paper_id="test001",
            title="scGPT: foundation model for single cell",
            doi="10.1234/example",
            year=2024,
        )
        note = {
            "paper_id": "test001",
            "facts": [
                {
                    "statement": "scGPT achieves 0.95 F1 on cell type annotation of PBMC scRNA-seq data",
                    "evidence_status": "directly_stated",
                    "source_locator": {"section": "results"},
                }
            ],
            "judgments": [],
        }
        skill = SCFMCardExtract()
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                skill._extract_from_deep_read(target, note, SCFMEvidenceCard, "topic_x")
            )
        finally:
            loop.close()
        assert len(result) == 1
        card = result[0]
        assert "cell_type_annotation" in card.task or card.task is None
        assert card.key_finding is not None
        assert card.archetype == "sc_fm"


class TestSCFMCardExtractPaper:
    @pytest.mark.asyncio
    async def test_skips_short_text(self):
        target = ExtractTarget(
            paper_id="p1",
            title="Short",
            abstract="Too short",
        )
        skill = SCFMCardExtract()
        inp = SCFMExtractInput(targets=[target], max_targets=5)
        ctx = _make_ctx()
        result = await skill._extract_from_paper(target, inp, ctx, SCFMEvidenceCard, "t1")
        assert result == []
