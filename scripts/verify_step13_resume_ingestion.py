# 使用真实 PostgreSQL 验证 PDF / DOCX / TXT 解析和简历版本持久化。

from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path
from uuid import uuid4

from docx import Document
from reportlab.pdfgen import canvas
from sqlalchemy import delete, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.event_loop import configure_event_loop_policy
from app.db.models import Resume, ResumeVersion, User
from app.db.session import async_session_factory
from app.repositories import ResumeRepository
from app.services.resume_file_parser import parse_resume_file
from app.services.resume_ingestion import persist_parsed_resume

configure_event_loop_policy()


def make_docx_bytes() -> bytes:
    document = Document()
    document.add_heading("技能", level=1)
    document.add_paragraph("Python、FastAPI、PostgreSQL")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf_bytes() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, "FastAPI backend RAG Agent")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


async def cleanup(user_id: int | None) -> None:
    if user_id is None:
        return

    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                delete(ResumeVersion).where(
                    ResumeVersion.resume_id.in_(
                        select(
                            Resume.resume_id
                        ).where(Resume.user_id == user_id)
                    )
                )
            )
            await session.execute(
                delete(Resume).where(Resume.user_id == user_id)
            )
            await session.execute(
                delete(User).where(User.user_id == user_id)
            )


async def main() -> None:
    user_id: int | None = None
    resume_id: int | None = None
    try:
        suffix = uuid4().hex[:12]
        async with async_session_factory() as session:
            async with session.begin():
                user = User(
                    username=f"step13_{suffix}",
                    email=f"step13_{suffix}@example.com",
                    role="user",
                    status="active",
                )
                session.add(user)
                await session.flush()
                user_id = user.user_id

        docx = parse_resume_file(
            filename="resume.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=make_docx_bytes(),
        )
        pdf = parse_resume_file(
            filename="resume.pdf",
            content_type="application/pdf",
            data=make_pdf_bytes(),
        )
        txt = parse_resume_file(
            filename="resume.txt",
            content_type="text/plain",
            data="Python Redis PostgreSQL".encode("utf-8"),
        )

        async with async_session_factory() as session:
            async with session.begin():
                first = await persist_parsed_resume(
                    session,
                    user_id=user_id,
                    parsed=docx,
                    title="STEP 13 验证简历",
                )
                resume_id = first.resume_id
                second = await persist_parsed_resume(
                    session,
                    user_id=user_id,
                    resume_id=resume_id,
                    parsed=pdf,
                )
                third = await persist_parsed_resume(
                    session,
                    user_id=user_id,
                    resume_id=resume_id,
                    parsed=txt,
                )
                resume = await ResumeRepository(session).get_for_user(
                    resume_id,
                    user_id,
                    with_versions=True,
                )

        assert resume is not None
        assert [item.source_type for item in resume.versions] == [
            "docx",
            "pdf",
            "txt",
        ]
        assert [item.version_no for item in resume.versions] == [1, 2, 3]
        assert second.version_no == 2
        assert third.version_no == 3

        print(
            json.dumps(
                {
                    "user_id": user_id,
                    "resume_id": resume_id,
                    "version_ids": [
                        first.resume_version_id,
                        second.resume_version_id,
                        third.resume_version_id,
                    ],
                    "source_types": [
                        item.source_type for item in resume.versions
                    ],
                    "version_count": len(resume.versions),
                    "cleanup_completed": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await cleanup(user_id)


if __name__ == "__main__":
    asyncio.run(main())
