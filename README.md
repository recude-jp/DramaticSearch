# Dramitic Search with recude-agents

汎用エージェント基盤 **agentkit** と、その上で動く競馬ドラマ生成サービス **hoofprints** を
1つの uv workspace に収めたモノレポ。

```
packages/agentkit/   汎用基盤。ドメイン（競馬）を知らない
apps/hoofprints/      hoofprints アプリ本体（agentkit を AppContext 経由で利用）
docs/                 FRAMEWORK-SPEC.md / APPLICATION-SPEC.md
tests/test_boundaries.py  agentkit ⇔ apps の境界を機械的に検査
```

開発規約・境界ルール（R1〜R10）・実装順序は [`CLAUDE.md`](./CLAUDE.md) を参照。

## セットアップ

```bash
uv sync --all-packages
```

PostgreSQL 16（pgvector）と Redis が必要。`ops/config/dev.yaml` は
`dev_app` によるローカル peer/trust 接続を前提とする。

## 動作確認

```bash
uv run pytest                              # 全テスト
uv run pytest tests/test_boundaries.py     # 境界検査のみ
uv run ruff check . && uv run ruff format .
uv run mypy packages/agentkit/src          # agentkit は strict

uv run hoofprints doctor --zone dev        # bootstrap() が実DBに接続できるか確認
```

## ドキュメント

- [`docs/FRAMEWORK-SPEC.md`](./docs/FRAMEWORK-SPEC.md) — agentkit の仕様
- [`docs/APPLICATION-SPEC.md`](./docs/APPLICATION-SPEC.md) — hoofprints の仕様
