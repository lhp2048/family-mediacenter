"""Persisted TVBox test report queries."""

from __future__ import annotations

import json

from sqlalchemy import select

from app.db import async_session
from app.models.tvbox_test_report import (
    TvboxTestReportORM,
    TvboxTestReportResponse,
    TvboxTestReportSummary,
)


def _row_to_summary(row: TvboxTestReportORM) -> TvboxTestReportSummary:
    return TvboxTestReportSummary(
        id=row.id,
        source_id=row.source_id,
        mode=row.mode,
        ok=row.ok,
        score=row.score,
        grade=row.grade or "unknown",
        availability=row.availability or "unknown",
        message=row.message or "",
        created_at=row.created_at,
    )


async def get_latest_report(source_id: int) -> TvboxTestReportResponse | None:
    async with async_session() as session:
        result = await session.execute(
            select(TvboxTestReportORM)
            .where(TvboxTestReportORM.source_id == source_id)
            .order_by(TvboxTestReportORM.id.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None
        report: dict = {}
        if row.report_json:
            try:
                report = json.loads(row.report_json)
            except json.JSONDecodeError:
                report = {}
        return TvboxTestReportResponse(
            id=row.id,
            source_id=row.source_id,
            run_id=row.run_id,
            mode=row.mode,
            ok=row.ok,
            score=row.score,
            grade=row.grade,
            availability=row.availability,
            message=row.message,
            report=report,
            created_at=row.created_at,
        )


async def list_report_history(
    source_id: int,
    *,
    limit: int = 30,
) -> list[TvboxTestReportSummary]:
    cap = max(1, min(int(limit), 100))
    async with async_session() as session:
        result = await session.execute(
            select(TvboxTestReportORM)
            .where(TvboxTestReportORM.source_id == source_id)
            .order_by(TvboxTestReportORM.id.desc())
            .limit(cap)
        )
        rows = list(result.scalars().all())
    return [_row_to_summary(row) for row in reversed(rows)]
