from __future__ import annotations

from pathlib import Path

import yaml

from agentkit.zone import Zone

from .errors import ExternalModelBoundToZoneA, ZoneConfigNotFound
from .models import ZoneConfig

DEFAULT_CONFIG_DIR = Path("ops/config")


def load_config(zone: Zone, *, config_dir: Path | str = DEFAULT_CONFIG_DIR) -> ZoneConfig:
    """ゾーンの設定ファイル（`<config_dir>/<zone>.yaml`）を読み込み、検証する。

    I-4: 区分Aの仮想キーに外部モデルが紐付いていたら、ここで起動を拒否する。
    """
    path = Path(config_dir) / f"{zone.value}.yaml"
    if not path.exists():
        raise ZoneConfigNotFound(f"zone config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    config = ZoneConfig.model_validate(raw)
    _reject_external_model_on_zone_a(config)
    return config


def _reject_external_model_on_zone_a(config: ZoneConfig) -> None:
    for key_name, virtual_key in config.litellm.virtual_keys.items():
        if virtual_key.classification == "A" and virtual_key.external_model is not None:
            raise ExternalModelBoundToZoneA(
                f"virtual key '{key_name}' is classification A "
                f"but has external_model={virtual_key.external_model!r}"
            )
