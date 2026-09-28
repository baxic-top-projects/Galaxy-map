from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config.settings import settings


class Base(DeclarativeBase):
    pass


class SystemRow(Base):
    """Indexed system row + full detail document for the system view."""

    __tablename__ = "systems"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    stem: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name_en: Mapped[str] = mapped_column(String(512), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(512), nullable=False)
    star_type_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    sector_id: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    capital: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    z: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    world_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shard: Mapped[str] = mapped_column(String(512), nullable=False, default="", index=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class PolityRow(Base):
    __tablename__ = "polities"

    stem: Mapped[str] = mapped_column(String(255), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class EdgeRow(Base):
    __tablename__ = "edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    a: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    b: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    graph: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # canon | display


class SearchEntryRow(Base):
    __tablename__ = "search_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class GalaxyMetaRow(Base):
    __tablename__ = "galaxy_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
    # Fail fast instead of hanging startup/health checks on an unreachable DB.
    connect_args={"connect_timeout": 10},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
