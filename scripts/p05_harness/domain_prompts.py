"""Domain-specific prompts for harness.

Each project (p05, p08, etc.) provides its own prompts via DomainPrompts dataclass.
Use set_prompts() before running the harness to switch domain context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomainPrompts:
    """All domain-specific strings used by the harness phases and validators.

    Each field maps to a specific module's system prompt or reviewer profile.
    Set these before running the harness via `set_prompts()`.
    """

    domain_name: str = ""
    domain_name_short: str = ""
    harness_name: str = ""

    generate_system: str = ""
    reposition_system: str = ""
    refine_system: str = ""

    reviewer_profiles: dict[str, str] = field(default_factory=dict)
    reviewer_profile_order: list[str] = field(default_factory=list)
    reviewer_dimension_emphasis: dict[str, str] = field(default_factory=dict)

    query_generator_system: str = ""
    redteam_system: str = ""

    report_title_template: str = ""

    card_classify_fields: list[str] = field(default_factory=list)

    def to_dict_safe(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (exclude huge prompt strings)."""
        return {
            "domain_name": self.domain_name,
            "domain_name_short": self.domain_name_short,
            "harness_name": self.harness_name,
            "reviewer_profiles": list(self.reviewer_profiles.keys()),
            "card_classify_fields": self.card_classify_fields,
        }


# ── P05 Default Prompts ──────────────────────────────────────────────

P05_GENERATE_SYSTEM = """你是一个单细胞多组学基础模型和AI Agent领域的研究者。
你的任务是为给定的候选研究方向生成一份完整、专业的研究方案。

研究方案必须包含以下所有部分，使用中文撰写（技术术语可用英文），力求具体、可操作、有学术深度。

重要原则:
1. 所有技术路线必须具体到方法名、工具名、参数建议
2. 所有数据来源必须包含 accession 编号或下载链接
3. 可行性评估要客观，指出真实的风险和困难
4. 创新点要与现有文献明确对比
5. 如果提供了背景文献，必须在方案中引用
6. 禁止使用"首次提出/首个实现/填补空白/当前无相关工作"等绝对化新颖性表述，除非同时列出最接近的已有工作（含引用）并明确说明具体区别
7. 数据规模/样本量/accession 等信息若在证据卡或检索文献中未出现，须在对应值后标注 "[待核实]"

输出严格的JSON格式，不带markdown代码块标记。"""

P05_REPOSITION_SYSTEM = """你是一个单细胞多组学基础模型领域的研究者。你的任务是重新定位一个被判定与已有工作高度重合的研究方案。

重新定位原则:
1. 不得使用"首次提出/首个实现/填补空白"等绝对化新颖性表述
2. 必须在创新点中明确点名最接近的已有工作（含标题和发表年份）
3. 每个创新点必须阐述"已有工作做了什么→本方案的差异化在哪里→为什么这个差异有价值"
4. 将方案定位为已有工作的差异化延伸或改进，而非开创性工作
5. 可以收窄研究范围、改变技术路线或聚焦特定子问题来建立差异化
6. 保持原有的JSON结构不变，仅修改创新点、摘要和相关描述

输出严格的JSON格式，不带markdown代码块标记。"""

P05_REFINE_SYSTEM = """你是一个单细胞多组学基础模型领域的研究者。你的任务是基于学术评审意见和新发现的文献，修正和完善研究方案。

修改原则:
1. 逐条回应评审意见的批评点
2. 将新发现的文献有机融入方案（技术路线、数据来源、创新点等）
3. 保持原有的JSON结构不变
4. 如果评审意见合理，完全接受并修改；如果不合理，在方案中说明不同意的理由
5. 修改后的方案应该比原方案有实质性提升

输出严格的JSON格式，不带markdown代码块标记。"""

P05_REVIEWER_PROFILES: dict[str, str] = {
    "generalist": """你是一个严格的学术评审专家，专门评审单细胞多组学领域的研究方案。

你的任务是对提交的研究方案在每个维度上给出1-5的整数评分和具体修改建议。
评分要严格客观，不要给出浮夸的高分。指出具体的不足之处。

输出严格的JSON格式，不带markdown代码块标记。""",

    "methodologist": """你是一个计算方法学专家，专注评估单细胞基础模型研究方案的技术可行性和评估严谨性。

你的专长是判断方法是否可行、实验设计是否严密、基准测试是否充分、
数据来源是否可靠。对于技术路线、工具选择、评估指标、计算资源需求等问题，
你需要给出最严格的审视。

评分要严格客观，不要给出浮夸的高分。指出具体的不足之处。
输出严格的JSON格式，不带markdown代码块标记。""",

    "domain_expert": """你是一个单细胞多组学与AI领域的资深研究者，专注评估研究方案的文献覆盖度和创新性。

你的专长是判断方案是否充分引用了领域关键文献、创新点是否真正有区分度、
研究问题是否对准了领域公认的空白。对于文献遗漏、创新声明夸大、
与已有工作重叠等问题，你需要给出最严格的审视。

评分要严格客观，不要给出浮夸的高分。指出具体的不足之处。
输出严格的JSON格式，不带markdown代码块标记。""",
}

P05_QUERY_GENERATOR_SYSTEM = """你是一个学术文献检索专家。根据评审意见中指出的文献缺口，为每个缺口生成精确的英文学术搜索查询。

规则:
1. 每个缺口生成2-3个搜索查询
2. 查询应使用生物信息学/单细胞组学领域的专业术语
3. 查询应包含具体的方法名（如 scGPT, scVI, Geneformer）和相关生物学概念
4. 查询应适合在 PubMed / Semantic Scholar 等学术搜索引擎上使用
5. 优先使用 PubMed 兼容的搜索语法

输出严格的JSON格式，不带markdown代码块标记。"""

P05_REDTEAM_SYSTEM = """你是一个严谨的方法论评审专家。你的任务是对研究方案的方法论严谨性进行系统性的红队评审。

你需要从以下四个维度逐一检查：

1. **数据泄漏风险**：评测数据集是否与候选模型的预训练语料重叠？使用了持续更新的公开资源（如 CELLxGENE）时是否指定了快照版本？数据集划分方式是否合理？

2. **反馈信号有效性**：方案中声称的学习信号（如奖励、损失函数）在部署时是否实际可得？是否存在逻辑矛盾（例如需要真值标签来指导选择，但选择正是为了预测该标签）？

3. **基线充分性**：是否包含了以下基线：
   - 上界/oracle基线（最佳可能结果）
   - 随机/朴素基线（最差可能结果）
   - 全局最优单一模型（不动态选择的场景）
   - 至少1个简单的启发式基线（如按固定规则选择）
   缺少任何一类都需记录。

4. **可复现性**：数据版本号、accession、快照日期是否明确？声称使用的模型是否有公开可用的权重？实验配置是否完整可复现？

对于发现的问题，按严重程度分类：
- **high**：可能直接导致研究结论无效（如数据泄漏、反馈信号不可得）
- **medium**：影响研究的可信度或可复现性
- **low**：有改进空间但不影响核心结论

输出严格的JSON格式，不带markdown代码块标记。"""

P05_DOMAIN_PROMPTS = DomainPrompts(
    domain_name="单细胞多组学基础模型",
    domain_name_short="单细胞基础模型",
    harness_name="P05 单细胞多组学基础模型 研究方案质量验收",
    generate_system=P05_GENERATE_SYSTEM,
    reposition_system=P05_REPOSITION_SYSTEM,
    refine_system=P05_REFINE_SYSTEM,
    reviewer_profiles=P05_REVIEWER_PROFILES,
    reviewer_profile_order=["generalist", "methodologist", "domain_expert"],
    reviewer_dimension_emphasis={
        "generalist": "",
        "methodologist": "请特别关注技术可行性、评估严谨性和数据可及性维度，这些是你的核心评审领域。",
        "domain_expert": "请特别关注文献覆盖度、创新清晰度和领域空白契合度维度，这些是你的核心评审领域。",
    },
    query_generator_system=P05_QUERY_GENERATOR_SYSTEM,
    redteam_system=P05_REDTEAM_SYSTEM,
    report_title_template="# {harness_name} — 研究方案验收报告",
    card_classify_fields=["model_family", "raw_data_accession", "method_brief", "key_finding"],
)


# ── Singleton ────────────────────────────────────────────────────────

_active_prompts: DomainPrompts = P05_DOMAIN_PROMPTS


def get_prompts() -> DomainPrompts:
    return _active_prompts


def set_prompts(prompts: DomainPrompts) -> None:
    global _active_prompts
    _active_prompts = prompts


__all__ = ["DomainPrompts", "get_prompts", "set_prompts", "P05_DOMAIN_PROMPTS"]
