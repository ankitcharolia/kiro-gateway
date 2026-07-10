# Kiro Gateway — ドキュメント

**完全ACP準拠**のブリッジです。OpenAI互換またはAnthropic互換のAIツールが、公式の`kiro` CLIバイナリを通じてリクエストをルーティングすることで、単一のKiroサブスクリプションを使用できます。

---

## 目次

1. [アーキテクチャ](#アーキテクチャ)
2. [インストール](#インストール)
3. [設定](#設定)
4. [クライアント設定](#クライアント設定)
5. [APIエンドポイント](#apiエンドポイント)
6. [ツール呼び出し](#ツール呼び出し)
7. [ツールの実行と権限](#ツールの実行と権限)
8. [ストリーミングイベント](#ストリーミングイベント)
9. [テストの実行](#テストの実行)
10. [リリースプロセス](#リリースプロセス)

---

## アーキテクチャ

すべてのリクエストは、stdioを介したJSON-RPC 2.0で公式の`kiro` CLIを通過します。プライベートHTTPエンドポイントなし、資格情報の共有なし、アカウントのプーリングなし。

```
OpenAI / Anthropicクライアント
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
    (オーケストレーション + ツール呼び出しラウンドトリップ)
               │
         acp_client.py
     (stdioを介したJSON-RPC 2.0)
               │
           kiro CLI
      (公式、認証済み)
               │
         Kiroバックエンド
```

### コアコンポーネント

| コンポーネント | ファイル | 目的 |
|---|---|---|
| ACPブリッジ | `kiro/acp_client.py` | `kiro` CLIを起動; stdioを介したJSON-RPC 2.0 |
| ACPモデル | `kiro/acp_models.py` | すべてのACP型のPydanticモデル |
| 権限処理 | `kiro/acp_client.py` | `session/request_permission` に応答（`ACP_TRUST_TOOLS` に従って自動承認/拒否） |
| オーケストレーション | `kiro/shim_service.py` | ストリーミング、ツール呼び出し、セッションライフサイクル |
| ACPルート | `kiro/routes_acp.py` | `/acp/chat`、`/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`、`/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`、`/v1/models` |
| コンプライアンスガード | `kiro/compliance.py` | 起動時のシングルアカウント強制 |
| モデルリゾルバー | `kiro/model_resolver.py` | モデル名をKiro対応IDにマップ |
| ペイロードガード | `kiro/payload_guards.py` | リクエスト検証とサイズ制限 |
| トークナイザー | `kiro/tokenizer.py` | トランケーション判断のためのトークンカウント |
| トランケーション | `kiro/truncation_state.py` | 会話履歴のトランケーション |

---

## インストール

### 前提条件

| 要件 | 注意 |
|---|---|
| **Kiro CLI** | [kiro.dev](https://kiro.dev)からインストール後、`kiro auth login`を実行 |
| **Python 3.14+** | ベアメタルパスのみ必要 |
| **Docker** | コンテナパスのみ必要 |

### オプションA — ベアメタル

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
uv sync
cp .env.example .env   # KIRO_GATEWAY_API_KEYを編集
kiro auth login
uv run main.py
```

### オプションB — Docker（公開イメージ）

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### オプションC — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # KIRO_GATEWAY_API_KEYを編集
docker compose up -d
```

---

## 設定

```env
# 必須
KIRO_GATEWAY_API_KEY=change-me

# CLIパス
KIRO_CLI_PATH=kiro-cli

ACP_TRUST_TOOLS=true        # kiro-cli は自前の組み込みツールを実行し許可を求める。true=承認, false=拒否
ACP_WORKSPACE_DIR=          # セッションの作業ディレクトリ（既定: プロセスの cwd）
ACP_TIMEOUT=120             # JSON-RPC 応答を待つ秒数

# 機能フラグ
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true

# サーバー
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# コンプライアンス
COMPLIANCE_MODE=true
```

---

## クライアント設定

### OpenAI互換クライアント
_(Cursor、Cline、Continue、OpenCode、Hermes-agent、OpenClaw、…)_

| 設定 | 値 |
|---|---|
| ベースURL | `http://localhost:8000/v1` |
| APIキー | `KIRO_GATEWAY_API_KEY`の値 |
| モデル | `claude-sonnet-4.6` |

### Anthropic互換クライアント
_(Claude Code、Kilo Code、Craft-agent、OpenClaw、…)_

| 設定 | 値 |
|---|---|
| ベースURL | `http://localhost:8000` |
| APIキーヘッダー | `x-api-key: <KIRO_GATEWAY_API_KEY>` |
| モデル | `claude-sonnet-4.6` |

### ネイティブACPクライアント

```
http://localhost:8000/acp/chat          # 非ストリーミング
http://localhost:8000/acp/chat/stream   # SSEストリーミング
```

---

## APIエンドポイント

| モード | メソッド | エンドポイント | 説明 |
|---|---|---|---|
| ACP | POST | `/acp/chat` | 非ストリーミングACP会話 |
| ACP | POST | `/acp/chat/stream` | SSEストリーミングACP会話 |
| OpenAI | GET | `/v1/models` | 利用可能なモデルの一覧 |
| OpenAI | POST | `/v1/chat/completions` | ストリーミング・非ストリーミング補完 |
| Anthropic | GET | `/v1/models` | 利用可能なモデルの一覧 |
| Anthropic | POST | `/v1/messages` | ストリーミング・非ストリーミングメッセージ |

---

## ツールの実行と権限

`kiro-cli` は **独自の** 組み込みツール（ファイル編集、コマンド実行）をセッションの作業ディレクトリ内で実行します。ゲートウェイはクライアント側の fs／ターミナル機能を一切提供せず、エージェントが送ってくる `session/request_permission` リクエストに応答するだけです。`ACP_TRUST_TOOLS=true` のときは単一の呼び出しを自動承認（`allow_once`）し、それ以外のときは拒否（`reject_once`）します。

| エージェントのリクエスト | ゲートウェイの動作 |
|---|---|
| `session/request_permission` | `ACP_TRUST_TOOLS=true` のとき単一の呼び出しを自動承認（`allow_once`）、`false` のとき拒否（`reject_once`） |

```env
ACP_TRUST_TOOLS=true     # 組み込みツールの実行を自動承認（ファイル編集・コマンド）
ACP_TRUST_TOOLS=false    # 回答のみ: すべての権限リクエストを拒否
ACP_WORKSPACE_DIR=/path  # kiro-cli が動作する作業ディレクトリ（既定: プロセスの cwd）
```

> **セキュリティ:** `ACP_TRUST_TOOLS=true` ではエージェントが確認なしにファイルの書き込みやコマンドの実行を行えます。回答のみのデプロイには `false` を使用してください。

---

## ストリーミングイベント

| ACPイベント | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | `delta.content`チャンク | `content_block_delta[text_delta]` |
| `tool_call` | `delta.tool_calls`チャンク | `content_block_start[tool_use]` |
| `thinking` | `delta.content`チャンク | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | エラーチャンク + `[DONE]` | `error`イベント |

---

## テストの実行

```bash
uv sync
pytest tests/ -v
pytest --cov=kiro --cov-report=term-missing
```

---

## サポート

このプロジェクトが役に立った場合は、継続的な開発の支援をご検討ください：

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

---

## ライセンス

AGPL-3.0 — [LICENSE](../../LICENSE)を参照。
