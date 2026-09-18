from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class Store:
    """アプリ実行時のDB接続一式。最小権限ロール（例: `dev_app`）で接続する。"""

    engine: Engine
    session_factory: sessionmaker[Session]

    def healthcheck(self) -> None:
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))


def build_store(dsn: str) -> Store:
    engine = create_engine(dsn, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return Store(engine=engine, session_factory=session_factory)
