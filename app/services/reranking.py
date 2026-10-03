# 定义可替换的 Reranker 和 FastEmbed Cross-Encoder 实现。

from collections.abc import Sequence
from threading import Lock
from typing import Protocol

from fastembed.rerank.cross_encoder import TextCrossEncoder


class Reranker(Protocol):
    """Cross-Encoder 重排接口。"""

    @property
    def model_name(self) -> str:
        ...

    def score(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> list[float]:
        ...


class FastEmbedReranker:
    """使用本地 ONNX Cross-Encoder 计算相关性。"""

    def __init__(
        self,
        *,
        model_name: str,
        cache_dir: str,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: TextCrossEncoder | None = None
        self._model_lock = Lock()

    @property
    def model_name(self) -> str:
        return self._model_name

    def _get_model(self) -> TextCrossEncoder:
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is None:
                self._model = TextCrossEncoder(
                    model_name=self._model_name,
                    cache_dir=self._cache_dir,
                )

        return self._model

    def score(
        self,
        *,
        query: str,
        documents: Sequence[str],
    ) -> list[float]:
        normalized_query = query.strip()
        normalized_documents = [
            document.strip()
            for document in documents
        ]

        if not normalized_query:
            raise ValueError("query 不能为空")

        if not normalized_documents:
            raise ValueError("documents 不能为空")

        if any(not document for document in normalized_documents):
            raise ValueError("待重排文本不能为空")

        scores = list(
            self._get_model().rerank(
                normalized_query,
                normalized_documents,
            )
        )

        if len(scores) != len(normalized_documents):
            raise RuntimeError("Reranker 返回的分数数量不匹配")

        return [float(score) for score in scores]
