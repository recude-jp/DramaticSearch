"""agentkitが所有するテーブルのための共有メタデータ。

`apps/**` のテーブルとスキーマを分けるため、agentkit所有のテーブルは
すべてこの `metadata`（スキーマ固定）に紐付けて宣言する。
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

AGENTKIT_SCHEMA = "agentkit"

metadata = MetaData(schema=AGENTKIT_SCHEMA)


class Base(DeclarativeBase):
    metadata = metadata
