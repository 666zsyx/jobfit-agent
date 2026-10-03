# 定义可替换的 EmbeddingProvider 和 FastEmbed 实现。

from collections.abc import Sequence
from threading import Lock
from typing import Protocol

from fastembed import TextEmbedding


class EmbeddingProvider(Protocol):
    """文本向量化接口。"""

    @property
    def model_name(self) -> str:
        ...

    @property
    def dimension(self) -> int:
        ...

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class FastEmbedEmbeddingProvider:
    """使用本地 ONNX 模型的 EmbeddingProvider。"""

    def __init__(
        self,
        *,
        model_name: str,
        cache_dir: str,
    ) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model: TextEmbedding | None = None
        self._model_lock = Lock()
        self._dimension = self._resolve_dimension(model_name)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @staticmethod
    def _resolve_dimension(model_name: str) -> int:
        for model_info in TextEmbedding.list_supported_models():
            if model_info["model"] == model_name:
                return int(model_info["dim"])

        raise ValueError(f"FastEmbed 不支持模型: {model_name}")

    def _get_model(self) -> TextEmbedding:
        if self._model is not None:
            return self._model

        with self._model_lock:
            if self._model is None:
                self._model = TextEmbedding(
                    model_name=self._model_name,
                    cache_dir=self._cache_dir,
                )

        return self._model

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        normalized_texts = [text.strip() for text in texts]

        if not normalized_texts:
            raise ValueError("texts 不能为空")

        if any(not text for text in normalized_texts):
            raise ValueError("待向量化文本不能为空")

        embeddings = self._get_model().embed(normalized_texts)
        return [embedding.tolist() for embedding in embeddings]

    def embed_query(self, text: str) -> list[float]:
        normalized = text.strip()

        if not normalized:
            raise ValueError("查询文本不能为空")

        return self.embed_documents([normalized])[0]
