from pathlib import Path

import pytest

from agentkit.config import ExternalModelBoundToZoneA, ZoneConfigNotFound, load_config
from agentkit.zone import Zone

FIXTURES = Path(__file__).parent / "fixtures" / "config"


def test_load_dev_config_from_repo() -> None:
    # リポジトリ実体の ops/config/dev.yaml が読めて、検証を通ることを確認する。
    repo_root = Path(__file__).resolve().parents[3]
    config = load_config(Zone.DEV, config_dir=repo_root / "ops" / "config")
    assert config.zone == "dev"
    assert config.allowed_classifications == ["C"]


def test_missing_config_raises() -> None:
    with pytest.raises(ZoneConfigNotFound):
        load_config(Zone.DEV, config_dir=FIXTURES / "does-not-exist")


def test_external_model_on_classification_a_is_rejected() -> None:
    with pytest.raises(ExternalModelBoundToZoneA):
        load_config(Zone.BIZ, config_dir=FIXTURES / "invalid")
