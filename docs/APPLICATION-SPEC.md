# hoofprints — アプリケーション仕様 v0.1

2026-09-09 / パッケージ: `apps/hoofprints` / ゾーン: DEV（一部 BIZ）
前提: `docs/FRAMEWORK-SPEC.md`（agentkit v0.1）、`claude/keiba-drama-service-design.md`

競馬の背後にある人と牧場のドラマを掘り起こし、**出典を付けた読み物**として複数媒体に公開する。
予想は出さない。データ提供もしない。

---

## 0. アプリが持つもの / 持たないもの

| アプリが持つ | フレームワークに任せる |
|---|---|
| ドメインモデル（馬・人・牧場・レース） | DB接続、マイグレーション基盤 |
| アーキタイプ定義と選択ロジック | — |
| Canonical Story のスキーマ | — |
| 8ノードの処理内容とプロンプト | グラフ実行・中断・再開・トレース |
| 何を機械チェックするか | 承認の状態機械と記録 |
| 媒体アダプタの具体（note / X / SSG） | 外部作用の実行制御と承認検証 |
| どの区分で送出するかの判断 | マスキング・監査・区分ごとの経路 |

**アプリは `agentkit` の `AppContext` 経由でしか外部に触れない。**
`litellm` や `psycopg` を直接 import した時点で CI が落ちる。

---

## 1. ドメインモデル

`hoofprints` スキーマ（開発ゾーンDB）。すべて公開情報から構築する。

| テーブル | 主な列 |
|---|---|
| `horses` | id, name, name_kana, birth_year, sex, sire_id, dam_id, damsire_id, farm_id, owner_id, trainer_id, retired_at, retirement_note |
| `people` | id, role(jockey/trainer/breeder/owner/groom), name, affiliation(美浦/栗東/地方), licensed_from, licensed_to |
| `farms` | id, name, prefecture, town, scale_hint(small/mid/large), note |
| `races` | id, held_on, course, name, grade, distance, surface, condition |
| `results` | race_id, horse_id, jockey_id, finish_pos, popularity, time_sec, margin, weight, abnormality(競走中止等) |
| `stories` | id, archetype, subject_horse_id, state, canonical(JSONB), embedding, created_at, published_at |
| `story_claims` | story_id, claim_id（agentkit.claims への参照）, section_ref |
| `media_targets` | id, name, max_chars, requires_ai_disclosure, allows_outbound_links, publish_mode(ci/api/manual), config(JSONB) |
| `publications` | story_id, media_target_id, url, published_at, canonical_url |

**業務ゾーン側（BIZ）に置くもの**（開発ゾーンからは ID 参照のみ）:

| テーブル | 内容 |
|---|---|
| `consents` | 取材対象、掲載許諾の有無・範囲・取得日・連絡先 |
| `interview_notes` | 取材メモ本文。**区分B**。開発ゾーンのプロセスから直接読めない |

取材メモを扱うノードだけが BIZ ゾーンのコンテキストで動く。理由は 5.2。

---

## 2. アーキタイプ

`apps/hoofprints/archetypes/*.yaml` に定義を持つ。**コードではなくデータ**にするのは、
型の追加・調整が最も頻繁に起きる箇所だから。

```yaml
# archetypes/bloodline.yaml
id: bloodline
name: 血の物語
description: 母・祖母の戦績と、その仔に託されたもの
required_claims:            # これが揃わないと記事にしない
  - dam_racing_record
  - horse_current_form
preferred_claims:
  - dam_progeny_history
  - breeder_intent
signals:                    # Scout のスコアリングに使う（SQLで評価可能なもの）
  - name: dam_was_graded_winner
    weight: 3
  - name: dam_never_won_but_progeny_did
    weight: 5
  - name: first_foal_of_notable_dam
    weight: 4
min_score: 6
```

初期の7型: `bloodline`（血の物語）/ `farm`（牧場の物語）/ `people`（人の物語）/
`owner`（馬主の物語）/ `comeback`（再起）/ `farewell`（別れ）/ `crossing`（交差）

**型に当てはまらない馬は記事にしない。** `min_score` を下回った候補は捨て、理由をログに残す。

---

## 3. Canonical Story

`hoofprints.story.models`。Pydantic。DBには `stories.canonical` に JSONB で持つ。

```python
class ClaimRef(BaseModel):
    claim_id: str                     # agentkit.claims の ID
    text: str                         # 表示用のキャッシュ

class Paragraph(BaseModel):
    text: str
    claim_ids: list[str]              # この段落が依拠した主張

class Emotional(BaseModel):
    text: str
    basis_claim_ids: list[str]        # ★空は Verifier が fail にする

class Section(BaseModel):
    heading: str
    paragraphs: list[Paragraph]

class ImageAsset(BaseModel):
    asset_id: str
    kind: Literal["pedigree_chart", "data_viz", "key_visual", "photo"]
    credit: str | None
    rights_status: Literal["own", "licensed", "generated", "unresolved"]

class CanonicalStory(BaseModel):
    archetype: str
    subject: Subject                  # horse_id, person_ids, farm_id
    title: str
    hook: str                         # 1〜2文
    sections: list[Section]
    emotional: list[Emotional]
    sources: list[SourceRef]
    images: list[ImageAsset]
    disclosure: Disclosure            # ai_assisted, reviewed_by, reviewed_at
```

**設計の要点**: `Emotional.basis_claim_ids` が空のものを機械的に落とせること。
「LLMが感動を作りに行く」という最大の失敗モードに対する構造的な対策であり、
この1フィールドがこのアプリの中心にある。

---

## 4. グラフ

```
[1 Scout] → [2 Researcher] → [3 FactLedger] → [4 Outliner] → [5 Writer] → [6 Verifier]
                  ↑                                 │                          │
                  └──── 主張が閾値未満 ─────────────┘                          │
                                                                               ▼
                                         [8 Publisher] ←── 承認 ──  [7 HumanGate]
```

状態: `StoryState(run_id, candidate, archetype, claim_ids, canonical, checks, approval_id)`

### 4.1 Scout — 候補抽出

**ここはLLMではなくSQLの仕事。** 休養日数、母の戦績、生産者の重賞歴、
騎手と馬の過去の組み合わせは、すべてクエリで評価できる。

処理: 対象レース群 → 出走馬ごとに全アーキタイプの `signals` を SQL で評価 → スコア →
`min_score` 以上かつ `stories.embedding` で既出でないものを候補化。

LLMを使うのは、上位候補に対する一言の説明生成のみ（区分C、小型モデル）。

**出力**: `Candidate(horse_id, archetype, score, signals_hit, rationale)`

### 4.2 Researcher — 一次情報収集

- Web検索と公式サイトの取得。**取得したものは必ず `record_source()`**（URL・取得日時・該当箇所・ライセンス注記）。
- スクレイピングはしない。robots とサイト規約に従う（設計書 7.1）。
- 取材メモがある場合は BIZ ゾーンのコンテキストで、**区分B** として送出ゲート経由で扱う。
- **同じ主張を複数の出典で裏取りできたものを優先する。**

**出力**: `source_ids`

### 4.3 FactLedger — 主張の構造化

収集物から1文1主張に分解して `record_claim()`。出典なしは登録できない（agentkit I-2）。
`find_conflicts()` で既存DBと矛盾する主張にフラグを立てる。

**出力**: `claim_ids`、`conflicts`

### 4.4 Outliner — 構成

アーキタイプの `required_claims` が揃っているか確認。**揃わなければ Researcher に差し戻す**（最大2回）。
2回で揃わない候補は破棄し、理由を記録する。

**出力**: セクション構成（見出しと、各セクションで使う claim_ids）

### 4.5 Writer — 執筆

区分C、主力モデル。構成と主張だけを渡す。**素材の再収集をさせない。**
各段落に、依拠した claim_ids を出力させる。

文体規約は `prompts/style.md` に置く。Phase 0 で人間が書いた3本から抽出したものを使う。

### 4.6 Verifier — 検証

2段構え。**機械チェックを先にやる**（安く、確実で、LLMより正確）。

機械チェック（`checks` として承認画面へ）:

| # | 検査 | fail 条件 |
|---|---|---|
| C1 | 馬名の実在と表記 | `horses` に存在しない馬名が本文にある |
| C2 | 日付・レース名・着順・距離 | `results` / `races` と不一致 |
| C3 | 未出典段落 | `Paragraph.claim_ids` が空 |
| C4 | 根拠なき情動的記述 | `Emotional.basis_claim_ids` が空 |
| C5 | 掲載許諾 | 取材由来の主張に対応する `consents` がない |
| C6 | 禁止表現 | 予想・買い目・オッズ・「必ず」等の断定 |
| C7 | 画像の権利状態 | `rights_status == "unresolved"` |
| C8 | 重複 | 既存 story との embedding 類似度が閾値超 |

LLMチェック（区分C、Writer と**別プロンプト・別セッション**）:
出典と本文の食い違い、主張の過剰な一般化、時制の誤り。

**出力**: `checks: list[Check]`

### 4.7 HumanGate

`agentkit.graph.human_gate()` を使う。`ApprovalItem` を組み立てるのがアプリの仕事。

承認画面に並べるもの:

1. 媒体ごとのプレビュー（自社SSG / note / X）
2. `checks` の結果（fail は赤、warn は黄）
3. 未出典段落・根拠なき情動的記述のハイライト
4. 出典一覧（URL と取得日時）
5. 掲載許諾の状態
6. 類似記事の上位3件

fail が1件でもあれば公開ボタンは押せない（agentkit の規則）。
差し戻し・破棄には理由を必須入力。**これがプロンプト改善の唯一の一次データになるので、捨てない。**

### 4.8 Publisher

承認済み Story を媒体アダプタへ。**正本は必ず自社サイト。**

---

## 5. 媒体アダプタ

### 5.1 抽象

```python
class MediaAdapter(Protocol):
    target: MediaTarget                       # DB の media_targets 行
    def render(self, story: CanonicalStory) -> RenderedContent: ...
    def to_effect_payload(self, r: RenderedContent) -> Mapping: ...
```

実際の送信は `agentkit.effects` の Effect が行う。アダプタは**変換だけ**を担当する。
この分割により、「投稿する権限」と「どう見せるか」が別々にテストできる。

| 媒体 | render の出力 | Effect | Phase |
|---|---|---|---|
| 自社SSG | `content/stories/<slug>.json` | `FileWriteEffect` → `GitPushEffect` → CI | 2 |
| note | 抜粋＋自社への導線（Markdown） | `HttpPostEffect` または手動 | 3 |
| X / Threads | フック1文＋画像1枚＋リンク | `HttpPostEffect` | 3 |
| ニュースレター | 週次まとめ | `HttpPostEffect` | 4 |
| 動画台本 | ナレーション原稿＋カット割 | `FileWriteEffect` | 4 |

### 5.2 規約はデータで持つ

`media_targets.requires_ai_disclosure` / `allows_outbound_links` / `max_chars` / `publish_mode`。
**コードに埋め込まない。** 各媒体の規約は変わるので、変わったらデータを直す。

`publish_mode`:
- `ci` — 自社サイトのみ。承認後の git push → CI → 本番。ここは自動でよい
- `api` — API投稿。承認済み Effect として実行
- `manual` — 生成物を出すところまで。投稿は人間

**Phase 2 で稼働させるのは自社SSGのみ。** アダプタ機構は最初から作るが、媒体を増やすのは
1媒体で読まれることを確認してから。

### 5.3 自社サイト（Next.js SSG）

- `apps/hoofprints/web/`。入力は `content/stories/*.json`（Canonical Story をそのまま）。
- 出典一覧・血統図・戦績のデータビジュアルを標準で描画する。**写真がなくても成立する設計。**
- ビルドとデプロイは CI（GitHub Actions → OIDC → S3/CloudFront）。
  **Mac mini に本番のデプロイ資格情報を置かない。**
- `apps/hoofprints/src` から `web/` へは JSON を書き出すだけ。Python と TS の結合点はここ1箇所に限る。

---

## 6. 区分の割り当て

| 処理 | 区分 | ゾーン |
|---|---|---|
| Scout の説明生成、Researcher の要約、Outliner、Writer、Verifier(LLM) | **C** | DEV |
| 取材メモの要約・引用整形 | **B** | BIZ |
| 掲載許諾の管理、収益・支払いの記録 | **A** | BIZ |
| 重複判定の一次フィルタ、実行ログの分類 | ローカル8B | DEV |

**このアプリの大半が区分C**であることが、プラットフォーム設計の
「開発ゾーンの大半はC」という想定の実証になる。

---

## 7. 実装フェーズ

`claude/keiba-drama-service-design.md` の Phase と対応。左端が agentkit 側の必要段階。

| | 必要な agentkit | 内容 | 完了判定 |
|---|---|---|---|
| **P0**（2週） | なし | **エージェントを作らず人間が3本書く**。文体・構成・出典の粒度を確定 | Canonical Story のスキーマと `prompts/style.md` が実物から決まる |
| **P1**（3週） | F1〜F3 | ドメインDB構築、Scout・Researcher・FactLedger。執筆は人間 | 候補5件に対し、出典つきの使える主張が集まる |
| **P2**（4週） | F4〜F5 | Outliner・Writer・Verifier、承認UI、SSG、CIデプロイ | 承認を経て1本が本番公開。Mac mini にデプロイ権限がない |
| **P3**（4週） | F6 | 取材メモの区分B処理、note アダプタ、重複検出 | 取材メモをマスクして外部に通せる根拠が説明できる |
| **P4**（継続） | F7 | launchd 定期実行、媒体追加、収益計測 | 週2本が承認待ちまで無人で到達する |

**P0 を飛ばさない。** 型を持たないまま自動化すると、何が良い記事かを判定できないまま
プロンプトを弄り続けることになる。

---

## 8. 受け入れテスト

各フェーズの「動いた」を機械的に判定する。

| ID | 内容 | Phase |
|---|---|---|
| A1 | 出典なしの主張を FactLedger が登録しようとすると例外 | P1 |
| A2 | `min_score` 未満の候補が Scout の出力に含まれない | P1 |
| A3 | `required_claims` 不足で Outliner が Researcher に差し戻す | P2 |
| A4 | 実在しない馬名を含む本文で C1 が fail | P2 |
| A5 | `basis_claim_ids` 空の情動的記述で C4 が fail | P2 |
| A6 | fail がある Story は Publisher を実行できない | P2 |
| A7 | 承認IDなしで `GitPushEffect.execute()` が例外 | P2 |
| A8 | グラフを HumanGate で止め、プロセス再起動後に再開できる | P2 |
| A9 | 取材メモ中の人名が送出本文（`egress_audit`）に現れない | P3 |
| A10 | 既出テーマと類似度が高い候補を Scout が落とす | P3 |

A9 は**実際の取材メモで確認する**。合成データでは取りこぼしが見つからない。

---

## 9. アプリ側の未決事項

- **画像の方針** — Phase 0 の3本を書く過程で決める。最も早く決めるべき論点。
  当面 `rights_status="unresolved"` の画像は C7 で fail にして、判断を先送りできないようにしておく
- **地方競馬（NAR）を含めるか** — ドラマの密度は地方のほうが高い可能性がある。
  データ入手経路が別系統になるため P1 は中央に限定し、P3 で判断
- **サービス名・ドメイン** — `hoofprints` は開発上の仮称。受託まで見るなら独立ドメイン
- **記事の頻度** — 週2本か週5本か。承認の人時間から逆算。P0 で実測する
- **JRA-VAN / JRADB の要否判定** — P4。それまで公開情報のみで組む（設計書 7.1）
