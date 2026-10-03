# 定义可替换的向量索引接口和 Chroma 持久化实现。

from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

import chromadb


@dataclass(frozen=True)
class VectorRecord:
    chunk_id: int
    vector: list[float]
    metadata: dict[str, str | int]


@dataclass(frozen=True)
class VectorQueryHit:
    chunk_id: int
    similarity: float
    rank: int


class VectorIndex(Protocol):
    """向量索引后端接口。"""

    @property
    def model_name(self) -> str:
        ...

    @property
    def dimension(self) -> int:
        ...

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        ...

    def query(
        self,
        *,
        user_id: int,
        resume_version_id: int,
        query_vector: list[float],
        top_k: int,
    ) -> list[VectorQueryHit]:
        ...

    def delete_resume_version(
        self,
        *,
        user_id: int,
        resume_version_id: int,
    ) -> int:
        ...


class ChromaVectorIndex:
    """使用本地 Chroma 持久化向量。"""

    def __init__(
        self,
        *,
        path: str,
        collection_name: str,
        model_name: str,
        dimension: int,
    ) -> None:
        if dimension < 1:
            raise ValueError("dimension 必须大于等于 1")

        self._model_name = model_name
        self._dimension = dimension
        self._lock = Lock()
        self._client = chromadb.PersistentClient(path=path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": model_name,
                "dimension": dimension,
            },
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _validate_vector(self, vector: Sequence[float]) -> None:
        if len(vector) != self._dimension:
            raise ValueError(
                f"向量维度不匹配: expected={self._dimension} "
                f"actual={len(vector)}"
            )

    @staticmethod
    def _resume_filter(
        user_id: int,
        resume_version_id: int,
    ) -> dict:
        return {
            "$and": [
                {"user_id": {"$eq": user_id}},
                {
                    "resume_version_id": {
                        "$eq": resume_version_id,
                    }
                },
            ]
        }

    def upsert(self, records: Sequence[VectorRecord]) -> int:
        if not records:
            return 0

        ids: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict] = []

        for record in records:
            self._validate_vector(record.vector)
            ids.append(str(record.chunk_id))
            embeddings.append(record.vector)
            metadatas.append(record.metadata)

        with self._lock:
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
            )

        return len(records)

    def query(
        self,
        *,
        user_id: int,
        resume_version_id: int,
        query_vector: list[float],
        top_k: int,
    ) -> list[VectorQueryHit]:
        self._validate_vector(query_vector)

        if top_k < 1:
            raise ValueError("top_k 必须大于等于 1")

        with self._lock:
            result = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=self._resume_filter(user_id, resume_version_id),
                include=["metadatas", "distances"],
            )

        ids = result.get("ids") or [[]]
        distances = result.get("distances") or [[]]

        hits: list[VectorQueryHit] = []

        for rank, (chunk_id, distance) in enumerate(
            zip(ids[0], distances[0], strict=False),
            start=1,
        ):
            similarity = max(-1.0, min(1.0, 1.0 - float(distance)))
            hits.append(
                VectorQueryHit(
                    chunk_id=int(chunk_id),
                    similarity=similarity,
                    rank=rank,
                )
            )

        return hits

    def delete_resume_version(
        self,
        *,
        user_id: int,
        resume_version_id: int,
    ) -> int:
        with self._lock:
            existing = self._collection.get(
                where=self._resume_filter(user_id, resume_version_id),
                include=[],
            )
            ids = existing.get("ids") or []
            count = len(ids)

            if count:
                self._collection.delete(
                    where=self._resume_filter(
                        user_id,
                        resume_version_id,
                    )
                )

        return count
