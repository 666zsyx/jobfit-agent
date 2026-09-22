import re

from app.schemas.evidence import (
    EvidenceItem,
    EvidenceSearchResult,
    MAX_EVIDENCE_PER_REQUIREMENT,
    RequirementEvidence,
)
from app.schemas.resume import ResumeSection


#单条岗位要求默认返回3条证据
DEFAULT_MAX_EVIDENCE_PER_REQUIREMENT = 3
#单条岗位要求最多返回10条证据
MIN_EVIDENCE_SCORE = 0.2

#英文token正则：以字母或数字开头，后面可跟字母/数字/下划线/加号/井号/点/短横线
#例如可匹配：fastapi、c++、c#、scikit-learn、python3.12
ENGLISH_TOKEN_PATTERN = re.compile(
    r"[a-z0-9][a-z0-9_+#.\-]*"
)
#中文连续串正则：匹配一段连续汉字
CHINESE_RUN_PATTERN = re.compile(
    r"[\u4e00-\u9fff]+"
)


#把任意文本切分成token集合（英文整词 + 中文整串 + 中文2-gram）
def tokenize(text: str) -> set[str]:
    #统一转小写便于匹配
    normalized = text.lower()
    tokens: set[str] = set()

    #抽取所有英文token
    english_tokens = ENGLISH_TOKEN_PATTERN.findall(normalized)
    tokens.update(english_tokens)

    #抽取所有中文连续串
    chinese_runs = CHINESE_RUN_PATTERN.findall(normalized)

    for run in chinese_runs:
        #整串加入
        tokens.add(run)

        #再按相邻两字切2-gram加入
        #例如"熟练使用" → "熟练"、"练使"、"使用"
        for index in range(len(run) - 1):
            tokens.add(run[index:index + 2])

    return tokens


#计算一条岗位要求和一段简历的匹配得分
def calculate_score(
    requirement: str,
    section: ResumeSection,
) -> float:
    #对岗位要求分词
    requirement_tokens = tokenize(requirement)
    #对简历段落的标题+正文分词
    section_tokens = tokenize(
        f"{section.title} {section.content}"
    )

    #防御：requirements没有token时避免除零
    if not requirement_tokens:
        return 0.0

    #取交集：既在要求里出现、又在简历段落里出现的token
    matched_tokens = requirement_tokens & section_tokens

    #得分 = 命中token数 / 要求token总数，保留3位小数
    return round(
        len(matched_tokens) / len(requirement_tokens),
        3,
    )


#校验岗位要求列表是否合法
def _validate_requirements(
    requirements: list[str],
) -> list[str]:
    #非空校验
    if not requirements:
        raise ValueError("requirements 不能为空")

    normalized_requirements: list[str] = []

    for requirement in requirements:
        #类型校验
        if not isinstance(requirement, str):
            raise ValueError("requirement 必须是字符串")

        #去掉首尾空白
        normalized = requirement.strip()

        #不能为纯空白
        if not normalized:
            raise ValueError("requirement 不能为空或纯空白")

        normalized_requirements.append(normalized)

    #返回清洗后的列表
    return normalized_requirements


#校验简历分段列表是否合法
def _validate_sections(
    sections: list[ResumeSection],
) -> None:
    #目前只要求非空
    if not sections:
        raise ValueError("sections 不能为空")


#校验每条要求允许返回的证据数量是否合法
def _validate_max_evidence(
    max_evidence_per_requirement: int,
) -> None:
    #必须是真的int，且排除bool（bool是int子类会被误判）
    if (
        not isinstance(max_evidence_per_requirement, int)
        or isinstance(max_evidence_per_requirement, bool)
    ):
        raise ValueError(
            "max_evidence_per_requirement 必须是整数"
        )

    #下限
    if max_evidence_per_requirement < 1:
        raise ValueError(
            "max_evidence_per_requirement 必须大于等于 1"
        )

    #上限
    if max_evidence_per_requirement > MAX_EVIDENCE_PER_REQUIREMENT:
        raise ValueError(
            "max_evidence_per_requirement 不能超过 "
            f"{MAX_EVIDENCE_PER_REQUIREMENT}"
        )


#主入口：对每条岗位要求，从简历分段中检索最相关的证据
def search_resume_evidence(
    requirements: list[str],
    sections: list[ResumeSection],
    max_evidence_per_requirement: int = (
        DEFAULT_MAX_EVIDENCE_PER_REQUIREMENT
    ),
) -> EvidenceSearchResult:
    #先做三项前置校验
    normalized_requirements = _validate_requirements(
        requirements
    )
    _validate_sections(sections)
    _validate_max_evidence(max_evidence_per_requirement)

    matches: list[RequirementEvidence] = []

    #逐条岗位要求处理
    for requirement in normalized_requirements:
        #候选池：存放(得分, 原始下标, 分段对象)三元组
        candidates: list[
            tuple[float, int, ResumeSection]
        ] = []

        #遍历简历每个分段，算匹配分
        for original_index, section in enumerate(sections):
            score = calculate_score(requirement, section)

            #只保留达到最低阈值的分段
            if score >= MIN_EVIDENCE_SCORE:
                candidates.append(
                    (score, original_index, section)
                )

        #排序：先按得分降序（-score），得分相同再按原始下标升序
        #这样能保证相同得分时保持简历原有顺序
        candidates.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )

        #截取前 N 条
        selected = candidates[
            :max_evidence_per_requirement
        ]

        #把选中的分段打包成 EvidenceItem 列表
        evidence = [
            EvidenceItem(
                section_type=section.section_type,
                title=section.title,
                content=section.content,
                score=score,
            )
            for score, _, section in selected
        ]

        #绑定这条要求与它的证据
        matches.append(
            RequirementEvidence(
                requirement=requirement,
                evidence=evidence,
            )
        )

    #包装成最终结果返回
    return EvidenceSearchResult(
        requirements=normalized_requirements,
        matches=matches,
    )
