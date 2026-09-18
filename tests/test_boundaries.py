"""境界の機械的検査（FRAMEWORK-SPEC 13節）。

F1時点では `packages/agentkit` と `apps/**` の実体がまだ揃っていないため、
現時点で意味のある検査（1・2・3・5相当）だけを実装する。
`Effect` に関する検査（4）は `agentkit.effects` の実装（F5）に合わせて追加する。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTKIT_SRC = REPO_ROOT / "packages" / "agentkit" / "src"
APPS_DIR = REPO_ROOT / "apps"

FORBIDDEN_WORDS = ("馬", "レース", "牧場", "騎手", "note", "JRA", "請求書", "horse", "race")

FORBIDDEN_IMPORTS = ("litellm", "openai", "anthropic", "psycopg", "boto3", "sqlalchemy")


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_agentkit_has_no_domain_words() -> None:
    offenders: list[str] = []
    for path in _python_files(AGENTKIT_SRC):
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN_WORDS:
            if word in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {word!r}")
    assert not offenders, "agentkit にドメイン語が含まれている:\n" + "\n".join(offenders)


def _imported_module_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_apps_do_not_import_provider_or_driver_libs_directly() -> None:
    offenders: list[str] = []
    for path in _python_files(APPS_DIR):
        hit = _imported_module_roots(path) & set(FORBIDDEN_IMPORTS)
        if hit:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {sorted(hit)}")
    message = "apps/** が直接importしてはいけないライブラリをimportしている:\n"
    assert not offenders, message + "\n".join(offenders)


def test_agentkit_does_not_import_apps() -> None:
    offenders: list[str] = []
    for path in _python_files(AGENTKIT_SRC):
        roots = _imported_module_roots(path)
        if "apps" in roots or "hoofprints" in roots:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, "agentkit が apps/** に依存している:\n" + "\n".join(offenders)


def test_zone_a_virtual_key_with_external_model_is_rejected_at_load() -> None:
    from agentkit.config import ExternalModelBoundToZoneA, load_config
    from agentkit.zone import Zone

    fixture_dir = REPO_ROOT / "packages" / "agentkit" / "tests" / "fixtures" / "config" / "invalid"
    with pytest.raises(ExternalModelBoundToZoneA):
        load_config(Zone.BIZ, config_dir=fixture_dir)
