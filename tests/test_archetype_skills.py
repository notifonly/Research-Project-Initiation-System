"""Tests for archetype-specific s3 scoping skills."""

from archetypes.archetype_b_prs.skills.skill_03_prs_study_collect import (
    PRSStudyCollect, PRSStudyCollectInput, PRSStudyRecord,
)
from archetypes.archetype_c_sc_ai.skills.skill_03_fm_resource_collect import (
    FMResourceCollect, FMResourceRecord,
)
from archetypes.archetype_d_omics_score.skills.skill_03_score_method_collect import (
    ScoreMethodCollect, ScoreMethodRecord,
)


class TestPRSStudyRecord:
    def test_defaults(self):
        r = PRSStudyRecord()
        assert r.trait == ""
        assert r.validation_cohorts == []
        assert r.ancestry_groups == []
        assert r.sample_size_training is None


class TestPRSStudyCollect:
    def test_name(self):
        skill = PRSStudyCollect()
        assert skill.name == "prs_study_collect"
        assert not skill.uses_llm

    def test_input_defaults(self):
        inp = PRSStudyCollectInput()
        assert inp.traits == []
        assert inp.efo_ids == []
        assert inp.max_per_trait == 50

    def test_deduplicate(self):
        skill = PRSStudyCollect()
        records = [
            PRSStudyRecord(trait="T1", method_name="LDpred2", training_cohort="UKBB"),
            PRSStudyRecord(trait="T1", method_name="LDpred2", training_cohort="UKBB"),
            PRSStudyRecord(trait="T1", method_name="PRS-CS", training_cohort="BBJ"),
        ]
        dedup = skill._deduplicate(records)
        assert len(dedup) == 2


class TestFMResourceRecord:
    def test_defaults(self):
        r = FMResourceRecord()
        assert r.model_name == ""
        assert r.supported_tasks == []
        assert r.benchmark_datasets == []


class TestFMResourceCollect:
    def test_name(self):
        skill = FMResourceCollect()
        assert skill.name == "fm_resource_collect"
        assert not skill.uses_llm

    def test_deduplicate(self):
        skill = FMResourceCollect()
        records = [
            FMResourceRecord(model_name="scGPT"),
            FMResourceRecord(model_name="scGPT"),
            FMResourceRecord(model_name="Geneformer"),
        ]
        dedup = skill._deduplicate(records)
        assert len(dedup) == 2


class TestScoreMethodRecord:
    def test_defaults(self):
        r = ScoreMethodRecord()
        assert r.method_name == ""
        assert r.validation_cohorts == []


class TestScoreMethodCollect:
    def test_name(self):
        skill = ScoreMethodCollect()
        assert skill.name == "score_method_collect"
        assert not skill.uses_llm

    def test_deduplicate(self):
        skill = ScoreMethodCollect()
        records = [
            ScoreMethodRecord(method_name="Horvath", trait="aging"),
            ScoreMethodRecord(method_name="Horvath", trait="aging"),
            ScoreMethodRecord(method_name="GrimAge", trait="aging"),
        ]
        dedup = skill._deduplicate(records)
        assert len(dedup) == 2
