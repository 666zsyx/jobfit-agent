# 为岗位要求生成确定性的检索 query 变体。

import re

_PREFIX_PATTERN = re.compile(
    r"^(具备|熟悉|掌握|了解|精通|需要|要求|拥有|使用|负责|参与|"
    r"能够|可以|会|有)\s*"
)
_SUFFIX_PATTERN = re.compile(r"\s*(经验|能力|技能|要求)$")
_PUNCTUATION_PATTERN = re.compile(r"[，,。；;：:、]")


def normalize_requirement_query(requirement: str) -> str:
    text = requirement.strip()
    text = re.sub(r"\s+", " ", text)

    changed = True
    while changed:
        changed = False
        new_text = _PREFIX_PATTERN.sub("", text, count=1).strip()
        if new_text != text:
            text = new_text
            changed = True

    text = _SUFFIX_PATTERN.sub("", text, count=1).strip()
    text = _PUNCTUATION_PATTERN.sub(" ", text)
    text = text.replace("进行", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or requirement.strip()


def build_query_variants(requirement: str) -> list[str]:
    normalized = requirement.strip()
    if not normalized:
        return []

    variants = [normalized]
    keyword_query = normalize_requirement_query(normalized)
    if keyword_query and keyword_query not in variants:
        variants.append(keyword_query)
    return variants


__all__ = ["build_query_variants", "normalize_requirement_query"]
