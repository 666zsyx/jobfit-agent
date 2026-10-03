# 验证 RAG 工具优先路径、回退和报告引用校验。

import asyncio

from app.schemas.auth import CurrentUser
from app.schemas.evidence import (
    EvidenceItem,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    RequirementEvidence,
)
from app.schemas.knowledge import (
    EvidenceItem as KnowledgeEvidenceItem,
    EvidencePack,
)
from app.tools import ToolContext
from app.tools import jobfit


class FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeSessionFactory:
    def __call__(self):
        return FakeSessionContext()


def make_context(
    *,
    rag_enabled: bool = True,
    event_sink=None,
) -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=1,
            username="demo_user",
            role="admin",
        ),
        session_factory=FakeSessionFactory(),
        task_id=10,
        resume_version_id=1001,
        rag_enabled=rag_enabled,
        event_sink=event_sink,
    )


def make_search_result() -> EvidenceSearchResult:
    return EvidenceSearchResult(
        requirements=["熟悉 Python"],
        matches=[
            RequirementEvidence(
                requirement="熟悉 Python",
                evidence=[
                    EvidenceItem(
                        section_type="skills",
                        title="技能",
                        content="Python",
                        score=0.9,
                        chunk_id=101,
                        source_version_id=1001,
                        position=1,
                        rerank_score=2.2,
                    )
                ],
            )
        ],
    )


def make_evidence_pack() -> EvidencePack:
    return EvidencePack(
        requirement="熟悉 Python",
        items=[
            KnowledgeEvidenceItem(
                chunk_id=101,
                user_id=1,
                resume_version_id=1001,
                section_type="skills",
                title="技能",
                content="Python",
                content_hash="a" * 64,
                position=1,
                start_offset=0,
                end_offset=6,
                chunker_version="v1",
                relevance_score=2.2,
                rank=1,
            )
        ],
        rerank_applied=True,
    )


def test_rag_search_handler_uses_hybrid_pipeline(monkeypatch):
    calls = []
    events = []

    async def fake_search_requirements_with_rag(
        session,
        *,
        user_id,
        resume_version_id,
        requirements,
    ):
        calls.append((user_id, resume_version_id, requirements))
        return make_search_result(), [make_evidence_pack()]

    async def fake_event_sink(event):
        events.append(event)

    monkeypatch.setattr(
        jobfit,
        "search_requirements_with_rag",
        fake_search_requirements_with_rag,
    )
    context = make_context(event_sink=fake_event_sink)

    result = asyncio.run(
        jobfit.search_resume_evidence_handler(
            EvidenceSearchRequest(requirements=["熟悉 Python"]),
            context,
        )
    )

    assert result["requirements"] == ["熟悉 Python"]
    assert len(context.retrieved_evidence_packs) == 1
    assert calls == [(1, 1001, ["熟悉 Python"])]
    assert [event.type for event in events] == [
        "retrieval_started",
        "retrieval_finished",
    ]


def test_rag_search_failure_falls_back_to_legacy(monkeypatch):
    legacy_calls = []

    async def fake_search_requirements_with_rag(*args, **kwargs):
        raise RuntimeError("vector backend failed")

    def fake_legacy_search(*, requirements, sections):
        legacy_calls.append((requirements, sections))
        return make_search_result()

    monkeypatch.setattr(
        jobfit,
        "search_requirements_with_rag",
        fake_search_requirements_with_rag,
    )
    monkeypatch.setattr(
        jobfit,
        "search_resume_evidence",
        fake_legacy_search,
    )

    context = make_context()
    context.resume_profile_snapshot = {
        "extracted_sections": {
            "sections": [
                {
                    "section_type": "skills",
                    "title": "技能",
                    "content": "Python",
                }
            ]
        }
    }
    result = asyncio.run(
        jobfit.search_resume_evidence_handler(
            EvidenceSearchRequest(requirements=["熟悉 Python"]),
            context,
        )
    )

    assert result["requirements"] == ["熟悉 Python"]
    assert len(legacy_calls) == 1


def test_report_citations_accept_known_chunk_id():
    context = make_context()
    context.retrieved_evidence_packs.append(make_evidence_pack())
    context.defer_report_save = True

    result = asyncio.run(
        jobfit.save_match_report_handler(
            jobfit.SaveMatchReportArgs(
                summary="总结",
                result_json={"evidence": [{"chunk_id": 101}]},
            ),
            context,
        )
    )

    assert result == {"saved": True, "queued": True}


def test_report_citations_reject_missing_or_unknown_chunk_id():
    context = make_context()
    context.retrieved_evidence_packs.append(make_evidence_pack())
    context.defer_report_save = True

    missing = asyncio.run(
        jobfit.save_match_report_handler(
            jobfit.SaveMatchReportArgs(
                summary="总结",
                result_json={"evidence": []},
            ),
            context,
        )
    )
    unknown = asyncio.run(
        jobfit.save_match_report_handler(
            jobfit.SaveMatchReportArgs(
                summary="总结",
                result_json={"chunk_ids": [999]},
            ),
            context,
        )
    )

    assert missing == {
        "saved": False,
        "error": "报告缺少证据引用",
    }
    assert unknown["saved"] is False
    assert "未知证据" in unknown["error"]
