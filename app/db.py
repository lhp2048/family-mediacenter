from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import DB_PATH, DATA_DIR


class Base(DeclarativeBase):
    pass


DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    f"sqlite+aiosqlite:///{DB_PATH.as_posix()}",
    echo=False,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from app.models.playlist import PlaylistItemORM, PlaylistORM  # noqa: F401
    from app.models.task import TaskORM  # noqa: F401
    from app.models.tvbox_source import TvboxSourceORM  # noqa: F401
    from app.models.tvbox_test_report import TvboxTestReportORM, TvboxTestRunORM  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_tvbox_columns)


def _migrate_tvbox_columns(sync_conn) -> None:
    import sqlalchemy as sa

    insp = sa.inspect(sync_conn)
    if insp.has_table("tvbox_sources"):
        columns = {col["name"] for col in insp.get_columns("tvbox_sources")}
        if "last_test_detail" not in columns:
            sync_conn.execute(
                sa.text("ALTER TABLE tvbox_sources ADD COLUMN last_test_detail TEXT DEFAULT ''")
            )
        if "last_test_score" not in columns:
            sync_conn.execute(
                sa.text("ALTER TABLE tvbox_sources ADD COLUMN last_test_score INTEGER")
            )
        if "last_test_grade" not in columns:
            sync_conn.execute(
                sa.text("ALTER TABLE tvbox_sources ADD COLUMN last_test_grade TEXT DEFAULT ''")
            )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
