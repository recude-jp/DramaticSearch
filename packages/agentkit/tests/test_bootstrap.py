from pathlib import Path

from agentkit import AppContext, Zone, bootstrap

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_bootstrap_dev_connects_to_db() -> None:
    ctx = bootstrap(Zone.DEV, app="agentkit-selftest", config_dir=REPO_ROOT / "ops" / "config")

    assert isinstance(ctx, AppContext)
    assert ctx.zone == Zone.DEV
    assert ctx.app == "agentkit-selftest"

    # bootstrap() 内で healthcheck 済みだが、Store がそのまま使えることも確認する。
    ctx.store.healthcheck()
