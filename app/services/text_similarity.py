# 提供需求文本归一化和近似去重。

import re

SIMILARITY_THRESHOLD = 0.45


def normalize_text(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


def char_bigram_jaccard(left: str, right: str) -> float:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if not left_normalized or not right_normalized:
        return 0.0

    left_bigrams = {
        left_normalized[index:index + 2]
        for index in range(len(left_normalized) - 1)
    }
    right_bigrams = {
        right_normalized[index:index + 2]
        for index in range(len(right_normalized) - 1)
    }
    if not left_bigrams or not right_bigrams:
        return 0.0
    return len(left_bigrams & right_bigrams) / len(left_bigrams | right_bigrams)


def _contains_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def requirements_are_similar(left: str, right: str) -> bool:
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)
    if left_normalized == right_normalized:
        return True

    shorter, longer = sorted(
        (left_normalized, right_normalized),
        key=len,
    )
    if shorter and _contains_chinese(shorter) and shorter in longer:
        return True
    return char_bigram_jaccard(left, right) >= SIMILARITY_THRESHOLD


__all__ = [
    "SIMILARITY_THRESHOLD",
    "char_bigram_jaccard",
    "normalize_text",
    "requirements_are_similar",
]
