from agentkit.zone import Zone


def test_zone_values() -> None:
    assert Zone.DEV == "dev"
    assert Zone.BIZ == "biz"
