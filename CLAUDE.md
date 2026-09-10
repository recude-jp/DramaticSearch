# cetacea-agents — 開発規約

このリポジトリは **汎用エージェント基盤（framework）** と **その上に載るアプリケーション** を
1つのモノレポに置く。境界を維持することがこのリポジトリの主目的なので、
以下の規則は「好み」ではなく **CI が機械的に強制する制約** である。

仕様書:
- `docs/FRAMEWORK-SPEC.md` — agentkit（基盤）
- `docs/APPLICATION-SPEC.md` — hoofprints（競馬ドラマサービス）

---

## 1. 構成

```
cetacea-agents/
├── CLAUDE.md
├── pyproject.toml                # uv workspace のルート
├── docs/
│   ├── FRAMEWORK-SPEC.md
│   └── APPLICATION-SPEC.md
├── packages/
│   └── agentkit/                 # 汎用基盤。ドメインを知らない
│       ├── pyproject.toml
│       ├── src/agentkit/
│       │   ├── zone.py  config/  store/
│       │   ├── egress/           # 送出ゲート（区分A/B/C）
│       │   ├── models/           # LiteLLM ラッパ
│       │   ├── ledger/           # sources / claims
│       │   ├── approval/         # 承認ゲート（+ 最小Web UI）
│       │   ├── effects/          # 外部作用アダプタ
│       │   ├── graph/            # LangGraph 規約
│       │   ├── obs/  queue/
│       │   └── migrations/       # agentkit スキーマ
│       └── tests/
├── apps/
│   └── hoofprints/               # 競馬ドラマサービス
│       ├── pyproject.toml
│       ├── src/hoofprints/
│       │   ├── domain/           # horses / people / farms / races
│       │   ├── archetypes/       # *.yaml
│       │   ├── story/            # Canonical Story スキーマ
│       │   ├── nodes/            # scout, researcher, ... publisher
│       │   ├── prompts/          # *.md（style.md を含む）
│       │   ├── adapters/         # 媒体アダプタ（変換のみ）
│       │   └── migrations/       # hoofprints スキーマ
│       ├── web/                  # Next.js SSG（入力は content/stories/*.json）
│       └── tests/
├── ops/
│   ├── launchd/                  # plist
│   ├── config/                   # dev.yaml / biz.yaml（秘密は SOPS）
│   └── ci/
└── tests/
    └── test_boundaries.py        # ★境界の機械的検査
```

---

## 2. 絶対に破らない規則

CI で検査する。**違反したまま先に進まないこと。**

| # | 規則 |
|---|---|
| **R1** | `packages/agentkit/**` にドメイン語（`馬` `レース` `牧場` `騎手` `note` `JRA` `請求書` `horse` `race`）を書かない |
| **R2** | `apps/**` から `litellm` `openai` `anthropic` `psycopg` `boto3` `sqlalchemy` を直接 import しない。全て `AppContext` 経由 |
| **R3** | `packages/agentkit` は `apps/**` を import しない（依存は一方通行） |
| **R4** | 出典を持たない主張を `Ledger` に登録しない。`record_claim()` は `source_ids` 空を例外にする |
| **R5** | 承認を要する `Effect` を `approval_id` なしで実行できるようにしない |
| **R6** | 区分Aの仮想キーに外部モデルを紐付けない。設定にあれば起動時に落とす |
| **R7** | 本番AWSへの書き込み資格情報をこのリポジトリにも実行環境にも置かない。デプロイは CI（OIDC）のみ |
| **R8** | 平文の秘密をコミットしない。SOPS/age か macOS Keychain |
| **R9** | LangGraph の状態を dict で扱わない。Pydantic モデルのみ |
| **R10** | 外部への送出は必ず `purpose` を指定する（監査ログが読めなくなる） |

### 判断に迷ったときの基準

- **「この機能は請求書処理アプリでも使うか？」** — Yes なら agentkit、No なら apps
- **「これは規約や設定か、それとも論理か」** — 規約・設定は DB か YAML。コードに埋めない
- **「失敗したとき、誰が気づくか」** — 誰も気づかないなら、そもそも自動化しない

---

## 3. スタック

- Python 3.12+ / `uv` workspace / `ruff` / `mypy`（strict は agentkit のみ）/ `pytest`
- PostgreSQL 16 + pgvector（Homebrew ネイティブ）/ Redis
- LangGraph（PostgresSaver）/ LiteLLM / FastAPI
- Next.js（SSG）は `apps/hoofprints/web/` のみ。**Python と TS の結合点は
  `content/stories/*.json` の1箇所に限る**

---

## 4. コマンド

```bash
uv sync --all-packages                     # 依存
uv run pytest                              # 全テスト
uv run pytest tests/test_boundaries.py     # 境界検査だけ
uv run ruff check . && uv run ruff format .
uv run mypy packages/agentkit/src

uv run alembic -c packages/agentkit/alembic.ini upgrade head
uv run alembic -c apps/hoofprints/alembic.ini upgrade head

uv run agentkit-approval                   # 承認UI（Tailscale 経由でのみ到達）
uv run hoofprints scout --date 2026-09-13  # 候補抽出
uv run hoofprints run --candidate <id>     # グラフ実行（HumanGate で止まる）

cd apps/hoofprints/web && npm run build    # SSG（デプロイは CI）
```

---

## 5. 作業の進め方

### 実装順序（この順で作る）

**agentkit**: F1 基盤 → F2 区分C送出＋計装 → F3 台帳 → F4 グラフ＋承認 → F5 作用 → F6 区分B → F7 区分A
**hoofprints**: P0 人間が3本書く → P1 Scout/Researcher/FactLedger → P2 Writer/Verifier/承認/公開 → P3 区分B・媒体追加 → P4 定期実行

**F2 まで出来れば P1 を始められる。最初から全部作らない。**

### 新しい作業を始めるとき

1. 該当する仕様書の節を読む（`docs/FRAMEWORK-SPEC.md` / `docs/APPLICATION-SPEC.md`）
2. 受け入れテスト（APPLICATION-SPEC 8節）に対応するテストを**先に**書く
3. 実装する
4. `uv run pytest tests/test_boundaries.py` を通す
5. 仕様と実装がずれたら、**コードではなく仕様書を直す**。仕様書が古くなったリポジトリは境界を失う

### やらないこと

- マルチエージェントの自律的協調（分岐は明示的な条件エッジで書く）
- 専用ベクトルDBの導入（pgvector で足りるうちは運用対象を増やさない）
- ファインチューニング（精度問題はほぼプロンプトと検索精度の問題）
- 無人での外部発信（投稿・送信は承認を挟む）
- デプロイのエージェント実行（コマンド組み立てまでは可、実行は CI か人間）

---

## 6. テスト方針

- `agentkit` は**契約のテスト**を厚くする。R4・R5・R6 は「破ろうとすると例外になる」ことを直接テストする
- `hoofprints` は**受け入れテスト**（APPLICATION-SPEC 8節 A1〜A10）を基準にする
- 外部APIはテストで呼ばない。`EgressGate` のフェイク実装を `agentkit.testing` に置く
- **A9（マスキングの取りこぼし）だけは実データで確認する。** 合成データでは見つからない

---

## 7. コミット

- 1コミット = 1つの意味のある変更。仕様書の更新は同じコミットに含める
- 境界検査が落ちるコミットは作らない
- コミットメッセージ末尾:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

---

## 8. 参照

- プラットフォーム設計: プロジェクトドキュメント `claude/platform-architecture.md`（rev.3）
- 設計判断の記録: `claude/architecture-decisions.md`
- サービス設計: `claude/keiba-drama-service-design.md`
