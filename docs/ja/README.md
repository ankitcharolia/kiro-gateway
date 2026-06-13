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
7. [ファイルシステム・ターミナルサンドボックス](#ファイルシステムターミナルサンドボックス)
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
| 機能サンドボックス | `kiro/capability_executor.py` | readFile / writeFile / listDirectory / runCommandのサンドボックス |
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
| **Python 3.11+** | ベアメタルパスのみ必要 |
| **Docker** | コンテナパスのみ必要 |

### オプションA — ベアメタル

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # PROXY_API_KEYを編集
kiro auth login
python main.py
```

### オプションB — Docker（公開イメージ）

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### オプションC — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # PROXY_API_KEYを編集
docker compose up -d
```

---

## 設定

```env
# 必須
PROXY_API_KEY=change-me

# CLIパス
KIRO_CLI_COMMAND=kiro

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
| APIキー | `PROXY_API_KEY`の値 |
| モデル | `claude-sonnet-4-5` |

### Anthropic互換クライアント
_(Claude Code、Kilo Code、Craft-agent、OpenClaw、…)_

| 設定 | 値 |
|---|---|
| ベースURL | `http://localhost:8000` |
| APIキーヘッダー | `x-api-key: <PROXY_API_KEY>` |
| モデル | `claude-sonnet-4-5` |

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
pip install -e ".[dev]"
pytest tests/ -v
pytest --cov=kiro --cov-report=term-missing
```

---

## ライセンス

AGPL-3.0 — [LICENSE](../../LICENSE)を参照。
