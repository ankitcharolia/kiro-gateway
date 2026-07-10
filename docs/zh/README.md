# Kiro Gateway — 文档

这是一个**完全符合ACP规范**的网关，允许任何兼容OpenAI或Anthropic的AI工具通过官方`kiro` CLI二进制文件路由请求，从而使用您的单一Kiro订阅。

---

## 目录

1. [架构](#架构)
2. [安装](#安装)
3. [配置](#配置)
4. [客户端设置](#客户端设置)
5. [API端点](#api端点)
6. [工具调用](#工具调用)
7. [工具执行与权限](#工具执行与权限)
8. [流式事件](#流式事件)
9. [运行测试](#运行测试)
10. [发布流程](#发布流程)

---

## 架构

每个请求通过stdio上的JSON-RPC 2.0流经官方`kiro` CLI——无私有HTTP端点，无凭证共享，无账户池。

```
任何OpenAI / Anthropic客户端
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
    (编排 + 工具调用往返)
               │
         acp_client.py
     (stdio上的JSON-RPC 2.0)
               │
           kiro CLI
      (官方，已认证)
               │
         Kiro后端
```

### 核心组件

| 组件 | 文件 | 用途 |
|---|---|---|
| ACP桥接 | `kiro/acp_client.py` | 启动`kiro` CLI；stdio上的JSON-RPC 2.0 |
| ACP模型 | `kiro/acp_models.py` | 所有ACP类型的Pydantic模型 |
| 权限处理 | `kiro/acp_client.py` | 响应 `session/request_permission`（依据 `ACP_TRUST_TOOLS` 自动批准或拒绝） |
| 编排 | `kiro/shim_service.py` | 流式传输、工具调用往返、会话生命周期 |
| ACP路由 | `kiro/routes_acp.py` | `/acp/chat`、`/acp/chat/stream` |
| OpenAI shim | `kiro/routes_openai_shim.py` | `/v1/chat/completions`、`/v1/models` |
| Anthropic shim | `kiro/routes_anthropic_shim.py` | `/v1/messages`、`/v1/models` |
| 合规性守卫 | `kiro/compliance.py` | 启动时强制单账户 |
| 模型解析器 | `kiro/model_resolver.py` | 将模型名称映射到Kiro支持的ID |
| 负载守卫 | `kiro/payload_guards.py` | 请求验证和大小限制 |
| 分词器 | `kiro/tokenizer.py` | 用于截断决策的令牌计数 |
| 截断 | `kiro/truncation_state.py` | 对话历史截断 |

---

## 安装

### 前提条件

| 要求 | 说明 |
|---|---|
| **Kiro CLI** | 从[kiro.dev](https://kiro.dev)安装，然后运行`kiro auth login` |
| **Python 3.14+** | 仅裸机路径需要 |
| **Docker** | 仅容器路径需要 |

### 选项A — 裸机

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
uv sync
cp .env.example .env   # 编辑 KIRO_GATEWAY_API_KEY
kiro auth login
uv run main.py
```

### 选项B — Docker（已发布镜像）

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e KIRO_GATEWAY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### 选项C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # 编辑 KIRO_GATEWAY_API_KEY
docker compose up -d
```

---

## 配置

```env
# 必需
KIRO_GATEWAY_API_KEY=change-me

# CLI路径
KIRO_CLI_PATH=kiro-cli

ACP_TRUST_TOOLS=true        # kiro-cli 运行其自带工具并请求许可；true=批准，false=拒绝
ACP_WORKSPACE_DIR=          # 会话工作目录（默认：进程 cwd）
ACP_TIMEOUT=120             # 等待 JSON-RPC 响应的秒数

# 功能标志
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true

# 服务器
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# 合规性
COMPLIANCE_MODE=true
```

---

## 客户端设置

### OpenAI兼容客户端
_(Cursor、Cline、Continue、OpenCode、Hermes-agent、OpenClaw等)_

| 设置 | 值 |
|---|---|
| 基础URL | `http://localhost:8000/v1` |
| API密钥 | `KIRO_GATEWAY_API_KEY`的值 |
| 模型 | `claude-sonnet-4.6` |

### Anthropic兼容客户端
_(Claude Code、Kilo Code、Craft-agent、OpenClaw等)_

| 设置 | 值 |
|---|---|
| 基础URL | `http://localhost:8000` |
| API密钥头 | `x-api-key: <KIRO_GATEWAY_API_KEY>` |
| 模型 | `claude-sonnet-4.6` |

### 原生ACP客户端

```
http://localhost:8000/acp/chat          # 非流式
http://localhost:8000/acp/chat/stream   # SSE流式
```

---

## 工具执行与权限

kiro-cli 运行其自带的内置工具（文件编辑、命令执行）于会话工作目录中；网关不公布任何客户端 fs/terminal 能力，仅响应代理的 `session/request_permission` 请求——当 `ACP_TRUST_TOOLS=true` 时自动批准单次调用（`allow_once`），否则拒绝（`reject_once`）。

| 代理请求 | 网关行为 |
|---|---|
| `session/request_permission` | 当 `ACP_TRUST_TOOLS=true` 时自动批准单次调用（`allow_once`）；当为 `false` 时拒绝（`reject_once`）。 |

```env
ACP_TRUST_TOOLS=true     # 自动批准内置工具运行（文件编辑、命令）
ACP_TRUST_TOOLS=false    # 仅回答：拒绝所有权限请求
ACP_WORKSPACE_DIR=/path  # kiro-cli 的工作目录（默认：进程 cwd）
```

> **安全提示：** `ACP_TRUST_TOOLS=true` 允许代理在无确认下写文件和执行命令；仅回答场景请用 `false`。

---

## 流式事件

| ACP事件 | OpenAI SSE | Anthropic SSE |
|---|---|---|
| `text` | `delta.content`块 | `content_block_delta[text_delta]` |
| `tool_call` | `delta.tool_calls`块 | `content_block_start[tool_use]` |
| `thinking` | `delta.content`块 | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | 错误块 + `[DONE]` | `error`事件 |

---

## 支持

如果这个项目为你节省了时间，欢迎支持它的持续开发：

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/achar)
[![PayPal](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/ankitcharolia)

---

## 许可证

AGPL-3.0 — 详见[LICENSE](../../LICENSE)。
