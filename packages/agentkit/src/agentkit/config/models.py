"""ゾーンごとの設定スキーマ。

このモジュールは「区分（Classification）」の値（A/B/C）を文字列として扱うだけで、
`agentkit.egress` の `Classification` 型そのものには依存しない（F1時点ではegressは未実装のため）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ClassificationLabel = Literal["A", "B", "C"]


class DbConfig(BaseModel):
    """DB接続設定。

    `dsn` はアプリ実行時が使う最小権限ロールの接続文字列。
    `migration_dsn` はマイグレーション実行者（スキーマ作成権限を持つロール）の接続文字列で、
    省略時はローカルのpeer認証（OSユーザー）にフォールバックする。
    """

    dsn: str
    migration_dsn: str | None = None
    schema_name: str = Field(default="agentkit", alias="schema")

    model_config = ConfigDict(populate_by_name=True)


class VirtualKeyConfig(BaseModel):
    classification: ClassificationLabel
    external_model: str | None = None


class LiteLLMConfig(BaseModel):
    virtual_keys: dict[str, VirtualKeyConfig] = Field(default_factory=dict)


class PhoenixConfig(BaseModel):
    project: str


class EffectsConfig(BaseModel):
    file_root: str


class ZoneConfig(BaseModel):
    zone: Literal["dev", "biz"]
    db: DbConfig
    litellm: LiteLLMConfig
    phoenix: PhoenixConfig
    effects: EffectsConfig
    allowed_classifications: list[ClassificationLabel]
