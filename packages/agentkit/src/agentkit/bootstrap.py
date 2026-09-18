from __future__ import annotations

from pathlib import Path

from agentkit.config import DEFAULT_CONFIG_DIR, load_config
from agentkit.context import AppContext
from agentkit.store import build_store
from agentkit.zone import Zone


def bootstrap(zone: Zone, *, app: str, config_dir: Path | str = DEFAULT_CONFIG_DIR) -> AppContext:
    """アプリの唯一のエントリポイント。

    ゾーンの設定を読み込み、検証し（I-4）、DBへの接続を確立して疎通を確認する。
    """
    config = load_config(zone, config_dir=config_dir)
    store = build_store(config.db.dsn)
    store.healthcheck()
    return AppContext(zone=zone, app=app, config=config, store=store)
