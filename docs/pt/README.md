# Kiro Gateway — Documentação

Uma ponte **totalmente compatível com ACP** que permite que qualquer ferramenta de IA compatível com OpenAI ou Anthropic use sua assinatura única do Kiro, roteando cada solicitação através do binário oficial `kiro` CLI.

---

## Índice

1. [Arquitetura](#arquitetura)
2. [Instalação](#instalação)
3. [Configuração](#configuração)
4. [Configuração do Cliente](#configuração-do-cliente)
5. [Endpoints da API](#endpoints-da-api)
6. [Chamadas de Ferramentas](#chamadas-de-ferramentas)
7. [Sandbox de Arquivos e Terminal](#sandbox-de-arquivos-e-terminal)
8. [Eventos de Streaming](#eventos-de-streaming)
9. [Executando Testes](#executando-testes)
10. [Processo de Lançamento](#processo-de-lançamento)

---

## Arquitetura

Cada solicitação passa pelo CLI oficial do `kiro` via JSON-RPC 2.0 sobre stdio — sem endpoints HTTP privados, sem compartilhamento de credenciais, sem pooling de contas.

```
Qualquer cliente OpenAI / Anthropic
               │
  ┌────────────┴────────────┐
  │                         │
routes_openai_shim    routes_anthropic_shim
 /v1/chat/completions   /v1/messages
               │
         shim_service.py
    (orquestração + viagens de ida e volta de chamadas de ferramentas)
               │
         acp_client.py
     (JSON-RPC 2.0 sobre stdio)
               │
           kiro CLI
      (oficial, autenticado)
               │
         Backend Kiro
```

### Componentes Principais

| Componente | Arquivo | Propósito |
|---|---|---|
| Ponte ACP | `kiro/acp_client.py` | Lança o CLI `kiro`; JSON-RPC 2.0 sobre stdio |
| Modelos ACP | `kiro/acp_models.py` | Modelos Pydantic para todos os tipos ACP |
| Sandbox de capacidades | `kiro/capability_executor.py` | Sandbox de readFile/writeFile/listDirectory/runCommand |
| Orquestração | `kiro/shim_service.py` | Streaming, viagens de ferramentas, ciclo de vida de sessão |
| Rotas ACP | `kiro/routes_acp.py` | `/acp/chat`, `/acp/chat/stream` |
| Shim OpenAI | `kiro/routes_openai_shim.py` | `/v1/chat/completions`, `/v1/models` |
| Shim Anthropic | `kiro/routes_anthropic_shim.py` | `/v1/messages`, `/v1/models` |
| Guarda de conformidade | `kiro/compliance.py` | Aplicação de conta única na inicialização |
| Resolvedor de modelos | `kiro/model_resolver.py` | Mapeia nomes de modelos para IDs suportados pelo Kiro |
| Guardas de payload | `kiro/payload_guards.py` | Validação de solicitações e limites de tamanho |
| Tokenizador | `kiro/tokenizer.py` | Contagem de tokens para decisões de truncamento |
| Truncamento | `kiro/truncation_state.py` | Truncamento do histórico de conversa |

---

## Instalação

### Pré-requisitos

| Requisito | Notas |
|---|---|
| **Kiro CLI** | Instale em [kiro.dev](https://kiro.dev), depois execute `kiro auth login` |
| **Python 3.11+** | Necessário apenas para o caminho bare-metal |
| **Docker** | Necessário apenas para o caminho de contêiner |

### Opção A — Bare metal

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # editar PROXY_API_KEY
kiro auth login
python main.py
```

### Opção B — Docker (imagem publicada)

```bash
docker pull ghcr.io/ankitcharolia/kiro-gateway:latest
docker run -d \
  --name kiro-gateway \
  -p 8000:8000 \
  -e PROXY_API_KEY=change-me \
  -v "${HOME}/.kiro:/root/.kiro:ro" \
  ghcr.io/ankitcharolia/kiro-gateway:latest
```

### Opção C — Docker Compose

```bash
git clone https://github.com/ankitcharolia/kiro-gateway.git
cd kiro-gateway
cp .env.example .env   # editar PROXY_API_KEY
docker compose up -d
```

---

## Configuração

```env
# Obrigatório
PROXY_API_KEY=change-me

KIRO_CLI_COMMAND=kiro
ACP_ENABLED=true
OPENAI_SHIM_ENABLED=true
ANTHROPIC_SHIM_ENABLED=true
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
COMPLIANCE_MODE=true
```

---

## Eventos de Streaming

| Evento ACP | SSE OpenAI | SSE Anthropic |
|---|---|---|
| `text` | chunk `delta.content` | `content_block_delta[text_delta]` |
| `tool_call` | chunk `delta.tool_calls` | `content_block_start[tool_use]` |
| `thinking` | chunk `delta.content` | `content_block_delta[text_delta]` |
| `done` | `[DONE]` + `finish_reason` | `message_delta` + `message_stop` |
| `error` | chunk de erro + `[DONE]` | evento `error` |

---

## Licença

AGPL-3.0 — ver [LICENSE](../../LICENSE).
