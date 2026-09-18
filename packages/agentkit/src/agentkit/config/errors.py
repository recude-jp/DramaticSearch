from __future__ import annotations


class ConfigError(Exception):
    """設定関連のエラーの基底クラス。"""


class ZoneConfigNotFound(ConfigError):
    """ゾーンに対応する設定ファイルが見つからない。"""


class ExternalModelBoundToZoneA(ConfigError):
    """区分Aの仮想キーに外部モデルが紐付けられている（I-4違反）。

    実行時ではなく起動時に検出し、起動そのものを拒否する。
    """
