"""アプリから見える唯一の入口。

F1時点では `zone` / `config` / `store` のみを持つ。
`gate`（F2）・`ledger`（F3）・`approval`（F4）・`effects`（F5）・`graph`（F4）は、
それぞれのモジュールが実装され次第この型に追加する。存在しない機能を先取りしてダミーで
埋めない。
"""

from __future__ import annotations

from dataclasses import dataclass

from agentkit.config import ZoneConfig
from agentkit.store import Store
from agentkit.zone import Zone


@dataclass(frozen=True)
class AppContext:
    zone: Zone
    app: str
    config: ZoneConfig
    store: Store
