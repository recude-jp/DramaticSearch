# agentkit — フレームワーク仕様 v0.1

2026-09-09 / パッケージ: `packages/agentkit` / Python 3.12+

`claude/platform-architecture.md`（rev.3）で定めた機構を、**サービスに依存しない形で1回だけ実装する**層。
最初の利用者は競馬ドラマサービス（`apps/hoofprints`）だが、次に来る業務自動化アプリでもそのまま使えることを要件とする。

---

## 0. このフレームワークが引き受けること

| 引き受ける | 引き受けない |
|---|---|
| 外部LLMへの送出の制御（区分A/B/C・マスキング・監査） | プロンプトの内容 |
| 証跡（出典と主張）の記録と、出典なし主張の拒否 | 何が「良い主張」か |
| 人間承認の状態機械と記録 | 承認画面に何を並べるか（アプリが組み立てる） |
| 外部作用（投稿・送信・書き込み）の実行制御 | どの媒体に何を出すか |
| グラフ実行・中断・再開・トレース | ノードの中身 |
| ゾーンによる接続先・権限の切り替え | ドメインモデル |

**判定の目安**: `agentkit` のコードに「馬」「レース」「note」「請求書」といった語が現れたら、それは境界の誤りである。
この判定は CI で機械的に行う（8節）。

---

## 1. 中核となる4つの不変条件

実装が守るべき契約。すべてテストで固定し、破れないようにする。

| # | 不変条件 | 強制方法 |
|---|---|---|
| **I-1** | **アプリケーションは LLM プロバイダを直接呼べない。外部への推論要求は必ず `EgressGate` を通る** | アプリ側から `litellm` / `openai` / `boto3.client("bedrock*")` を import したら CI で失敗 |
| **I-2** | **出典を持たない主張は台帳に登録できない** | `Ledger.record_claim()` が `source_ids` 空で `ClaimWithoutSource` を送出 |
| **I-3** | **承認を要する外部作用は、有効な承認IDなしに実行できない** | `Effect.execute()` が `approval_id` を必須引数に取り、状態を検証してから実行 |
| **I-4** | **区分Aの要求は、外部モデルが紐付いていない仮想キーにしか到達しない** | ルータ設定で区分Aキーに外部モデルを登録しない。設定の起動時検証で外部モデルがあれば起動拒否 |

I-1 と I-4 の組み合わせが「顧客情報は外に出さない」の実装であり、
I-2 と I-3 の組み合わせが「無人での外部発信をしない」の実装である。

---

## 2. モジュール構成

```
packages/agentkit/src/agentkit/
├── zone.py            # Zone enum とゾーン解決
├── config/            # 設定・シークレット
├── store/             # DB接続、マイグレーション基盤
├── egress/            # 送出ゲート  ★中核
│   ├── gate.py
│   ├── detectors/     # regex, ginza
│   ├── masker.py
│   ├── preflight.py
│   └── audit.py
├── models/            # LiteLLM ルータの薄いラッパ
├── ledger/            # sources / claims  ★中核
├── approval/          # 承認ゲート     ★中核
├── effects/           # 外部作用アダプタ ★中核
│   ├── base.py
│   ├── filewrite.py
│   ├── gitpush.py
│   ├── http.py
│   └── s3.py
├── graph/             # LangGraph 規約・checkpointer・interrupt
├── obs/               # Phoenix / OTel 計装
└── queue/             # ローカル推論の直列化（Redis）
```

---

## 3. ゾーン

```python
class Zone(StrEnum):
    DEV = "dev"   # 開発ゾーン。成果物は git push まで
    BIZ = "biz"   # 業務ゾーン。区分Aのデータを保持
```

アプリは起動時に自分のゾーンを宣言するだけで、以下が自動的に決まる。

| 決まるもの | DEV | BIZ |
|---|---|---|
| DB接続（DSNとロール） | 開発DB / `dev_app` | 業務DB / `biz_app`（暗号化ボリューム上） |
| LiteLLM 仮想キー | `dev-external` | `biz-a-local` / `biz-b-gated` |
| Phoenix プロジェクト | `dev` | `biz`（暗号化ボリューム上） |
| ファイル作用のルート | 開発用ルート | 業務用ルート |
| 許可される区分 | C のみ（Bは明示的な昇格が必要） | A / B |

**ゾーンは環境変数ではなく設定ファイルで固定する。** 環境変数だと事故で切り替わる。

```python
from agentkit import Zone, bootstrap
ctx = bootstrap(Zone.DEV, app="hoofprints")   # -> AppContext（gate, ledger, approval, effects, graph）
```

`AppContext` がアプリから見える唯一の入口。個別のモジュールを直接組み立てさせない。

---

## 4. 送出ゲート（`agentkit.egress`）

### 4.1 インターフェース

```python
class Classification(StrEnum):
    A = "A"   # ローカル固定。外部に出さない
    B = "B"   # マスクして外部へ。復元して返す
    C = "C"   # そのまま外部へ

class EgressGate(Protocol):
    def complete(
        self,
        req: LLMRequest,
        *,
        classification: Classification,
        purpose: str,          # 監査ログに残る。必須
        run_id: str | None = None,
    ) -> LLMResponse: ...
```

`purpose` を必須にしているのは、監査ログを後から読める形にするため。
「何のために外に出したか」が空欄の記録は、あとで誰も判断できない。

### 4.2 区分ごとの経路

```
区分C:  req ──────────────────────────────▶ router(dev-external) ──▶ 外部API
                                                                        │
                                            audit(送出全文) ◀───────────┘

区分B:  req ─▶ detect ─▶ mask ─▶ preflight ─▶ router(biz-b-gated) ──▶ 外部API
                 │         │         │                                  │
             MaskMap(PG) ──┘    再スキャンで残存検出 → 中断             │
                 │                                                      │
                 └────────── unmask ◀── audit(マスク後の全文) ◀─────────┘

区分A:  req ─────────────────────────────▶ router(biz-a-local) ──▶ ローカル8B
                                            （外部モデルは登録されていない）
```

### 4.3 検出器

```python
@dataclass(frozen=True)
class Span:
    start: int
    end: int
    label: str          # PERSON / ORG / EMAIL / PHONE / ACCOUNT / MONEY / ADDRESS
    confidence: float
    detector: str

class Detector(Protocol):
    name: str
    def detect(self, text: str) -> list[Span]: ...
```

同梱実装:

| 実装 | 対象 | 常駐 |
|---|---|---|
| `RegexDetector` | メール、電話、口座番号、金額、住所、マイナンバー形式 | する（軽量） |
| `GinzaNerDetector` | 人名、法人名、地名 | **する（約1GB）** |

**GiNZA を常駐させ、LLMベースの検出器を主力にしないのは、8Bがロードされていない状態でも
ゲートが機能する必要があるため**（プラットフォーム設計判断 5）。
検出器はリストで渡され、Span はマージされる（重複区間は広いほうを採る）。

### 4.4 マスクと復元

- 置換形式: `<PERSON_01>` `<ORG_02>` `<EMAIL_01>`。ラベル＋連番。
- 対応表は **リクエスト単位**で `egress_mask_map` に保存。**Mac miniから出ない。**
- 保持期間は設定（既定 30日）。期限切れは削除ジョブで消す。
- 復元時、応答に**未知のプレースホルダ**が含まれていたら `UnknownPlaceholder` を送出して異常扱いにする。
  外部モデルがプレースホルダを創作した、あるいは取り違えたということなので、黙って通さない。

### 4.5 送出前の再スキャン（preflight）

マスク後のテキストに対して、決定的な検出器（regex）をもう一度かける。
**残存があれば送出を中止し、`EgressBlocked` を送出する。** 自動で再マスクして通さない。

### 4.6 監査ログ

`egress_audit` に、区分・purpose・run_id・モデル・**実際に送出した本文（区分Bはマスク後）**・
トークン数・キャッシュヒット・所要時間・結果を残す。マスク前の原文は残さない（残すと監査ログが機密になる）。

### 4.7 限界の明記

マスキングは100%ではない。「先週退職した経理担当」のような文脈依存の特定はパターンで検出できない。
**区分Aは経路そのものを断つことで守る。マスキングは区分Bのための安全策であって、区分Aの代替ではない。**
この文はコードのdocstringにも書く。実装者が後で忘れるため。

---

## 5. 証跡台帳（`agentkit.ledger`）

出典のある主張だけを積み上げるための汎用機構。
記事の事実確認にも、請求書からの項目抽出の根拠にも同じものを使う。

```python
class SourceKind(StrEnum):
    WEB = "web"; DOCUMENT = "document"; INTERVIEW = "interview"; DATASET = "dataset"; HUMAN = "human"

@dataclass
class SourceInput:
    kind: SourceKind
    uri: str | None            # URL、ファイルパス、DB識別子
    title: str
    publisher: str | None
    accessed_at: datetime
    excerpt: str               # 根拠となる該当箇所。全文ではない
    license_note: str | None   # 引用可否・転載条件のメモ
    classification: Classification   # 取材メモは B

@dataclass
class ClaimInput:
    text: str                  # 1文1主張
    subject_ref: str           # アプリのドメインID（不透明文字列として扱う）
    source_ids: list[SourceId] # ★空は拒否（I-2）
    kind: str                  # アプリが定義。フレームワークは値を解釈しない
    confidence: float

class Ledger(Protocol):
    def record_source(self, s: SourceInput) -> SourceId: ...
    def record_claim(self, c: ClaimInput) -> ClaimId: ...          # 出典なしは ClaimWithoutSource
    def get_claims(self, subject_ref: str) -> list[Claim]: ...
    def find_similar_sources(self, text: str, k: int) -> list[Source]: ...
    def find_conflicts(self, c: ClaimInput) -> list[Claim]: ...    # 同一subjectの矛盾候補
```

- 埋め込みは `sources.embedding` / `claims.embedding`（pgvector）。埋め込みモデルはゾーン設定で決まる。
- `subject_ref` は**フレームワークにとって不透明な文字列**。ここにドメイン型を持ち込まないことが境界の要。
- `find_conflicts` は完全な矛盾検出ではなく候補提示。判定はアプリと人間が行う。

---

## 6. 承認ゲート（`agentkit.approval`）

```python
class Decision(StrEnum):
    APPROVE = "approve"; REVISE = "revise"; DISCARD = "discard"

@dataclass
class Check:                       # アプリが組み立てる機械チェックの結果
    name: str
    status: Literal["pass", "warn", "fail"]
    detail: str
    anchor: str | None             # 本文中の該当位置

@dataclass
class ApprovalItem:
    kind: str                      # アプリ定義（"story" など）
    run_id: str
    title: str
    previews: list[Preview]        # 媒体ごとのプレビュー（label, content_type, body）
    checks: list[Check]
    payload_ref: str               # 承認対象の実体への参照

class ApprovalGate(Protocol):
    def request(self, item: ApprovalItem) -> ApprovalId: ...
    def get(self, id: ApprovalId) -> Approval: ...
    def decide(self, id: ApprovalId, d: Decision, *, reason: str, actor: str) -> None: ...
    def is_approved(self, id: ApprovalId) -> bool: ...
```

- `reason` は APPROVE 以外で必須。差し戻しと破棄の理由が、プロンプト改善の唯一の一次データになる。
- すべての決定は `approval_events` に追記。更新はしない。
- **承認は失効する**（既定7日）。古い承認IDで作用を実行できないようにする。
- **`checks` の中身をフレームワークは解釈しない。** 何を検査するかはアプリの責任。
  フレームワークは「fail が1件でもあれば承認UIで公開ボタンを押せない」という規則だけを持つ。

### 承認UI

`agentkit.approval.web` に FastAPI の最小UIを同梱する（一覧・詳細・3ボタン）。
Tailscale 経由でのみ到達。**凝らない。** 見た目に時間を使うと承認そのものが後回しになる。

---

## 7. 外部作用（`agentkit.effects`）

グラフの外側に影響を与える操作をすべてここに集約する。

```python
class Effect(Protocol):
    name: str
    requires_approval: bool         # 既定 True
    zone: Zone

    def dry_run(self, payload: Mapping) -> EffectPreview: ...
    def execute(self, payload: Mapping, *, approval_id: ApprovalId | None) -> EffectResult: ...
```

`requires_approval=True` の Effect は、`approval_id` が None、失効、未承認、
または対象が一致しない場合に `ApprovalRequired` を送出する（I-3）。

同梱アダプタ:

| アダプタ | 内容 | 承認 |
|---|---|---|
| `FileWriteEffect` | ルート固定のファイル書き込み。ルート外は拒否 | 設定次第 |
| `GitPushEffect` | ブランチを切って commit & push。**本番へのデプロイはしない** | 要 |
| `HttpPostEffect` | 汎用POST。許可ホストのallowlist必須 | 要 |
| `S3PutEffect` | S3への配置。**読み取り専用プロファイルでは失敗する**ことを前提に設計 | 要 |

**同梱しないもの**: 本番AWSへの書き込み、メール送信、支払い。
本番デプロイは CI の仕事であり、エージェントの実行環境にデプロイ用資格情報を置かない
（プラットフォーム設計 6節）。`GitPushEffect` が push するところまでがフレームワークの責任範囲。

すべての実行は `effect_log` に記録（name, payload要約, approval_id, 結果, 所要時間）。

---

## 8. グラフ実行（`agentkit.graph`）

LangGraph の薄いラッパ。規約を固定するためだけに存在する。

- **状態は Pydantic モデル**。dict の生使用は禁止。
- **チェックポインタは PostgresSaver 固定**。中断・再開が要件のため。
- **ノードは AppContext を受け取る**。グローバル変数からの取得を禁止。
- **Human-in-the-loop は `agentkit.graph.human_gate(item)` で書く**。
  内部で `ApprovalGate.request()` → LangGraph `interrupt` → 再開時に決定を読む、までを1つにまとめる。
- 各ノードは自動的に OTel span になり、`run_id` で Phoenix のトレースに紐付く。

```python
graph = build_graph(
    ctx,
    nodes=[scout, researcher, fact_ledger, outliner, writer, verifier, human_gate_node, publisher],
    state=StoryState,
)
```

**マルチエージェントの自律的協調は提供しない。** 分岐は明示的な条件エッジで書く
（プラットフォーム設計 12節）。

---

## 9. 可観測性（`agentkit.obs`）

- OTel → Phoenix。ゾーン別プロジェクト。
- 全 LLM 呼び出しに、モデル・入出力トークン・**キャッシュ読みトークン**・コスト概算・区分・purpose を属性として付ける。
- `run_id` 単位でコストを集計するヘルパを提供する。
  「1本あたりいくらか」が即答できない状態で「APIが高い」という判断をしない、という運用のための実装。

---

## 10. 設定とシークレット（`agentkit.config`）

- `pydantic-settings` + YAML。ゾーンごとに1ファイル（`config/dev.yaml` / `config/biz.yaml`）。
- 秘密は macOS Keychain、または SOPS/age で暗号化して git 管理。**平文の秘密をリポジトリに置かない。**
- **起動時検証**: 区分Aの仮想キーに外部モデルが1つでも紐付いていたら起動を拒否する（I-4）。
  これは設定ミスで最も起きやすい事故なので、実行時ではなく起動時に落とす。

---

## 11. ローカル推論キュー（`agentkit.queue`）

ローカルモデルへの要求は Redis のリストで**直列化**する。
帯域律速のため並列化してもスループットは増えず、レイテンシだけ悪化するため
（プラットフォーム設計 7節）。8Bのロード／アンロードもこのキューの責任。

---

## 12. テーブル（フレームワーク所有）

`agentkit` は自分のマイグレーションを持つ。アプリのテーブルとはスキーマを分ける（`agentkit` スキーマ）。

| テーブル | 内容 |
|---|---|
| `egress_audit` | 送出記録。区分、purpose、送出本文（マスク後）、トークン、結果 |
| `egress_mask_map` | プレースホルダ対応表。リクエスト単位、期限付き |
| `sources` | 出典台帳（embedding付き） |
| `claims` | 主張台帳（embedding付き、source_ids必須） |
| `approvals` / `approval_events` | 承認要求と決定履歴 |
| `effect_log` | 外部作用の実行記録 |
| `runs` | グラフ実行。run_id、状態、コスト集計 |
| `checkpoints` | LangGraph PostgresSaver |

---

## 13. 境界の機械的検査

`tests/test_boundaries.py` と CI で以下を強制する。**これが分割を維持する唯一の現実的手段。**

1. `packages/agentkit/**` に禁止語（`馬` `レース` `note` `JRA` `請求書` `horse` `race`）が出現したら失敗
2. `apps/**` から `litellm` / `openai` / `anthropic` / `psycopg` / `boto3` の直接 import があれば失敗
3. `packages/agentkit` は `apps/**` を import しない（依存方向の一方通行）
4. `Effect` 実装で `requires_approval=True` かつ `approval_id` 検証のないものがあれば失敗
5. 区分Aキーに外部モデルが紐付いた設定を読み込ませて、起動が拒否されることを確認

---

## 14. 実装順序

| | 内容 | 完了判定 |
|---|---|---|
| **F1** | `zone` / `config` / `store` / `bootstrap` | `bootstrap(Zone.DEV)` が通り、DBに繋がる |
| **F2** | `models`（LiteLLMラッパ）＋ `egress` の区分Cのみ ＋ `obs` | 区分Cで外部APIを呼び、Phoenixにトークンとキャッシュ率が出る |
| **F3** | `ledger` | 出典なし主張が例外で拒否される。類似検索が動く |
| **F4** | `graph` ＋ `approval` ＋ 承認UI | 中断して数日後に再開し、承認で先へ進む |
| **F5** | `effects`（FileWrite / GitPush） | 承認なしで execute すると例外になる |
| **F6** | `egress` の区分B（detectors / masker / preflight / mask_map） | 実文書で取りこぼしを検証できる |
| **F7** | `queue` ＋ 区分A（ローカル8Bオンデマンド） | 区分Aの要求が外部に到達しないことを設定検証で示せる |

**F2 まで出来ればアプリの Phase 1 が始められる。** F6・F7 はアプリの Phase 3 と並走で構わない。
最初から全部作らないこと。

---

## 15. 依存

`langgraph`, `litellm`, `pydantic`, `pydantic-settings`, `psycopg[binary]`, `pgvector`,
`sqlalchemy`, `alembic`, `fastapi`, `uvicorn`, `redis`, `arize-phoenix-otel`, `opentelemetry-sdk`,
`ginza` + `ja-ginza`（F6以降）, `mlx-lm`（F7以降）

`sudachipy`/`ginza` と `mlx-lm` は重いので **extras に分ける**（`agentkit[ner]`, `agentkit[local]`）。
アプリのCIで不要な依存を引かないため。
