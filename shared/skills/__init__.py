"""Shared skills registry."""
from shared.skills.base_skill import BaseSkill, SkillContext, SkillInput, SkillOutput
from shared.skills.skill_01_direction_decompose import DirectionDecompose
from shared.skills.skill_02_terminology_normalize import TerminologyNormalize
from shared.skills.skill_04_multi_source_search import MultiSourceSearch
from shared.skills.skill_05_citation_snowball import CitationSnowballSkill
from shared.skills.skill_06_literature_screening import LiteratureScreening
from shared.skills.skill_06b_pdf_download import PDFDownloadSkill
from shared.skills.skill_06c_deep_read import DeepReadSkill
from shared.skills.skill_07_evidence_card_extract import EvidenceCardExtract
from shared.skills.skill_08_data_availability import DataAvailability
from shared.skills.skill_09_method_dataset_match import MethodDatasetMatch
from shared.skills.skill_11_gap_analysis import GapAnalysis
from shared.skills.skill_12_hypothesis_generate import HypothesisGenerate

SHARED_SKILLS = {
    "s1_direction_decompose": DirectionDecompose,
    "s2_terminology_normalize": TerminologyNormalize,
    "s4_multi_source_search": MultiSourceSearch,
    "s5_citation_snowball": CitationSnowballSkill,
    "s6_literature_screening": LiteratureScreening,
    "s6b_pdf_download": PDFDownloadSkill,
    "s6c_deep_read": DeepReadSkill,
    "s7_evidence_card_extract": EvidenceCardExtract,
    "s8_data_availability": DataAvailability,
    "s9_method_dataset_match": MethodDatasetMatch,
    "s11_gap_analysis": GapAnalysis,
    "s12_hypothesis_generate": HypothesisGenerate,
}

__all__ = [
    "BaseSkill", "SkillContext", "SkillInput", "SkillOutput", "SHARED_SKILLS",
    "DirectionDecompose", "TerminologyNormalize", "MultiSourceSearch",
    "CitationSnowballSkill", "LiteratureScreening", "PDFDownloadSkill", "EvidenceCardExtract",
    "DataAvailability", "MethodDatasetMatch", "GapAnalysis", "HypothesisGenerate",
]
