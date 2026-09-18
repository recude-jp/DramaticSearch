from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from agentkit.config import load_config
from agentkit.store import metadata
from agentkit.zone import Zone

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _resolve_dsn() -> str:
    """マイグレーション用DSNの決定順序。

    1. `-x dsn=...` で明示指定されたもの
    2. `-x zone=biz` などで選んだゾーンの `db.migration_dsn`
       （未指定ならローカルpeer認証にフォールバック）
    3. 既定は DEV ゾーン
    """
    x_args = context.get_x_argument(as_dictionary=True)
    if "dsn" in x_args:
        return x_args["dsn"]

    zone = Zone(x_args.get("zone", Zone.DEV.value))
    zone_config = load_config(zone)
    return zone_config.db.migration_dsn or zone_config.db.dsn


def run_migrations_offline() -> None:
    # alembic_version 自体は既定スキーマに置く。agentkit スキーマは migration 0001 が作るため、
    # ここで agentkit スキーマを前提にすると「スキーマがまだ無い状態でのバージョン記録」が
    # 成立しなくなる（鶏と卵）。
    context.configure(
        url=_resolve_dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_resolve_dsn())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
