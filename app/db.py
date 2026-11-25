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
    from app.models.material_share import MaterialShareORM  # noqa: F401
    from app.models.playlist import PlaylistItemORM, PlaylistORM  # noqa: F401
    from app.models.share_read import ShareReadORM, ShareReadVisitORM  # noqa: F401
    from app.models.share_watch import (  # noqa: F401
        ShareDeviceORM,
        ShareEyeCareORM,
        SharePlaybackORM,
        ShareVisitORM,
    )
    from app.models.task import TaskORM  # noqa: F401
    from app.models.tvbox_source import TvboxSourceORM  # noqa: F401
    from app.models.tvbox_test_report import TvboxTestReportORM, TvboxTestRunORM  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_tvbox_columns)
        await conn.run_sync(_migrate_playlist_share_columns)
        await conn.run_sync(_migrate_playlist_item_share_hide)
        await conn.run_sync(_migrate_share_eye_columns)


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


def _migrate_playlist_share_columns(sync_conn) -> None:
    import sqlalchemy as sa

    insp = sa.inspect(sync_conn)
    if not insp.has_table("playlists"):
        return
    columns = {col["name"] for col in insp.get_columns("playlists")}
    alters = [
        ("share_token", "ALTER TABLE playlists ADD COLUMN share_token VARCHAR(64)"),
        ("share_enabled", "ALTER TABLE playlists ADD COLUMN share_enabled BOOLEAN DEFAULT 0"),
        ("share_last_item_id", "ALTER TABLE playlists ADD COLUMN share_last_item_id INTEGER"),
        (
            "share_position_sec",
            "ALTER TABLE playlists ADD COLUMN share_position_sec FLOAT DEFAULT 0",
        ),
        ("share_updated_at", "ALTER TABLE playlists ADD COLUMN share_updated_at DATETIME"),
        ("share_autoplay", "ALTER TABLE playlists ADD COLUMN share_autoplay BOOLEAN DEFAULT 0"),
        (
            "share_hide_completed",
            "ALTER TABLE playlists ADD COLUMN share_hide_completed BOOLEAN DEFAULT 0",
        ),
        (
            "share_hide_after",
            "ALTER TABLE playlists ADD COLUMN share_hide_after INTEGER DEFAULT 1",
        ),
    ]
    for name, sql in alters:
        if name not in columns:
            sync_conn.execute(sa.text(sql))
    # Unique index for share_token (ignore if already exists)
    try:
        sync_conn.execute(
            sa.text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_playlists_share_token "
                "ON playlists (share_token)"
            )
        )
    except Exception:
        pass


def _migrate_playlist_item_share_hide(sync_conn) -> None:
    import sqlalchemy as sa

    insp = sa.inspect(sync_conn)
    if not insp.has_table("playlist_items"):
        return
    columns = {col["name"] for col in insp.get_columns("playlist_items")}
    if "share_hidden_on" not in columns:
        sync_conn.execute(
            sa.text("ALTER TABLE playlist_items ADD COLUMN share_hidden_on VARCHAR(10)")
        )


def _migrate_share_eye_columns(sync_conn) -> None:
    import sqlalchemy as sa

    insp = sa.inspect(sync_conn)
    if not insp.has_table("share_devices"):
        return
    columns = {col["name"] for col in insp.get_columns("share_devices")}
    alters = [
        ("eye_watched_sec", "ALTER TABLE share_devices ADD COLUMN eye_watched_sec FLOAT DEFAULT 0"),
        ("eye_last_play_at", "ALTER TABLE share_devices ADD COLUMN eye_last_play_at DATETIME"),
        ("eye_locked_until", "ALTER TABLE share_devices ADD COLUMN eye_locked_until DATETIME"),
    ]
    for name, sql in alters:
        if name not in columns:
            sync_conn.execute(sa.text(sql))


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
