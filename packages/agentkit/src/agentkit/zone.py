"""ゾーン定義。

ゾーンは呼び出し側が `bootstrap()` に明示的に渡す値でなければならない。
環境変数から自動的に読み取らないこと（設定ミスによる事故切り替えを防ぐため）。
"""

from __future__ import annotations

from enum import StrEnum


class Zone(StrEnum):
    DEV = "dev"
    BIZ = "biz"
