from pathlib import Path

import pytest

from hoofprints.cli import main

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_doctor_connects_to_dev_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(REPO_ROOT)
    with pytest.raises(SystemExit) as excinfo:
        main(["doctor", "--zone", "dev"])
    assert excinfo.value.code == 0
